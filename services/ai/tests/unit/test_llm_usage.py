"""LlmUsageUseCase: maps the provider record, caches successes only, never leaks the key (P10.17)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import SecretStr

from campuspulse_ai.adapters.llm.openrouter_usage import OpenRouterKeyUsage
from campuspulse_ai.application.use_cases.llm_usage import LlmUsageUseCase

T0 = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
RECORD: dict[str, object] = {
    "usage": 3.677452815,
    "usage_daily": 0.045717191,
    "usage_weekly": 0.220012594,
    "usage_monthly": 3.330792815,
    "limit": 7,
    "limit_remaining": 6.954282809,
    "limit_reset": "daily",
    "expires_at": "2026-11-30T12:20:01.314Z",
}


class Clock:
    def __init__(self) -> None:
        self.t = T0

    def now(self) -> datetime:
        return self.t


class Source:
    def __init__(self, answers: list[Mapping[str, object] | None]) -> None:
        self.answers = answers
        self.calls = 0

    def fetch(self) -> Mapping[str, object] | None:
        self.calls += 1
        return self.answers.pop(0)


def test_maps_the_provider_record() -> None:
    out = LlmUsageUseCase(Source([RECORD]), Clock(), ["b/model", "a/model", "b/model"]).run()
    assert out.available
    assert out.spent_today_usd == 0.045717
    assert out.spent_month_usd == 3.330793
    assert out.spent_total_usd == 3.677453
    assert out.limit_usd == 7.0
    assert out.limit_reset == "daily"
    assert out.key_expires_at == datetime(2026, 11, 30, 12, 20, 1, 314000, tzinfo=UTC)
    assert out.models == ["a/model", "b/model"]


def test_without_a_key_everything_is_null() -> None:
    out = LlmUsageUseCase(None, Clock(), []).run()
    assert not out.available
    assert out.spent_today_usd is None and out.limit_usd is None and out.key_expires_at is None


def test_caches_a_success_for_the_ttl_but_not_a_failure() -> None:
    clock = Clock()
    source = Source([None, RECORD, {**RECORD, "usage_daily": 1.0}])
    usage = LlmUsageUseCase(source, clock, [], ttl_s=60)
    assert not usage.run().available  # failure: not cached
    assert usage.run().spent_today_usd == 0.045717
    clock.t = T0 + timedelta(seconds=30)
    assert usage.run().spent_today_usd == 0.045717  # cached
    clock.t = T0 + timedelta(seconds=61)
    assert usage.run().spent_today_usd == 1.0
    assert source.calls == 3


def test_odd_values_become_null() -> None:
    out = LlmUsageUseCase(Source([{"usage": "lots", "limit": None, "expires_at": "soon"}]), Clock(), []).run()
    assert out.available
    assert out.spent_total_usd is None and out.limit_usd is None and out.key_expires_at is None


def test_adapter_keeps_only_documented_fields_and_survives_errors() -> None:
    seen: list[str] = []

    def ok(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        extra = {"label": "sk-or-v1-abc...", "creator_user_id": "u"}
        return httpx.Response(200, json={"data": {**RECORD, **extra}})

    data = OpenRouterKeyUsage(SecretStr("k"), httpx.Client(transport=httpx.MockTransport(ok))).fetch()
    assert data is not None and "label" not in data and "creator_user_id" not in data
    assert data["usage_daily"] == RECORD["usage_daily"]
    assert seen == ["Bearer k"]

    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    failing = httpx.Client(transport=httpx.MockTransport(down))
    assert OpenRouterKeyUsage(SecretStr("k"), failing).fetch() is None
