"""The student-journey store port (P9.3): the thread, the hints, contacts and the reminder claim.

Implemented by `adapters/store/journey_inmemory.InMemoryJourneyStore` and
`adapters/store/journey_supabase.SupabaseJourneyStore` (service role). Announcements are not here:
they have their own store (P9.5). Errors: `StoreError`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from campuspulse_ai.domain.journey import Contact, HintMatch, TicketActivity, TicketHint


@runtime_checkable
class JourneyStore(Protocol):
    def add_activity(self, a: TicketActivity) -> TicketActivity:
        """Insert one thread row; the returned copy carries the id."""
        ...

    def activity_for(self, ticket_id: str) -> list[TicketActivity]:
        """The ticket's thread, oldest first."""
        ...

    def add_hint(self, h: TicketHint) -> TicketHint:
        """Insert a hint row; the returned copy carries the id."""
        ...

    def nearest_hints(self, embedding: Sequence[float], k: int, min_sim: float) -> list[HintMatch]:
        """The `k` hints most similar (cosine >= `min_sim`) to `embedding`, best first. Rows without an
        embedding never match."""
        ...

    def contact_for_alias(self, alias: str) -> Contact | None:
        """The profile with this alias (role, office, display name, demo inbox), or None."""
        ...

    def claim_reminder(self, ticket_id: str, level: int, now: datetime) -> bool:
        """Conditional update `reminder_count = level, reminder_sent_at = now where reminder_count =
        level - 1 and status in (new, in_progress) and sla_due_at < now`. True iff this call changed the
        row, so two concurrent scans never send the same reminder twice."""
        ...
