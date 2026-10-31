"""`PriorityFinalizer` floors (P1.13, §3.8)."""

from __future__ import annotations

import itertools

from campuspulse_ai.application.services.priority_finalizer import PriorityFinalizer
from campuspulse_ai.domain.labels import PRIORITY_LABELS, Priority
from campuspulse_ai.domain.values import ClarificationConstraint, GuardVerdict, ProbVector

LOWISH = ProbVector((0.6, 0.3, 0.1), PRIORITY_LABELS)
NONE = GuardVerdict(kind="none")
INJECTION = GuardVerdict("injection", ("mark this as high",), "the bus is late", 1.0)


def test_safety_forces_high() -> None:
    p, floors = PriorityFinalizer().apply(LOWISH, True, NONE, ())
    assert p.values == (0.0, 0.0, 1.0)
    assert floors == ("safety",)


def test_priority_constraint_onehot() -> None:
    answer = [ClarificationConstraint("priority", "medium")]
    p, floors = PriorityFinalizer().apply(LOWISH, False, NONE, answer)
    assert p.values == (0.0, 1.0, 0.0)
    assert floors == ("clarification_constraint",)
    # a category or feature constraint does not touch the priority vector
    other = [ClarificationConstraint("category", "Finance")]
    same, none = PriorityFinalizer().apply(LOWISH, False, NONE, other)
    assert same == LOWISH and none == ()


def test_never_lowers_priority() -> None:
    fin = PriorityFinalizer()
    for values in itertools.permutations((0.6, 0.3, 0.1)):
        head = ProbVector(values, PRIORITY_LABELS)
        rank = Priority(head.argmax()).rank
        for verdict in (NONE, INJECTION):
            out, floors = fin.apply(head, False, verdict, ())
            assert out == head and floors == ()  # no rule fires: the head's vector is returned unchanged
            for answer in PRIORITY_LABELS:  # safety beats any clarification answer, even "low"
                high, _ = fin.apply(head, True, verdict, [ClarificationConstraint("priority", answer)])
                assert Priority(high.argmax()).rank >= rank
                assert high.argmax() == "high"
