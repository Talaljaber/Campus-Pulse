"""`PriorityFinalizer`: the rule floors applied after the priority head (P1.13, §3.8, §2.1 step 9).

Pure application service (domain only). Precedence, highest first (`domain.priority_rules.FLOOR_PRECEDENCE`):

    distress > safety → high > clarification constraint > urgency rule → high > injection strip > head
    > conformal

- **safety** (`SafetyGuard` verdict `danger`): `p_pri := onehot(high)`, floor `"safety"`.
  Nothing overrides it.
- **priority constraint** (the student's clarification answer, LD-29): `p_pri := onehot(value)`, floor
  `"clarification_constraint"`. It is information from the student, not a rule; it never applies over safety.
- **urgency rule** (P7.3): one or more `high_floor` families fired on the stripped text → `p_pri :=
  onehot(high)`, floor `"urgency_rule"`. Raise-only; it never overrides safety or a student's answer.
- **injection**: the head already scored the stripped text, so nothing changes here (stripping can only remove
  words; it never adds a priority cue). An injection can therefore never raise a priority.
- **distress** never changes a label: the online use case stops before labelling (§2.1 [4']), and batch
  keeps the model's label.
No rule ever lowers a priority: the only lowering is an explicit answer from the student.
"""

from __future__ import annotations

from collections.abc import Sequence

from campuspulse_ai.domain.labels import Priority
from campuspulse_ai.domain.values import ClarificationConstraint, GuardVerdict, ProbVector

FLOOR_SAFETY = "safety"
FLOOR_CONSTRAINT = "clarification_constraint"
FLOOR_URGENCY = "urgency_rule"


def onehot(p: ProbVector, label: str) -> ProbVector:
    """A vector over `p.labels` with all mass on `label` (ValueError if it is not one of them)."""
    if label not in p.labels:
        raise ValueError(f"{label!r} is not one of {p.labels}")
    return ProbVector(tuple(1.0 if lab == label else 0.0 for lab in p.labels), p.labels)


class PriorityFinalizer:
    """`apply(p_pri_head, safety, verdict, constraints, floor_hits=()) -> (p_pri_final, floors_applied)`.

    See the module docstring.

    Raises:
        ValueError: a priority constraint whose value is not a priority label.
    """

    def apply(
        self,
        p_pri_head: ProbVector,
        safety: bool,
        verdict: GuardVerdict,
        constraints: Sequence[ClarificationConstraint],
        floor_hits: Sequence[str] = (),
    ) -> tuple[ProbVector, tuple[str, ...]]:
        if safety:
            return onehot(p_pri_head, Priority.HIGH.value), (FLOOR_SAFETY,)
        answered = [c.value for c in constraints if c.kind == "priority"]
        if answered:
            value = Priority(answered[-1]).value  # the latest answer wins; ValueError if not a priority
            return onehot(p_pri_head, value), (FLOOR_CONSTRAINT,)
        if floor_hits:
            return onehot(p_pri_head, Priority.HIGH.value), (FLOOR_URGENCY,)
        return p_pri_head, ()
