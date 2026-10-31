"""P0.4: domain vocabulary and value-object invariants."""

from __future__ import annotations

import csv
import inspect
from pathlib import Path

import pytest

from campuspulse_ai.domain import ports
from campuspulse_ai.domain.errors import RecipientNotAllowed
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS, Category, Priority
from campuspulse_ai.domain.policy import RecipientPolicy
from campuspulse_ai.domain.values import PredictionSet, ProbVector, TicketStatus

REPO_ROOT = Path(__file__).resolve().parents[4]
SCENARIOS = REPO_ROOT / "data" / "clean" / "scenarios.csv"


def _official_values(column: str) -> set[str]:
    with SCENARIOS.open(encoding="utf-8-sig", newline="") as fh:
        return {row[column] for row in csv.DictReader(fh)}


def test_category_values_match_official_labels() -> None:
    assert {c.value for c in Category} == _official_values("category")
    assert {p.value for p in Priority} == _official_values("priority")
    assert set(CATEGORY_LABELS) == {c.value for c in Category}
    assert set(PRIORITY_LABELS) == {p.value for p in Priority}


def test_priority_rank_and_bump_caps_at_high() -> None:
    assert [p.rank for p in (Priority.LOW, Priority.MEDIUM, Priority.HIGH)] == [0, 1, 2]
    assert Priority.LOW.bump() is Priority.MEDIUM
    assert Priority.MEDIUM.bump() is Priority.HIGH
    assert Priority.HIGH.bump() is Priority.HIGH


def test_probvector_rejects_non_normalized() -> None:
    with pytest.raises(ValueError):
        ProbVector((0.5, 0.6, 0.0), PRIORITY_LABELS)
    with pytest.raises(ValueError):
        ProbVector((1.0, 0.0), PRIORITY_LABELS)
    with pytest.raises(ValueError):
        ProbVector((1.2, -0.2, 0.0), PRIORITY_LABELS)
    ok = ProbVector((0.2, 0.3, 0.5 + 5e-7), PRIORITY_LABELS)
    assert ok.as_dict()["high"] == pytest.approx(0.5)


def test_probvector_argmax_tiebreak_follows_label_order() -> None:
    tie = ProbVector((0.4, 0.4, 0.2), PRIORITY_LABELS)
    assert tie.argmax() == "low"
    assert tie.top(2) == [("low", 0.4), ("medium", 0.4)]
    assert ProbVector((0.1, 0.2, 0.7), PRIORITY_LABELS).argmax() == "high"


def test_predictionset_size_and_singleton() -> None:
    single = PredictionSet(frozenset({"Finance"}))
    pair = PredictionSet(frozenset({"Registration", "IT Support"}))
    assert single.size == 1 and single.is_singleton
    assert pair.size == 2 and not pair.is_singleton


def test_ports_are_runtime_checkable_protocols() -> None:
    declared = {
        name
        for name, obj in inspect.getmembers(ports, inspect.isclass)
        if obj.__module__ == ports.__name__ and getattr(obj, "_is_protocol", False)
    }
    assert declared == {p.__name__ for p in ports.ALL_PORTS}
    for port in ports.ALL_PORTS:
        assert getattr(port, "_is_runtime_protocol", False), port.__name__


def test_recipient_policy_allows_only_listed_and_rejects_all_when_empty() -> None:
    policy = RecipientPolicy(frozenset({"Demo.Student@Example.com"}))
    policy.check("  demo.student@example.com ")
    with pytest.raises(RecipientNotAllowed):
        policy.check("someone@gju.edu.jo")
    with pytest.raises(RecipientNotAllowed):
        RecipientPolicy(frozenset()).check("demo.student@example.com")


def test_ticket_status_rank_is_the_forward_lifecycle_order() -> None:
    # D-013 moved the order from the sync use case into the domain.
    order = [TicketStatus.OPEN, TicketStatus.ESCALATED, TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED]
    assert [s.rank for s in order] == [0, 1, 2, 3]
    assert TicketStatus.CLOSED.rank == TicketStatus.MERGED.rank > TicketStatus.RESOLVED.rank
