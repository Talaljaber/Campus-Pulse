"""WindowedCentroidDetector (P4.10): local stores always, Supabase + pgvector with `-m supabase`."""

from __future__ import annotations

import math
import random
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import pytest
from fixtures.supabase_test import supabase_test_client

from campuspulse_ai.adapters.pulse.incident_detector import WindowedCentroidDetector
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.domain.entities import CoreResult, IncidentDecision, Prediction, Request
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS, Category, Priority
from campuspulse_ai.domain.ports import IncidentDetector, Repository, VectorStore
from campuspulse_ai.domain.values import (
    ArtifactVersion,
    EvidenceVector,
    GuardVerdict,
    Lang,
    Location,
    Money,
    NormalizedRequest,
    PredictionSet,
    ProbVector,
    RequestStatus,
    Tier,
    VectorItem,
)

DIM = 384
TAU = 0.80
WINDOW_MIN = 30
B1, B2 = "zz-pulse-1", "zz-pulse-2"


class FixedClock:
    def __init__(self) -> None:
        self.t = datetime.now(UTC).replace(microsecond=0)

    def now(self) -> datetime:
        return self.t


def unit(v: list[float]) -> tuple[float, ...]:
    n = math.sqrt(sum(x * x for x in v))
    return tuple(x / n for x in v)


def around(seed: int, i: int, noise: float = 0.05) -> tuple[float, ...]:
    """A report embedding near the topic vector `seed` (cosine ≈ 0.99 to its siblings)."""
    base = random.Random(seed)
    jitter = random.Random(seed * 1000 + i)
    return unit([base.gauss(0, 1) + noise * jitter.gauss(0, 1) for _ in range(DIM)])


class Harness(Protocol):
    repo: Repository
    vectors: VectorStore
    clock: FixedClock
    tag: str

    def cleanup(self) -> None: ...


class LocalHarness:
    def __init__(self) -> None:
        self.clock = FixedClock()
        self.repo = InMemoryRepository(self.clock)
        self.vectors = LocalNumpyVectorStore(DIM, collections=("requests",))
        self.tag = f"pulse-test-{uuid.uuid4().hex[:8]}"

    def cleanup(self) -> None:
        pass


class SupabaseHarness:
    def __init__(self) -> None:
        from campuspulse_ai.adapters.store.supabase_store import SupabaseRepository
        from campuspulse_ai.adapters.vectors.pgvector import PgVectorStore

        self.db: Any = supabase_test_client()
        self.clock = FixedClock()
        self.repo = SupabaseRepository(self.db, self.clock)
        self.vectors = PgVectorStore(self.db, DIM)
        self.tag = f"pulse-test-{uuid.uuid4().hex[:8]}"
        for b in (B1, B2):
            self.db.table("buildings").upsert({"id": b, "code": b, "name_en": b, "name_ar": b}).execute()

    def cleanup(self) -> None:
        self.db.table("requests").delete().like("alias", f"{self.tag}%").execute()
        self.db.table("incidents").delete().in_("building_id", [B1, B2]).execute()
        self.db.table("buildings").delete().in_("id", [B1, B2]).execute()


@pytest.fixture(
    params=[pytest.param(LocalHarness), pytest.param(SupabaseHarness, marks=pytest.mark.supabase)],
    ids=["local", "supabase"],
)
def h(request: pytest.FixtureRequest) -> Iterator[Harness]:
    harness: Harness = request.param()
    try:
        yield harness
    finally:
        harness.cleanup()


def detector(h: Harness, **overrides: Any) -> WindowedCentroidDetector:
    kwargs: dict[str, Any] = {"tau_inc": TAU, "window_min": WINDOW_MIN, "min_reports": 3, "bump_at": 6}
    kwargs.update(overrides)
    return WindowedCentroidDetector(h.repo, h.vectors, h.clock, **kwargs)


def prediction(request_id: str, category: Category, priority: Priority) -> Prediction:
    flat = (1 / len(CATEGORY_LABELS),) * len(CATEGORY_LABELS)
    core = CoreResult(
        p_cat=ProbVector(flat, CATEGORY_LABELS),
        p_pri=ProbVector((1 / 3, 1 / 3, 1 / 3), PRIORITY_LABELS),
        per_model={},
        flags=frozenset(),
        set_cat=PredictionSet(frozenset({str(category)})),
        set_pri=PredictionSet(frozenset({str(priority)})),
        ood_score=0.0,
        neighbors=(),
        evidence=EvidenceVector(flags={}),
        guard=GuardVerdict(kind="none"),
        safety=False,
        floors_applied=(),
        tier=Tier.TIER0,
        latency_ms=1,
        artifact=ArtifactVersion("test", "0" * 64),
    )
    return Prediction("", request_id, category, priority, core, Tier.TIER0, set(), None, Money(0.0), "test")


def report(
    h: Harness,
    det: WindowedCentroidDetector,
    emb: tuple[float, ...],
    *,
    building: str | None = B1,
    category: Category = Category.IT_SUPPORT,
    priority: Priority = Priority.MEDIUM,
    minutes_ago: float = 0.0,
) -> IncidentDecision:
    """What TriageUseCase does per request: save, store the embedding ([12b]), then detect ([13])."""
    created = h.clock.now() - timedelta(minutes=minutes_ago)
    text = f"wifi down {uuid.uuid4().hex[:6]}"
    location = Location(building, "204", "picked") if building else None
    normalized = NormalizedRequest(text, text, text, text, Lang.EN, False, False, False, location)
    req = h.repo.save_request(Request("", h.tag, text, normalized, "text", RequestStatus.DECIDED, created))
    meta = {
        "building_id": building,
        "category": str(category),
        "priority": str(priority),
        "created_at": created.isoformat(),
    }
    h.vectors.upsert("requests", [VectorItem(req.id, emb, text, Lang.EN, meta)])
    return det.detect(req, prediction(req.id, category, priority), emb)


def test_satisfies_port(h: Harness) -> None:
    assert isinstance(detector(h), IncidentDetector)


def test_two_none_third_new_fourth_attach(h: Harness) -> None:
    det = detector(h)
    first, second = report(h, det, around(1, 1)), report(h, det, around(1, 2))
    assert (first.kind, second.kind) == ("none", "none")
    third = report(h, det, around(1, 3))
    assert third.kind == "new" and third.incident is not None
    assert (third.incident.report_count, third.incident.building, third.incident.status) == (3, B1, "open")
    assert len(third.members) == 3
    fourth = report(h, det, around(1, 4))
    assert fourth.kind == "attach" and fourth.incident is not None
    assert (fourth.incident.id, fourth.incident.report_count) == (third.incident.id, 4)
    assert (
        h.repo.open_incidents(B1, Category.IT_SUPPORT, h.clock.now() - timedelta(hours=1))[0].report_count
        == 4
    )


def test_priority_is_max_then_bumped_once_at_six(h: Harness) -> None:
    det = detector(h)
    decisions = [report(h, det, around(2, i), priority=Priority.LOW) for i in range(5)]
    assert decisions[2].incident is not None and decisions[2].incident.priority == Priority.LOW
    assert decisions[4].incident is not None and decisions[4].incident.priority == Priority.LOW
    sixth = report(h, det, around(2, 5), priority=Priority.MEDIUM)
    assert sixth.incident is not None and sixth.incident.priority == Priority.HIGH  # max(low, medium) bumped
    seventh = report(h, det, around(2, 6), priority=Priority.LOW)
    assert seventh.incident is not None and seventh.incident.priority == Priority.HIGH  # not bumped again


def test_other_building_and_category_are_separate(h: Harness) -> None:
    det = detector(h)
    for i in range(2):
        report(h, det, around(3, i), building=B1)
        report(h, det, around(3, 10 + i), building=B2)
        report(h, det, around(3, 20 + i), building=B1, category=Category.FACILITIES)
    assert report(h, det, around(3, 30), building=B2).kind == "new"
    assert report(h, det, around(3, 31), building=B1).kind == "new"
    assert len(h.repo.open_incidents(B1, Category.IT_SUPPORT, h.clock.now() - timedelta(hours=1))) == 1
    assert h.repo.open_incidents(B1, Category.FACILITIES, h.clock.now() - timedelta(hours=1)) == []


def test_reports_outside_the_window_do_not_count(h: Harness) -> None:
    det = detector(h)
    report(h, det, around(4, 1), minutes_ago=WINDOW_MIN + 5)
    report(h, det, around(4, 2), minutes_ago=WINDOW_MIN + 1)
    assert report(h, det, around(4, 3)).kind == "none"
    assert report(h, det, around(4, 4)).kind == "none"
    assert report(h, det, around(4, 5)).kind == "new"


def test_no_location_and_dissimilar_reports_give_none(h: Harness) -> None:
    det = detector(h)
    assert report(h, det, around(5, 1), building=None).kind == "none"
    report(h, det, around(5, 2))
    report(h, det, around(5, 3))
    odd = report(h, det, around(99, 1))  # a different topic in the same building/category
    assert odd.kind == "none"


def test_thresholds_come_from_config(h: Harness) -> None:
    det = detector(h, min_reports=2, bump_at=3)
    report(h, det, around(6, 1), priority=Priority.LOW)
    second = report(h, det, around(6, 2), priority=Priority.LOW)
    assert second.kind == "new" and second.incident is not None and second.incident.priority == Priority.LOW
    third = report(h, det, around(6, 3), priority=Priority.LOW)
    assert third.incident is not None and third.incident.priority == Priority.MEDIUM
