"""Repository contract (P4.3): InMemoryRepository always, SupabaseRepository with keys.

Both must give the same answers for every port method: round trips are lossless, NotFound and
StoreError fire in the same cases, and orderings match. Supabase rows are tagged per run and
deleted in teardown.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import pytest
from fixtures.supabase_test import supabase_test_client

from campuspulse_ai.adapters.store import codec
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.domain.entities import (
    Case,
    Clarification,
    CoreResult,
    Explanation,
    Incident,
    OutboxMessage,
    Prediction,
    Request,
    ReviewItem,
    Scorecard,
    Ticket,
)
from campuspulse_ai.domain.errors import NotFound, StoreError
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS, Category, Priority
from campuspulse_ai.domain.ports import Repository
from campuspulse_ai.domain.values import (
    Advisor,
    ArtifactVersion,
    Booking,
    ClarificationConstraint,
    ClarificationOption,
    Counterfactual,
    Evidence,
    EvidenceVector,
    GuardVerdict,
    Lang,
    Location,
    Money,
    Neighbor,
    NormalizedRequest,
    PredictionSet,
    ProbVector,
    RequestStatus,
    Slot,
    TicketLink,
    TicketStatus,
    Tier,
)

BUILDING = "zz-repo-test"
T0 = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class Harness(Protocol):
    repo: Repository
    tag: str

    def advisor(self, name: str, department: str) -> Advisor: ...
    def slot(self, advisor_id: str, starts_at: datetime) -> Slot: ...
    def llm_call(self, cached: bool) -> None: ...
    def track_run(self, run_id: str) -> None: ...
    def cleanup(self) -> None: ...


class InMemoryHarness:
    def __init__(self) -> None:
        self.repo = InMemoryRepository(UtcClock())
        self.tag = f"repo-test-{uuid.uuid4().hex[:8]}"

    def advisor(self, name: str, department: str) -> Advisor:
        return self.repo.add_advisor(name, department, f"{self.tag}@example.invalid")

    def slot(self, advisor_id: str, starts_at: datetime) -> Slot:
        return self.repo.add_slot(advisor_id, starts_at, starts_at + timedelta(minutes=30))

    def llm_call(self, cached: bool) -> None:
        self.repo.add_llm_call(Tier.TIER1, 0.001, cached)

    def track_run(self, run_id: str) -> None:
        pass

    def cleanup(self) -> None:
        pass


class SupabaseHarness:
    """Seeds through the table API and deletes everything carrying this run's tag."""

    def __init__(self) -> None:
        from campuspulse_ai.adapters.store.supabase_store import SupabaseRepository

        self.db: Any = supabase_test_client()
        self.repo = SupabaseRepository(self.db, UtcClock())
        self.tag = f"repo-test-{uuid.uuid4().hex[:8]}"
        self._runs: list[str] = []
        self.db.table("buildings").upsert(
            {"id": BUILDING, "code": BUILDING, "name_en": "Repository test", "name_ar": "اختبار"}
        ).execute()

    def advisor(self, name: str, department: str) -> Advisor:
        row = {"fictional_name": name, "department": department, "demo_email": f"{self.tag}@example.invalid"}
        data = self.db.table("advisors").insert(row).execute().data[0]
        return Advisor(id=data["id"], name=name, department=department, email=row["demo_email"])

    def slot(self, advisor_id: str, starts_at: datetime) -> Slot:
        ends_at = starts_at + timedelta(minutes=30)
        row = {"advisor_id": advisor_id, "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()}
        data = self.db.table("advisor_slots").insert(row).execute().data[0]
        return Slot(id=data["id"], advisor_id=advisor_id, starts_at=starts_at, ends_at=ends_at)

    def llm_call(self, cached: bool) -> None:
        self.db.table("llm_calls").insert(
            {"tier": "tier1", "model": self.tag, "prompt_hash": self.tag, "cost_usd": 0.001, "cached": cached}
        ).execute()

    def track_run(self, run_id: str) -> None:
        self._runs.append(run_id)

    def cleanup(self) -> None:
        t = self.db.table
        t("requests").delete().like("alias", f"{self.tag}%").execute()  # cascades to the rest
        t("incidents").delete().eq("building_id", BUILDING).execute()
        t("outbox").delete().like("to_address", f"{self.tag}%").execute()
        t("notifications").delete().eq("alias", self.tag).execute()
        t("events").delete().eq("actor", self.tag).execute()
        t("student_signals").delete().eq("alias", self.tag).execute()
        t("llm_calls").delete().eq("model", self.tag).execute()
        t("advisors").delete().like("demo_email", f"{self.tag}%").execute()
        if self._runs:
            t("redteam_runs").delete().in_("id", self._runs).execute()
        t("buildings").delete().eq("id", BUILDING).execute()


@pytest.fixture(
    params=[pytest.param(InMemoryHarness), pytest.param(SupabaseHarness, marks=pytest.mark.supabase)],
    ids=["inmemory", "supabase"],
)
def h(request: pytest.FixtureRequest) -> Iterator[Harness]:
    harness: Harness = request.param()
    try:
        yield harness
    finally:
        harness.cleanup()


# --------------------------------------------------------------------------- builders


def pv(labels: tuple[str, ...], top: int) -> ProbVector:
    rest = 0.4 / (len(labels) - 1)
    return ProbVector(values=tuple(0.6 if i == top else rest for i in range(len(labels))), labels=labels)


def make_request(h: Harness, *, building: str | None = BUILDING, id: str = "") -> Request:
    location = Location(building=building, room="M-204", source="extracted") if building else None
    normalized = NormalizedRequest(
        raw="URGENT: wifi down in M today",
        core="wifi down in M today",
        text_norm="wifi down in m today",
        model_text="wifi down in m today",
        lang=Lang.EN,
        is_arabizi=False,
        stated_urgency=True,
        truncated=False,
        location=location,
    )
    return Request(
        id=id,
        alias=h.tag,
        raw_text=normalized.raw,
        normalized=normalized,
        input_mode="text",
        status=RequestStatus.RECEIVED,
        created_at=T0,
    )


def make_prediction(
    request_id: str, tier: Tier = Tier.TIER0, priority: Priority = Priority.HIGH
) -> Prediction:
    neighbor = Neighbor("wifi broken", Category.IT_SUPPORT, Priority.HIGH, 0.91, "memory", T0)
    core = CoreResult(
        p_cat=pv(CATEGORY_LABELS, 1),
        p_pri=pv(PRIORITY_LABELS, 2),
        per_model={"m1.category": pv(CATEGORY_LABELS, 1), "m2lr.priority": pv(PRIORITY_LABELS, 2)},
        flags=frozenset({"urgency_unsupported", "needs_review"}),
        set_cat=PredictionSet(frozenset({"IT Support", "Facilities"})),
        set_pri=PredictionSet(frozenset({"high"})),
        ood_score=0.12,
        neighbors=(neighbor,),
        evidence=EvidenceVector(
            flags={"deadline_today": True, "exam_now": False},
            spans=(Evidence("deadline_today", "today", Lang.EN),),
        ),
        guard=GuardVerdict(kind="none"),
        safety=False,
        floors_applied=("deadline_floor",),
        tier=tier,
        latency_ms=42,
        artifact=ArtifactVersion("v1", "ab" * 32),
    )
    explanation = Explanation(
        top_tokens=[("wifi", 0.31), ("today", 0.22)],
        urgency_reasons=[Evidence("deadline_today", "today", Lang.EN)],
        neighbors=[neighbor],
        counterfactual=Counterfactual(drop="today", category=Category.IT_SUPPORT, priority=Priority.MEDIUM),
        trace={"tier": "tier0", "asked": False},
    )
    return Prediction(
        id="",
        request_id=request_id,
        category=Category.IT_SUPPORT,
        priority=priority,
        core=core,
        tier=tier,
        flags={"urgency_unsupported"},
        explanation=explanation,
        cost=Money(0.0012),
        artifact_version="v1",
    )


def make_ticket(request_id: str, *, sla: datetime, status: TicketStatus = TicketStatus.NEW) -> Ticket:
    return Ticket(
        id="",
        request_id=request_id,
        incident_id=None,
        office="it",
        category=Category.IT_SUPPORT,
        priority=Priority.HIGH,
        status=status,
        provisional=False,
        sla_due_at=sla,
        title="Wi-Fi down in M",
        body="Reported from M-204.",
    )


# --------------------------------------------------------------------------- requests


def test_satisfies_port(h: Harness) -> None:
    assert isinstance(h.repo, Repository)


def test_request_round_trip_and_status(h: Harness) -> None:
    saved = h.repo.save_request(make_request(h))
    assert saved.id
    assert h.repo.get_request(saved.id) == saved
    h.repo.set_request_status(saved.id, RequestStatus.DECIDED)
    assert h.repo.get_request(saved.id).status == RequestStatus.DECIDED
    plain = h.repo.save_request(make_request(h, building=None))
    assert h.repo.get_request(plain.id).normalized == plain.normalized


def test_missing_rows_raise_not_found(h: Harness) -> None:
    missing = str(uuid.uuid4())
    for call in (
        lambda: h.repo.get_request(missing),
        lambda: h.repo.set_request_status(missing, RequestStatus.DECIDED),
        lambda: h.repo.latest_prediction(missing),
        lambda: h.repo.get_ticket(missing),
        lambda: h.repo.ticket_by_link("linear", f"{h.tag}-none"),
        lambda: h.repo.resolve_review(
            ReviewItem(id=missing, prediction_id=missing, reason="x", status="confirmed")
        ),
    ):
        with pytest.raises(NotFound):
            call()


def test_foreign_keys_raise_store_error(h: Harness) -> None:
    with pytest.raises(StoreError):
        h.repo.save_prediction(make_prediction(str(uuid.uuid4())))
    with pytest.raises(StoreError):
        h.repo.save_ticket(make_ticket(str(uuid.uuid4()), sla=T0))


# --------------------------------------------------------------------------- predictions / clarify / review


def test_prediction_round_trip_and_latest(h: Harness) -> None:
    req = h.repo.save_request(make_request(h))
    first = h.repo.save_prediction(make_prediction(req.id, priority=Priority.MEDIUM))
    assert h.repo.latest_prediction(req.id) == first
    second = h.repo.save_prediction(make_prediction(req.id, tier=Tier.TIER1))
    latest = h.repo.latest_prediction(req.id)
    assert latest == second
    assert latest.core.p_cat.labels == CATEGORY_LABELS


def test_clarifications_in_asked_order(h: Harness) -> None:
    req = h.repo.save_request(make_request(h))
    options = (ClarificationOption("o1", "Wi-Fi", ClarificationConstraint("category", "IT Support")),)
    later = Clarification("", req.id, "q2", options, None, T0 + timedelta(minutes=5))
    earlier = Clarification("", req.id, "q1", options, "o1", T0, answered_at=T0 + timedelta(minutes=1))
    saved = [h.repo.save_clarification(later), h.repo.save_clarification(earlier)]
    assert h.repo.clarifications_for(req.id) == [saved[1], saved[0]]


def test_review_enqueue_and_resolve(h: Harness) -> None:
    req = h.repo.save_request(make_request(h))
    pred = h.repo.save_prediction(make_prediction(req.id))
    item = h.repo.enqueue_review(
        ReviewItem(id="", prediction_id=pred.id, reason="needs_review", status="open")
    )
    assert item.id
    item.status, item.corrected_priority, item.note = "corrected", Priority.MEDIUM, "not urgent"
    h.repo.resolve_review(item)
    with pytest.raises(StoreError):
        h.repo.enqueue_review(ReviewItem(id="", prediction_id=str(uuid.uuid4()), reason="x", status="open"))


# --------------------------------------------------------------------------- tickets / incidents


def test_ticket_round_trip_with_links(h: Harness) -> None:
    req = h.repo.save_request(make_request(h))
    ticket = make_ticket(req.id, sla=T0 + timedelta(hours=24))
    ticket.links = [TicketLink("", "linear", f"{h.tag}-1", "https://linear.app/x/1")]
    saved = h.repo.save_ticket(ticket)
    assert saved.links[0].ticket_id == saved.id
    stored = h.repo.get_ticket(saved.id)
    # P9: the DB fills these two on insert (column default, requester trigger); the entity sent none.
    assert stored.clock_started_at is not None and stored.requester_alias == req.alias
    expected = dataclasses.replace(
        saved, clock_started_at=stored.clock_started_at, requester_alias=stored.requester_alias
    )
    assert stored == expected
    assert h.repo.ticket_by_link("linear", f"{h.tag}-1") == expected
    h.repo.save_ticket_link(TicketLink(saved.id, "webhook", f"{h.tag}-w"))
    assert [link.sink for link in h.repo.get_ticket(saved.id).links] == ["linear", "webhook"]


def test_ticket_clock_columns_round_trip(h: Harness) -> None:
    req = h.repo.save_request(make_request(h))
    ticket = make_ticket(req.id, sla=T0 + timedelta(hours=24))
    started = T0 - timedelta(hours=1)
    ticket.clock_started_at, ticket.reminder_sent_at, ticket.awaiting_student = started, T0, True
    stored = h.repo.get_ticket(h.repo.save_ticket(ticket).id)
    assert (stored.clock_started_at, stored.reminder_sent_at, stored.awaiting_student) == (started, T0, True)
    # An update that sets no clock start keeps the stored one; the requester is never overwritten.
    again = dataclasses.replace(stored, clock_started_at=None, reminder_sent_at=None, requester_alias="x")
    kept = h.repo.get_ticket(h.repo.save_ticket(again).id)
    assert kept.clock_started_at == started and kept.reminder_sent_at is None
    assert kept.requester_alias == req.alias


def test_ticket_tags_and_link_error_round_trip(h: Harness) -> None:
    """D-011: `Ticket.tags` and `TicketLink.error` (-> ticket_links.last_error) survive a round trip.

    Should `tickets.tags` ever be a pending column again (codec.PENDING_COLUMNS), SupabaseRepository
    drops it on write, so the save must still succeed and the tags read back empty.
    """
    req = h.repo.save_request(make_request(h))
    ticket = make_ticket(req.id, sla=T0 + timedelta(hours=24))
    ticket.tags = ("safety", "deferred:booking")
    ticket.links = [TicketLink("", "linear", f"error:{h.tag}", None, "Linear timed out")]
    saved = h.repo.save_ticket(ticket)
    back = h.repo.get_ticket(saved.id)
    assert back.links == saved.links and back.links[0].error == "Linear timed out"
    tags_pending = isinstance(h, SupabaseHarness) and "tags" in codec.PENDING_COLUMNS.get("tickets", ())
    assert back.tags == (() if tags_pending else ("safety", "deferred:booking"))


def test_ticket_link_is_unique_per_sink(h: Harness) -> None:
    req = h.repo.save_request(make_request(h))
    a = h.repo.save_ticket(make_ticket(req.id, sla=T0))
    b = h.repo.save_ticket(make_ticket(req.id, sla=T0))
    h.repo.save_ticket_link(TicketLink(a.id, "linear", f"{h.tag}-dup"))
    with pytest.raises(StoreError):
        h.repo.save_ticket_link(TicketLink(b.id, "linear", f"{h.tag}-dup"))


def test_overdue_open_tickets(h: Harness) -> None:
    req = h.repo.save_request(make_request(h))
    now = datetime.now(UTC)
    late = h.repo.save_ticket(make_ticket(req.id, sla=now - timedelta(hours=1)))
    later = h.repo.save_ticket(make_ticket(req.id, sla=now - timedelta(hours=3)))
    h.repo.save_ticket(make_ticket(req.id, sla=now + timedelta(hours=1)))
    h.repo.save_ticket(make_ticket(req.id, sla=now - timedelta(hours=2), status=TicketStatus.SOLVED))
    mine = [t.id for t in h.repo.overdue_open_tickets(now) if t.request_id == req.id]
    assert mine == [later.id, late.id]


def test_open_tickets_for_alias(h: Harness) -> None:
    req = h.repo.save_request(make_request(h))
    other = h.repo.save_request(dataclasses.replace(make_request(h), alias=f"{h.tag}-other"))
    first = h.repo.save_ticket(make_ticket(req.id, sla=T0))
    second = h.repo.save_ticket(make_ticket(req.id, sla=T0, status=TicketStatus.IN_PROGRESS))
    h.repo.save_ticket(make_ticket(req.id, sla=T0, status=TicketStatus.SOLVED))
    h.repo.save_ticket(make_ticket(req.id, sla=T0, status=TicketStatus.CLOSED))
    h.repo.save_ticket(make_ticket(other.id, sla=T0))
    mine = h.repo.open_tickets_for_alias(h.tag)
    assert {t.id for t in mine} == {first.id, second.id}
    assert all(t.requester_alias == h.tag for t in mine)
    assert len(h.repo.open_tickets_for_alias(h.tag, limit=1)) == 1
    assert h.repo.open_tickets_for_alias(f"{h.tag}-nobody") == []


def test_incidents_members_and_open_filter(h: Harness) -> None:
    r1 = h.repo.save_request(make_request(h))
    r2 = h.repo.save_request(make_request(h))
    t1 = h.repo.save_ticket(make_ticket(r1.id, sla=T0))
    t2 = h.repo.save_ticket(make_ticket(r2.id, sla=T0))
    opened = datetime.now(UTC) - timedelta(minutes=10)
    incident = Incident("", BUILDING, Category.IT_SUPPORT, "Wi-Fi outage in M", Priority.HIGH, 2, "open",
                        [t1.id, t2.id], opened)  # fmt: skip
    saved = h.repo.save_incident(incident)
    assert saved.member_ticket_ids == [t1.id, t2.id]
    assert h.repo.get_ticket(t1.id).incident_id == saved.id
    found = h.repo.open_incidents(BUILDING, Category.IT_SUPPORT, opened - timedelta(minutes=1))
    assert [i.id for i in found] == [saved.id]
    assert h.repo.open_incidents(BUILDING, Category.FINANCE, opened - timedelta(minutes=1)) == []
    assert h.repo.open_incidents(BUILDING, Category.IT_SUPPORT, opened + timedelta(minutes=1)) == []
    members = h.repo.incident_members(saved.id)
    assert [(t.id, r.id) for t, r in members] == [(t1.id, r1.id), (t2.id, r2.id)]
    saved.status, saved.resolved_at = "resolved", datetime.now(UTC)
    h.repo.save_incident(saved)
    assert h.repo.open_incidents(BUILDING, Category.IT_SUPPORT, opened - timedelta(minutes=1)) == []


# ---------------------------------------------------------------- outbox / signals / audit / red team


def test_outbox_notification_and_events_save(h: Harness) -> None:
    msg = OutboxMessage("", "email", f"{h.tag}@example.invalid", "Ticket opened", "Body", None, "rejected",
                        T0, Priority.HIGH, frozenset({"safety"}))  # fmt: skip
    assert h.repo.save_outbox(msg).id
    # D-011: a held-back message is `deferred` with its reason (migration 0009 allows the status).
    held = OutboxMessage("", "email", f"{h.tag}@example.invalid", "Cap", "Body", None, "deferred", T0,
                         error="daily email cap of 100 reached")  # fmt: skip
    saved = h.repo.save_outbox(held)
    assert saved.error == "daily email cap of 100 reached"
    if isinstance(h, SupabaseHarness) and not codec.PENDING_VALUES.get(("outbox", "status")):
        row = h.db.table("outbox").select("status,error").eq("id", saved.id).execute().data[0]
        assert row == {"status": "deferred", "error": "daily email cap of 100 reached"}
    h.repo.save_notification(h.tag, "ticket_status", {"status": "resolved", "at": T0})
    h.repo.append_event(h.tag, "test", "request", {"n": 1, "at": T0})


def test_student_signals_accumulate(h: Harness) -> None:
    h.repo.bump_student_signals(h.tag, claimed_urgent=True, was_high=False, injection=False)
    h.repo.bump_student_signals(h.tag, claimed_urgent=True, was_high=True, injection=True)
    s = h.repo.bump_student_signals(h.tag, claimed_urgent=False, was_high=False, injection=False)
    assert (s.alias, s.requests, s.claimed_urgent, s.claimed_urgent_not_high, s.injection_attempts) == (
        h.tag, 3, 2, 1, 1)  # fmt: skip
    assert s.gaming_suspected is False


def test_redteam_runs_newest_first(h: Harness) -> None:
    # D-013: the scorecard carries created_at, n and seed; history is ordered by created_at.
    at = datetime.now(UTC).replace(microsecond=0)
    second_id = str(uuid.uuid4())
    second = h.repo.save_redteam_run(
        Scorecard(
            second_id, {"arabizi": 0.8}, {"ar": 0.85}, 0.83, [{"text": "x", "got": "Finance"}],
            created_at=at + timedelta(seconds=1), n=20, seed=7,
        )  # fmt: skip
    )
    first = h.repo.save_redteam_run(
        Scorecard("not-a-uuid", {"typo": 0.9}, {"en": 0.95}, 0.92, created_at=at, n=10, seed=42)
    )
    h.track_run(first)
    h.track_run(second)
    assert uuid.UUID(first) and second == second_id
    history = h.repo.redteam_history(limit=2)
    assert [s.run_id for s in history] == [second, first]
    assert history[0].failures == [{"text": "x", "got": "Finance"}] and history[1].by_style == {"typo": 0.9}
    assert (history[0].created_at, history[0].n, history[0].seed) == (at + timedelta(seconds=1), 20, 7)
    assert (history[1].created_at, history[1].n, history[1].seed) == (at, 10, 42)


def test_scorecard_stored_before_d013_reads_with_the_row_timestamp() -> None:
    legacy = {"run_id": "r", "by_style": {"typos": 1}, "by_lang": {"en": 1}, "overall": 1, "failures": []}
    s = codec.to_scorecard(legacy, "2026-11-02T08:00:00+00:00")
    assert (s.created_at, s.n, s.seed) == (T0, 0, 0)
    with pytest.raises(StoreError):
        codec.to_scorecard(legacy, None)


# --------------------------------------------------------------------------- advisors / slots / cases / stats


def test_slots_free_and_claimed_once(h: Harness) -> None:
    dept = h.tag
    b = h.advisor("Zaid Advisor", dept)
    a = h.advisor("Aseel Advisor", dept)
    assert [x.name for x in h.repo.advisors_for(dept)] == ["Aseel Advisor", "Zaid Advisor"]
    s_late = h.slot(a.id, T0 + timedelta(hours=2))
    s_early = h.slot(b.id, T0 + timedelta(hours=1))
    h.slot(a.id, T0 + timedelta(days=3))  # outside the window
    window = (T0, T0 + timedelta(days=1))
    assert [s.id for s in h.repo.free_slots([a.id, b.id], window)] == [s_early.id, s_late.id]
    assert h.repo.claim_slot(s_early, h.tag) is True
    assert h.repo.claim_slot(s_early, "someone-else") is False
    assert [s.id for s in h.repo.free_slots([a.id, b.id], window)] == [s_late.id]
    assert h.repo.free_slots([], window) == []

    req = h.repo.save_request(make_request(h))
    booking = Booking(s_early, (f"{h.tag}@example.invalid",), "Advising", "slots_table")
    assert h.repo.save_case(Case("", req.id, None, booking, T0)).id


def test_router_stats_counts_tiers_cost_and_cache(h: Harness) -> None:
    before = h.repo.router_stats()
    req = h.repo.save_request(make_request(h))
    h.repo.save_prediction(make_prediction(req.id, tier=Tier.TIER0))
    h.repo.save_prediction(make_prediction(req.id, tier=Tier.TIER1))
    h.llm_call(cached=True)
    h.llm_call(cached=False)
    after = h.repo.router_stats()
    assert after.total == before.total + 2
    assert after.by_tier.get("tier0", 0) == before.by_tier.get("tier0", 0) + 1
    assert after.by_tier.get("tier1", 0) == before.by_tier.get("tier1", 0) + 1
    assert after.cost_usd == pytest.approx(before.cost_usd + 0.0024)
    assert after.cached_calls == before.cached_calls + 1
    assert 0.0 <= after.resolved_tier0_pct <= 100.0
    future = h.repo.router_stats(since=datetime.now(UTC) + timedelta(days=1))
    assert (future.total, future.cached_calls, future.resolved_tier0_pct) == (0, 0, 0.0)
