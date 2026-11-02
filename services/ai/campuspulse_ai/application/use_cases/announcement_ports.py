"""The AnnouncementStore port (P9.5): persistence of announcements, separate from the Repository."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from campuspulse_ai.domain.announcements import Announcement


class AnnouncementStore(Protocol):
    """impls: InMemoryAnnouncementStore, SupabaseAnnouncementStore. Failures raise `StoreError`."""

    def save_announcement(self, a: Announcement) -> Announcement:
        """Upsert by id (an empty id gets a fresh UUID); returns the saved row."""
        ...

    def get_announcement(self, id: str) -> Announcement:
        """Raises `NotFound` for an unknown id."""
        ...

    def live_announcements(self, now: datetime, limit: int = 20) -> list[Announcement]:
        """Not archived, `starts_at <= now`, `ends_at` null or after `now`; newest `starts_at` first."""
        ...
