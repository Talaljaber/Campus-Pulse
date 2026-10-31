"""`LogisticPriorityHead` (P1.13)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from campuspulse_ai.adapters.models.priority_head import LogisticPriorityHead
from campuspulse_ai.domain.labels import PRIORITY_LABELS
from campuspulse_ai.domain.ports import PriorityHead
from campuspulse_ai.domain.priority_rules import EVIDENCE_FEATURES
from campuspulse_ai.domain.values import ClarificationConstraint, EvidenceVector, ProbVector


def _p(low: float, med: float, high: float) -> ProbVector:
    return ProbVector((low, med, high), PRIORITY_LABELS)


def _ev(**on: bool) -> EvidenceVector:
    return EvidenceVector(flags={f: on.get(f, False) for f in EVIDENCE_FEATURES})


def _fitted() -> LogisticPriorityHead:
    """Medium-looking model output; `deadline_today` alone separates high (the labeller's rule)."""
    rows = [
        (_p(0.7, 0.2, 0.1), _ev(info_request=True), "low"),
        (_p(0.6, 0.3, 0.1), _ev(info_request=True), "low"),
        (_p(0.2, 0.6, 0.2), _ev(fault_report=True), "medium"),
        (_p(0.2, 0.7, 0.1), _ev(fault_report=True), "medium"),
        (_p(0.2, 0.6, 0.2), _ev(fault_report=True, deadline_today=True), "high"),
        (_p(0.3, 0.5, 0.2), _ev(deadline_today=True), "high"),
    ]
    head = LogisticPriorityHead(EVIDENCE_FEATURES, C=10.0, seed=42)
    head.fit([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows], None)
    return head


def test_input_width_is_3_plus_features() -> None:
    head = _fitted()
    assert isinstance(head, PriorityHead)
    assert head.input_width == 3 + len(EVIDENCE_FEATURES)
    x = head.matrix([_p(0.2, 0.6, 0.2)], [_ev(fault_report=True)])
    assert x.shape == (1, 13)
    assert x[0, :3].tolist() == [0.2, 0.6, 0.2]
    with pytest.raises(ValueError):
        head.predict_matrix(np.zeros((1, 12)))
    with pytest.raises(ValueError):
        LogisticPriorityHead((*EVIDENCE_FEATURES, "stated_urgency"), C=1.0, seed=42)


def test_save_load(tmp_path: Path) -> None:
    head = _fitted()
    head.save(tmp_path / "head")
    loaded = LogisticPriorityHead.load(tmp_path / "head")
    args = (_p(0.2, 0.6, 0.2), _ev(fault_report=True))
    assert loaded.predict(*args).values == head.predict(*args).values
    assert loaded.features == EVIDENCE_FEATURES


def test_feature_constraint_sets_flag() -> None:
    head = _fitted()
    p, ev = _p(0.2, 0.6, 0.2), _ev(fault_report=True)
    plain = head.predict(p, ev)
    answered = head.predict(p, ev, [ClarificationConstraint("feature", "deadline_today")])
    assert plain.argmax() == "medium"
    assert answered.argmax() == "high"
    assert answered.values == head.predict(p, _ev(fault_report=True, deadline_today=True)).values
