XOR Network
===========

This example describes a system of three fully connected XOR nodes, |A|, |B|
and |C| (no self-connections).

First let's create the XOR network:

    >>> import pyphi
    >>> network = pyphi.examples.xor_network()

We'll consider the state with all nodes off.

    >>> state = (0, 0, 0)

According to IIT, existence is a holistic notion; the whole is more important
than its parts. The first step is to confirm the existence of the whole, by
finding the main complex of the network:

    >>> main_complex = pyphi.compute.main_complex(network, state)

The main complex exists (|big_phi > 0|),

    >>> main_complex.phi
    1.874999

and it consists of the entire network:

    >>> main_complex.subsystem
    Subsystem(A, B, C)

Knowing what exists at the system level, we can now investigate the existence
of concepts within the complex.

    >>> constellation = main_complex.unpartitioned_constellation
    >>> len(constellation)
    3
    >>> constellation.labeled_mechanisms
    [['A', 'B'], ['A', 'C'], ['B', 'C']]

There are three concepts in the constellation. They are all the possible second
order mechanisms: |AB|, |AC| and |BC|.

Focusing on the concept specified by mechanism |AB|, we investigate existence,
and the irreducible cause and effect. Based on the symmetry of the network, the
results will be similar for the other second order mechanisms.

    >>> concept = constellation[0]
    >>> concept.mechanism
    (0, 1)
    >>> concept.phi
    0.5

The concept has :math:`\varphi = \frac{1}{2}`.

    >>> concept.cause.purview
    (0, 1, 2)
    >>> concept.cause.repertoire
    array([[[ 0.5,  0. ],
            [ 0. ,  0. ]],
    <BLANKLINE>
           [[ 0. ,  0. ],
            [ 0. ,  0.5]]])

So we see that the cause purview of this mechanism is the whole system |ABC|,
and that the repertoire shows a :math:`0.5` of probability the past state being
``(0, 0, 0)`` and the same for ``(1, 1, 1)``:

    >>> concept.cause.repertoire[(0, 0, 0)]
    0.5
    >>> concept.cause.repertoire[(1, 1, 1)]
    0.5

This tells us that knowing both |A| and |B| are currently off means that
the past state of the system was either all off or all on with equal
probability.

For any reduced purview, we would still have the same information about the
elements in the purview (either all on or all off), but we would lose
the information about the elements outside the purview.

    >>> concept.effect.purview
    (2,)
    >>> concept.effect.repertoire
    array([[[ 1.,  0.]]])

The effect purview of this concept is the node |C|. The mechanism |AB| is able
to completely specify the next state of |C|. Since both nodes are off, the
next state of |C| will be off.

The mechanism |AB| does not provide any information about the next state of
either |A| or |B|, because the relationship depends on the value of |C|. That
is, the next state of |A| (or |B|) may be either on or off, depending
on the value of |C|. Any purview larger than |C| would be reducible by pruning
away the additional elements.

+------------------------------------------------------------------+
| Main Complex: |ABC| with :math:`\Phi = 1.875`                    |
+---------------+-----------------+---------------+----------------+
|   Mechanism   | :math:`\varphi` | Cause Purview | Effect Purview |
+===============+=================+===============+================+
| |AB|          |  0.5            | |ABC|         | |C|            |
+---------------+-----------------+---------------+----------------+
| |AC|          |  0.5            | |ABC|         | |B|            |
+---------------+-----------------+---------------+----------------+
| |BC|          |  0.5            | |ABC|         | |A|            |
+---------------+-----------------+---------------+----------------+

An analysis of the `intrinsic existence` of this system reveals that the main
complex of the system is the entire network of XOR nodes. Furthermore, the
concepts which exist within the complex are those specified by the second-order
mechanisms |AB|, |AC|, and |BC|.

To understand the notion of intrinsic existence, in addition to determining
what exists for the system, it is useful to consider also what does not exist.

Specifically, it may be surprising that none of the first order mechanisms |A|,
|B| or |C| exist. This physical system of XOR gates is sitting on the table in
front of me; I can touch the individual elements of the system, so how can it
be that they do not exist?

That sort of existence is what we term `extrinsic existence`. The XOR gates
exist for me as an observer, external to the system. I am able to manipulate
them, and observe their causes and effects, but the question that matters for
`intrinsic` existence is, do they have irreducible causes and effects within
the system? There are two reasons a mechanism may have no irreducible
cause-effect power: either the cause-effect power is completely reducible, or
there was no cause-effect power to begin with. In the case of elementary
mechanisms, it must be the latter.

To see this, again due to symmetry of the system, we will focus only on the
mechanism |A|.

   >>> subsystem = pyphi.examples.xor_subsystem()
   >>> A = (0,)
   >>> ABC = (0, 1, 2)

In order to exist, a mechanism must have irreducible cause and effect power
within the system.

   >>> subsystem.cause_info(A, ABC)
   0.5
   >>> subsystem.effect_info(A, ABC)
   0.0

The mechanism has no effect power over the entire subsystem, so it cannot have
effect power over any purview within the subsystem. Furthermore, if a mechanism
has no effect power, it certainly has no irreducible effect power. The
first-order mechanisms of this system do not exist intrinsically, because they
have no effect power (having causal power is not enough).

To see why this is true, consider the effect of |A|. There is no self-loop, so
|A| can have no effect on itself. Without knowing the current state of |A|, in
the next state |B| could be either on or off. If we know that the current state
of |A| is on, then |B| could still be either on or off, depending on the state
of |C|. Thus, on its own, the current state of |A| does not provide any
information about the next state of |B|. A similar result holds for the effect
of |A| on |C|. Since |A| has no effect power over any element of the system, it
does not exist from the intrinsic perspective.

To complete the discussion, we can also investigate the potential third order
mechanism |ABC|. Consider the cause information over the purview |ABC|:

   >>> subsystem.cause_info(ABC, ABC)
   0.749999

Since the mechanism has nonzero cause information, it has causal power over the
system—but is it irreducible?

   >>> mip = subsystem.mip_past(ABC, ABC)
   >>> mip.phi
   0.0
   >>> mip.partition  # doctest: +NORMALIZE_WHITESPACE
    0     1,2
   ─── ✕ ─────
    ∅    0,1,2

The mechanism has :math:`ci = 0.75`, but it is completely reducible
(:math:`\varphi = 0`) to the partition

.. math::

    \frac{A}{\varnothing} \times \frac{BC}{ABC}

This result can be understood as follows: knowing that |B| and |C| are off in
the current state is sufficient to know that |A|, |B|, and |C| were all off in
the past state; there is no additional information gained by knowing that |A|
is currently off.

Similarly for any other potential purview, the current state of |B| and |C|
being ``(0, 0)`` is always enough to fully specify the previous state, so the
mechanism is reducible for all possible purviews, and hence does not exist.
