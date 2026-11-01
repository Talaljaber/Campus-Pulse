"""OpenRouter over plain httpx: the shared chat client and the tier-1 `OpenRouterOracle` (P3.3).

`httpx` is imported inside `OpenRouterClient.__init__`, never at module level, so importing this
module (and the offline container) leaves `httpx` out of `sys.modules` (ARCHITECTURE §1.5).
Tier 2 is future work (UD-3): the class supports any tier, but only tier 1 is wired.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from campuspulse_ai.adapters.llm.cost import estimate_cost
from campuspulse_ai.adapters.llm.prompt import PromptTemplate
from campuspulse_ai.adapters.llm.set_constrained import (
    build_messages,
    cache_key,
    parse_answer,
    response_format,
)
from campuspulse_ai.domain.entities import LLMCall, OracleAnswer, OracleContext
from campuspulse_ai.domain.errors import LLMOutputOutOfSet, LLMUnavailable
from campuspulse_ai.domain.ports import CostLogger, ResponseCache
from campuspulse_ai.domain.values import Money, NormalizedRequest, PredictionSet, Tier

if TYPE_CHECKING:
    import httpx

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
# Retry policy from P3.3 step 3 ("5xx after 2 retries -> LLMUnavailable"); a short linear backoff.
MAX_RETRIES = 2
RETRY_BACKOFF_S = 0.5
_SERVER_ERROR = 500
_CLIENT_ERROR = 400
_NO_CREDITS = 402
_RATE_LIMITED = 429
_MS_PER_S = 1000
APP_TITLE = "CampusPulse"


@dataclass(frozen=True, slots=True)
class ChatResult:
    """One successful chat completion: the reply text and its accounting."""

    content: str
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    latency_ms: int
    reasoning_tokens: int = 0


class OpenRouterClient:
    """A minimal OpenRouter `/chat/completions` client over httpx (shared by the oracle and the
    understander).

    Errors (all `LLMUnavailable`): no API key (at construction); a timeout, connection error or 5xx
    after `max_retries` retries; 402 (no credits) and 429 (rate limited), not retried; any other 4xx;
    an error body or a reply with no message. The reply text is returned as-is: validating it is the
    caller's job. `transport` lets tests plug in a mock; `respx` also works without it. The API key is
    held only in the request headers and never logged.
    """

    def __init__(
        self,
        api_key: str,
        *,
        timeout_s: float,
        base_url: str = DEFAULT_BASE_URL,
        max_retries: int = MAX_RETRIES,
        retry_backoff_s: float = RETRY_BACKOFF_S,
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
        provider: Mapping[str, object] | None = None,
        reasoning_off: bool = False,
    ) -> None:
        import httpx  # lazy: keeps httpx out of the offline import graph (§1.5)

        if not api_key:
            raise LLMUnavailable("no OpenRouter API key configured")
        self._httpx = httpx
        self._max_retries = max_retries
        self._provider = dict(provider) if provider else None  # OpenRouter provider preferences (P8.11)
        self._reasoning_off = reasoning_off
        self._backoff_s = retry_backoff_s
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": APP_TITLE},
            transport=transport,
        )

    def chat(
        self,
        model_id: str,
        messages: list[dict[str, str]],
        *,
        params: Mapping[str, object],
        response_format: Mapping[str, object] | None = None,
    ) -> ChatResult:
        """POST one chat completion. `params` are the prompt's pinned request parameters."""
        body: dict[str, object] = {
            "model": model_id,
            "messages": messages,
            **params,
            "usage": {"include": True},
        }
        if self._provider is not None:
            body["provider"] = self._provider
        if self._reasoning_off:
            body["reasoning"] = {"enabled": False}
        if response_format is not None:
            body["response_format"] = dict(response_format)
        httpx = self._httpx
        last_error = "no attempt made"
        for attempt in range(self._max_retries + 1):
            if attempt:
                self._sleep(self._backoff_s * attempt)
            started = time.perf_counter()
            try:
                resp = self._client.post("/chat/completions", json=body)
            except httpx.TimeoutException:
                last_error = "OpenRouter timed out"
                continue
            except httpx.TransportError as exc:
                last_error = f"OpenRouter unreachable ({type(exc).__name__})"
                continue
            latency_ms = int((time.perf_counter() - started) * _MS_PER_S)
            if resp.status_code >= _SERVER_ERROR:
                last_error = f"OpenRouter server error {resp.status_code}"
                continue
            if resp.status_code in (_NO_CREDITS, _RATE_LIMITED):
                raise LLMUnavailable(
                    f"OpenRouter refused the call ({resp.status_code}: credits or rate limit)"
                )
            if resp.status_code >= _CLIENT_ERROR:
                raise LLMUnavailable(f"OpenRouter rejected the request ({resp.status_code})")
            return self._parse(resp, latency_ms)
        raise LLMUnavailable(f"{last_error} after {self._max_retries} retries")

    @staticmethod
    def _parse(resp: httpx.Response, latency_ms: int) -> ChatResult:
        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMUnavailable("OpenRouter returned a non-JSON body") from exc
        if not isinstance(data, dict) or "error" in data:
            raise LLMUnavailable("OpenRouter returned an error body")
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailable("OpenRouter reply has no message") from exc
        content = message.get("content") if isinstance(message, dict) else None
        raw_usage = data.get("usage")
        usage: dict[str, object] = raw_usage if isinstance(raw_usage, dict) else {}
        cost = usage.get("cost")
        tokens_in, tokens_out = usage.get("prompt_tokens"), usage.get("completion_tokens")
        details = usage.get("completion_tokens_details")
        reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else 0
        return ChatResult(
            reasoning_tokens=reasoning if isinstance(reasoning, int) else 0,
            content=content if isinstance(content, str) else "",
            tokens_in=tokens_in if isinstance(tokens_in, int) else 0,
            tokens_out=tokens_out if isinstance(tokens_out, int) else 0,
            cost_usd=float(cost) if isinstance(cost, int | float) else None,
            latency_ms=latency_ms,
        )

    def close(self) -> None:
        self._client.close()


def make_call(
    tier: Tier,
    model_id: str,
    key: str,
    *,
    result: ChatResult | None = None,
    latency_ms: int = 0,
    cached: bool = False,
) -> LLMCall:
    """An `LLMCall` record: a cache hit (cost 0), a failure (no result: zero tokens, cost 0) or a
    completed call (OpenRouter's `usage.cost` if reported, else the price-table estimate).
    `prompt_hash` is the cache key, which identifies model, prompt version, text and sets."""
    tokens_in = result.tokens_in if result else 0
    tokens_out = result.tokens_out if result else 0
    if result is None or cached:
        usd = 0.0
    elif result.cost_usd is not None:
        usd = result.cost_usd
    else:
        usd = estimate_cost(model_id, tokens_in, tokens_out)
    return LLMCall(
        id=str(uuid.uuid4()),
        request_id=None,
        tier=tier,
        model=model_id,
        prompt_hash=key,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=Money(usd),
        latency_ms=result.latency_ms if result else latency_ms,
        cached=cached,
    )


class OpenRouterOracle:
    """The set-constrained LLM tie-breaker (implements `LabelOracle`; ARCHITECTURE §3.9).

    `choose(req, allowed_cat, allowed_pri, context)`:
      1. cache lookup on `cache_key(model_id, prompt.version, req.model_text, sets)`; a hit makes no HTTP
         call and logs `cached=True, cost=0`;
      2. `LLMUnavailable` before any call when `cost.totals()["usd"] >= daily_budget_usd`;
      3. one chat call with the prompt's pinned parameters (temperature 0, top_p 1, seed 42,
         max_tokens 80) and a JSON-schema `response_format` whose enums are the allowed sets;
      4. the cost is logged on every path that reaches the network, including failures (zero tokens);
      5. the reply is validated by `parse_answer`; a label outside a set raises `LLMOutputOutOfSet` and
         is not cached. A valid reply is cached and returned with its `LLMCall`.

    Injection-flagged requests must never reach `choose`; the TriageUseCase enforces that (P3.9).
    `context` is accepted for the port; the neighbours are not sent, so the cache key stays exact.
    """

    def __init__(
        self,
        tier: Tier,
        model_id: str,
        http: OpenRouterClient,
        cache: ResponseCache,
        cost: CostLogger,
        *,
        prompt: PromptTemplate,
        max_input_tokens: int,
        daily_budget_usd: float,
    ) -> None:
        if not model_id:
            raise LLMUnavailable(f"no model id configured for {tier}")
        self.tier = tier
        self.model_id = model_id
        self._http = http
        self._cache = cache
        self._cost = cost
        self._prompt = prompt
        self._max_input_tokens = max_input_tokens
        self._budget = daily_budget_usd
        self._max_reason_words = prompt.limit("max_reason_words")

    @property
    def prompt_version(self) -> str:
        return self._prompt.version

    def choose(
        self,
        req: NormalizedRequest,
        allowed_cat: PredictionSet,
        allowed_pri: PredictionSet,
        context: OracleContext,
    ) -> OracleAnswer:
        key = cache_key(self.model_id, self._prompt.version, req.model_text, allowed_cat, allowed_pri)
        hit = self._cache.get(key)
        if hit is not None:
            try:
                cat, pri, reason = parse_answer(
                    hit, allowed_cat, allowed_pri, max_reason_words=self._max_reason_words
                )
            except LLMOutputOutOfSet:
                pass  # a stale or corrupt entry: ask the model again
            else:
                call = make_call(self.tier, self.model_id, key, cached=True)
                self._cost.log(call)
                return OracleAnswer(category=cat, priority=pri, rationale=reason, call=call)
        if self._cost.totals().get("usd", 0.0) >= self._budget:
            raise LLMUnavailable("the daily LLM budget is spent (LLM_DAILY_BUDGET_USD)")
        messages = build_messages(
            req, allowed_cat, allowed_pri, self._prompt, max_input_tokens=self._max_input_tokens
        )
        started = time.perf_counter()
        try:
            result = self._http.chat(
                self.model_id,
                messages,
                params=self._prompt.request,
                response_format=response_format(allowed_cat, allowed_pri),
            )
        except LLMUnavailable:
            elapsed = int((time.perf_counter() - started) * _MS_PER_S)
            self._cost.log(make_call(self.tier, self.model_id, key, latency_ms=elapsed))
            raise
        call = make_call(self.tier, self.model_id, key, result=result)
        self._cost.log(call)
        cat, pri, reason = parse_answer(
            result.content, allowed_cat, allowed_pri, max_reason_words=self._max_reason_words
        )
        self._cache.put(key, result.content)
        return OracleAnswer(category=cat, priority=pri, rationale=reason, call=call)
