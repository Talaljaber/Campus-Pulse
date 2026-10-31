"""SupabaseIdentityVerifier: who is calling, from the user's Supabase access token (P4.12).

`AUTH_MODE=supabase_jwt`: the Next.js server forwards the signed-in user's access token in
`X-CP-User-JWT`. This adapter
1. asks Supabase Auth to verify it (`GET {SUPABASE_URL}/auth/v1/user`, `apikey` = the service-role
   key, `Authorization: Bearer <user token>`), which also catches expired and revoked sessions;
2. reads that user's `profiles` row with the service role
   (`GET {SUPABASE_URL}/rest/v1/profiles?id=eq.<uid>&select=role,office,alias`).

The role, office and alias come only from `profiles`, never from the token claims or a header.
Results are cached by the token's sha256 for `ttl_s` (`AUTH_CACHE_S`, 60 s), so a token revoked
mid-session is honoured for at most that long. Tokens and keys are never logged.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import SecretStr

from campuspulse_ai.application.use_cases.ports import USER_ROLES, UserIdentity
from campuspulse_ai.domain.errors import StoreError

log = logging.getLogger(__name__)

AUTH_USER_PATH = "/auth/v1/user"
PROFILES_PATH = "/rest/v1/profiles"
PROFILE_COLUMNS = "role,office,alias"
HTTP_OK = 200
HTTP_SERVER_ERROR = 500


class SupabaseIdentityVerifier:
    """`verify(token) -> UserIdentity | None` (`IdentityVerifier`).

    None: Supabase Auth rejects the token (any 4xx), the user has no profile, or the profile role is
    not student/staff/admin. `StoreError`: Supabase is unreachable, times out or answers 5xx, or the
    profiles read is refused (a wrong service-role key: our misconfiguration, not the user's).
    Positive and negative answers are cached; errors are not.
    """

    def __init__(
        self,
        url: str,
        service_key: SecretStr,
        http: httpx.Client,
        *,
        ttl_s: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = url.rstrip("/")
        self._key = service_key
        self._http = http
        self._ttl_s = ttl_s
        self._now = monotonic
        self._cache: dict[str, tuple[float, UserIdentity | None]] = {}

    def __repr__(self) -> str:
        return f"SupabaseIdentityVerifier(url={self._url!r}, service_key={self._key!r})"

    def verify(self, token: str) -> UserIdentity | None:
        key = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = self._now()
        cached = self._cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]
        identity = self._lookup(token)
        self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
        self._cache[key] = (now + self._ttl_s, identity)
        return identity

    def _lookup(self, token: str) -> UserIdentity | None:
        user = self._get(AUTH_USER_PATH, bearer=token, client_error_is_none=True)
        if not isinstance(user, dict) or not isinstance(user.get("id"), str) or not user["id"]:
            return None
        user_id: str = user["id"]
        rows = self._get(
            PROFILES_PATH,
            bearer=self._key.get_secret_value(),
            params={"id": f"eq.{user_id}", "select": PROFILE_COLUMNS},
            client_error_is_none=False,  # a 4xx here is our misconfiguration, not a bad user token
        )
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            log.info("user %s has no profile; treated as unauthenticated", user_id)
            return None
        profile = rows[0]
        role = profile.get("role")
        if role not in USER_ROLES:
            log.warning("user %s has an unknown role %r", user_id, role)
            return None
        return UserIdentity(
            user_id=user_id,
            role=str(role),
            office=_text(profile.get("office")),
            alias=_text(profile.get("alias")),
        )

    def _get(
        self, path: str, *, bearer: str, client_error_is_none: bool, params: dict[str, str] | None = None
    ) -> Any:
        """GET JSON with the service-role `apikey`. A 4xx is None when `client_error_is_none`, else a
        `StoreError`; 5xx, no answer or non-JSON is a `StoreError`."""
        headers = {
            "apikey": self._key.get_secret_value(),
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/json",
        }
        try:
            response = self._http.get(f"{self._url}{path}", headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise StoreError(f"Supabase {path} unreachable: {type(exc).__name__}") from None
        if response.status_code != HTTP_OK:
            if client_error_is_none and response.status_code < HTTP_SERVER_ERROR:
                return None
            raise StoreError(f"Supabase {path} answered {response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise StoreError(f"Supabase {path} answered non-JSON") from None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
