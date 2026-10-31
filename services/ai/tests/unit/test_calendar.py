"""P4.7: SlotsTableCalendar (InMemoryRepository always, SupabaseRepository with `-m supabase`) and
FallbackCalendar. Covers: earliest slot, office hours, the window, race-safe double booking, the
attendee allow-list before any write (X4.7, booking part), fallback order and store failures.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any

import pytest
from fixtures.backend_fakes import AMMAN, FakeCalendar, FrozenClock
from fixtures.supabase_test import supabase_test_client

from campuspulse_ai.adapters.calendar.fallback import FallbackCalendar
from campuspulse_ai.adapters.calendar.slots_table import SlotsTableCalendar, in_office_hours
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.domain.errors import CalendarUnavailable, RecipientNotAllowed, StoreError
from campuspulse_ai.domain.policy import RecipientPolicy
from campuspulse_ai.domain.ports import CalendarProvider, Repository
from campuspulse_ai.domain.values import OfficeHours, Slot

# Seed office hours (supabase/seed/02_advisors.sql): Sun-Thu 09:00-15:00 Asia/Amman. Monday = 0.
HOURS = OfficeHours(tz="Asia/Amman", weekdays=(6, 0, 1, 2, 3), start=time(9), end=time(15))
SLOT_MIN = 30
SLA_HIGH_H = 24
NOW = datetime(2026, 11, 5, 9, 5, tzinfo=AMMAN)  # a Thursday
STUDENT = "campuspulse.support+student17@gmail.com"
ADVISOR = "campuspulse.support+adv-rania@gmail.com"
POLICY = RecipientPolicy(frozenset({STUDENT, ADVISOR}))
TITLE = "Advising: CS 201 registration (demo)"


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=AMMAN)


@dataclass
class Harness:
    repo: Repository
    add_advisor: Callable[[str], str]
    add_slot: Callable[[str, datetime], Slot]
    is_booked: Callable[[Slot], bool]
    cleanup: Callable[[], None]


def inmemory() -> Harness:
    repo = InMemoryRepository(FrozenClock(NOW))
    return Harness(
        repo=repo,
        add_advisor=lambda name: repo.add_advisor(name, "academic", ADVISOR).id,
        add_slot=lambda adv, start: repo.add_slot(adv, start, start + timedelta(minutes=SLOT_MIN)),
        is_booked=lambda slot: repo.tables["advisor_slots"][slot.id]["booked_by"] is not None,
        cleanup=lambda: None,
    )


def supabase() -> Harness:
    from campuspulse_ai.adapters.store.supabase_store import SupabaseRepository

    db: Any = supabase_test_client()
    tag = f"calendar-test-{uuid.uuid4().hex[:8]}"

    def add_advisor(name: str) -> str:
        row = {
            "fictional_name": f"{name} (fictional)",
            "department": "academic",
            "demo_email": f"{tag}@example.invalid",
        }
        return str(db.table("advisors").insert(row).execute().data[0]["id"])

    def add_slot(advisor_id: str, start: datetime) -> Slot:
        end = start + timedelta(minutes=SLOT_MIN)
        row = {"advisor_id": advisor_id, "starts_at": start.isoformat(), "ends_at": end.isoformat()}
        data = db.table("advisor_slots").insert(row).execute().data[0]
        return Slot(id=str(data["id"]), advisor_id=advisor_id, starts_at=start, ends_at=end)

    def is_booked(slot: Slot) -> bool:
        rows = db.table("advisor_slots").select("booked_by").eq("id", slot.id).execute().data
        return rows[0]["booked_by"] is not None

    def cleanup() -> None:
        db.table("advisors").delete().eq("demo_email", f"{tag}@example.invalid").execute()  # slots cascade

    return Harness(SupabaseRepository(db, FrozenClock(NOW)), add_advisor, add_slot, is_booked, cleanup)


@pytest.fixture(
    params=[pytest.param(inmemory), pytest.param(supabase, marks=pytest.mark.supabase)],
    ids=["inmemory", "supabase"],
)
def h(request: pytest.FixtureRequest) -> Iterator[Harness]:
    harness: Harness = request.param()
    try:
        yield harness
    finally:
        harness.cleanup()


def calendar(h: Harness) -> SlotsTableCalendar:
    return SlotsTableCalendar(h.repo, FrozenClock(NOW), POLICY)


SLA_WINDOW = (NOW, NOW + timedelta(hours=SLA_HIGH_H))


# --------------------------------------------------------------------------- SlotsTableCalendar


def test_earliest_free_slot_in_office_hours_and_window(h: Harness) -> None:
    rania, omar = h.add_advisor("Rania"), h.add_advisor("Omar")
    h.add_slot(rania, at(5, 8, 30))  # before now and before office hours
    h.add_slot(rania, at(5, 15))  # starts at closing time
    h.add_slot(rania, at(5, 14, 45))  # runs past 15:00
    h.add_slot(rania, at(6, 10))  # Friday
    h.add_slot(omar, at(8, 9))  # Sunday: valid, but outside the 24 h window
    earliest = h.add_slot(omar, at(5, 9, 30))
    h.add_slot(rania, at(5, 10))
    cal = calendar(h)
    assert isinstance(cal, CalendarProvider)
    assert cal.find_slot([rania, omar], SLA_WINDOW, HOURS) == earliest


def test_no_slot_in_the_window_returns_none(h: Harness) -> None:
    rania = h.add_advisor("Rania")
    h.add_slot(rania, at(6, 10))  # Friday
    sunday = h.add_slot(rania, at(8, 9))
    cal = calendar(h)
    assert cal.find_slot([rania], SLA_WINDOW, HOURS) is None
    assert cal.find_slot([rania], (NOW, NOW + timedelta(days=7)), HOURS) == sunday
    assert cal.find_slot([], SLA_WINDOW, HOURS) is None


def test_book_claims_the_slot(h: Harness) -> None:
    rania = h.add_advisor("Rania")
    slot = h.add_slot(rania, at(5, 9, 30))
    cal = calendar(h)
    found = cal.find_slot([rania], SLA_WINDOW, HOURS)
    assert found is not None
    booking = cal.book(found, [STUDENT, ADVISOR], TITLE)
    assert (booking.slot, booking.attendees, booking.provider, booking.external_id) == (
        slot,
        (STUDENT, ADVISOR),
        "slots_table",
        slot.id,
    )
    assert h.is_booked(slot) and cal.find_slot([rania], SLA_WINDOW, HOURS) is None


def test_double_booking_is_prevented(h: Harness) -> None:
    rania = h.add_advisor("Rania")
    first, second = h.add_slot(rania, at(5, 9, 30)), h.add_slot(rania, at(5, 10))
    a, b, c = calendar(h), calendar(h), calendar(h)
    slot_a, slot_b = a.find_slot([rania], SLA_WINDOW, HOURS), b.find_slot([rania], SLA_WINDOW, HOURS)
    assert slot_a == slot_b == first
    assert a.book(first, [STUDENT], TITLE).slot == first
    assert b.book(first, [STUDENT], TITLE).slot == second  # lost the race: the next slot, once
    slot_c = c.find_slot([rania], SLA_WINDOW, HOURS)
    assert slot_c is None
    with pytest.raises(CalendarUnavailable):
        c.book(first, [STUDENT], TITLE)  # taken, and nothing left to retry


def test_non_allow_listed_attendee_is_rejected_before_any_write(h: Harness) -> None:
    rania = h.add_advisor("Rania")
    slot = h.add_slot(rania, at(5, 9, 30))
    cal = calendar(h)
    with pytest.raises(RecipientNotAllowed):
        cal.book(slot, [STUDENT, "real.person@gju.edu.jo"], TITLE)
    assert not h.is_booked(slot)


def test_store_failures_become_calendar_unavailable() -> None:
    class Down(InMemoryRepository):
        def free_slots(self, advisor_ids: Any, window: Any) -> list[Slot]:
            raise StoreError("supabase down")

        def claim_slot(self, slot: Slot, booked_by: str) -> bool:
            raise StoreError("supabase down")

    cal = SlotsTableCalendar(Down(), FrozenClock(NOW), POLICY)
    with pytest.raises(CalendarUnavailable):
        cal.find_slot(["adv"], SLA_WINDOW, HOURS)
    with pytest.raises(CalendarUnavailable):
        cal.book(Slot("s", "adv", at(5, 10), at(5, 10, 30)), [STUDENT], TITLE)


def test_office_hours_use_the_amman_clock() -> None:
    utc_slot = Slot("s", "adv", at(5, 9, 30).astimezone(UTC), at(5, 10).astimezone(UTC))
    assert in_office_hours(utc_slot, HOURS)
    early = Slot("s", "adv", at(5, 8, 30), at(5, 9))
    assert not in_office_hours(early, HOURS)


# --------------------------------------------------------------------------- FallbackCalendar

SLOT_X = Slot("slot-x", "adv-x", at(5, 9, 30), at(5, 10))
SLOT_Y = Slot("slot-y", "adv-y", at(5, 11), at(5, 11, 30))


def test_fallback_skips_an_unavailable_provider() -> None:
    down, up = FakeCalendar(unavailable=True), FakeCalendar(slot=SLOT_Y)
    chain = FallbackCalendar([down, up], POLICY)
    assert isinstance(chain, CalendarProvider)
    found = chain.find_slot(["adv"], SLA_WINDOW, HOURS)
    assert found == SLOT_Y
    chain.book(found, [STUDENT], TITLE)
    assert up.booked and not down.booked and down.finds == 1


def test_fallback_tries_the_next_provider_when_one_has_no_slot() -> None:
    empty, full = FakeCalendar(slot=None), FakeCalendar(slot=SLOT_Y)
    assert FallbackCalendar([empty, full], POLICY).find_slot(["adv"], SLA_WINDOW, HOURS) == SLOT_Y
    assert FallbackCalendar([empty], POLICY).find_slot(["adv"], SLA_WINDOW, HOURS) is None


def test_fallback_books_with_the_finder_then_falls_through() -> None:
    first, second = FakeCalendar(slot=SLOT_X, book_unavailable=True), FakeCalendar(slot=SLOT_Y)
    chain = FallbackCalendar([first, second], POLICY)
    found = chain.find_slot(["adv"], SLA_WINDOW, HOURS)
    assert found == SLOT_X and second.finds == 0  # order: the first provider wins
    booking = chain.book(found, [STUDENT], TITLE)
    assert booking.slot == SLOT_Y and second.booked and not first.booked


def test_fallback_all_unavailable_raises() -> None:
    chain = FallbackCalendar([FakeCalendar(unavailable=True), FakeCalendar(unavailable=True)], POLICY)
    with pytest.raises(CalendarUnavailable):
        chain.find_slot(["adv"], SLA_WINDOW, HOURS)


def test_fallback_never_reaches_a_provider_with_a_real_attendee() -> None:
    provider = FakeCalendar(slot=SLOT_X)
    chain = FallbackCalendar([provider], POLICY)
    found = chain.find_slot(["adv"], SLA_WINDOW, HOURS)
    assert found is not None
    for attendees in ([STUDENT, "real.person@gju.edu.jo"], ["REAL.PERSON@gju.edu.jo"]):
        with pytest.raises(RecipientNotAllowed):
            chain.book(found, attendees, TITLE)
    assert provider.booked == []
    with pytest.raises(RecipientNotAllowed):
        FallbackCalendar([provider], RecipientPolicy(frozenset())).book(SLOT_X, [STUDENT], TITLE)
    assert provider.booked == []
