"""P4.12: auth on every route. The service token guards everything but `/health` and the webhook, roles
follow `api_contract` x-roles, and in `supabase_jwt` mode the role comes only from `profiles`."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from fixtures.api import api_client, api_settings, auth
from fixtures.containers import BackendTestContainer, build_test

from campuspulse_ai.application.use_cases.ports import UserIdentity
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.errors import StoreError
from campuspulse_ai.frameworks.api_contract import ENDPOINTS, EndpointDoc

PROTECTED = [e for e in ENDPOINTS if e.auth == "service_token"]
TEXT = "wifi is down in the library"


def concrete(path: str) -> str:
    return path.replace("{request_id}", "r-1").replace("{ticket_id}", "t-1").replace("{incident_id}", "i-1")


@pytest.mark.parametrize("endpoint", PROTECTED, ids=[e.op_id for e in PROTECTED])
def test_missing_service_token_is_401_on_every_protected_route(endpoint: EndpointDoc) -> None:
    client = api_client(build_test())
    r = client.request(endpoint.method, concrete(endpoint.path), headers={"X-CP-Role": "admin"})
    assert r.status_code == 401, (endpoint.op_id, r.text)
    assert r.json()["error"]["code"] == "unauthenticated"


def test_only_health_and_the_webhook_skip_the_service_token() -> None:
    open_routes = {(e.method, e.path) for e in ENDPOINTS if e.auth != "service_token"}
    assert open_routes == {
        ("GET", "/health"),
        ("GET", "/v1/health"),
        ("POST", "/v1/integrations/linear/webhook"),
    }
    client = api_client(build_test())
    assert client.get("/health").status_code == 200
    assert client.post("/v1/integrations/linear/webhook", content=b"{}").status_code in (401, 501)


@pytest.mark.parametrize(
    ("method", "path", "role", "body"),
    [
        ("POST", "/v1/feedback", "student", {"prediction_id": "p-1"}),
        ("POST", "/v1/redteam/run", "staff", {"n": 5}),
        ("GET", "/v1/metrics", "staff", None),
        ("POST", "/v1/tickets/t-1/status", "student", {"status": "closed"}),
        ("POST", "/v1/triage/r-1/clarify", "admin", {"question_id": "q", "option_id": "o"}),
        ("GET", "/v1/incidents", "student", None),
        ("POST", "/v1/admin/reindex", "staff", {}),
    ],
)
def test_roles_outside_x_roles_are_403(method: str, path: str, role: str, body: object) -> None:
    client = api_client(build_test())
    r = client.request(method, path, json=body, headers=auth(role, office="it"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


# --------------------------------------------------------------------------- supabase_jwt mode


@dataclass
class FakeIdentity:
    users: dict[str, UserIdentity] = field(default_factory=dict)
    error: Exception | None = None
    calls: list[str] = field(default_factory=list)

    def verify(self, token: str) -> UserIdentity | None:
        self.calls.append(token)
        if self.error is not None:
            raise self.error
        return self.users.get(token)


STUDENT = UserIdentity(user_id="u-student", role="student", office=None, alias="demo-17")
STAFF = UserIdentity(user_id="u-staff", role="staff", office="it", alias=None)


def jwt_client(identity: FakeIdentity | None) -> tuple[TestClient, BackendTestContainer]:
    c = build_test()
    client = api_client(c, identity=identity, settings=api_settings(auth_mode="supabase_jwt"))
    return client, c


def test_role_and_alias_come_from_the_profile_not_from_headers() -> None:
    identity = FakeIdentity({"jwt-student": STUDENT})
    client, c = jwt_client(identity)
    spoof = {**auth("admin", "demo-99", "it"), "X-CP-User-JWT": "jwt-student"}
    assert client.get("/v1/metrics", headers=spoof).status_code == 403
    r = client.post("/v1/triage", json={"text": TEXT, "student_alias": "demo-55"}, headers=spoof)
    assert r.status_code == 200
    assert c.repo.get_request(r.json()["request_id"]).alias == "demo-17"
    assert identity.calls == ["jwt-student", "jwt-student"]


def test_staff_profile_reaches_staff_routes() -> None:
    client, _ = jwt_client(FakeIdentity({"jwt-staff": STAFF}))
    headers = {**auth(), "X-CP-User-JWT": "jwt-staff"}
    r = client.post("/v1/feedback", json={"prediction_id": "p-1"}, headers=headers)
    assert r.status_code == 501  # past auth and the role check; P3.11 is not wired here


def test_bad_token_is_401_and_no_token_is_the_service_role() -> None:
    client, _ = jwt_client(FakeIdentity({"jwt-staff": STAFF}))
    bad = client.post("/v1/triage", json={"text": TEXT}, headers={**auth(), "X-CP-User-JWT": "forged"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "unauthenticated"
    # Without a user token the caller is the service token; X-CP-Role is ignored in this mode.
    assert client.get("/v1/metrics", headers=auth("admin")).status_code == 403
    assert client.post("/v1/triage", json={"text": TEXT}, headers=auth("admin")).status_code == 200


def test_unknown_profile_role_is_401() -> None:
    odd = UserIdentity(user_id="u-x", role="superuser", office=None, alias=None)
    client, _ = jwt_client(FakeIdentity({"jwt-x": odd}))
    r = client.post("/v1/triage", json={"text": TEXT}, headers={**auth(), "X-CP-User-JWT": "jwt-x"})
    assert r.status_code == 401


def test_supabase_down_or_no_verifier_is_503() -> None:
    down, _ = jwt_client(FakeIdentity(error=StoreError("auth endpoint timed out")))
    headers = {**auth(), "X-CP-User-JWT": "jwt-student"}
    r = down.post("/v1/triage", json={"text": TEXT}, headers=headers)
    assert r.status_code == 503 and r.json()["error"]["code"] == "store_unavailable"
    unwired, _ = jwt_client(None)
    assert unwired.post("/v1/triage", json={"text": TEXT}, headers=headers).status_code == 503


def test_production_default_is_supabase_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API tests opt into trusted headers explicitly; an unconfigured deployment never does."""
    monkeypatch.delenv("AUTH_MODE", raising=False)
    assert Settings(_env_file=None).auth_mode == "supabase_jwt"  # type: ignore[call-arg]
