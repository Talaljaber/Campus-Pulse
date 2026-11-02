"""Announcements (P9.5): `POST /v1/announcements` and `POST /v1/announcements/{id}/archive`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from campuspulse_ai.application.dto import AnnouncementIn, AnnouncementOut
from campuspulse_ai.domain.announcements import Announcement, NewAnnouncement
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()


def announcement_out(a: Announcement) -> AnnouncementOut:
    return AnnouncementOut(
        id=a.id, office=a.office, kind=a.kind, title=a.title, body=a.body, starts_at=a.starts_at,
        ends_at=a.ends_at, archived_at=a.archived_at, created_by=a.created_by, created_at=a.created_at,
    )  # fmt: skip


@router.api_route(**route_kwargs("announcement_create"))
def announcement_create(
    body: AnnouncementIn,
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("announcement_create"))],
) -> AnnouncementOut:
    """Post an announcement (staff: own office, admin: any office or campus-wide; the use case checks)."""
    if services.announcements is None:
        raise not_wired("announcements")
    cmd = NewAnnouncement(body.title, body.body, body.kind, body.office, body.starts_at, body.ends_at)
    return announcement_out(services.announcements.create(caller, cmd, caller.user_id))


@router.api_route(**route_kwargs("announcement_archive"))
def announcement_archive(
    announcement_id: str,
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("announcement_archive"))],
) -> AnnouncementOut:
    """Archive an announcement (staff of its office or admin; the use case checks)."""
    if services.announcements is None:
        raise not_wired("announcements")
    return announcement_out(services.announcements.archive(caller, announcement_id))
