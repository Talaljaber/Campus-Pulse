"""Priority evidence features and floor precedence (P1.12, ARCHITECTURE §3.8). Stdlib only.

`EVIDENCE_FEATURES` is the fixed, ordered list of labeller-rule cues the priority head sees next to the
model's priority probabilities. It must equal `config/train.yaml priority_head.features` (and therefore
`FrozenConfig.priority_head.features`); a test asserts it.

`stated_urgency` (an `URGENT:` wrapper or `عاجل` marker) is NEVER a feature: tone never raises priority
(SPEC §5.1[9]); it only feeds the gaming detector.

Floor precedence (highest first), applied outside the head by `PriorityFinalizer`:
    distress > safety -> high > clarification constraint > injection strip > head > conformal
Nothing ever lowers a priority by rule.
"""

from __future__ import annotations

from collections.abc import Mapping

EVIDENCE_FEATURES: tuple[str, ...] = (
    "deadline_today",      # a same-day deadline: today / اليوم / elyom, closes tonight, last day
    "exam_now",            # an exam or quiz is happening now (online exam, during the quiz)
    "safety_risk",         # a physical hazard: water near electricity, fire, smoke, gas, sparks
    "stranded",            # people cannot leave or get home: stranded, cannot leave, بدون مواصلات
    "enrollment_blocked",  # a definitive loss or block of enrolment: removed course, cannot register
    "transient_glitch",    # a temporary system fault: hanging page, keeps disconnecting, slow, error
    "info_request",        # an information request (where/how/when ... at the start), no fault reported
    "fault_report",        # something is broken, not working, wrong, missing, late
    "ambient_fixture",     # a shared-space fixture: hallway, corridor, light, lamp
    "teaching_room",       # a teaching space or its equipment: lecture room, classroom, lab, projector
)

FORBIDDEN_FEATURES: frozenset[str] = frozenset({"stated_urgency"})

FLOOR_PRECEDENCE: tuple[str, ...] = (
    "distress", "safety", "clarification_constraint", "injection_strip", "head", "conformal",
)


def evidence_row(
    flags: Mapping[str, bool], features: tuple[str, ...] = EVIDENCE_FEATURES
) -> tuple[float, ...]:
    """The flags as 0.0/1.0 in feature order (a missing flag counts as absent).

    Raises:
        ValueError: `features` contains a forbidden feature such as `stated_urgency`.
    """
    banned = FORBIDDEN_FEATURES.intersection(features)
    if banned:
        raise ValueError(f"{sorted(banned)} must never be a priority feature")
    return tuple(1.0 if flags.get(name, False) else 0.0 for name in features)
