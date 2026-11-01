"""WindowedCentroidDetector (P4.10): local stores always, Supabase + pgvector with `-m supabase`."""

from __future__ import annotations

import dataclasses
import math
import random
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import pytest
from fixtures.supabase_test import supabase_test_client

from campuspulse_ai.adapters.pulse.incident_detector import WindowedCentroidDetector, majority
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.domain.entities import CoreResult, IncidentDecision, Prediction, Request, Ticket
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
    TicketStatus,
    Tier,
    VectorItem,
)

DIM = 384
TAU = 0.80
WINDOW_MIN = 30
B1, B2 = "zz-pulse-1", "zz-pulse-2"
TICKETS: dict[str, str] = {}  # request id -> its ticket id (the flow creates one per report)


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
    ticket = h.repo.save_ticket(Ticket("", req.id, None, "it", category, priority, TicketStatus.OPEN, False,
                                       created + timedelta(days=1)))  # fmt: skip
    TICKETS[req.id] = ticket.id
    decision = det.detect(req, prediction(req.id, category, priority), emb)
    if decision.incident is not None:  # what the action engine does: link the members' tickets
        ids = [TICKETS[m] for m in decision.members if m in TICKETS]
        h.repo.save_incident(dataclasses.replace(decision.incident, member_ticket_ids=ids))
    return decision


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


def test_other_buildings_are_separate(h: Harness) -> None:
    det = detector(h)
    for i in range(2):
        report(h, det, around(3, i), building=B1)
        report(h, det, around(3, 10 + i), building=B2)
    assert report(h, det, around(3, 30), building=B2).kind == "new"
    assert report(h, det, around(3, 31), building=B1).kind == "new"
    since = h.clock.now() - timedelta(hours=1)
    assert (
        len(h.repo.open_incidents(B1, None, since)) == 1 and len(h.repo.open_incidents(B2, None, since)) == 1
    )


def test_d017_one_outage_with_mixed_predicted_categories_is_one_incident(h: Harness) -> None:
    """D-017: v1-rc1 scattered the Wi-Fi reports across categories; similarity groups them, and the
    incident takes the majority category."""
    det = detector(h, tau_inc=0.92)
    topic = around(12, 0, noise=0.0)
    it, fac = Category.IT_SUPPORT, Category.FACILITIES
    labels = [it, Category.TRANSPORTATION, it, fac, Category.REGISTRATION, fac, fac, fac]
    decisions = [report(h, det, toward(topic, 0.97, 900 + i), category=c) for i, c in enumerate(labels)]
    assert [d.kind for d in decisions] == ["none", "none", "new"] + ["attach"] * 5
    ids = {d.incident.id for d in decisions[2:] if d.incident is not None}
    assert len(ids) == 1
    assert (
        decisions[2].incident is not None and decisions[2].incident.category == Category.IT_SUPPORT
    )  # 2 of 3
    assert (
        decisions[4].incident is not None and decisions[4].incident.category == Category.IT_SUPPORT
    )  # 2 of 5
    assert (
        decisions[5].incident is not None and decisions[5].incident.category == Category.IT_SUPPORT
    )  # 2:2, the incident keeps its category
    last = decisions[-1].incident
    assert last is not None and last.category == Category.FACILITIES and last.report_count == 8
    assert last.title == f"Facilities reports in building {B1}"
    assert h.repo.open_incidents(B1, Category.FACILITIES, h.clock.now() - timedelta(hours=1))[0].id in ids


def test_d017_an_unrelated_it_complaint_in_the_building_does_not_attach(h: Harness) -> None:
    det = detector(h, tau_inc=0.92)
    topic = around(13, 0, noise=0.0)
    mixed = [Category.TRANSPORTATION, Category.IT_SUPPORT, Category.FACILITIES]
    wifi = [report(h, det, toward(topic, 0.97, 1000 + i), category=c) for i, c in enumerate(mixed)]
    assert wifi[-1].kind == "new" and wifi[-1].incident is not None
    printer = report(h, det, toward(topic, 0.89, 1100), category=Category.IT_SUPPORT)
    assert printer.kind == "none"
    assert h.repo.get_incident(wifi[-1].incident.id).report_count == 3


@pytest.mark.parametrize(
    ("reported", "prefer", "expected"),
    [
        (
            [Category.IT_SUPPORT, Category.IT_SUPPORT, Category.FACILITIES],
            Category.FACILITIES,
            Category.IT_SUPPORT,
        ),
        ([Category.IT_SUPPORT, Category.FACILITIES], Category.FACILITIES, Category.FACILITIES),  # tie: prefer
        ([Category.IT_SUPPORT, Category.FACILITIES, Category.FINANCE], Category.FINANCE, Category.FINANCE),
        ([None, Category.FINANCE], Category.REGISTRATION, Category.FINANCE),
        ([None], Category.REGISTRATION, Category.REGISTRATION),
    ],
)
def test_d017_majority_category(
    reported: list[Category | None], prefer: Category, expected: Category
) -> None:
    assert majority(reported, prefer) == expected


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


def test_open_incident_takes_reports_whatever_its_age(h: Harness) -> None:
    """D-007: the window bounds opening only; an ongoing outage stays one incident."""
    det = detector(h)
    opened = [report(h, det, around(7, i)) for i in range(3)][-1]
    assert opened.kind == "new" and opened.incident is not None
    h.clock.t += timedelta(minutes=3 * WINDOW_MIN)
    late = report(h, det, around(7, 10))
    assert late.kind == "attach" and late.incident is not None
    assert (late.incident.id, late.incident.report_count, len(late.members)) == (opened.incident.id, 4, 1)
    elsewhere = report(h, det, around(7, 11), building=B2)
    assert elsewhere.kind == "none"


def toward(base: tuple[float, ...], cos: float, seed: int) -> tuple[float, ...]:
    """A unit vector at cosine `cos` to `base`, in a random direction of its own."""
    rnd = random.Random(seed)
    g = [rnd.gauss(0, 1) for _ in range(DIM)]
    dot = sum(a * b for a, b in zip(g, base, strict=True))
    ortho = unit([a - dot * b for a, b in zip(g, base, strict=True)])
    sin = math.sqrt(1 - cos * cos)
    return unit([cos * b + sin * o for b, o in zip(base, ortho, strict=True)])


def test_d015_unrelated_it_complaints_do_not_join_the_wifi_incident(h: Harness) -> None:
    """D-015 geometry measured on the v1-rc1 encoder: Wi-Fi reports >= 0.926 to their centroid,
    unrelated IT complaints in the same building 0.856-0.909. tau_inc = 0.92 separates them."""
    det = detector(h, tau_inc=0.92)
    topic = around(8, 0, noise=0.0)
    wifi = [report(h, det, toward(topic, 0.97, 100 + i)) for i in range(3)]
    assert [d.kind for d in wifi] == ["none", "none", "new"] and wifi[-1].incident is not None
    incident_id = wifi[-1].incident.id
    # printer, projector, ... (cosines vary like the measured 0.856-0.909)
    others = [report(h, det, toward(topic, 0.86 + 0.005 * i, 200 + i)) for i in range(8)]
    assert not [d for d in others if d.incident is not None and d.incident.id == incident_id]
    late = report(h, det, toward(topic, 0.97, 300))
    assert late.kind == "attach" and late.incident is not None
    assert (late.incident.id, late.incident.report_count) == (incident_id, 4)


def test_d015_the_old_threshold_would_have_merged_them(h: Harness) -> None:
    det = detector(h, tau_inc=0.80)
    topic = around(9, 0, noise=0.0)
    for i in range(3):
        report(h, det, toward(topic, 0.97, 400 + i))
    assert report(h, det, toward(topic, 0.89, 500)).kind == "attach"


def test_d015_attach_picks_the_open_incident_whose_centroid_is_closest(h: Harness) -> None:
    det = detector(h, tau_inc=0.92)
    a, b = around(10, 0, noise=0.0), around(11, 0, noise=0.0)
    for i in range(3):
        report(h, det, toward(a, 0.97, 600 + i))
    second = [report(h, det, toward(b, 0.97, 700 + i)) for i in range(3)]
    assert second[-1].kind == "new"  # a different problem in the same building opens its own incident
    nxt = report(h, det, toward(b, 0.97, 800))
    assert nxt.kind == "attach" and nxt.incident is not None and second[-1].incident is not None
    assert nxt.incident.id == second[-1].incident.id


def test_d021_reports_just_under_tau_join_the_incident_instead_of_opening_a_second(h: Harness) -> None:
    """D-021, the live Wi-Fi run: reports 6-8 scored 0.907-0.919 to the first centroid (tau 0.92) and
    opened a second incident whose centroid was 0.959 from the first. They now join the first."""
    det = detector(h, tau_inc=0.92)
    topic = around(21, 0, noise=0.0)
    first = [report(h, det, toward(topic, 0.97, 2100 + i)) for i in range(5)]
    assert first[2].kind == "new" and first[2].incident is not None
    incident_id = first[2].incident.id
    late = [report(h, det, toward(topic, c, 2200 + i)) for i, c in enumerate((0.915, 0.919, 0.907))]
    assert "new" not in [d.kind for d in late]
    since = h.clock.now() - timedelta(hours=1)
    opened = h.repo.open_incidents(B1, None, since)
    assert [i.id for i in opened] == [incident_id] and opened[0].report_count == 8
    assert {d.incident.id for d in late if d.incident is not None} == {incident_id}


def test_d021_unrelated_reports_at_0857_to_0900_stay_separate(h: Harness) -> None:
    det = detector(h, tau_inc=0.92)
    topic = around(22, 0, noise=0.0)
    for i in range(3):
        report(h, det, toward(topic, 0.97, 2300 + i))
    sims = (0.857, 0.88, 0.9, 0.87, 0.89, 0.86, 0.9, 0.875)
    others = [report(h, det, toward(topic, c, 2400 + i)) for i, c in enumerate(sims)]
    assert [d.kind for d in others] == ["none"] * len(sims)
    opened = h.repo.open_incidents(B1, None, h.clock.now() - timedelta(hours=1))
    assert len(opened) == 1 and opened[0].report_count == 3


def test_d021_two_open_incidents_that_drift_together_are_merged(h: Harness) -> None:
    topic_a = around(23, 0, noise=0.0)
    topic_b = toward(topic_a, 0.959, 2500)  # the two centroids sit 0.959 apart
    strict = detector(h, tau_inc=0.97)
    ids = []
    for topic, base in ((topic_a, 2600), (topic_b, 2700)):
        decisions = [report(h, strict, toward(topic, 0.99, base + i)) for i in range(3)]
        assert decisions[-1].kind == "new" and decisions[-1].incident is not None
        ids.append(decisions[-1].incident.id)
    assert ids[0] != ids[1]
    marked = [dataclasses.replace(h.repo.incident_members(i)[0][0], tags=("incident",)) for i in ids]
    for ticket in marked:
        h.repo.save_ticket(ticket)

    decision = report(h, detector(h, tau_inc=0.92), around(99, 0))  # an unrelated report triggers the check
    assert decision.kind == "none"
    assert len(decision.absorbed) == 1 and decision.absorbed[0].id in {t.id for t in marked}
    assert decision.absorbed[0].status == TicketStatus.MERGED and "incident" not in decision.absorbed[0].tags
    open_now = h.repo.open_incidents(B1, None, h.clock.now() - timedelta(hours=1))
    assert len(open_now) == 1 and open_now[0].id in ids and open_now[0].report_count == 6
    keep, gone = (ids[0], ids[1]) if open_now[0].id == ids[0] else (ids[1], ids[0])
    assert h.repo.get_incident(gone).status == "resolved"
    assert len(h.repo.incident_members(keep)) == 6 and h.repo.incident_members(gone) == []
    if isinstance(h.repo, InMemoryRepository):
        actions = [e["action"] for e in h.repo.tables["events"].values()]
        assert "incident.absorbed" in actions
