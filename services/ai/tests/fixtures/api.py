"""The real FastAPI app over `build_test()` (P3.12): HTTP tests without network, models or Supabase.

`api_client(c)` wires the container's use cases into `ApiServices` and returns a `TestClient` with
`AUTH_MODE=trusted_headers` and a test service token. `auth(role, alias, office)` builds the headers.
Settings never read the developer's `.env` here (`_env_file=None`).
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr

from campuspulse_ai.composition.api import ApiServices, HealthInfo
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.values import Tier
from campuspulse_ai.frameworks.fastapi_app import create_app
from fixtures.containers import BackendTestContainer

SERVICE_TOKEN = "test-service-token"
HEALTH = HealthInfo(
    artifact="v1", sha="0" * 64, encoder_loaded=True, sinks=("linear",), llm_tiers=(Tier.TIER1,)
)


def api_settings(**overrides: Any) -> Settings:
    """Settings for API tests: trusted headers, a known token, nothing read from `.env`."""
    values: dict[str, Any] = {
        "ai_service_token": SecretStr(SERVICE_TOKEN),
        "auth_mode": "trusted_headers",
        "sla_scan_minutes": 0,
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def services_for(c: BackendTestContainer, **overrides: Any) -> ApiServices:
    """`ApiServices` with the container's triage and clarify use cases (+ overrides)."""
    fields: dict[str, Any] = {"triage": c.triage, "clarify": c.clarify, "health": HEALTH, **overrides}
    return ApiServices(**fields)


def api_client(
    c: BackendTestContainer | None = None,
    *,
    services: ApiServices | None = None,
    settings: Settings | None = None,
    raise_server_exceptions: bool = True,
    **overrides: Any,
) -> TestClient:
    """A TestClient over the real app. `services` wins over `c` (+ `overrides`)."""
    wired = services if services is not None else services_for(c, **overrides) if c else ApiServices()
    app = create_app(wired, settings or api_settings())
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def auth(
    role: str | None = None,
    alias: str | None = None,
    office: str | None = None,
    *,
    token: str = SERVICE_TOKEN,
) -> dict[str, str]:
    """Service token + trusted identity headers (only the given ones)."""
    headers = {"Authorization": f"Bearer {token}"}
    for name, value in (("X-CP-Role", role), ("X-CP-Alias", alias), ("X-CP-Office", office)):
        if value is not None:
            headers[name] = value
    return headers
