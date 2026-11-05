"""Chat-only OpenRouter retry policy over a fake HTTP transport."""

import httpx
import pytest

from campuspulse_ai.adapters.llm.openrouter import OpenRouterClient
from campuspulse_ai.domain.errors import LLMUnavailable


@pytest.mark.parametrize("first,expected", [(429, 2), (503, 2), (401, 1), (402, 1), (400, 1)])
def test_chat_retry_is_status_scoped(first: int, expected: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(first)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = OpenRouterClient(
        "fake-key", timeout_s=5, max_retries=1, retry_backoff_s=0,
        retry_on_rate_limit=True, total_deadline_s=5, sleep=lambda _: None,
        transport=httpx.MockTransport(handler),
    )
    if expected == 1:
        with pytest.raises(LLMUnavailable):
            client.chat("test-model", [], params={})
    else:
        assert client.chat("test-model", [], params={}).content == "{}"
    assert calls == expected
    client.close()


def test_long_retry_after_falls_back_without_second_call() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "30"})

    client = OpenRouterClient(
        "fake-key", timeout_s=5, max_retries=1, retry_backoff_s=1,
        retry_on_rate_limit=True, total_deadline_s=5, sleep=lambda _: None,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMUnavailable):
        client.chat("test-model", [], params={})
    assert calls == 1
    client.close()
