"""What the chat use case needs from the LLM, and what it hands over (P9.8).

`ChatAgent` is implemented by `adapters/llm/chat_agent.ChatAgentLLM` (OpenRouter, pinned, cached) and by
scripted fakes in tests. The LLM only talks: `AgentReply` has a reply text and an intent, never a
category, priority, office or flag. Every method returns None when the model is unavailable or its output
is unusable; the use case then answers in fallback mode.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

Intent = Literal["chat", "request", "confirm", "decline", "announcement"]
INTENTS: tuple[Intent, ...] = ("chat", "request", "confirm", "decline", "announcement")
ReplyLang = Literal["en", "ar"]


@dataclass(frozen=True, slots=True)
class AgentReply:
    reply: str
    intent: Intent


@dataclass(frozen=True, slots=True)
class Turn:
    """One message of the conversation as the model sees it."""

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class ChatContext:
    """Everything the system prompt is filled with.

    `first_name` is None for staff, admin and anyone without a display name; `role` is the caller's
    role (`student`, `staff`, `admin`); `lang` is the language the reply must be in (Arabic and
    Arabizi in -> `ar`); `announcements` are the live notices (quoted as data); `proposal` is the
    summary of the pending, signed proposal when the token is valid.
    """

    role: str
    lang: ReplyLang
    first_name: str | None = None
    announcements: Sequence[str] = field(default_factory=tuple)
    proposal: str | None = None


@dataclass(frozen=True, slots=True)
class ProposalFacts:
    """What the "phrase this proposal" call may talk about (all decided by the server)."""

    department: str
    action_kind: str
    faq_answer: str | None = None
    hint_used: bool = False
    asks_question: str | None = None


class ChatAgent(Protocol):
    def reply(self, ctx: ChatContext, messages: Sequence[Turn]) -> AgentReply | None:
        """The agent's next message and its intent, or None on any failure."""
        ...

    def phrase(self, ctx: ChatContext, facts: ProposalFacts) -> str | None:
        """One short message that offers `facts` to the person, or None on any failure."""
        ...
