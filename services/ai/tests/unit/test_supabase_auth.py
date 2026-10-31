"""P4.12: SupabaseIdentityVerifier over a mocked Supabase (httpx.MockTransport; no network)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from campuspulse_ai.adapters.integrations.supabase_auth import SupabaseIdentityVerifier
from campuspulse_ai.application.use_cases.ports import IdentityVerifier, UserIdentity
from campuspulse_ai.domain.errors import StoreError

URL = "https://project.supabase.test"
SERVICE_KEY = "service-role-test-key"
USER_ID = "8f1c2d3e-0000-4000-8000-000000000017"
TTL_S = 60.0


@dataclass
class FakeSupabase:
    """`/auth/v1/user` knows `tokens`; `/rest/v1/profiles` serves `profiles` by user id."""

    tokens: dict[str, str] = field(default_factory=lambda: {"good-jwt": USER_ID})
    profiles: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {USER_ID: {"role": "student", "office": None, "alias": "demo-17"}}
    )
    auth_status: int | None = None
    profiles_status: int = 200
    requests: list[httpx.Request] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["apikey"] == SERVICE_KEY
        bearer = request.headers["Authorization"].removeprefix("Bearer ")
        if request.url.path == "/auth/v1/user":
            if self.auth_status is not None:
                return httpx.Response(self.auth_status, json={"msg": "down"})
            user = self.tokens.get(bearer)
            return httpx.Response(200, json={"id": user}) if user else httpx.Response(401, json={})
        assert request.url.path == "/rest/v1/profiles" and bearer == SERVICE_KEY
        assert request.url.params["select"] == "role,office,alias"
        if self.profiles_status != 200:
            return httpx.Response(self.profiles_status, json={})
        uid = request.url.params["id"].removeprefix("eq.")
        row = self.profiles.get(uid)
        return httpx.Response(200, content=json.dumps([row] if row else []))


@dataclass
class Ticker:
    now: float = 1000.0

    def __call__(self) -> float:
        return self.now


def verifier(fake: FakeSupabase, ticker: Ticker | None = None) -> SupabaseIdentityVerifier:
    http = httpx.Client(transport=httpx.MockTransport(fake.handler))
    return SupabaseIdentityVerifier(
        URL, SecretStr(SERVICE_KEY), http, ttl_s=TTL_S, monotonic=ticker or Ticker()
    )


def test_valid_token_gives_the_profile_identity() -> None:
    v = verifier(FakeSupabase())
    assert isinstance(v, IdentityVerifier)
    assert v.verify("good-jwt") == UserIdentity(USER_ID, "student", None, "demo-17")


def test_rejected_token_no_profile_or_unknown_role_is_none() -> None:
    fake = FakeSupabase()
    assert verifier(fake).verify("forged") is None
    fake.profiles.clear()
    assert verifier(fake).verify("good-jwt") is None
    fake.profiles[USER_ID] = {"role": "root", "office": None, "alias": None}
    assert verifier(fake).verify("good-jwt") is None


@pytest.mark.parametrize("status", [500, 503])
def test_supabase_errors_raise_store_error(status: int) -> None:
    with pytest.raises(StoreError):
        verifier(FakeSupabase(auth_status=status)).verify("good-jwt")


def test_a_refused_profiles_read_is_our_misconfiguration() -> None:
    with pytest.raises(StoreError):
        verifier(FakeSupabase(profiles_status=401)).verify("good-jwt")


def test_network_failure_raises_store_error_without_the_token() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    http = httpx.Client(transport=httpx.MockTransport(boom))
    v = SupabaseIdentityVerifier(URL, SecretStr(SERVICE_KEY), http, ttl_s=TTL_S)
    with pytest.raises(StoreError) as info:
        v.verify("good-jwt")
    assert "good-jwt" not in str(info.value) and SERVICE_KEY not in repr(v)


def test_answers_are_cached_for_the_ttl() -> None:
    fake, ticker = FakeSupabase(), Ticker()
    v = verifier(fake, ticker)
    v.verify("good-jwt")
    v.verify("good-jwt")
    v.verify("forged")
    v.verify("forged")
    assert len(fake.requests) == 3  # user + profile once, the forged token once
    ticker.now += TTL_S + 1
    v.verify("good-jwt")
    assert len(fake.requests) == 5
