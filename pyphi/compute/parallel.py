#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# compute/parallel.py


'''
Utilities for parallel computation.
'''

# pylint: disable=too-few-public-methods,too-many-instance-attributes

import logging
import multiprocessing
import sys
import threading
from itertools import chain, islice

from tblib import Traceback

from .. import config
from ..log import ProgressBar

log = logging.getLogger(__name__)


def get_num_processes():
    '''Return the number of processes to use in parallel.'''
    cpu_count = multiprocessing.cpu_count()

    if config.NUMBER_OF_CORES == 0:
        raise ValueError(
            'Invalid NUMBER_OF_CORES; value may not be 0.')

    if config.NUMBER_OF_CORES > cpu_count:
        raise ValueError(
            'Invalid NUMBER_OF_CORES; value must be less than or '
            'equal to the available number of cores ({} for this '
            'system).'.format(cpu_count))

    if config.NUMBER_OF_CORES < 0:
        num = cpu_count + config.NUMBER_OF_CORES + 1
        if num <= 0:
            raise ValueError(
                'Invalid NUMBER_OF_CORES; negative value is too negative: '
                'requesting {} cores, {} available.'.format(num, cpu_count))

        return num

    return config.NUMBER_OF_CORES


class ExceptionWrapper:
    '''A picklable wrapper suitable for passing exception tracebacks through
    instances of ``multiprocessing.Queue``.

    Args:
        exception (Exception): The exception to wrap.
    '''
    def __init__(self, exception):  # coverage: disable
        self.exception = exception
        _, _, tb = sys.exc_info()
        self.tb = Traceback(tb)

    def reraise(self):
        '''Re-raise the exception.'''
        raise self.exception.with_traceback(self.tb.as_traceback())


POISON_PILL = None
Q_MAX_SIZE = multiprocessing.synchronize.SEM_VALUE_MAX


class MapReduce:
    '''An engine for doing heavy computations over an iterable.

    This is similar to ``multiprocessing.Pool``, but allows computations to
    shortcircuit, and supports both parallel and sequential computations.

    Args:
        iterable (Iterable): A collection of objects to perform a computation
            over.
        *context: Any additional data necessary to complete the computation.

    Any subclass of ``MapReduce`` must implement three methods::

        - ``empty_result``,
        - ``compute``, (map), and
        - ``process_result`` (reduce).

    The engine includes a builtin ``tqdm`` progress bar; this can be disabled
    by setting ``pyphi.config.PROGRESS_BARS`` to ``False``.

    Parallel operations start a daemon thread which handles log messages sent
    from worker processes.

    Subprocesses spawned by ``MapReduce`` cannot spawn more subprocesses; be
    aware of this when composing nested computations. This is not an issue in
    practice because it is typically most efficient to only parallelize the top
    level computation.
    '''
    # Description for the tqdm progress bar
    description = ''

    def __init__(self, iterable, *context):
        self.iterable = iterable
        self.context = context
        self.done = False
        self.progress = self.init_progress_bar()

        # Attributes used by parallel computations
        self.in_queue = None
        self.out_queue = None
        self.log_queue = None
        self.log_thread = None
        self.processes = None
        self.num_processes = None
        self.tasks = None

    def empty_result(self, *context):
        '''Return the default result with which to begin the computation.'''
        raise NotImplementedError

    @staticmethod
    def compute(obj, *context):
        '''Map over a single object from ``self.iterable``.'''
        raise NotImplementedError

    def process_result(self, new_result, old_result):
        '''Reduce handler.

        Every time a new result is generated by ``compute``, this method is
        called with the result and the previous (accumulated) result. This
        method compares or collates these two values, returning the new result.

        Setting ``self.done`` to ``True`` in this method will abort the
        remainder of the computation, returning this final result.
        '''
        raise NotImplementedError

    #: Is this process a subprocess in a parallel computation?
    _forked = False

    # TODO: pass size of iterable alongside?
    def init_progress_bar(self):
        '''Initialize and return a progress bar.'''
        # Forked worker processes can't show progress bars.
        disable = MapReduce._forked or not config.PROGRESS_BARS

        # Don't materialize iterable unless we have to: huge iterables
        # (e.g. of `KCuts`) eat memory.
        if disable:
            total = None
        else:
            self.iterable = list(self.iterable)
            total = len(self.iterable)

        return ProgressBar(total=total, disable=disable, leave=False,
                           desc=self.description)

    @staticmethod  # coverage: disable
    def worker(compute, in_queue, out_queue, log_queue, *context):
        '''A worker process, run by ``multiprocessing.Process``.'''
        try:
            MapReduce._forked = True
            log.debug('Worker process starting...')

            configure_worker_logging(log_queue)

            for obj in iter(in_queue.get, POISON_PILL):
                out_queue.put(compute(obj, *context))

            out_queue.put(POISON_PILL)
            log.debug('Worker process exiting - no more jobs')

        except Exception as e:  # pylint: disable=broad-except
            out_queue.put(ExceptionWrapper(e))

    def start_parallel(self):
        '''Initialize all queues and start the worker processes and the log
        thread.
        '''
        self.num_processes = get_num_processes()

        self.in_queue = multiprocessing.Queue(maxsize=Q_MAX_SIZE)
        # Don't print `BrokenPipeError` when workers are terminated and
        # break the queue.
        # TODO: this is a private implementation detail
        self.in_queue._ignore_epipe = True  # pylint: disable=protected-access

        self.out_queue = multiprocessing.Queue()
        self.log_queue = multiprocessing.Queue()

        args = (self.compute, self.in_queue, self.out_queue, self.log_queue) + self.context
        self.processes = [
            multiprocessing.Process(target=self.worker, args=args, daemon=True)
            for i in range(self.num_processes)]

        for process in self.processes:
            process.start()

        self.log_thread = LogThread(self.log_queue)
        self.log_thread.start()

        self.initialize_tasks()

    def initialize_tasks(self):
        '''Load the input queue to capacity.

        Overfilling causes a deadlock when `queue.put` blocks when
        full, so further tasks are enqueued as results are returned.
        '''
        # Add a poison pill to shutdown each process.
        poison = [POISON_PILL] * self.num_processes
        self.tasks = chain(self.iterable, poison)
        for obj in islice(self.tasks, Q_MAX_SIZE):
            self.in_queue.put(obj)

    def maybe_put_task(self):
        '''Enqueue the next task, if there are any waiting.'''
        try:
            self.in_queue.put(next(self.tasks))
        except StopIteration:
            pass

    def run_parallel(self):
        '''Perform the computation in parallel, reading results from the output
        queue and passing them to ``process_result``.
        '''
        self.start_parallel()

        result = self.empty_result(*self.context)

        while not self.done:
            r = self.out_queue.get()
            self.maybe_put_task()

            if r is POISON_PILL:
                self.num_processes -= 1
                if self.num_processes == 0:
                    break

            elif isinstance(r, ExceptionWrapper):
                r.reraise()

            else:
                result = self.process_result(r, result)
                self.progress.update(1)

        if self.num_processes > 0:
            log.debug('Shortcircuit: terminating workers early')

        self.finish_parallel()

        return result

    def finish_parallel(self):
        '''Terminate all processes and the log thread.'''
        # Shutdown the log thread
        self.log_queue.put(POISON_PILL)
        self.log_thread.join()

        # Close all queues
        self.log_queue.close()
        self.in_queue.close()
        self.out_queue.close()

        # Remove the progress bar
        self.progress.close()

        # Terminating processes which are holding resources (open files, locks)
        # can cause issues, so we make sure the log thread and progress bar
        # are shut down before terminating.
        # TODO: use an Event instead?
        for process in self.processes:
            log.debug('Terminating worker process %s', process)
            process.terminate()

    def run_sequential(self):
        '''Perform the computation sequentially, only holding two computed
        objects in memory at a time.
        '''
        result = self.empty_result(*self.context)

        for obj in self.iterable:
            r = self.compute(obj, *self.context)
            result = self.process_result(r, result)
            self.progress.update(1)

            # Short-circuited?
            if self.done:
                break

        # Remove progress bar
        self.progress.close()

        return result

    def run(self, parallel=True):
        '''Perform the computation.

        Keyword Args:
            parallel (boolean): If True, run the computation in parallel.
                Otherwise, operate sequentially.
        '''
        if parallel:
            return self.run_parallel()
        return self.run_sequential()


# TODO: maintain a single log thread?
class LogThread(threading.Thread):
    '''Thread which handles log records sent from ``MapReduce`` processes.

    It listens to an instance of ``multiprocessing.Queue``, rewriting log
    messages to the PyPhi log handler.
    '''
    def __init__(self, q):
        self.q = q
        super().__init__()
        self.daemon = True

    def run(self):
        log.debug('Log thread started')
        while True:
            record = self.q.get()
            if record is POISON_PILL:
                break
            logger = logging.getLogger(record.name)
            logger.handle(record)
        log.debug('Log thread exiting')


def configure_worker_logging(queue):  # coverage: disable
    '''Configure a worker process to log all messages to ``queue``.'''
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'queue': {
                'class': 'logging.handlers.QueueHandler',
                'queue': queue,
            },
        },
        'root': {
            'level': 'DEBUG',
            'handlers': ['queue']
        },
    })
