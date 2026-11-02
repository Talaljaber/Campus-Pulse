"""`ChatAgentLLM`: the chat agent's language model calls (P9.8, docs/plan/p9/PLAN.md section f).

Two calls through `CachedChat` (pinned model, temperature 0, cached, never raises): `reply` (the next
message and its intent) and `phrase` (one message that offers a proposal the server already decided).
The model returns only `{"reply", "intent"}`; whatever else it adds is dropped, and a reply that is not a
JSON object with a non-empty text and a known intent counts as a failure (None), so the use case falls
back. The system prompt is `config/prompts/chat_agent_v1.md`, filled from a `ChatContext`; announcements and
the pending proposal are passed as quoted JSON data, never as instructions.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from string import Template
from typing import Any

from campuspulse_ai.adapters.llm.cached_chat import CachedChat, prompt_hash
from campuspulse_ai.application.use_cases.chat_ports import (
    INTENTS,
    AgentReply,
    ChatContext,
    ProposalFacts,
    Turn,
)

log = logging.getLogger(__name__)

JSON_OBJECT: dict[str, object] = {"type": "json_object"}
REPLY_MAX_CHARS = 1200
ROLE_STUDENT = "student"
LANGUAGE_RULES = {
    "en": "Reply in English.",
    "ar": (
        "Reply in Arabic (simple Jordanian-style words are fine), also when the person wrote in Arabizi "
        "(Arabic in Latin letters). Never answer an Arabic or Arabizi message in English."
    ),
}
AUDIENCE_RULES = {
    "student": "Never ask for a student ID or any other personal number.",
    "staff": (
        "The person is a staff member using the assistant for their own problem: use neutral words, never "
        "say 'student' and never mention a student ID."
    ),
}
PHRASE_TASK = (
    "Write ONE short message (at most 40 words) for the person. Say what you can do with the facts below and "
    "ask whether they want you to record the request. Name the department exactly as given in the facts. "
    "If a FAQ answer is given, give that answer first (do not change it), then offer to record a request "
    "anyway. If a question is given, ask exactly that question. Do not mention scores, priorities or "
    'categories. Reply with ONE JSON object: {"reply": "<your message>"}.'
)


def parse_reply(raw: str | None) -> AgentReply | None:
    """`{"reply", "intent"}` from the model's text, or None when it is not usable."""
    data = _json_object(raw)
    if data is None:
        return None
    text, intent = data.get("reply"), data.get("intent")
    if not isinstance(text, str) or not text.strip() or len(text) > REPLY_MAX_CHARS or intent not in INTENTS:
        return None
    return AgentReply(reply=text.strip(), intent=intent)


def parse_phrase(raw: str | None) -> str | None:
    data = _json_object(raw)
    text = data.get("reply") if data is not None else None
    if not isinstance(text, str) or not text.strip() or len(text) > REPLY_MAX_CHARS:
        return None
    return text.strip()


def _json_object(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    text = raw.strip()
    if text.startswith("```"):  # a fenced block: drop the fences
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


class ChatAgentLLM:
    """Implements `ChatAgent` over a `CachedChat`. `prompt` is the text of the prompt file."""

    def __init__(
        self, chat: CachedChat, prompt: str, prompt_version: str, *, history_turns: int = 12
    ) -> None:
        self._chat = chat
        self._prompt = prompt
        self._version = prompt_version
        self._history = history_turns
        self._purpose = f"chat-agent:{prompt_version}:{prompt_hash(prompt)}"

    def render_system(self, ctx: ChatContext, *, greet: bool) -> str:
        """The system prompt for `ctx` (public so tests and the regression script can read it)."""
        staff = ctx.role != ROLE_STUDENT
        if ctx.first_name and greet:
            greeting = (
                f'Greet the person by first name once, now: "{ctx.first_name}". Do not greet again later.'
            )
        else:
            greeting = "Do not greet the person again."
        return Template(self._prompt).safe_substitute(
            role_label="a member of the university staff" if staff else "a student",
            language_rule=LANGUAGE_RULES[ctx.lang],
            greeting_rule=greeting,
            audience_rule=AUDIENCE_RULES["staff" if staff else "student"],
            announcements=json.dumps(list(ctx.announcements), ensure_ascii=False)
            if ctx.announcements
            else "[]",
            proposal=json.dumps(ctx.proposal, ensure_ascii=False) if ctx.proposal else "null",
        )

    def reply(self, ctx: ChatContext, messages: Sequence[Turn]) -> AgentReply | None:
        turns = list(messages)[-self._history :]
        system = self.render_system(ctx, greet=not any(t.role == "assistant" for t in messages))
        payload = json.dumps([system, [(t.role, t.content) for t in turns]], ensure_ascii=False)
        wire = [
            {"role": "system", "content": system},
            *({"role": t.role, "content": t.content} for t in turns),
        ]
        parsed = parse_reply(self._chat.ask(self._purpose, payload, wire, response_format=JSON_OBJECT))
        if parsed is None:
            log.info("chat agent: no usable reply (%s)", self._version)
        return parsed

    def phrase(self, ctx: ChatContext, facts: ProposalFacts) -> str | None:
        system = self.render_system(ctx, greet=False)
        lines = {
            "department": facts.department,
            "action": facts.action_kind,
            "faq_answer": facts.faq_answer,
            "a_past_correction_was_used": facts.hint_used,
            "question_to_ask": facts.asks_question,
        }
        user = f"{PHRASE_TASK}\nFACTS (data): {json.dumps(lines, ensure_ascii=False)}"
        payload = json.dumps([system, user], ensure_ascii=False)
        wire = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return parse_phrase(
            self._chat.ask(f"{self._purpose}:phrase", payload, wire, response_format=JSON_OBJECT)
        )
