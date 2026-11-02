"""Announcements (P9.5): a notice staff post for one office or for the whole campus."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

AnnouncementKind = Literal["info", "outage", "maintenance"]
"""Mirrors the `announcements.kind` check of migration 0013."""
ANNOUNCEMENT_KINDS: tuple[AnnouncementKind, ...] = ("info", "outage", "maintenance")
TITLE_MAX = 120
BODY_MAX = 1000


@dataclass(frozen=True, slots=True)
class Announcement:
    """One `announcements` row. `office` None = campus-wide. Live = not archived, started, not ended."""

    id: str
    office: str | None
    kind: AnnouncementKind
    title: str
    body: str
    starts_at: datetime
    ends_at: datetime | None = None
    archived_at: datetime | None = None
    created_by: str | None = None
    created_at: datetime | None = None

    def is_live(self, now: datetime) -> bool:
        """Archived none, `starts_at <= now`, and `ends_at` unset or after `now`."""
        return (
            self.archived_at is None
            and self.starts_at <= now
            and (self.ends_at is None or self.ends_at > now)
        )


@dataclass(frozen=True, slots=True)
class NewAnnouncement:
    """The fields of `AnnouncementIn`."""

    title: str
    body: str
    kind: AnnouncementKind = "info"
    office: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
