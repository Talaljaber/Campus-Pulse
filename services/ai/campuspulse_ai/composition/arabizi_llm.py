"""Optional LLM Arabizi translation wiring (P2.20, D-025).

Off by default; never part of the scored offline path.

Enabled by `--use-llm` (predict.py) or `LLM_ARABIZI_TRANSLATE=true` (API) together with `OPENROUTER_API_KEY`.
Without a key the flag is ignored with a warning (API) or refused (`--use-llm`, exit 3). The only text sent to
the provider is the student's request text of an Arabizi request (never names, ids or labels).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from campuspulse_ai.adapters.llm.arabizi_translator import LlmArabiziTranslator
from campuspulse_ai.adapters.llm.cache_sqlite import SqliteCache
from campuspulse_ai.adapters.llm.cached_chat import CachedChat
from campuspulse_ai.adapters.llm.cost import InMemoryCostLogger
from campuspulse_ai.adapters.llm.openrouter import OpenRouterClient
from campuspulse_ai.adapters.models.llm_arabizi_encoder import LlmArabiziEncoder
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.ports import CostLogger, ResponseCache, SentenceEncoder

log = logging.getLogger(__name__)

DEFAULT_CACHE = Path(".cache/llm_arabizi.sqlite")


def llm_arabizi_requested(settings: Settings, use_llm: bool) -> bool:
    return use_llm or settings.llm_arabizi_translate


def has_key(settings: Settings) -> bool:
    key = settings.openrouter_api_key
    return key is not None and bool(key.get_secret_value())


def make_llm_arabizi_translator(
    settings: Settings,
    *,
    cache: ResponseCache | None = None,
    cost: CostLogger | None = None,
    context: Callable[[str], Sequence[str]] | None = None,
) -> LlmArabiziTranslator:
    """Translator over OpenRouter with the pinned model, a short timeout and one retry (needs a key)."""
    key = settings.openrouter_api_key
    assert key is not None  # noqa: S101 - callers check `has_key` first
    client = OpenRouterClient(
        key.get_secret_value(),
        timeout_s=settings.llm_arabizi_timeout_s,
        max_retries=1,
        retry_backoff_s=settings.llm_retry_backoff_s,
        provider=settings.llm_provider_preferences(),
        reasoning_off=settings.llm_reasoning_off,
    )
    chat = CachedChat(
        client,
        settings.llm_model or settings.llm_arabizi_model,
        cache if cache is not None else SqliteCache(settings.llm_arabizi_cache_path),
        cost if cost is not None else InMemoryCostLogger(),
        daily_budget_usd=settings.llm_daily_budget_usd,
    )
    return LlmArabiziTranslator(chat, context=context)


def wrap_llm_arabizi(encoder: SentenceEncoder, settings: Settings) -> SentenceEncoder:
    """`LlmArabiziEncoder` over `encoder` when a key is configured, else `encoder` itself."""
    if not has_key(settings):
        log.warning("LLM Arabizi translation requested but OPENROUTER_API_KEY is not set; staying offline")
        return encoder
    return LlmArabiziEncoder(encoder, make_llm_arabizi_translator(settings))
