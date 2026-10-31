"""LLM cost accounting (ARCHITECTURE §3.9, P3.3).

- `PRICES_PER_MTOK`: the pinned OpenRouter prices (USD per 1 M tokens, input/output) from
  docs/plan/appendix_B_models.md, verified 2026-10-31. They are only a fallback: the cost OpenRouter
  reports in `usage.cost` wins when present. Which model is called comes from env, never from here.
- `InMemoryCostLogger`: the `CostLogger` port for tests, `predict.py --use-llm` and the API process.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Mapping
from datetime import date

from campuspulse_ai.domain.entities import LLMCall
from campuspulse_ai.domain.ports import Clock

TOKENS_PER_PRICE_UNIT = 1_000_000

# model id -> (USD per 1M input tokens, USD per 1M output tokens). Appendix B, 2026-10-31.
PRICES_PER_MTOK: Mapping[str, tuple[float, float]] = {
    "anthropic/claude-haiku-5.5": (0.10, 0.50),  # tier 1
    "deepseek/deepseek-v4.1-flash": (0.045, 0.50),  # tier 1 alternate
    "anthropic/claude-sonnet-5.5": (2.00, 10.00),  # tier 2 (future work, UD-3)
    "google/gemini-3.8-flash": (0.825, 4.125),  # tier 2 alternate
}


def estimate_cost(model_id: str, tokens_in: int, tokens_out: int) -> float:
    """USD for one call from the price table.

    An unknown model id is priced at the most expensive pinned rate, so the daily budget cap errs on
    the safe side instead of counting the call as free.
    """
    price_in, price_out = PRICES_PER_MTOK.get(
        model_id,
        (max(p[0] for p in PRICES_PER_MTOK.values()), max(p[1] for p in PRICES_PER_MTOK.values())),
    )
    return (tokens_in * price_in + tokens_out * price_out) / TOKENS_PER_PRICE_UNIT


class InMemoryCostLogger:
    """Keeps every logged `LLMCall` in memory (implements `CostLogger`). Thread-safe.

    `totals()` returns `{"usd", "calls", "cached"}`. With a `clock`, totals cover only the calls logged
    on the clock's current day (Asia/Amman), which is what the oracle's daily budget check reads;
    without one they cover everything logged. `calls` exposes all calls for tests and the debug summary.
    Never raises.
    """

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: list[tuple[date | None, LLMCall]] = []

    def _today(self) -> date | None:
        return self._clock.now().date() if self._clock is not None else None

    def log(self, call: LLMCall) -> None:
        with self._lock:
            self._entries.append((self._today(), call))

    def totals(self) -> dict[str, float]:
        today = self._today()
        with self._lock:
            calls = [c for d, c in self._entries if today is None or d == today]
        return {
            "usd": math.fsum(c.cost.usd for c in calls),
            "calls": float(len(calls)),
            "cached": float(sum(1 for c in calls if c.cached)),
        }

    @property
    def calls(self) -> list[LLMCall]:
        with self._lock:
            return [c for _, c in self._entries]
