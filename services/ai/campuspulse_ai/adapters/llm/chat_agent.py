"""`ChatAgentLLM`: the chat agent's language model calls (P9.8, docs/plan/p9/PLAN.md section f).

Two calls through `CachedChat` (pinned model, temperature 0, cached, never raises): `reply` (the next
message and its intent) and `phrase` (one message that offers a proposal the server already decided).
The model returns `{"reply", "intent", "source_ids", "ticket_refs", "corrected_text"}`; anything else is
dropped, and a reply that is not a JSON object with a non-empty text and a known intent counts as a failure
(None), so the use case falls back. Malformed `ticket_refs` or `corrected_text` are dropped (they are only
hints the use case checks). The system prompt is the `prompt_file` of `config/chat_agent.yaml`, filled from
a `ChatContext`; announcements, the pending proposal and the person's requests are passed as quoted JSON
data, never as instructions.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import replace
from string import Template
from typing import Any

from campuspulse_ai.adapters.llm.cached_chat import CachedChat, prompt_hash
from campuspulse_ai.application.use_cases.chat_ports import (
    INTENTS,
    AgentReply,
    ChatContext,
    GroundingSource,
    ProposalFacts,
    Turn,
)
from campuspulse_ai.application.use_cases.issue_context import IssueContextPreparer

log = logging.getLogger(__name__)

JSON_OBJECT: dict[str, object] = {"type": "json_object"}
REPLY_MAX_CHARS = 1200
CORRECTED_MAX_CHARS = 1000
REFS_MAX = 5
_REF = re.compile(r"[0-9A-F]{8}")
SERVER_WORDED = frozenset({"correct", "withdraw", "separate"})
"""Intents whose reply text the person never sees (the server answers with a template), so the grounding
check must not turn them into "chat" and lose the intent."""
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
    'categories. Cite current-turn source ids for any operational claim. Reply with ONE JSON object: '
    '{"reply": "<your message>", "source_ids": []}.'
)

_UNSUPPORTED = re.compile(
    r"\b(?:working on it|team is working|meanwhile|please use|use the (?:lab|other)|"
    r"will be (?:fixed|restored)|back (?:by|at)|resolved (?:by|at))\b|"
    r"(?:الفريق يعمل|نعمل على|استخدم|استعمل|بإمكانك استخدام|سيتم إصلاح|رح ينحل|خلال ساعة)",
    re.IGNORECASE,
)
_OPERATIONAL = re.compile(
    r"\b(?:notice|announcement|maintenance|outage|down in|available at|"
    r"working on|please use|will be fixed)\b|(?:إعلان|صيانة|انقطاع|عطل|استخدم)",
    re.IGNORECASE,
)
_KIND_TAG = re.compile(r"^\[[a-z_]+\]\s*")  # the internal "[outage] " prefix of an announcement line
_SAFE = {
    "en": (
        "I do not have information about the cause, a workaround, or when it will be fixed. "
        "Where is the problem? I can help record a request."
    ),
    "ar": "ما عندي معلومات عن السبب أو حل مؤقت أو وقت الإصلاح. وين المشكلة؟ بقدر أساعدك تسجّل طلب.",
}


def parse_reply(raw: str | None) -> AgentReply | None:
    """`{"reply", "intent"}` from the model's text, or None when it is not usable."""
    data = _json_object(raw)
    if data is None:
        return None
    text, intent = data.get("reply"), data.get("intent")
    if not isinstance(text, str) or not text.strip() or len(text) > REPLY_MAX_CHARS or intent not in INTENTS:
        return None
    ids = data.get("source_ids", [])
    if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids):
        return None
    return AgentReply(
        reply=text.strip(),
        intent=intent,
        source_ids=tuple(ids),
        ticket_refs=_refs(data.get("ticket_refs")),
        corrected_text=_corrected(data.get("corrected_text")),
    )


def _refs(raw: object) -> tuple[str, ...]:
    """Ticket numbers as the server prints them ("#ab12cd34" -> "AB12CD34"); anything else is dropped."""
    if not isinstance(raw, list):
        return ()
    refs: list[str] = []
    for item in raw[:REFS_MAX]:
        if isinstance(item, bool) or not isinstance(item, str | int):
            continue
        ref = str(item).strip().lstrip("#").strip().upper()
        if _REF.fullmatch(ref) and ref not in refs:
            refs.append(ref)
    return tuple(refs)


def _corrected(raw: object) -> str:
    return raw.strip()[:CORRECTED_MAX_CHARS] if isinstance(raw, str) else ""


def parse_phrase(raw: str | None) -> str | None:
    data = _json_object(raw)
    text = data.get("reply") if data is not None else None
    if not isinstance(text, str) or not text.strip() or len(text) > REPLY_MAX_CHARS:
        return None
    return text.strip()


def _phrase_with_sources(raw: str | None) -> tuple[str, tuple[str, ...]] | None:
    data = _json_object(raw)
    text = parse_phrase(raw)
    ids = data.get("source_ids", []) if data is not None else []
    if text is None or not isinstance(ids, list) or any(not isinstance(x, str) for x in ids):
        return None
    return text, tuple(ids)


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
        self.preparer: IssueContextPreparer | None = None
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
            sources=json.dumps([{"id": s.id, "kind": s.kind, "text": s.text, "scope": s.scope}
                                for s in ctx.sources], ensure_ascii=False),
            requests=json.dumps(list(ctx.requests), ensure_ascii=False) if ctx.requests else "[]",
        )

    @staticmethod
    def _grounded(text: str, source_ids: Sequence[str], ctx: ChatContext) -> bool:
        sources = {s.id: s for s in ctx.sources}
        if any(identifier not in sources for identifier in source_ids):
            return False
        operational = bool(_OPERATIONAL.search(text))
        if operational and not source_ids:
            return False
        if operational and any(
            sources[identifier].kind == "announcement"
            and sources[identifier].scope
            and sources[identifier].scope.casefold() not in text.casefold()
            for identifier in source_ids
        ):
            return False
        if not _UNSUPPORTED.search(text):
            return True
        # This is deliberately conservative: a cited source must state the risky wording.
        cited = " ".join(sources[identifier].text for identifier in source_ids)
        return all(match.group().casefold() in cited.casefold() for match in _UNSUPPORTED.finditer(text))

    @staticmethod
    def _safe(ctx: ChatContext, source_ids: Sequence[str] = ()) -> str:
        """The canned reply for an ungrounded answer. It quotes a notice only when the model's own reply
        cited it; a live notice that has nothing to do with the conversation is never pulled in."""
        by_id = {s.id: s for s in ctx.sources}
        notice = next((by_id[i] for i in source_ids if i in by_id and by_id[i].kind == "announcement"), None)
        if notice is None:
            return _SAFE[ctx.lang]
        quoted = _KIND_TAG.sub("", notice.text.strip())[:300]
        if ctx.lang == "ar":
            return f"الإعلان يقول: «{quoted}». هل المشكلة بنفس المكان؟ بقدر أساعدك تسجّل طلب."
        return f'The notice says: "{quoted}". Is your problem in the same place? I can help record a request.'

    def reply(self, ctx: ChatContext, messages: Sequence[Turn]) -> AgentReply | None:
        turns = list(messages)[-self._history :]
        system = self.render_system(ctx, greet=not any(t.role == "assistant" for t in messages))
        payload = json.dumps([system, [(t.role, t.content) for t in turns]], ensure_ascii=False)
        wire = [
            {"role": "system", "content": system},
            *({"role": t.role, "content": t.content} for t in turns),
        ]
        parsed = parse_reply(self._chat.ask(self._purpose, payload, wire, response_format=JSON_OBJECT))
        if (
            parsed is not None
            and parsed.intent not in SERVER_WORDED
            and not self._grounded(parsed.reply, parsed.source_ids, ctx)
        ):
            log.info("chat agent: unsupported operational claim replaced (%s)", self._version)
            return AgentReply(self._safe(ctx, parsed.source_ids), "chat")
        if parsed is None:
            log.info("chat agent: no usable reply (%s)", self._version)
        return parsed

    def phrase(self, ctx: ChatContext, facts: ProposalFacts) -> str | None:
        if facts.faq_answer:
            ctx = replace(
                ctx, sources=(*ctx.sources, GroundingSource("faq:proposal", "faq", facts.faq_answer))
            )
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
        parsed = _phrase_with_sources(
            self._chat.ask(f"{self._purpose}:phrase", payload, wire, response_format=JSON_OBJECT)
        )
        if parsed is None:
            return None
        text, ids = parsed
        if not self._grounded(text, ids, ctx):
            return self._safe(ctx, ids)
        return text
