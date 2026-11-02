"""InMemoryAnnouncementStore: the AnnouncementStore port for tests and offline wiring (P9.5)."""

from __future__ import annotations

import dataclasses
from datetime import datetime

from campuspulse_ai.adapters.store.inmemory import new_id
from campuspulse_ai.domain.announcements import Announcement
from campuspulse_ai.domain.errors import NotFound


class InMemoryAnnouncementStore:
    """Same semantics as `SupabaseAnnouncementStore` (tests/contracts/test_announcement_store_contract.py)."""

    def __init__(self) -> None:
        self._rows: dict[str, Announcement] = {}

    def save_announcement(self, a: Announcement) -> Announcement:
        saved = dataclasses.replace(a, id=new_id(a.id))
        self._rows[saved.id] = saved
        return saved

    def get_announcement(self, id: str) -> Announcement:
        try:
            return self._rows[id]
        except KeyError:
            raise NotFound(f"announcements {id} not found") from None

    def live_announcements(self, now: datetime, limit: int = 20) -> list[Announcement]:
        live = [a for a in self._rows.values() if a.is_live(now)]
        return sorted(live, key=lambda a: a.starts_at, reverse=True)[:limit]
