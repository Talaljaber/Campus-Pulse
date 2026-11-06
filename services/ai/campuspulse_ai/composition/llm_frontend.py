"""Optional LLM front-end wiring (P7.4, D-050).

Off by default; never part of the scored offline path. Enabled by `--use-llm` (predict.py) or
`LLM_FRONTEND=true` (API) together with `OPENROUTER_API_KEY`. The only text sent to the provider is the
request text (never names, ids or labels). Settings come from `config/llm_frontend.yaml`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from campuspulse_ai.adapters.llm.cache_sqlite import SqliteCache
from campuspulse_ai.adapters.llm.cached_chat import CachedChat
from campuspulse_ai.adapters.llm.cost import InMemoryCostLogger
from campuspulse_ai.adapters.llm.frontend import LlmFrontend
from campuspulse_ai.adapters.llm.openrouter import OpenRouterClient
from campuspulse_ai.adapters.models.llm_cue_floor import Condition, LlmCueFloor, parse_rules
from campuspulse_ai.adapters.models.llm_frontend_encoder import LlmFrontendEncoder
from campuspulse_ai.composition.arabizi_llm import has_key
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.ports import CostLogger, LabelOracle, ResponseCache, SentenceEncoder

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
    cue_floor_enabled: bool = False
    cue_rules: dict[str, dict[str, Condition]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> FrontendCfg:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        cue = dict(raw.get("cue_floor") or {})
        return cls(
            cue_floor_enabled=bool(cue.get("enabled", False)),
            cue_rules=parse_rules(cue.get("rules") or {}),
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


def cue_floor_for(encoder: SentenceEncoder, settings: Settings) -> LlmCueFloor | None:
    """The raise-only LLM-cue floor (P7.9) when `encoder` is the LLM front end and the yaml enables it."""
    if not isinstance(encoder, LlmFrontendEncoder):
        return None
    cfg = FrontendCfg.load(settings.llm_frontend_config)
    if not (cfg.cue_floor_enabled and cfg.cue_rules):
        return None
    return LlmCueFloor(encoder, cfg.cue_rules)


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


def make_batch_oracle(settings: Settings, prompt_version: str, max_input_tokens: int) -> LabelOracle | None:
    """D-058: the tier-1 set-constrained tie-breaker for predict.py's LLM mode, or None when it is off or no
    key is configured. Same adapter as the live app (`composition.online.llm_wiring`); `oracle.prompt_version`
    in the yaml overrides the frozen config's version (the frozen artifact stays unchanged)."""
    if not has_key(settings):
        return None
    raw = yaml.safe_load(Path(settings.llm_frontend_config).read_text(encoding="utf-8")) or {}
    cfg = dict(raw.get("oracle") or {})
    enabled = settings.llm_oracle if settings.llm_oracle is not None else bool(cfg.get("enabled", False))
    model = settings.openrouter_tier1_model or str(cfg.get("model") or "")
    if not enabled or not model:
        return None
    from campuspulse_ai.adapters.llm.openrouter import OpenRouterOracle
    from campuspulse_ai.adapters.llm.prompt import load_prompt
    from campuspulse_ai.config.paths import CONFIG_DIR
    from campuspulse_ai.domain.values import Tier

    key = settings.openrouter_api_key
    assert key is not None  # noqa: S101 - has_key above
    version = settings.llm_oracle_prompt_version or str(cfg.get("prompt_version") or prompt_version)
    http = OpenRouterClient(
        key.get_secret_value(),
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        retry_backoff_s=settings.llm_retry_backoff_s,
        provider=settings.chat_provider_preferences(),  # fallbacks on a 429, as in the chat (D-060)
        reasoning_off=settings.llm_reasoning_off,
    )
    settings.llm_cache_path.parent.mkdir(parents=True, exist_ok=True)
    return OpenRouterOracle(
        Tier.TIER1,
        model,
        http,
        SqliteCache(settings.llm_cache_path),
        InMemoryCostLogger(),
        prompt=load_prompt(CONFIG_DIR / "prompts", "oracle", version),
        max_input_tokens=max_input_tokens,
        daily_budget_usd=settings.llm_daily_budget_usd,
    )


def batch_llm_priority(settings: Settings) -> bool:
    """D-058: whether the tie-breaker may also judge priority on every row (`oracle.priority`, env
    LLM_ORACLE_PRIORITY overrides)."""
    if settings.llm_oracle_priority is not None:
        return settings.llm_oracle_priority
    raw = yaml.safe_load(Path(settings.llm_frontend_config).read_text(encoding="utf-8")) or {}
    return bool(dict(raw.get("oracle") or {}).get("priority", False))


def batch_lower_unflagged_high(settings: Settings) -> bool:
    """D-059: whether the tie-breaker may also correct a model `high` that no safety or deadline floor set
    (`oracle.lower_unflagged_high`, env LLM_ORACLE_LOWER_HIGH overrides)."""
    if settings.llm_oracle_lower_high is not None:
        return settings.llm_oracle_lower_high
    raw = yaml.safe_load(Path(settings.llm_frontend_config).read_text(encoding="utf-8")) or {}
    return bool(dict(raw.get("oracle") or {}).get("lower_unflagged_high", False))


def batch_category_top_k(settings: Settings) -> int:
    """D-060: how many of the model's top categories the tie-breaker may choose from on every row (0 = only
    the calibrated set; `oracle.category_top_k`, env LLM_ORACLE_CATEGORY_TOP_K overrides)."""
    if settings.llm_oracle_category_top_k is not None:
        return max(0, settings.llm_oracle_category_top_k)
    raw = yaml.safe_load(Path(settings.llm_frontend_config).read_text(encoding="utf-8")) or {}
    return max(0, int(dict(raw.get("oracle") or {}).get("category_top_k", 0)))
