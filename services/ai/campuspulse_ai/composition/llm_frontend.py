"""Optional LLM front-end wiring (P7.4, D-050).

Off by default; never part of the scored offline path. Enabled by `--use-llm` (predict.py) or
`LLM_FRONTEND=true` (API) together with `OPENROUTER_API_KEY`. The only text sent to the provider is the
request text (never names, ids or labels). Settings come from `config/llm_frontend.yaml`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from campuspulse_ai.adapters.llm.cache_sqlite import SqliteCache
from campuspulse_ai.adapters.llm.cached_chat import CachedChat
from campuspulse_ai.adapters.llm.cost import InMemoryCostLogger
from campuspulse_ai.adapters.llm.frontend import LlmFrontend
from campuspulse_ai.adapters.llm.openrouter import OpenRouterClient
from campuspulse_ai.adapters.models.llm_frontend_encoder import LlmFrontendEncoder
from campuspulse_ai.composition.arabizi_llm import has_key
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.ports import CostLogger, ResponseCache, SentenceEncoder

log = logging.getLogger(__name__)

DEFAULT_CONFIG = Path("config/llm_frontend.yaml")


@dataclass(frozen=True)
class FrontendCfg:
    model: str
    prompt_version: str
    timeout_s: float
    max_retries: int
    max_tokens: int
    reasoning: dict[str, Any]
    workers: int
    explain_english: bool
    cache_path: Path

    @classmethod
    def load(cls, path: Path) -> FrontendCfg:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(
            model=str(raw["model"]),
            prompt_version=str(raw["prompt_version"]),
            timeout_s=float(raw["timeout_s"]),
            max_retries=int(raw["max_retries"]),
            max_tokens=int(raw["max_tokens"]),
            reasoning=dict(raw.get("reasoning") or {}),
            workers=int(raw["workers"]),
            explain_english=bool(raw["explain_english"]),
            cache_path=Path(raw["cache_path"]),
        )


def llm_frontend_requested(settings: Settings, use_llm: bool) -> bool:
    return use_llm or settings.llm_frontend


def make_frontend(
    settings: Settings,
    cfg: FrontendCfg,
    *,
    cache: ResponseCache | None = None,
    cost: CostLogger | None = None,
) -> LlmFrontend:
    key = settings.openrouter_api_key
    assert key is not None  # noqa: S101 - callers check `has_key` first
    cost = cost if cost is not None else InMemoryCostLogger()
    model = settings.llm_frontend_model or cfg.model
    cache_path = settings.llm_frontend_cache_path or cfg.cache_path
    client = OpenRouterClient(
        key.get_secret_value(),
        timeout_s=cfg.timeout_s,
        max_retries=cfg.max_retries,
        retry_backoff_s=settings.llm_retry_backoff_s,
    )
    chat = CachedChat(
        client,
        model,
        cache if cache is not None else SqliteCache(cache_path),
        cost,
        max_tokens=cfg.max_tokens,
        daily_budget_usd=settings.llm_daily_budget_usd,
        extra_params={"reasoning": cfg.reasoning} if cfg.reasoning else None,
    )
    return LlmFrontend(chat, cfg.prompt_version, cost)


def wrap_llm_frontend(
    encoder: SentenceEncoder,
    settings: Settings,
    *,
    cfg: FrontendCfg | None = None,
    cost: CostLogger | None = None,
) -> LlmFrontendEncoder | SentenceEncoder:
    """`LlmFrontendEncoder` over `encoder` when a key is configured, else `encoder` itself."""
    if not has_key(settings):
        log.warning("LLM front end requested but OPENROUTER_API_KEY is not set; staying offline")
        return encoder
    cfg = cfg or FrontendCfg.load(settings.llm_frontend_config)
    frontend = make_frontend(settings, cfg, cost=cost)
    return LlmFrontendEncoder(encoder, frontend, workers=cfg.workers, explain_english=cfg.explain_english)
