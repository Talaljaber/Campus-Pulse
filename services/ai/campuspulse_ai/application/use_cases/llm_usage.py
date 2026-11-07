"""`GET /v1/admin/usage`: the LLM spend an administrator needs to see (P10.17).

The provider is the source of truth for money: `UsageSource.fetch()` returns its raw key record
(`adapters/llm/openrouter_usage.OpenRouterKeyUsage`), or None when it cannot. Answers are cached for
`ttl_s` so a dashboard refresh never hammers the provider. Read-only; no key or secret is ever returned.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from campuspulse_ai.application import dto
from campuspulse_ai.domain.ports import Clock

DEFAULT_TTL_S = 60.0


class UsageSource(Protocol):
    """The provider's record for the configured key, or None when it cannot be read."""

    def fetch(self) -> Mapping[str, object] | None: ...


def _money(raw: Mapping[str, object], key: str) -> float | None:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return round(float(value), 6)


def _text(raw: Mapping[str, object], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) and value else None


def _when(raw: Mapping[str, object], key: str) -> datetime | None:
    value = _text(raw, key)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class LlmUsageUseCase:
    """`run() -> LlmUsageResponse`. `source` None means no key is configured."""

    def __init__(
        self,
        source: UsageSource | None,
        clock: Clock,
        models: Sequence[str],
        *,
        ttl_s: float = DEFAULT_TTL_S,
    ) -> None:
        self._source = source
        self._clock = clock
        self._models = sorted(set(models))
        self._ttl_s = ttl_s
        self._cached: dto.LlmUsageResponse | None = None

    def run(self) -> dto.LlmUsageResponse:
        now = self._clock.now()
        cached = self._cached
        if cached is not None and (now - cached.checked_at).total_seconds() < self._ttl_s:
            return cached
        raw = self._source.fetch() if self._source is not None else None
        result = self._build(raw, now)
        if raw is not None:  # never cache a failure: the next refresh tries again
            self._cached = result
        return result

    def _build(self, raw: Mapping[str, object] | None, now: datetime) -> dto.LlmUsageResponse:
        if raw is None:
            return dto.LlmUsageResponse(
                available=False,
                spent_today_usd=None,
                spent_week_usd=None,
                spent_month_usd=None,
                spent_total_usd=None,
                limit_usd=None,
                limit_remaining_usd=None,
                limit_reset=None,
                key_expires_at=None,
                models=self._models,
                checked_at=now,
            )
        return dto.LlmUsageResponse(
            available=True,
            spent_today_usd=_money(raw, "usage_daily"),
            spent_week_usd=_money(raw, "usage_weekly"),
            spent_month_usd=_money(raw, "usage_monthly"),
            spent_total_usd=_money(raw, "usage"),
            limit_usd=_money(raw, "limit"),
            limit_remaining_usd=_money(raw, "limit_remaining"),
            limit_reset=_text(raw, "limit_reset"),
            key_expires_at=_when(raw, "expires_at"),
            models=self._models,
            checked_at=now,
        )
