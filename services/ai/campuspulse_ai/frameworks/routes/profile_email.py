"""P10 notification email routes. Register the three operation IDs in api_contract."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from campuspulse_ai.application.dto import ProfileEmailIn, ProfileEmailOut
from campuspulse_ai.application.use_cases.profile_email import (
    NotificationEmail,
    ProfileEmailDisabled,
    ProfileEmailRateLimited,
    ProfileEmailService,
)
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize

router = APIRouter()


def _service(request: Request) -> ProfileEmailService:
    service: ProfileEmailService | None = getattr(request.app.state.services, "profile_email", None)
    if service is None:
        from campuspulse_ai.frameworks.errors import not_wired

        raise not_wired("profile email")
    return service


def _user_id(caller: Principal) -> str:
    if caller.user_id is None:
        from campuspulse_ai.application.dto import ErrorCode
        from campuspulse_ai.frameworks.errors import ApiError

        raise ApiError(ErrorCode.UNAUTHENTICATED, "A user session is required.")
    return caller.user_id


def _out(row: NotificationEmail | None, enabled: bool) -> ProfileEmailOut:
    return ProfileEmailOut(
        email=row.email if row else None,
        consented_at=row.consented_at if row else None,
        opt_in_enabled=enabled,
    )


@router.api_route(**route_kwargs("profile_email_get"))
def get_profile_email(
    request: Request, caller: Annotated[Principal, Depends(authorize("profile_email_get"))]
) -> ProfileEmailOut:
    service = _service(request)
    return _out(service.get(_user_id(caller)), service.opt_in_enabled)


@router.api_route(**route_kwargs("profile_email_put"))
def put_profile_email(
    body: ProfileEmailIn,
    request: Request,
    caller: Annotated[Principal, Depends(authorize("profile_email_put"))],
) -> ProfileEmailOut:
    from campuspulse_ai.application.dto import ErrorCode
    from campuspulse_ai.frameworks.errors import ApiError

    service = _service(request)
    try:
        row = service.set(_user_id(caller), body.email, body.consent, datetime.now().astimezone())
    except ProfileEmailDisabled as exc:
        raise ApiError(ErrorCode.STORE_UNAVAILABLE, "Notification email opt-in is disabled.") from exc
    except ProfileEmailRateLimited as exc:
        raise HTTPException(status_code=429, detail="Too many email changes; try again later.") from exc
    return _out(row, service.opt_in_enabled)


@router.api_route(**route_kwargs("profile_email_delete"))
def delete_profile_email(
    request: Request, caller: Annotated[Principal, Depends(authorize("profile_email_delete"))]
) -> ProfileEmailOut:
    service = _service(request)
    service.remove(_user_id(caller))
    return _out(None, service.opt_in_enabled)
