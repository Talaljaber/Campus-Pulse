"""Staff review endpoints for incident-derived announcement drafts (P10.3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from campuspulse_ai.application.dto import (
    AnnouncementDraftChangeIn,
    AnnouncementDraftOut,
    AnnouncementDraftVersionIn,
)
from campuspulse_ai.application.use_cases.announcement_drafts import AnnouncementDraft, DraftConflict
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()


def _out(draft: AnnouncementDraft) -> AnnouncementDraftOut:
    return AnnouncementDraftOut(
        id=draft.id, incident_id=draft.incident_id, office=draft.office,
        title=draft.title, body=draft.body, status=draft.status,
        version=draft.version, published_announcement_id=draft.published_announcement_id,
    )


@router.api_route(**route_kwargs("announcement_drafts_list"))
def list_drafts(
    request: Request, services: Services,
    caller: Annotated[Principal, Depends(authorize("announcement_drafts_list"))],
) -> list[AnnouncementDraftOut]:
    if services.announcement_drafts is None:
        raise not_wired("announcement drafts")
    return [_out(d) for d in services.announcement_drafts.list(caller)]


@router.api_route(**route_kwargs("announcement_drafts_edit"))
def edit_draft(
    draft_id: str, body: AnnouncementDraftChangeIn, request: Request, services: Services,
    caller: Annotated[Principal, Depends(authorize("announcement_drafts_edit"))],
) -> AnnouncementDraftOut:
    if services.announcement_drafts is None:
        raise not_wired("announcement drafts")
    try:
        return _out(services.announcement_drafts.edit(caller, draft_id, body.version, body.title, body.body))
    except DraftConflict as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.api_route(**route_kwargs("announcement_drafts_publish"))
def publish_draft(
    draft_id: str, body: AnnouncementDraftVersionIn, request: Request, services: Services,
    caller: Annotated[Principal, Depends(authorize("announcement_drafts_publish"))],
) -> AnnouncementDraftOut:
    if services.announcement_drafts is None:
        raise not_wired("announcement drafts")
    if caller.user_id is None:
        raise HTTPException(401, detail="A user session is required.")
    try:
        return _out(services.announcement_drafts.publish(caller, draft_id, body.version, caller.user_id))
    except DraftConflict as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.api_route(**route_kwargs("announcement_drafts_dismiss"))
def dismiss_draft(
    draft_id: str, body: AnnouncementDraftVersionIn, request: Request, services: Services,
    caller: Annotated[Principal, Depends(authorize("announcement_drafts_dismiss"))],
) -> AnnouncementDraftOut:
    if services.announcement_drafts is None:
        raise not_wired("announcement drafts")
    try:
        return _out(services.announcement_drafts.dismiss(caller, draft_id, body.version))
    except DraftConflict as exc:
        raise HTTPException(409, detail=str(exc)) from exc
