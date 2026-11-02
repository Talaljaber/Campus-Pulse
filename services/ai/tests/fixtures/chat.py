"""Chat agent test harness (P9.8): a `ChatUseCase` over `build_test()`, a lifecycle, a journey store and a
scripted agent. Nothing here calls a language model or the network."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from campuspulse_ai.adapters.clarify.bank import QuestionBank
from campuspulse_ai.adapters.clarify.info_gain import InfoGainStrategy
from campuspulse_ai.adapters.store.announcements_inmemory import InMemoryAnnouncementStore
from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases.chat import ChatConfig, ChatUseCase
from campuspulse_ai.application.use_cases.chat_ports import (
    AgentReply,
    ChatContext,
    Intent,
    ProposalFacts,
    Turn,
)
from campuspulse_ai.application.use_cases.proposals import derive_key
from campuspulse_ai.config.paths import CONFIG_DIR
from campuspulse_ai.domain.policy import DefaultDecisionPolicy
from fixtures.backend_fakes import FakeCore, FakeFAQ
from fixtures.containers import BackendTestContainer, build_test, load_yaml
from fixtures.lifecycle import ALIAS, LifecycleHarness, build_lifecycle

SERVICE_TOKEN = "test-service-token"
KEY = derive_key(SERVICE_TOKEN)
HINT_VECTOR = (1.0, 0.0, 0.0)


@dataclass(frozen=True)
class Caller:
    """An `Actor`: role, office and alias."""

    role: str = "student"
    alias: str | None = ALIAS
    office: str | None = None


STAFF = Caller(role="staff", alias="staff-registrar", office="registrar")


class ConstEncoder:
    """Every text gets `HINT_VECTOR`, so a hint stored with it is always similar."""

    dim = 3

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        return np.array([HINT_VECTOR for _ in texts])


@dataclass
class ScriptedAgent:
    """A `ChatAgent` that answers from a script: `replies` in order (None = the model failed), `phrase`
    a text, a function of the facts, or None. Records what it was asked."""

    replies: list[AgentReply | None] = field(default_factory=list)
    phrase_text: str | Callable[[ProposalFacts], str] | None = None
    reply_calls: list[tuple[ChatContext, list[Turn]]] = field(default_factory=list)
    phrase_calls: list[ProposalFacts] = field(default_factory=list)

    def reply(self, ctx: ChatContext, messages: Sequence[Turn]) -> AgentReply | None:
        self.reply_calls.append((ctx, list(messages)))
        return self.replies.pop(0) if self.replies else None

    def phrase(self, ctx: ChatContext, facts: ProposalFacts) -> str | None:
        self.phrase_calls.append(facts)
        text = self.phrase_text
        return text(facts) if callable(text) else text


def says(text: str, intent: Intent) -> AgentReply:
    return AgentReply(reply=text, intent=intent)


@dataclass
class ChatHarness:
    c: BackendTestContainer
    h: LifecycleHarness
    uc: ChatUseCase
    agent: ScriptedAgent | None
    announcements: InMemoryAnnouncementStore

    @property
    def core(self) -> FakeCore:
        return self.c.core

    def tickets(self) -> list[dict[str, Any]]:
        return list(self.c.repo.tables["tickets"].values())


def chat_config() -> ChatConfig:
    return ChatConfig.from_dict(load_yaml(CONFIG_DIR / "chat_agent.yaml"))


def build_chat(
    *, agent: ScriptedAgent | None | str = "default", faq: FakeFAQ | None = None, core: FakeCore | None = None
) -> ChatHarness:
    """`agent="default"` = an empty ScriptedAgent, None = no LLM wired (fallback mode)."""
    c = build_test(core=core, faq=faq)
    c.repo.add_profile(ALIAS, "student", display_name="Lina Haddad")
    h = build_lifecycle(c, encoder=ConstEncoder())
    scripted = ScriptedAgent() if agent == "default" else agent
    assert scripted is None or isinstance(scripted, ScriptedAgent)
    announcements = InMemoryAnnouncementStore()
    uc = ChatUseCase(
        classifier=c.core,
        policy=DefaultDecisionPolicy(c.config.thresholds.tau_ood),
        clarifier=InfoGainStrategy(QuestionBank.load(CONFIG_DIR / "clarify_questions.yaml")),
        act=c.act,
        triage=c.triage,
        repo=c.repo,
        clock=c.clock,
        key=KEY,
        config=chat_config(),
        agent=scripted,
        lifecycle=h.lifecycle,
        journey=h.journey,
        announcements=announcements,
        encoder=ConstEncoder(),
    )
    return ChatHarness(c, h, uc, scripted, announcements)


def user(text: str) -> dto.ChatMessage:
    return dto.ChatMessage(role="user", content=text)


def assistant(text: str, kind: str = "text") -> dto.ChatMessage:
    return dto.ChatMessage(role="assistant", content=text, kind=kind)  # type: ignore[arg-type]


def turn_of(*messages: dto.ChatMessage, token: str | None = None) -> dto.ChatTurnRequest:
    return dto.ChatTurnRequest(messages=list(messages), proposal_token=token)
