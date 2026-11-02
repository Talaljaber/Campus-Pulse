"""AnnouncementsUseCase (P9.5): staff and admins post and archive announcements.

Staff post for their own office only (an explicit other office is `Unauthorized` -> 403); admins post
for any office or campus-wide (`office` None). Archive: staff of that office, or an admin. Reads are
done by the browser under RLS, so there is no list method here.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection

from campuspulse_ai.application.use_cases.announcement_ports import AnnouncementStore
from campuspulse_ai.application.use_cases.ports import Actor
from campuspulse_ai.domain.announcements import (
    ANNOUNCEMENT_KINDS,
    BODY_MAX,
    TITLE_MAX,
    Announcement,
    NewAnnouncement,
)
from campuspulse_ai.domain.errors import InvalidInput, Unauthorized
from campuspulse_ai.domain.ports import Clock

ROLE_STAFF = "staff"
ROLE_ADMIN = "admin"


class AnnouncementsUseCase:
    """`create(actor, cmd, created_by)` and `archive(actor, id)` (module docstring)."""

    def __init__(self, store: AnnouncementStore, clock: Clock, offices: Collection[str]) -> None:
        self._store = store
        self._clock = clock
        self._offices = tuple(offices)

    def create(self, actor: Actor, cmd: NewAnnouncement, created_by: str | None = None) -> Announcement:
        office = self._office_for(actor, cmd.office)
        title, body = cmd.title.strip(), cmd.body.strip()
        if not 1 <= len(title) <= TITLE_MAX:
            raise InvalidInput(f"title must have 1 to {TITLE_MAX} characters")
        if not 1 <= len(body) <= BODY_MAX:
            raise InvalidInput(f"body must have 1 to {BODY_MAX} characters")
        if cmd.kind not in ANNOUNCEMENT_KINDS:
            raise InvalidInput(f"kind must be one of {list(ANNOUNCEMENT_KINDS)}")
        now = self._clock.now()
        starts_at = cmd.starts_at or now
        if cmd.ends_at is not None and cmd.ends_at <= starts_at:
            raise InvalidInput("ends_at must be after starts_at")
        return self._store.save_announcement(
            Announcement(
                id="",
                office=office,
                kind=cmd.kind,
                title=title,
                body=body,
                starts_at=starts_at,
                ends_at=cmd.ends_at,
                created_by=created_by,
                created_at=now,
            )  # fmt: skip
        )

    def archive(self, actor: Actor, announcement_id: str) -> Announcement:
        found = self._store.get_announcement(announcement_id)
        if actor.role != ROLE_ADMIN and not (
            actor.role == ROLE_STAFF and actor.office is not None and actor.office == found.office
        ):
            raise Unauthorized(f"role {actor.role!r} of office {actor.office!r} may not archive this")
        if found.archived_at is not None:
            return found
        return self._store.save_announcement(dataclasses.replace(found, archived_at=self._clock.now()))

    def _office_for(self, actor: Actor, requested: str | None) -> str | None:
        if actor.role == ROLE_ADMIN:
            if requested is not None and requested not in self._offices:
                raise InvalidInput(f"unknown office {requested!r}; expected one of {list(self._offices)}")
            return requested
        if actor.role == ROLE_STAFF and actor.office is not None:
            if requested is not None and requested != actor.office:
                raise Unauthorized("staff may only post for their own office")
            return actor.office
        raise Unauthorized(f"role {actor.role!r} may not post announcements")
