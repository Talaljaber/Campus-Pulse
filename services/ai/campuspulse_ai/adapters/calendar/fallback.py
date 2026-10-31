"""FallbackCalendar: try calendar providers in order (P4.7, ARCHITECTURE §1.4).

Today the chain is `FallbackCalendar([SlotsTableCalendar(...)], policy)`; a future
`GoogleCalendarProvider` (UD-3) would go first. The allow-list check on attendees happens here,
before any provider is asked to book, so every provider is covered (ARCHITECTURE §3.13).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from campuspulse_ai.domain.errors import CalendarUnavailable
from campuspulse_ai.domain.policy import RecipientPolicy
from campuspulse_ai.domain.ports import CalendarProvider
from campuspulse_ai.domain.values import Booking, OfficeHours, Slot

Search = tuple[tuple[str, ...], tuple[datetime, datetime], OfficeHours]


class FallbackCalendar:
    """`CalendarProvider` that falls through `providers` on `CalendarUnavailable`.

    - `find_slot`: asks each provider in order; an unavailable provider or one with no slot passes
      to the next. Returns the first slot found (remembering which provider found it), None when
      none has a slot, and raises `CalendarUnavailable` only when every provider was unavailable.
    - `book`: checks every attendee with `RecipientPolicy` first (`RecipientNotAllowed`, no provider
      is called). Then books with the provider that found the slot; if it is unavailable, the
      search is repeated on the later providers and the first slot found there is booked. Raises
      `CalendarUnavailable` when no provider can book.
    """

    def __init__(self, providers: Sequence[CalendarProvider], policy: RecipientPolicy) -> None:
        if not providers:
            raise ValueError("FallbackCalendar needs at least one provider")
        self._providers = tuple(providers)
        self._policy = policy
        self._found: dict[str, tuple[int, Search]] = {}

    def find_slot(
        self, advisor_ids: Sequence[str], window: tuple[datetime, datetime], office_hours: OfficeHours
    ) -> Slot | None:
        search: Search = (tuple(advisor_ids), window, office_hours)
        slot, unavailable = self._search(search, start=0)
        if slot is None and unavailable == len(self._providers):
            raise CalendarUnavailable("no calendar provider is available")
        return slot

    def book(self, slot: Slot, attendees: Sequence[str], title: str) -> Booking:
        for address in attendees:
            self._policy.check(address)  # RecipientNotAllowed before any provider is called
        found = self._found.pop(slot.id, None)
        if found is None:
            for provider in self._providers:
                try:
                    return provider.book(slot, attendees, title)
                except CalendarUnavailable:
                    continue
            raise CalendarUnavailable(f"no provider could book slot {slot.id}")
        index, search = found
        try:
            return self._providers[index].book(slot, attendees, title)
        except CalendarUnavailable:
            retry, _ = self._search(search, start=index + 1)
            if retry is None:
                raise
            return self.book(retry, attendees, title)

    def _search(self, search: Search, *, start: int) -> tuple[Slot | None, int]:
        unavailable = 0
        for index in range(start, len(self._providers)):
            try:
                slot = self._providers[index].find_slot(*search)
            except CalendarUnavailable:
                unavailable += 1
                continue
            if slot is not None:
                self._found[slot.id] = (index, search)
                return slot, unavailable
        return None, unavailable
