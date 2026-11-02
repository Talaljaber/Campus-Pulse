"""JourneyStore contract (P9.3): InMemoryJourneyStore always, SupabaseJourneyStore with keys.

Both must give the same answers: the thread comes back oldest first, hints match by cosine with a
floor and a limit (rows without an embedding never match), and `claim_reminder` is a conditional
update that exactly one caller wins. Supabase rows are tagged per run and deleted in teardown.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import pytest
from fixtures.backend_fakes import make_request, make_ticket
from fixtures.supabase_test import supabase_test_client

from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.adapters.store.journey_inmemory import InMemoryJourneyStore
from campuspulse_ai.application.use_cases.journey_ports import JourneyStore
from campuspulse_ai.domain.entities import Request, Ticket
from campuspulse_ai.domain.journey import ActivityKind, TicketActivity, TicketHint, Visibility
from campuspulse_ai.domain.ports import Repository
from campuspulse_ai.domain.values import RequestStatus, TicketStatus

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
DIM = 384  # ticket_hints.embedding is vector(384)


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class Harness(Protocol):
    repo: Repository
    store: JourneyStore
    tag: str
    can_seed_profiles: bool

    def seed_profile(self, alias: str) -> None: ...
    def cleanup(self) -> None: ...


class InMemoryHarness:
    can_seed_profiles = True

    def __init__(self) -> None:
        repo = InMemoryRepository(UtcClock())
        self._repo = repo
        self.repo = repo
        self.store: JourneyStore = InMemoryJourneyStore(repo)
        self.tag = f"journey-test-{uuid.uuid4().hex[:8]}"

    def seed_profile(self, alias: str) -> None:
        self._repo.add_profile(alias, "student", display_name="Test Student", demo_inbox="x@example.invalid")

    def cleanup(self) -> None:
        pass


class SupabaseHarness:
    """`profiles` rows need an auth user, so the positive contact check is skipped here."""

    can_seed_profiles = False

    def __init__(self) -> None:
        from campuspulse_ai.adapters.store.journey_supabase import SupabaseJourneyStore
        from campuspulse_ai.adapters.store.supabase_store import SupabaseRepository

        self.db: Any = supabase_test_client()
        self.repo = SupabaseRepository(self.db, UtcClock())
        self.store = SupabaseJourneyStore(self.db, UtcClock())
        self.tag = f"journey-test-{uuid.uuid4().hex[:8]}"

    def seed_profile(self, alias: str) -> None:
        raise NotImplementedError

    def cleanup(self) -> None:
        self.db.table("requests").delete().like("alias", f"{self.tag}%").execute()  # cascades to tickets
        self.db.table("ticket_hints").delete().eq("author_alias", self.tag).execute()


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


def seed_ticket(h: Harness, **changes: Any) -> Ticket:
    text = "the portal is down"
    req = h.repo.save_request(
        Request(
            id="",
            alias=f"{h.tag}-student",
            raw_text=text,
            normalized=make_request(text),
            input_mode="text",
            status=RequestStatus.DECIDED,
            created_at=NOW,
        )
    )
    ticket = make_ticket(req.id, sla_due_at=datetime.now(UTC) - timedelta(hours=2))
    return h.repo.save_ticket(dataclasses.replace(ticket, **changes))


def activity(ticket: Ticket, kind: ActivityKind, minutes: int, body: str = "") -> TicketActivity:
    return TicketActivity(
        ticket_id=ticket.id,
        kind=kind,
        actor_role="staff",
        actor_alias="staff-registrar",
        actor_office="registrar",
        body=body,
        created_at=NOW + timedelta(minutes=minutes),
        visibility=Visibility.INTERNAL if kind == ActivityKind.NOTE else Visibility.PUBLIC,
        from_status="new",
        to_status="in_progress",
    )


def vec(*pairs: tuple[int, float]) -> tuple[float, ...]:
    v = [0.0] * DIM
    for i, x in pairs:
        v[i] = x
    return tuple(v)


def hint(
    h: Harness, text: str, embedding: tuple[float, ...] | None, category: str = "IT Support"
) -> TicketHint:
    return TicketHint(
        kind="forward",
        request_text=text,
        corrected_category=category,
        corrected_priority="high",
        embedding=embedding,
        model_category="Registration",
        model_priority="medium",
        author_alias=h.tag,
        author_role="staff",
    )


def test_activity_round_trip_and_order(h: Harness) -> None:
    t, other = seed_ticket(h), seed_ticket(h)
    second = h.store.add_activity(activity(t, ActivityKind.COMMENT, 5, "second"))
    first = h.store.add_activity(activity(t, ActivityKind.CREATED, 0, "first"))
    note = h.store.add_activity(activity(t, ActivityKind.NOTE, 9, "private"))
    h.store.add_activity(activity(other, ActivityKind.COMMENT, 1, "elsewhere"))
    assert first.id and second.id and first.id != second.id
    thread = h.store.activity_for(t.id)
    assert [a.body for a in thread] == ["first", "second", "private"]
    assert thread[0] == first and thread[2] == note
    assert thread[2].visibility == Visibility.INTERNAL and thread[1].visibility == Visibility.PUBLIC
    assert (thread[1].from_status, thread[1].to_status, thread[1].actor_office) == (
        "new",
        "in_progress",
        "registrar",
    )
    assert h.store.activity_for(str(uuid.uuid4())) == []


def test_nearest_hints_by_cosine_with_floor_and_limit(h: Harness) -> None:
    near = h.store.add_hint(hint(h, "near", vec((0, 1.0), (1, 0.1)), "Finance"))
    mid = h.store.add_hint(hint(h, "mid", vec((0, 1.0), (1, 1.0))))
    h.store.add_hint(hint(h, "far", vec((5, 1.0))))
    h.store.add_hint(hint(h, "no embedding", None))
    assert near.id and mid.id
    query = vec((0, 1.0))
    hits = h.store.nearest_hints(query, 5, 0.0)
    assert [x.request_text for x in hits][:2] == ["near", "mid"]
    assert hits[0].sim == pytest.approx(0.995, abs=1e-3) and hits[1].sim == pytest.approx(0.7071, abs=1e-3)
    assert hits[0].hint_id == near.id and (hits[0].corrected_category, hits[0].corrected_priority) == (
        "Finance",
        "high",
    )
    assert (hits[0].model_category, hits[0].model_priority) == ("Registration", "medium")
    assert "no embedding" not in [x.request_text for x in hits]
    assert [x.request_text for x in h.store.nearest_hints(query, 5, 0.85)] == ["near"]
    assert [x.request_text for x in h.store.nearest_hints(query, 1, 0.0)] == ["near"]
    assert h.store.nearest_hints(query, 0, 0.0) == []


def test_contact_for_alias(h: Harness) -> None:
    assert h.store.contact_for_alias(f"{h.tag}-nobody") is None
    assert h.store.contact_for_alias("  ") is None
    if not h.can_seed_profiles:
        pytest.skip("profiles need an auth user")
    alias = f"{h.tag}-student"
    h.seed_profile(alias)
    contact = h.store.contact_for_alias(alias)
    assert contact is not None
    assert (contact.alias, contact.role, contact.display_name, contact.demo_inbox) == (
        alias,
        "student",
        "Test Student",
        "x@example.invalid",
    )


def test_claim_reminder_is_won_by_exactly_one_caller(h: Harness) -> None:
    t = seed_ticket(h)
    now = datetime.now(UTC)
    assert h.store.claim_reminder(t.id, 2, now) is False  # level 2 needs a first reminder
    assert h.store.claim_reminder(t.id, 1, now) is True
    assert h.store.claim_reminder(t.id, 1, now) is False  # a second scan loses
    saved = h.repo.get_ticket(t.id)
    assert saved.reminder_count == 1 and saved.reminder_sent_at is not None
    assert h.store.claim_reminder(t.id, 2, now) is True
    assert h.store.claim_reminder(t.id, 2, now) is False
    assert h.repo.get_ticket(t.id).reminder_count == 2


def test_claim_reminder_needs_an_overdue_running_ticket(h: Harness) -> None:
    now = datetime.now(UTC)
    future = seed_ticket(h, sla_due_at=now + timedelta(hours=1))
    assert h.store.claim_reminder(future.id, 1, now) is False
    solved = seed_ticket(h, status=TicketStatus.SOLVED)
    assert h.store.claim_reminder(solved.id, 1, now) is False
    assert h.store.claim_reminder(str(uuid.uuid4()), 1, now) is False
    assert h.repo.get_ticket(future.id).reminder_count == 0
