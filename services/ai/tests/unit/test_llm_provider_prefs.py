"""Provider-agnostic LLM routing settings and the OpenRouter provider preferences (P8.11). No network."""

from __future__ import annotations

import json

import httpx
import pytest

from campuspulse_ai.adapters.llm.openrouter import OpenRouterClient
from campuspulse_ai.config.settings import Settings


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for name in ("LLM_MODEL", "LLM_PROVIDER_ORDER", "LLM_PROVIDER_ALLOW_FALLBACKS",
                 "LLM_PROVIDER_DATA_COLLECTION", "LLM_REASONING_OFF"):
        monkeypatch.delenv(name, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_defaults_deny_data_collection_and_no_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    assert s.llm_model is None
    assert s.llm_provider_preferences() == {"allow_fallbacks": False, "data_collection": "deny"}
    assert s.llm_reasoning_off is True


def test_order_is_parsed_and_kept_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(
        monkeypatch,
        LLM_PROVIDER_ORDER=" deepinfra , together ",
        LLM_PROVIDER_ALLOW_FALLBACKS="true",
        LLM_PROVIDER_DATA_COLLECTION="allow",
        LLM_MODEL="qwen/qwen3.8-flash",
    )
    assert s.llm_model == "qwen/qwen3.8-flash"
    assert s.llm_provider_preferences() == {
        "allow_fallbacks": True, "data_collection": "allow", "order": ["deepinfra", "together"]}


def test_bad_data_collection_value_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        _settings(monkeypatch, LLM_PROVIDER_DATA_COLLECTION="maybe")


def _body(client_kwargs: dict[str, object]) -> dict[str, object]:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        reply = {"choices": [{"message": {"content": "ok"}}],
                 "usage": {"prompt_tokens": 3, "completion_tokens": 2, "cost": 0.0001,
                           "completion_tokens_details": {"reasoning_tokens": 7}}}
        return httpx.Response(200, json=reply)

    client = OpenRouterClient("k", timeout_s=1.0, transport=httpx.MockTransport(handler), **client_kwargs)  # type: ignore[arg-type]
    result = client.chat("m/x", [{"role": "user", "content": "hi"}], params={"temperature": 0})
    assert result.reasoning_tokens == 7
    return seen[0]


def test_client_sends_provider_and_reasoning_when_configured() -> None:
    prefs = {"allow_fallbacks": False, "data_collection": "deny", "order": ["a"]}
    body = _body({"provider": prefs, "reasoning_off": True})
    assert body["provider"] == prefs
    assert body["reasoning"] == {"enabled": False}
    assert body["temperature"] == 0


def test_client_sends_neither_by_default() -> None:
    body = _body({})
    assert "provider" not in body
    assert "reasoning" not in body
