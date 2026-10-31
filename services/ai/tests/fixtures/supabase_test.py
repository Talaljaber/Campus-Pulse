"""Service-role Supabase client for `-m supabase` tests, gated on env vars.

Reads the process env first, then the repo-root `.env` (gitignored). The key is
SUPABASE_TEST_SERVICE_ROLE_KEY, or SUPABASE_SERVICE_ROLE_KEY when SUPABASE_TEST_URL is the same
project as SUPABASE_URL. Tests that use it write uniquely-identified rows and delete them in
teardown. Never point SUPABASE_TEST_URL at a project holding data you cannot lose.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

URL_ENV = "SUPABASE_TEST_URL"
KEY_ENV = "SUPABASE_TEST_SERVICE_ROLE_KEY"
REPO_ROOT = Path(__file__).resolve().parents[4]


def _env() -> dict[str, str]:
    from dotenv import dotenv_values

    values = {k: v for k, v in dotenv_values(REPO_ROOT / ".env").items() if v}
    values.update({k: v for k, v in os.environ.items() if v})
    return values


def supabase_test_settings() -> tuple[str, str]:
    """(url, service-role key) for the test project, or skip the calling test."""
    env = _env()
    url = env.get(URL_ENV, "").rstrip("/")
    key = env.get(KEY_ENV)
    if not key and url and url == env.get("SUPABASE_URL", "").rstrip("/"):
        key = env.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        pytest.skip(f"{URL_ENV} and a service-role key are not set")
    return url, key


def supabase_test_client() -> Any:
    """Return a service-role client, or skip the calling test when the settings are missing."""
    from supabase import create_client

    return create_client(*supabase_test_settings())
