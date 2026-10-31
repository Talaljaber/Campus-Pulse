"""`LLMUnderstander`: structured understanding written by the tier-1 model (UD-10, P3.3a).

Reuses the P3.3 pieces: `OpenRouterClient`, the `ResponseCache`, the `CostLogger` and versioned prompt
files. Only the online container builds it; `predict.py` never does.
"""

from __future__ import annotations

import hashlib
import logging
import time

from campuspulse_ai.adapters.llm.openrouter import OpenRouterClient, make_call
from campuspulse_ai.adapters.llm.prompt import PromptTemplate
from campuspulse_ai.adapters.llm.set_constrained import truncate_tokens
from campuspulse_ai.adapters.understand.schema import (
    UnderstandLimits,
    decided_labels,
    parse_understanding,
    response_format,
)
from campuspulse_ai.domain.entities import CoreResult
from campuspulse_ai.domain.errors import LLMOutputOutOfSet, LLMUnavailable
from campuspulse_ai.domain.ports import Clock, CostLogger, RequestUnderstander, ResponseCache
from campuspulse_ai.domain.values import ActionType, NormalizedRequest, Tier, Understanding

log = logging.getLogger(__name__)

INJECTION_FLAG = "injection_attempt"
_KEY_SEP = "\x1f"
_MS_PER_S = 1000
_NO_LOCATION = "none"
_NO_ACTION = "none"


class LLMUnderstander:
    """The model-written understanding (implements `RequestUnderstander`).

    `understand(req, decided, action_hint)`:
      1. an injection-flagged request (`injection_attempt` in `decided.flags`) goes straight to the
         `fallback` with no network call;
      2. cache lookup on sha256(model_id ‖ prompt version ‖ text ‖ language ‖ decided labels ‖ action ‖
         today ‖ location); a valid hit makes no HTTP call and logs `cached=True, cost=0`;
      3. the shared daily budget (`daily_budget_usd` against `cost.totals()["usd"]`) is checked before
         the call;
      4. one chat call with the prompt's pinned parameters (temperature 0) and a JSON-schema
         `response_format` whose label enums hold only the decided labels; the cost is logged on every
         networked path, failures included;
      5. the reply goes through `parse_understanding` (schema, limits, unchanged labels, grounded
         entities, reply language). A valid reply is cached and returned with source "llm".
    Any `LLMUnavailable` or `LLMOutputOutOfSet` returns `fallback.understand(...)` (source "rules"); the
    caller marks that with flag `understanding_fallback` (see `application/services/understanding.py`).
    It never raises and never modifies `decided`.
    """

    def __init__(
        self,
        http: OpenRouterClient,
        model_id: str,
        prompt: PromptTemplate,
        cache: ResponseCache,
        cost: CostLogger,
        fallback: RequestUnderstander,
        *,
        clock: Clock,
        max_input_tokens: int,
        daily_budget_usd: float,
        tier: Tier = Tier.TIER1,
    ) -> None:
        if not model_id:
            raise LLMUnavailable("no model id configured for the understander")
        self.model_id = model_id
        self._http = http
        self._prompt = prompt
        self._cache = cache
        self._cost = cost
        self._fallback = fallback
        self._clock = clock
        self._max_input_tokens = max_input_tokens
        self._budget = daily_budget_usd
        self._tier = tier
        self._limits = UnderstandLimits.from_prompt(prompt)

    @property
    def prompt_version(self) -> str:
        return self._prompt.version

    def understand(
        self, req: NormalizedRequest, decided: CoreResult, action_hint: ActionType | None
    ) -> Understanding:
        if INJECTION_FLAG in decided.flags:
            return self._fallback.understand(req, decided, action_hint)
        category, priority = decided_labels(decided)
        today = self._clock.now().date().isoformat()
        location = (
            f"building {req.location.building}" + (f", room {req.location.room}" if req.location.room else "")
            if req.location
            else _NO_LOCATION
        )
        action = action_hint.value if action_hint else _NO_ACTION
        key = hashlib.sha256(
            _KEY_SEP.join(
                [
                    "understand",
                    self.model_id,
                    self._prompt.version,
                    req.core,
                    req.model_text,
                    str(req.lang),
                    str(category),
                    str(priority),
                    action,
                    today,
                    location,
                ]
            ).encode("utf-8")
        ).hexdigest()

        def parse(content: str) -> Understanding:
            return parse_understanding(content, req, category, priority, self._limits, self._prompt.version)

        hit = self._cache.get(key)
        if hit is not None:
            try:
                understanding = parse(hit)
            except LLMOutputOutOfSet:
                pass  # a stale or corrupt entry: ask the model again
            else:
                self._cost.log(make_call(self._tier, self.model_id, key, cached=True))
                return understanding
        if self._cost.totals().get("usd", 0.0) >= self._budget:
            log.info("understanding fell back to rules: daily LLM budget spent")
            return self._fallback.understand(req, decided, action_hint)
        lim = self._limits
        messages = self._prompt.render(
            text=truncate_tokens(req.core, self._max_input_tokens),
            normalized=truncate_tokens(req.model_text, self._max_input_tokens),
            lang=str(req.lang),
            category=str(category),
            priority=str(priority),
            action=action,
            today=today,
            location=location,
            max_title_chars=str(lim.max_title_chars),
            max_reply_chars=str(lim.max_reply_chars),
            max_summary_chars=str(lim.max_summary_chars),
            max_body_chars=str(lim.max_body_chars),
            max_entity_chars=str(lim.max_entity_chars),
        )
        started = time.perf_counter()
        try:
            result = self._http.chat(
                self.model_id,
                messages,
                params=self._prompt.request,
                response_format=response_format(category, priority, lim),
            )
        except LLMUnavailable as exc:
            elapsed = int((time.perf_counter() - started) * _MS_PER_S)
            self._cost.log(make_call(self._tier, self.model_id, key, latency_ms=elapsed))
            log.info("understanding fell back to rules: %s", exc)
            return self._fallback.understand(req, decided, action_hint)
        self._cost.log(make_call(self._tier, self.model_id, key, result=result))
        try:
            understanding = parse(result.content)
        except LLMOutputOutOfSet as exc:
            log.info("understanding fell back to rules: %s", exc)
            return self._fallback.understand(req, decided, action_hint)
        self._cache.put(key, result.content)
        return understanding
