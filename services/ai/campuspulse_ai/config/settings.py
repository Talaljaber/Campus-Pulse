"""Typed runtime settings for the AI service, read from the environment.

Inputs: process env vars (case-insensitive) and an optional ``.env`` file in the
working directory. Errors: ``pydantic.ValidationError`` on a bad type, raised once
when ``Settings()`` is built at startup. Side effects: none.

Secrets are ``SecretStr`` so they never leak through ``repr``. Empty env values
count as unset, so copying ``.env.example`` to ``.env`` works unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

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

    # Supabase (service role is server-side only)
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None

    # Auth between Netlify route handlers and this service
    ai_service_token: SecretStr | None = None

    # Email: Gmail SMTP with an app password (LD-3)
    gmail_smtp_user: str | None = None
    gmail_app_password: SecretStr | None = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    # Comma-separated, lower-cased. Empty rejects every recipient.
    demo_email_allowlist: Annotated[frozenset[str], NoDecode] = frozenset()

    # Linear and outbound sinks
    linear_api_key: SecretStr | None = None
    linear_webhook_secret: SecretStr | None = None
    outbound_webhook_url: str | None = None
    outbound_webhook_secret: SecretStr | None = None
    enable_sinks: bool = True

    # Background loops
    sla_scan_minutes: int = 5
    incident_window_min: int = 30

    # Artifacts and runtime
    artifact_dir: Path = Path("models/frozen")
    ort_intra_op_threads: int = 4  # Render sets 1 (ARCHITECTURE 3.17)
    campuspulse_root: Path | None = None

    @field_validator("demo_email_allowlist", mode="before")
    @classmethod
    def _split_allowlist(cls, value: object) -> object:
        """Accept ``a@x.com, B@y.com`` and normalise to a lower-cased frozenset."""
        if isinstance(value, str):
            return frozenset(p.strip().lower() for p in value.split(",") if p.strip())
        return value
