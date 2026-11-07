"""OpenRouter's record of the configured key (`GET https://openrouter.ai/api/v1/key`), for the admin
spend view (P10.17). Only the documented numeric and date fields are passed on; the key's label and ids
are dropped. Any HTTP or JSON failure returns None, so the dashboard shows "unavailable" instead of
failing.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

import httpx
from pydantic import SecretStr

log = logging.getLogger(__name__)

KEY_URL = "https://openrouter.ai/api/v1/key"
FIELDS = (
    "usage",
    "usage_daily",
    "usage_weekly",
    "usage_monthly",
    "limit",
    "limit_remaining",
    "limit_reset",
    "expires_at",
)


class OpenRouterKeyUsage:
    """`UsageSource` for OpenRouter (`application/use_cases/llm_usage.py`)."""

    def __init__(self, api_key: SecretStr, client: httpx.Client) -> None:
        self._api_key = api_key
        self._client = client

    def fetch(self) -> Mapping[str, object] | None:
        try:
            response = self._client.get(
                KEY_URL, headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"}
            )
            response.raise_for_status()
            data = response.json().get("data")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            log.warning("openrouter key usage unavailable: %s", type(exc).__name__)
            return None
        if not isinstance(data, dict):
            return None
        return {k: data[k] for k in FIELDS if k in data}
