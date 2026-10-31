"""P3.3: OpenRouterOracle (set-constrained), the HTTP client, the caches and NullOracle.

Every HTTP call goes through `respx`; an unmatched request fails the test, so nothing reaches the
network. The `tests/fixtures/openrouter/*.json` replies are hand-written in the shape of OpenRouter
chat-completion responses (no API key existed when they were made); replace them with real
recordings later, keeping the file names.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx
from fixtures.backend_fakes import fake_call, make_request

from campuspulse_ai.adapters.llm.cache_dict import DictCache
from campuspulse_ai.adapters.llm.cache_sqlite import SqliteCache
from campuspulse_ai.adapters.llm.cost import InMemoryCostLogger, estimate_cost
from campuspulse_ai.adapters.llm.null import NullOracle
from campuspulse_ai.adapters.llm.openrouter import OpenRouterClient, OpenRouterOracle
from campuspulse_ai.adapters.llm.prompt import PromptTemplate, load_prompt
from campuspulse_ai.adapters.llm.set_constrained import parse_answer
from campuspulse_ai.domain.entities import OracleContext
from campuspulse_ai.domain.errors import InvalidInput, LLMOutputOutOfSet, LLMUnavailable
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.ports import LabelOracle, ResponseCache
from campuspulse_ai.domain.values import Lang, Money, PredictionSet, Tier

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "openrouter"
BASE = "https://openrouter.test/api/v1"
MODEL = "anthropic/claude-haiku-5.5"  # in production this comes only from OPENROUTER_TIER1_MODEL
MAX_TOKENS = 256  # FrozenConfig guards.max_tokens in production
BUDGET = 5.0
CTX = OracleContext(lang=Lang.AR, neighbors=(), prompt_version="v1")
S_CAT = PredictionSet(frozenset({"Registration", "IT Support"}))
S_PRI = PredictionSet(frozenset({"high"}))
TEXT = "مش قادر أسجل مادة CS 201، كل ما أكبس تسجيل بعطيني خطأ واليوم آخر يوم"


def reply(name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def prompt() -> PromptTemplate:
    return load_prompt(ROOT / "config" / "prompts", "oracle", "v1")


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE, assert_all_called=False) as r:
        yield r


def make_oracle(
    prompt: PromptTemplate, cache: ResponseCache | None = None, cost: InMemoryCostLogger | None = None
) -> tuple[OpenRouterOracle, DictCache | ResponseCache, InMemoryCostLogger]:
    http = OpenRouterClient("test-key", timeout_s=1.0, base_url=BASE, sleep=lambda _s: None)
    cache = cache if cache is not None else DictCache()
    cost = cost if cost is not None else InMemoryCostLogger()
    oracle = OpenRouterOracle(
        Tier.TIER1,
        MODEL,
        http,
        cache,
        cost,
        prompt=prompt,
        max_input_tokens=MAX_TOKENS,
        daily_budget_usd=BUDGET,
    )
    return oracle, cache, cost


def test_in_set_answer_with_pinned_request(prompt: PromptTemplate, router: respx.MockRouter) -> None:
    route = router.post("/chat/completions").mock(
        return_value=httpx.Response(200, json=reply("oracle_in_set.json"))
    )
    oracle, _, cost = make_oracle(prompt)
    req = make_request("URGENT: " + TEXT, core=TEXT, lang=Lang.AR)  # the normalizer stripped the wrapper

    answer = oracle.choose(req, S_CAT, S_PRI, CTX)

    assert (answer.category, answer.priority) == (Category.REGISTRATION, Priority.HIGH)
    assert answer.call.tier == Tier.TIER1 and answer.call.model == MODEL and not answer.call.cached
    assert answer.call.cost.usd == pytest.approx(0.0000567) and answer.call.tokens_in == 412
    body = json.loads(route.calls.last.request.content)
    assert body["model"] == MODEL
    assert (body["temperature"], body["top_p"], body["seed"], body["max_tokens"]) == (0, 1, 42, 80)
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["category"]["enum"] == ["Registration", "IT Support"]
    assert schema["properties"]["priority"]["enum"] == ["high"]
    system, user = body["messages"][0]["content"], body["messages"][1]["content"]
    assert "Allowed categories: Registration, IT Support" in system and "Allowed priorities: high" in system
    assert "URGENT" not in user and TEXT in user
    assert route.calls.last.request.headers["Authorization"] == "Bearer test-key"
    assert cost.totals() == {"usd": pytest.approx(0.0000567), "calls": 1.0, "cached": 0.0}


def test_out_of_set_answer_raises_and_is_not_cached(prompt: PromptTemplate, router: respx.MockRouter) -> None:
    router.post("/chat/completions").mock(
        return_value=httpx.Response(200, json=reply("oracle_out_of_set.json"))
    )
    oracle, cache, cost = make_oracle(prompt)
    with pytest.raises(LLMOutputOutOfSet):
        oracle.choose(make_request(TEXT, lang=Lang.AR), S_CAT, S_PRI, CTX)
    assert isinstance(cache, DictCache) and cache.data == {}
    assert cost.totals()["calls"] == 1.0 and cost.totals()["usd"] > 0  # the failed call is still costed


def test_cache_hit_makes_no_http_call(prompt: PromptTemplate, router: respx.MockRouter) -> None:
    route = router.post("/chat/completions").mock(
        return_value=httpx.Response(200, json=reply("oracle_in_set.json"))
    )
    oracle, _, cost = make_oracle(prompt)
    req = make_request(TEXT, lang=Lang.AR)
    first = oracle.choose(req, S_CAT, S_PRI, CTX)
    second = oracle.choose(req, S_CAT, S_PRI, CTX)
    assert route.call_count == 1
    assert (second.category, second.priority) == (first.category, first.priority)
    assert second.call.cached and second.call.cost.usd == 0.0
    assert cost.totals()["calls"] == 2.0 and cost.totals()["cached"] == 1.0
    # A different allowed set is a different cache key, so it calls the model again.
    oracle.choose(req, PredictionSet(frozenset({"Registration", "Finance"})), S_PRI, CTX)
    assert route.call_count == 2


def test_server_error_after_retries_is_unavailable_and_costed(
    prompt: PromptTemplate, router: respx.MockRouter
) -> None:
    route = router.post("/chat/completions").mock(return_value=httpx.Response(500))
    oracle, _, cost = make_oracle(prompt)
    with pytest.raises(LLMUnavailable, match="after 2 retries"):
        oracle.choose(make_request(TEXT), S_CAT, S_PRI, CTX)
    assert route.call_count == 3  # first try + 2 retries
    [call] = cost.calls
    assert (call.tokens_in, call.tokens_out, call.cost.usd, call.cached) == (0, 0, 0.0, False)


@pytest.mark.parametrize(
    ("response", "calls"),
    [
        (httpx.Response(429), 1),
        (httpx.Response(402), 1),
        (httpx.Response(401), 1),
        (httpx.Response(200, json=reply("error_body.json")), 1),
        (httpx.ReadTimeout("slow"), 3),
        (httpx.ConnectError("down"), 3),
    ],
    ids=["429", "402", "401", "error_body", "timeout", "connect"],
)
def test_transport_failures_are_unavailable(
    prompt: PromptTemplate, router: respx.MockRouter, response: httpx.Response | Exception, calls: int
) -> None:
    route = router.post("/chat/completions")
    if isinstance(response, Exception):
        route.mock(side_effect=response)
    else:
        route.mock(return_value=response)
    oracle, _, cost = make_oracle(prompt)
    with pytest.raises(LLMUnavailable):
        oracle.choose(make_request(TEXT), S_CAT, S_PRI, CTX)
    assert route.call_count == calls
    assert cost.totals()["calls"] == 1.0


def test_budget_exceeded_before_the_call(prompt: PromptTemplate, router: respx.MockRouter) -> None:
    route = router.post("/chat/completions").mock(
        return_value=httpx.Response(200, json=reply("oracle_in_set.json"))
    )
    oracle, _, cost = make_oracle(prompt)
    spent = fake_call()
    spent.cost = Money(BUDGET)
    cost.log(spent)
    with pytest.raises(LLMUnavailable, match="budget"):
        oracle.choose(make_request(TEXT), S_CAT, S_PRI, CTX)
    assert route.call_count == 0


def test_missing_usage_cost_uses_the_price_table(prompt: PromptTemplate, router: respx.MockRouter) -> None:
    router.post("/chat/completions").mock(return_value=httpx.Response(200, json=reply("oracle_no_cost.json")))
    oracle, _, _ = make_oracle(prompt)
    answer = oracle.choose(
        make_request("my portal fails in the exam"),
        PredictionSet(frozenset({"IT Support", "Registration"})),
        S_PRI,
        CTX,
    )
    assert answer.category == Category.IT_SUPPORT  # the ```json fence is tolerated
    assert answer.call.cost.usd == pytest.approx(estimate_cost(MODEL, 400, 40))


def test_null_oracle_and_ports() -> None:
    null = NullOracle()
    assert isinstance(null, LabelOracle)
    with pytest.raises(LLMUnavailable):
        null.choose(make_request(TEXT), S_CAT, S_PRI, CTX)
    with pytest.raises(LLMUnavailable):
        OpenRouterClient("", timeout_s=1.0)


def test_no_model_id_and_oracle_port(prompt: PromptTemplate) -> None:
    http = OpenRouterClient("k", timeout_s=1.0, base_url=BASE)
    with pytest.raises(LLMUnavailable):
        OpenRouterOracle(
            Tier.TIER1,
            "",
            http,
            DictCache(),
            InMemoryCostLogger(),
            prompt=prompt,
            max_input_tokens=8,
            daily_budget_usd=1,
        )
    oracle, _, _ = make_oracle(prompt)
    assert isinstance(oracle, LabelOracle)


def test_importing_the_oracle_does_not_import_httpx() -> None:
    code = (
        "import sys, campuspulse_ai.adapters.llm.openrouter, campuspulse_ai.adapters.llm.null; "
        "sys.exit(1 if 'httpx' in sys.modules else 0)"
    )
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0


def test_caches_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "llm.sqlite"
    first = SqliteCache(path)
    assert isinstance(first, ResponseCache) and isinstance(DictCache(), ResponseCache)
    assert first.get("k") is None
    first.put("k", '{"a": "عربي"}')
    first.put("k", '{"a": "b"}')
    first.close()
    second = SqliteCache(path)  # persisted on disk
    assert second.get("k") == '{"a": "b"}'
    second.close()
    d = DictCache()
    d.put("x", "y")
    assert d.get("x") == "y" and d.get("z") is None


def test_parse_answer_is_strict() -> None:
    ok = parse_answer(
        '{"category": "IT Support", "priority": "high", "reason": "a b c"}', S_CAT, S_PRI, max_reason_words=2
    )
    assert ok == (Category.IT_SUPPORT, Priority.HIGH, "a b")
    for bad in (
        "not json",
        "[1, 2]",
        '{"category": "IT Support", "priority": "high", "reason": "r", "extra": 1}',
        '{"category": "IT Support", "priority": "low", "reason": "r"}',
        '{"priority": "high", "reason": "r"}',
    ):
        with pytest.raises(LLMOutputOutOfSet):
            parse_answer(bad, S_CAT, S_PRI, max_reason_words=20)


def test_prompt_truncates_and_rejects_missing_files(prompt: PromptTemplate, router: respx.MockRouter) -> None:
    route = router.post("/chat/completions").mock(
        return_value=httpx.Response(200, json=reply("oracle_in_set.json"))
    )
    http = OpenRouterClient("k", timeout_s=1.0, base_url=BASE)
    oracle = OpenRouterOracle(
        Tier.TIER1,
        MODEL,
        http,
        DictCache(),
        InMemoryCostLogger(),
        prompt=prompt,
        max_input_tokens=3,
        daily_budget_usd=1,
    )
    oracle.choose(make_request("one two three four five"), S_CAT, S_PRI, CTX)
    user = json.loads(route.calls.last.request.content)["messages"][1]["content"]
    assert "one two three" in user and "four" not in user
    with pytest.raises(InvalidInput):
        load_prompt(ROOT / "config" / "prompts", "oracle", "v9")
