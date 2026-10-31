"""Keeps `.env.example` and `Settings` in sync and free of secret values."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from campuspulse_ai.config.settings import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[4] / ".env.example"
LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=([^#\n]*?)\s*(?:#\s*scope:\s*(ai|web|cli).*)?$")


def _entries() -> list[tuple[str, str, str | None]]:
    out = []
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if raw.startswith("#") or not raw.strip():
            continue
        m = LINE.match(raw)
        assert m, f"unparseable line: {raw!r}"
        out.append((m[1], m[2], m[3]))
    return out


def test_every_settings_field_documented() -> None:
    documented = {name for name, _, scope in _entries() if scope == "ai"}
    missing = {f.upper() for f in Settings.model_fields} - documented
    assert not missing, f"fields missing from .env.example: {sorted(missing)}"


def test_every_ai_scoped_var_is_a_field() -> None:
    fields = {f.upper() for f in Settings.model_fields}
    extra = {name for name, _, scope in _entries() if scope == "ai"} - fields
    assert not extra, f"ai-scoped vars with no Settings field: {sorted(extra)}"
    assert all(scope for _, _, scope in _entries()), "every line needs a scope comment"


def test_defaults_build_with_empty_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name, _, _ in _entries():
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no stray .env
    s = Settings()
    assert s.enable_llm is False
    assert s.demo_email_allowlist == frozenset()
    assert s.smtp_host == "smtp.gmail.com" and s.smtp_port == 587
    assert s.openrouter_tier2_model is None
    monkeypatch.setenv("DEMO_EMAIL_ALLOWLIST", " A@x.com, b@y.com ,")
    assert Settings().demo_email_allowlist == frozenset({"a@x.com", "b@y.com"})


def test_example_contains_no_secret_values() -> None:
    for name, value, _ in _entries():
        if re.search(r"(_KEY|_SECRET|_PASSWORD|_TOKEN)$", name):
            assert value == "", f"{name} must be empty in .env.example"
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for prefix in ("sk-", "eyJ", "re_"):
        assert prefix not in text, f"secret-looking prefix {prefix!r} in .env.example"
