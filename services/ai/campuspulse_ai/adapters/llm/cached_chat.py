"""`CachedChat`: one pinned, cached, never-raising chat call for the optional Arabizi LLM helpers (P2.20).

Every call: cache lookup keyed by (model id, purpose/prompt hash, payload); a miss makes one OpenRouter call
at temperature 0 with the client's timeout and logs an `LLMCall` (cost, tokens, latency). Any failure (no
network, 4xx/5xx, timeout, budget) returns `None`: the caller continues on the offline path, never errors.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Mapping, Sequence
from typing import Protocol

from campuspulse_ai.adapters.llm.openrouter import ChatResult, make_call
from campuspulse_ai.domain.errors import LLMUnavailable
from campuspulse_ai.domain.ports import CostLogger, ResponseCache
from campuspulse_ai.domain.values import Tier

log = logging.getLogger(__name__)
_MS = 1000

PINNED_PARAMS: Mapping[str, object] = {"temperature": 0, "top_p": 1, "seed": 42}


class ChatClient(Protocol):
    def chat(
        self,
        model_id: str,
        messages: list[dict[str, str]],
        *,
        params: Mapping[str, object],
        response_format: Mapping[str, object] | None = None,
    ) -> ChatResult: ...


def prompt_hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


class CachedChat:
    def __init__(
        self,
        client: ChatClient | None,
        model_id: str,
        cache: ResponseCache,
        cost: CostLogger | None = None,
        *,
        max_tokens: int = 160,
        daily_budget_usd: float | None = None,
        extra_params: Mapping[str, object] | None = None,
    ) -> None:
        self._client = client
        self.model_id = model_id
        self._cache = cache
        self._cost = cost
        self._params: dict[str, object] = {
            **PINNED_PARAMS,
            "max_tokens": max_tokens,
            **(extra_params or {}),
        }
        self._budget = daily_budget_usd
        self.cache_hits = 0
        self.failures = 0

    def ask(
        self,
        purpose: str,
        payload: str,
        messages: Sequence[Mapping[str, str]],
        *,
        response_format: Mapping[str, object] | None = None,
    ) -> str | None:
        """The model's reply text, or None on any failure. `purpose` carries the prompt hash."""
        key = hashlib.sha256(
            json.dumps([self.model_id, purpose, payload, sorted(self._params.items())]).encode("utf-8")
        ).hexdigest()
        hit = self._cache.get(key)
        if hit is not None:
            self.cache_hits += 1
            if self._cost is not None:
                self._cost.log(make_call(Tier.TIER1, self.model_id, key, cached=True))
            return hit
        if self._client is None:
            return None
        if self._budget is not None and self._cost is not None and self._cost.totals()["usd"] >= self._budget:
            self.failures += 1
            return None
        started = time.perf_counter()
        try:
            result = self._client.chat(
                self.model_id,
                [dict(m) for m in messages],
                params=self._params,
                response_format=response_format,
            )
        except LLMUnavailable as exc:
            self.failures += 1
            log.warning("llm call failed (%s); falling back to the offline path", exc)
            if self._cost is not None:
                elapsed = int((time.perf_counter() - started) * _MS)
                self._cost.log(make_call(Tier.TIER1, self.model_id, key, latency_ms=elapsed))
            return None
        except Exception as exc:  # a helper must never fail a request
            self.failures += 1
            log.warning("llm call crashed (%s); falling back to the offline path", type(exc).__name__)
            return None
        if self._cost is not None:
            self._cost.log(make_call(Tier.TIER1, self.model_id, key, result=result))
        if not result.content.strip():
            self.failures += 1
            return None
        self._cache.put(key, result.content)
        return result.content
