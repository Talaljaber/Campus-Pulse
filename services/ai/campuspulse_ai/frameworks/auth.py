"""Service-token auth and caller identity for the `/v1` routes (P3.12).

Every route except `/health`, `/v1/health` and the Linear webhook depends on `authorize(op_id)`:
1. **Service token.** `Authorization: Bearer <AI_SERVICE_TOKEN>`, compared with
   `hmac.compare_digest`. Missing, wrong, or no token configured on the server -> 401
   `unauthenticated` (fail closed).
2. **Caller.** `Principal(user_id, role, alias, office)`, by `Settings.auth_mode`:
   - `trusted_headers` (tests, local dev): `X-CP-Role`, `X-CP-Alias`, `X-CP-Office`; no role header
     means `service`.
   - `supabase_jwt` (production, the default): `X-CP-User-JWT` is verified with Supabase Auth by
     `ApiServices.identity` and the role, office and alias come from the user's `profiles` row
     (P4.12); the `X-CP-Role/Alias/Office` headers are ignored. No user token means `service` (a
     server script holding only the service token). A bad token is 401.
3. **Role.** A role outside the endpoint's `x-roles` (`api_contract.ENDPOINTS`) -> 403 `forbidden`.

The dependency declares exactly the parameters of the mock app's guard (`PrincipalHeaders` +
`SERVICE_TOKEN_SCHEME`), so both apps export the same OpenAPI document.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials

from campuspulse_ai.application.dto import ErrorCode, PrincipalHeaders, Role
from campuspulse_ai.composition.api import ApiServices
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.frameworks.api_contract import ENDPOINTS_BY_ID, SERVICE_TOKEN_SCHEME
from campuspulse_ai.frameworks.errors import ApiError

ROLE_SERVICE: Role = "service"
USER_ROLES: dict[str, Role] = {"student": "student", "staff": "staff", "admin": "admin"}
"""`profiles.role` values a user token may carry (never `service`)."""


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller of one request.

    `user_id` is the Supabase auth user id (None for the bare service token and in trusted-headers
    mode); `alias` the student alias; `office` the staff office (D-005 code). Satisfies the use cases'
    `Actor` protocol.
    """

    user_id: str | None
    role: Role
    alias: str | None
    office: str | None


SERVICE_PRINCIPAL = Principal(user_id=None, role=ROLE_SERVICE, alias=None, office=None)


def check_service_token(settings: Settings, credentials: HTTPAuthorizationCredentials | None) -> None:
    """Raise 401 unless the bearer token equals `AI_SERVICE_TOKEN` (constant-time comparison)."""
    expected = settings.ai_service_token
    if (
        expected is None
        or credentials is None
        or not hmac.compare_digest(
            credentials.credentials.encode("utf-8"), expected.get_secret_value().encode("utf-8")
        )
    ):
        raise ApiError(ErrorCode.UNAUTHENTICATED, "Missing or invalid service token.")


def resolve_principal(settings: Settings, headers: PrincipalHeaders, services: ApiServices) -> Principal:
    """The caller, per `settings.auth_mode` (see the module docstring).

    `supabase_jwt` errors: no verifier wired -> 503 `store_unavailable`; Supabase unreachable ->
    `StoreError` (503); an invalid or expired token, no profile, or an unknown role -> 401.
    """
    if settings.auth_mode == "trusted_headers":
        return Principal(
            user_id=None,
            role=headers.x_cp_role or ROLE_SERVICE,
            alias=headers.x_cp_alias or None,
            office=headers.x_cp_office or None,
        )
    token = headers.x_cp_user_jwt
    if not token:
        return SERVICE_PRINCIPAL
    if services.identity is None:
        raise ApiError(ErrorCode.STORE_UNAVAILABLE, "User token verification is not configured.")
    user = services.identity.verify(token)
    role = USER_ROLES.get(user.role) if user is not None else None
    if user is None or role is None:
        raise ApiError(ErrorCode.UNAUTHENTICATED, "Invalid or expired user token.")
    return Principal(user_id=user.user_id, role=role, alias=user.alias, office=user.office)


def authorize(op_id: str) -> Callable[..., Principal]:
    """FastAPI dependency for endpoint `op_id`: service token, caller, role check; returns the caller."""
    endpoint = ENDPOINTS_BY_ID[op_id]

    def dependency(
        request: Request,
        principal: Annotated[PrincipalHeaders, Header()],
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(SERVICE_TOKEN_SCHEME)],
    ) -> Principal:
        settings: Settings = request.app.state.settings
        check_service_token(settings, credentials)
        caller = resolve_principal(settings, principal, request.app.state.services)
        if caller.role not in endpoint.roles:
            raise ApiError(ErrorCode.FORBIDDEN, "This role may not use this endpoint.", {"role": caller.role})
        return caller

    return dependency
