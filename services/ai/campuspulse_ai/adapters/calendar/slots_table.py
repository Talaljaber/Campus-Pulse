"""SlotsTableCalendar: advisor booking over the `advisor_slots` table (P4.7, UD-1).

The default and, for this submission, the only calendar: Google Calendar is future work (UD-3).
Only Academic Support x high books (UD-1). Advisors are fictional seed rows and their `demo_email`s
are developer-owned, allow-listed inboxes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from campuspulse_ai.domain.errors import CalendarUnavailable, StoreError
from campuspulse_ai.domain.policy import RecipientPolicy
from campuspulse_ai.domain.ports import Clock, Repository
from campuspulse_ai.domain.values import Booking, OfficeHours, Slot

PROVIDER = "slots_table"
Search = tuple[tuple[str, ...], tuple[datetime, datetime], OfficeHours]


def in_office_hours(slot: Slot, hours: OfficeHours) -> bool:
    """True when the whole slot lies inside one office-hours day (weekday and times in `hours.tz`)."""
    tz = ZoneInfo(hours.tz)
    start, end = slot.starts_at.astimezone(tz), slot.ends_at.astimezone(tz)
    return (
        start.date() == end.date()
        and start.weekday() in hours.weekdays
        and hours.start <= start.time()
        and end.time() <= hours.end
    )


class SlotsTableCalendar:
    """`CalendarProvider` over `Repository.free_slots` / `claim_slot`.

    - `find_slot(advisor_ids, window, office_hours)`: the earliest free slot of those advisors that
      starts no earlier than `clock.now()` (and `window[0]`), ends by `window[1]` and lies inside
      office hours (Asia/Amman). None when there is none. Ties: the repository order (start, id).
    - `book(slot, attendees, title)`: every attendee must pass the allow-list **before** anything
      is written (`RecipientNotAllowed`; the slot stays free). Then a race-safe `claim_slot`
      (`update ... where booked_by is null`). If another booking won the race, the search that
      found the slot is re-run once and the next slot is claimed; if that also fails, or the slot
      did not come from this instance's `find_slot`, `CalendarUnavailable` is raised.
      `booked_by` is the first attendee (the student's demo inbox), since the port carries no alias.

    Errors: `CalendarUnavailable` (also for any `StoreError`), `RecipientNotAllowed`.
    """

    def __init__(self, repo: Repository, clock: Clock, policy: RecipientPolicy) -> None:
        self._repo = repo
        self._clock = clock
        self._policy = policy
        self._searches: dict[str, Search] = {}

    def find_slot(
        self, advisor_ids: Sequence[str], window: tuple[datetime, datetime], office_hours: OfficeHours
    ) -> Slot | None:
        start, end = max(window[0], self._clock.now()), window[1]
        if not advisor_ids or start >= end:
            return None
        try:
            slots = self._repo.free_slots(advisor_ids, (start, end))
        except StoreError as exc:
            raise CalendarUnavailable(f"advisor slots unavailable: {exc}") from exc
        for slot in slots:
            if in_office_hours(slot, office_hours):
                self._searches[slot.id] = (tuple(advisor_ids), window, office_hours)
                return slot
        return None

    def book(self, slot: Slot, attendees: Sequence[str], title: str) -> Booking:
        for address in attendees:
            self._policy.check(address)  # RecipientNotAllowed before any write
        booked_by = attendees[0] if attendees else title
        if self._claim(slot, booked_by):
            return self._booking(slot, attendees, title)
        search = self._searches.pop(slot.id, None)
        if search is not None:
            retry = self.find_slot(*search)
            if retry is not None and self._claim(retry, booked_by):
                return self._booking(retry, attendees, title)
        raise CalendarUnavailable(f"slot {slot.id} was taken and no other slot could be claimed")

    def _claim(self, slot: Slot, booked_by: str) -> bool:
        try:
            return self._repo.claim_slot(slot, booked_by)
        except StoreError as exc:
            raise CalendarUnavailable(f"could not claim slot {slot.id}: {exc}") from exc

    def _booking(self, slot: Slot, attendees: Sequence[str], title: str) -> Booking:
        self._searches.pop(slot.id, None)
        return Booking(
            slot=slot, attendees=tuple(attendees), title=title, provider=PROVIDER, external_id=slot.id
        )
