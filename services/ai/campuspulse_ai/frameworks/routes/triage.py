"""`POST /v1/triage` and `POST /v1/triage/{request_id}/clarify` (P3.12). Routes only: auth, the
caller's alias, the role view; the decisions are in `TriageUseCase` / `ClarifyUseCase`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from campuspulse_ai.application.dto import (
    ClarifyRequest,
    ErrorCode,
    TriageQuery,
    TriageRequest,
    TriageResponse,
)
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import ApiError, not_wired
from campuspulse_ai.frameworks.presenters import triage_view
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()

DEBUG_ROLE = "admin"
"""`?debug=members` (per-model probabilities) is admin-only (P5.16)."""


def student_alias(caller: Principal) -> str | None:
    """The alias a student caller is limited to (None for staff, admin and the service token)."""
    return caller.alias if caller.role == "student" else None


@router.api_route(**route_kwargs("triage"))
def triage(
    body: TriageRequest,
    query: Annotated[TriageQuery, Query()],
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("triage"))],
) -> TriageResponse:
    """Triage one message. The alias comes from the caller when it has one, never from another user's
    body; `?debug=members` needs the admin role."""
    if services.triage is None:
        raise not_wired("triage")
    debug = query.debug == "members"
    if debug and caller.role != DEBUG_ROLE:
        raise ApiError(ErrorCode.FORBIDDEN, "debug=members is for admins only.", {"role": caller.role})
    cmd = body if caller.alias is None else body.model_copy(update={"student_alias": caller.alias})
    return triage_view(services.triage.run(cmd, debug_members=debug), caller.role)


@router.api_route(**route_kwargs("clarify"))
def clarify(
    request_id: str,
    body: ClarifyRequest,
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("clarify"))],
) -> TriageResponse:
    """Answer the pending clarifying question of a request (a student only for their own request)."""
    if services.clarify is None:
        raise not_wired("clarify")
    response = services.clarify.run(request_id, body, caller_alias=student_alias(caller))
    return triage_view(response, caller.role)
