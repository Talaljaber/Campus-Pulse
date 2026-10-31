"""Service-role Supabase client for `-m supabase` tests, gated on env vars.

Tests that use it write uniquely-identified rows to the configured project and delete them
in teardown. Never point SUPABASE_TEST_URL at a project holding data you cannot lose.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

URL_ENV = "SUPABASE_TEST_URL"
KEY_ENV = "SUPABASE_TEST_SERVICE_ROLE_KEY"


def supabase_test_client() -> Any:
    """Return a service-role client, or skip the calling test when the env vars are unset."""
    url, key = os.environ.get(URL_ENV), os.environ.get(KEY_ENV)
    if not url or not key:
        pytest.skip(f"{URL_ENV} / {KEY_ENV} not set")
    from supabase import create_client

    return create_client(url, key)
