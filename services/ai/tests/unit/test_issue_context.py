import json
from typing import Any

from campuspulse_ai.adapters.llm.cache_dict import DictCache
from campuspulse_ai.adapters.llm.cached_chat import CachedChat
from campuspulse_ai.adapters.llm.issue_context import IssueContextLLM
from campuspulse_ai.adapters.llm.openrouter import ChatResult
from campuspulse_ai.application.use_cases.chat_ports import Turn


class ScriptedClient:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[Any] = []

    def chat(self, model_id: str, messages: list[dict[str, str]], **kwargs: Any) -> ChatResult:
        self.calls.append((model_id, messages))
        return ChatResult(content=self.answer, tokens_in=1, tokens_out=1, cost_usd=0.0, latency_ms=1)



def test_preparation_preserves_full_history_and_checks_priority_evidence() -> None:
    messages = [Turn("user", "I cannot log in to e-learning")]
    messages += [Turn("assistant", "Which building?"), Turn("user", "L")] * 6
    messages += [Turn("user", "My exam starts in 20 minutes")]
    raw = json.dumps(
        {
            "classifier_text": "I cannot log in to e-learning; my exam starts in 20 minutes in L.",
            "priority_recommendation": "high",
            "priority_evidence": ["My exam starts in 20 minutes"],
        }
    )
    client = ScriptedClient(raw)
    adapter = IssueContextLLM(CachedChat(client, "test", DictCache()), "prepare")
    result = adapter.prepare(messages, "2026-11-05T10:00:00+03:00")
    assert result is not None and result.priority_recommendation == "high"
    wire = json.loads(client.calls[0][1][1]["content"])
    assert len(wire["messages"]) == 14
    assert wire["messages"][0]["content"] == messages[0].content


def test_fabricated_evidence_is_rejected() -> None:
    client = ScriptedClient(
        json.dumps(
            {
                "classifier_text": "Wifi is down",
                "priority_recommendation": "high",
                "priority_evidence": ["exam now"],
            }
        )
    )
    adapter = IssueContextLLM(CachedChat(client, "test", DictCache()), "prepare")
    assert adapter.prepare([Turn("user", "Wifi is down")], "now") is None


def _prepare_with(duplicate: object, open_numbers: tuple[str, ...]) -> tuple[Any, ScriptedClient]:
    from campuspulse_ai.application.use_cases.issue_context import OpenTicket

    raw = json.dumps(
        {"classifier_text": "e-learning is down", "priority_recommendation": None, "priority_evidence": [],
         "duplicate_of": duplicate}
    )
    client = ScriptedClient(raw)
    adapter = IssueContextLLM(CachedChat(client, "test", DictCache()), "prepare")
    tickets = [OpenTicket(n, "e-learning is not working", "medium", "new") for n in open_numbers]
    return adapter.prepare([Turn("user", "e-learning is down")], "now", tickets), client


def test_the_open_tickets_are_sent_and_a_listed_number_is_accepted() -> None:
    result, client = _prepare_with("B7249E6B", ("B7249E6B", "F7ED0A91"))
    assert result is not None and result.duplicate_of == "B7249E6B"
    wire = json.loads(client.calls[0][1][1]["content"])
    assert [t["number"] for t in wire["open_tickets"]] == ["B7249E6B", "F7ED0A91"]
    assert wire["open_tickets"][0]["priority"] == "medium" and wire["open_tickets"][0]["status"] == "new"


def test_a_number_that_was_not_listed_or_is_not_a_string_is_dropped() -> None:
    for bad in ("DEADBEEF", 12345, ["B7249E6B"], ""):
        result, _ = _prepare_with(bad, ("B7249E6B",))
        assert result is not None and result.duplicate_of is None, bad


def test_without_open_tickets_nothing_is_sent_and_no_duplicate_is_possible() -> None:
    result, client = _prepare_with("B7249E6B", ())
    assert result is not None and result.duplicate_of is None
    assert "open_tickets" not in json.loads(client.calls[0][1][1]["content"])
