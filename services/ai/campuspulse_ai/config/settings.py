"""Typed runtime settings for the AI service, read from the environment.

Inputs: process env vars (case-insensitive) and an optional ``.env`` file in the
working directory. Errors: ``pydantic.ValidationError`` on a bad type, raised once
when ``Settings()`` is built at startup. Side effects: none.

Secrets are ``SecretStr`` so they never leak through ``repr``. Empty env values
count as unset, so copying ``.env.example`` to ``.env`` works unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Every runtime knob of the AI service. See ``.env.example`` (kept in sync by test)."""

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # LLM (tier 1 only; tier 2 stays unset, UD-3). Calls are pinned, temperature 0, cached.
    openrouter_api_key: SecretStr | None = None
    openrouter_tier1_model: str | None = None
    openrouter_tier2_model: str | None = None
    enable_llm: bool = False
    llm_daily_budget_usd: float = 5.0
    llm_timeout_s: float = 20.0
    llm_max_retries: int = 2
    llm_retry_backoff_s: float = 0.5
    llm_cache_path: Path = Path(".cache/llm.sqlite")
    # Optional LLM Arabizi->English translation in front of the encoder (P2.20, D-025). Off by default.
    llm_arabizi_translate: bool = False
    llm_arabizi_model: str = "openai/gpt-4o-mini-2024-07-18"
    llm_arabizi_timeout_s: float = 6.0
    llm_arabizi_cache_path: Path = Path(".cache/llm_arabizi.sqlite")
    # Optional LLM front end: translate Arabic and Arabizi, plus an internal explanation (P7.4, D-050).
    llm_frontend: bool = False
    llm_frontend_config: Path = Path("config/llm_frontend.yaml")
    llm_frontend_model: str | None = None  # overrides the pinned model of the yaml (measurements only)
    llm_frontend_cache_path: Path | None = None  # overrides the yaml cache (scratch caches)

    # Supabase (service role is server-side only)
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    store_timeout_s: float = 30.0  # per PostgREST call of the API (repository, pgvector, memory)

    # Auth between Netlify route handlers and this service. Unset token = every /v1 route answers 401.
    ai_service_token: SecretStr | None = None
    # Who the caller is: the Supabase user JWT + profiles (production, P4.12) or X-CP-* headers
    # (tests and local dev only).
    auth_mode: Literal["trusted_headers", "supabase_jwt"] = "supabase_jwt"
    auth_cache_s: float = 60.0  # a verified user token is trusted this long without re-asking Supabase
    auth_timeout_s: float = 5.0  # per Supabase Auth / profiles call

    # Model lab (P4.12)
    reports_dir: Path = Path("reports")  # model_lab.json from evaluate.py; copied into the image
    batch_max_rows: int = 10_000  # /v1/batch rows per upload
    batch_max_bytes: int = 5_000_000  # /v1/batch upload size

    # Red team (P4.11)
    redteam_max_n: int = 200  # items per POST /v1/redteam/run (and per CLI run)
    # Seed texts to perturb, relative to the repo root: official training rows only (holdouts are refused)
    redteam_seed_csv: Path = Path("data/clean/train_clean.csv")

    # Email: Gmail SMTP with an app password (LD-3)
    gmail_smtp_user: str | None = None
    gmail_app_password: SecretStr | None = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_timeout_s: float = 10.0
    smtp_max_retries: int = 2  # 4xx, disconnects and timeouts only
    smtp_backoff_s: float = 1.0  # exponential: backoff * 2**attempt
    smtp_daily_cap: int = 100  # far below Gmail's 500/day; counted per Amman day in-process
    # Comma-separated, lower-cased. Empty rejects every recipient.
    demo_email_allowlist: Annotated[frozenset[str], NoDecode] = frozenset()
    # Allow-listed demo inboxes the action engine emails (P4.8). Unset = that email is skipped.
    demo_student_inbox: str | None = None  # stands in for every student's email (booking confirmations)
    demo_office_inbox: str | None = None  # safety and transport alerts

    # Linear and outbound sinks
    linear_api_key: SecretStr | None = None
    linear_webhook_secret: SecretStr | None = None
    outbound_webhook_url: str | None = None
    outbound_webhook_secret: SecretStr | None = None
    enable_sinks: bool = True
    sink_retry_max: int = 3  # attempts per sink call, retryable errors only
    sink_retry_base_s: float = 0.5  # exponential: base * 2**(attempt - 1)

    # Anti-gaming thresholds (P3.6); flags only, never a label change
    gaming_min_requests: int = 5
    gaming_claim_ratio: float = 0.8
    gaming_high_ratio_max: float = 0.2

    # Hybrid advisor routing (UD-13)
    review_fallback_office: str = "academic"  # queue of an unsure request whose student has no advisor
    review_list_limit: int = 50  # GET /v1/reviews items per call
    review_email_advisor: bool = True  # also email the advisor's allow-listed demo inbox on assignment

    # Background loops
    sla_scan_minutes: int = 5
    incident_window_min: int = 30

    # Artifacts and runtime
    artifact_dir: Path = Path("models/frozen")
    ort_intra_op_threads: int = 4  # Render sets 1 (ARCHITECTURE 3.17)
    # ONNX Runtime without the CPU arena, memory patterns and weight pre-packing: ~15 MB less RSS,
    # identical vectors (P4.13)
    ort_low_memory: bool = True
    # In-process cache of one live-memory neighbour query (the kNN category and priority heads ask
    # the same question per request); 0 disables it
    memory_query_cache_s: float = 2.0
    campuspulse_root: Path | None = None

    @field_validator("demo_email_allowlist", mode="before")
    @classmethod
    def _split_allowlist(cls, value: object) -> object:
        """Accept ``a@x.com, B@y.com`` and normalise to a lower-cased frozenset."""
        if isinstance(value, str):
            return frozenset(p.strip().lower() for p in value.split(",") if p.strip())
        return value
