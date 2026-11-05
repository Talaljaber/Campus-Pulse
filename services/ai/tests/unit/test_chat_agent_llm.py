"""P9.8: the chat agent's LLM adapter over a scripted client (prompt, JSON parsing, pinned params, cache)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from campuspulse_ai.adapters.llm.cache_dict import DictCache
from campuspulse_ai.adapters.llm.cached_chat import CachedChat
from campuspulse_ai.adapters.llm.chat_agent import ChatAgentLLM, parse_phrase, parse_reply
from campuspulse_ai.adapters.llm.openrouter import ChatResult
from campuspulse_ai.application.use_cases.chat_ports import ChatContext, GroundingSource, ProposalFacts, Turn
from campuspulse_ai.composition.chat import load_chat_yaml
from campuspulse_ai.config.paths import REPO_ROOT
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.errors import LLMUnavailable

PROMPT = (REPO_ROOT / "config" / "prompts" / "chat_agent_v2.md").read_text(encoding="utf-8")


class ScriptedClient:
    """An OpenRouter-like client: answers from `answers` in order and records every call."""

    def __init__(self, *answers: str | Exception) -> None:
        self.answers = list(answers)
        self.calls: list[
            tuple[str, list[dict[str, str]], Mapping[str, object], Mapping[str, object] | None]
        ] = []

    def chat(
        self,
        model_id: str,
        messages: list[dict[str, str]],
        *,
        params: Mapping[str, object],
        response_format: Mapping[str, object] | None = None,
    ) -> ChatResult:
        self.calls.append((model_id, messages, params, response_format))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return ChatResult(content=answer, tokens_in=1, tokens_out=1, cost_usd=0.0, latency_ms=1)


def agent_over(client: ScriptedClient) -> ChatAgentLLM:
    chat = CachedChat(client, "pinned/model", DictCache(), max_tokens=500)
    return ChatAgentLLM(chat, PROMPT, "chat-v2", history_turns=3)


def ok(reply: str = "Hello!", intent: str = "chat") -> str:
    return json.dumps({"reply": reply, "intent": intent})


def system_of(client: ScriptedClient) -> str:
    return client.calls[-1][1][0]["content"]


def test_arabic_context_asks_the_model_for_arabic() -> None:
    client = ScriptedClient(ok(), ok())
    agent = agent_over(client)
    agent.reply(ChatContext(role="student", lang="ar"), [Turn("user", "el wifi ma byeshteghel")])
    assert "Reply in Arabic" in system_of(client) and "Arabizi" in system_of(client)
    agent.reply(ChatContext(role="student", lang="en"), [Turn("user", "my wifi is down")])
    assert "Reply in English." in system_of(client) and "Reply in Arabic" not in system_of(client)


def test_the_call_is_pinned_json_and_temperature_zero() -> None:
    client = ScriptedClient(ok())
    agent_over(client).reply(ChatContext(role="student", lang="en"), [Turn("user", "hi")])
    model, messages, params, response_format = client.calls[0]
    assert model == "pinned/model" and params["temperature"] == 0 and params["max_tokens"] == 500
    assert response_format == {"type": "json_object"} and messages[0]["role"] == "system"


def test_staff_wording_greeting_announcements_and_proposal_are_in_the_prompt_as_data() -> None:
    client = ScriptedClient(ok(), ok())
    agent = agent_over(client)
    ctx = ChatContext(
        role="staff", lang="en", first_name="Omar", announcements=['[outage] Wi-Fi: "down" until 14:00'],
        proposal="IT Support: my laptop is broken",
    )  # fmt: skip
    agent.reply(ctx, [Turn("user", "hi")])
    system = system_of(client)
    assert "never mention a student ID" in system and "Greet the person by first name once, now" in system
    assert '"Omar"' in system and "Wi-Fi" in system and '"IT Support: my laptop is broken"' in system
    assert "Never ask for a student ID" not in system
    agent.reply(ctx, [Turn("user", "hi"), Turn("assistant", "hello Omar"), Turn("user", "yes")])
    assert "Do not greet the person again" in system_of(client)


def test_history_is_cut_to_the_last_turns() -> None:
    client = ScriptedClient(ok())
    turns = [Turn("user" if i % 2 == 0 else "assistant", f"m{i}") for i in range(6)] + [Turn("user", "last")]
    agent_over(client).reply(ChatContext(role="student", lang="en"), turns)
    assert [m["content"] for m in client.calls[0][1][1:]] == ["m4", "m5", "last"]


def test_valid_replies_parse_and_junk_is_none() -> None:
    reply = parse_reply(ok("Hi", "request"))
    assert reply is not None and (reply.reply, reply.intent) == ("Hi", "request")
    fenced = parse_reply("```json\n" + ok("Hi", "confirm") + "\n```")
    assert fenced is not None and fenced.intent == "confirm"
    extra = parse_reply(
        json.dumps({"reply": "Hi", "intent": "chat", "category": "Finance", "priority": "high"})
    )
    assert extra is not None and not hasattr(extra, "category")  # the model's extra keys are dropped
    for junk in (
        None,
        "",
        "not json",
        "[1]",
        ok("", "chat"),
        ok("x", "send_to_finance"),
        '{"reply": 3, "intent": "chat"}',
        ok("x" * 2000, "chat"),
    ):
        assert parse_reply(junk) is None, junk
    assert parse_phrase('{"reply": "Shall I?"}') == "Shall I?" and parse_phrase("nope") is None


def test_failures_and_invalid_output_return_none() -> None:
    client = ScriptedClient(LLMUnavailable("down"), "not json at all", ok(intent="bogus"))
    agent = agent_over(client)
    ctx = ChatContext(role="student", lang="en")
    assert agent.reply(ctx, [Turn("user", "a")]) is None
    assert agent.reply(ctx, [Turn("user", "b")]) is None
    assert agent.reply(ctx, [Turn("user", "c")]) is None


def test_responses_are_cached() -> None:
    client = ScriptedClient(ok("first"))
    agent = agent_over(client)
    ctx = ChatContext(role="student", lang="en")
    a = agent.reply(ctx, [Turn("user", "same")])
    b = agent.reply(ctx, [Turn("user", "same")])
    assert a == b and len(client.calls) == 1


def test_phrase_asks_for_the_department_and_the_facts_as_data() -> None:
    client = ScriptedClient('{"reply": "I can send this to Finance. Shall I?"}')
    facts = ProposalFacts(department="Finance", action_kind="faq_answer", faq_answer="Pay at the bank.")
    text = agent_over(client).phrase(ChatContext(role="student", lang="en"), facts)
    assert text == "I can send this to Finance. Shall I?"
    user_message = client.calls[0][1][1]["content"]
    assert '"department": "Finance"' in user_message and "Pay at the bank." in user_message


def test_the_pinned_yaml_is_valid_and_temperature_zero() -> None:
    raw = load_chat_yaml(Settings(_env_file=None))  # type: ignore[call-arg]
    assert raw["temperature"] == 0 and raw["model"] == "deepseek/deepseek-v4.1-flash"
    assert raw["prompt_version"] == "chat-v2" and Path(REPO_ROOT / raw["prompt_file"]).is_file()


def test_library_notice_cannot_support_invented_workaround() -> None:
    client = ScriptedClient(
        json.dumps({"reply": "Our team is working on it. Please use the lab network meanwhile.",
                    "intent": "announcement", "source_ids": ["notice-1"]})
    )
    ctx = ChatContext(role="student", lang="en", sources=(
        GroundingSource("notice-1", "announcement", "Library Wi-Fi is down", "library"),
    ))
    reply = agent_over(client).reply(ctx, [Turn("user", "wifi is down why")])
    assert reply is not None and "Library Wi-Fi is down" in reply.reply
    assert "lab network" not in reply.reply and reply.intent == "chat"


def test_current_source_id_is_required_for_operational_claim() -> None:
    client = ScriptedClient(json.dumps({"reply": "A notice says the library Wi-Fi is down.",
                                        "intent": "announcement", "source_ids": ["invented"]}))
    ctx = ChatContext(role="student", lang="en")
    reply = agent_over(client).reply(ctx, [Turn("user", "library wifi?")])
    assert reply is not None and reply.intent == "chat" and "do not have information" in reply.reply


def test_scoped_notice_cannot_be_rephrased_as_campus_wide_outage() -> None:
    client = ScriptedClient(json.dumps({"reply": "A notice says Wi-Fi is down campus wide.",
                                        "intent": "announcement", "source_ids": ["notice-1"]}))
    ctx = ChatContext(role="student", lang="en", sources=(
        GroundingSource("notice-1", "announcement", "Library Wi-Fi is down", "library"),
    ))
    reply = agent_over(client).reply(ctx, [Turn("user", "wifi is down")])
    assert reply is not None and "Library Wi-Fi is down" in reply.reply
    assert "campus wide" not in reply.reply
