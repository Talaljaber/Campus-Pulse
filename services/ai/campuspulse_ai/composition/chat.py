"""Chat agent wiring (P9.8): `config/chat_agent.yaml`, the LLM adapter and the `ChatUseCase`.

The chat's LLM exists only with `OPENROUTER_API_KEY` and `CHAT_AGENT_ENABLED` not false; preview and
confirm (the plain form) are always wired, as long as `AI_SERVICE_TOKEN` can sign proposals. The model id,
temperature 0 and the prompt file are pinned in the yaml; replies are cached (`cache_path`).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from campuspulse_ai.adapters.llm.cache_sqlite import SqliteCache
from campuspulse_ai.adapters.llm.cached_chat import PINNED_PARAMS, CachedChat
from campuspulse_ai.adapters.llm.chat_agent import ChatAgentLLM
from campuspulse_ai.adapters.llm.cost import InMemoryCostLogger
from campuspulse_ai.adapters.llm.issue_context import IssueContextLLM
from campuspulse_ai.adapters.llm.openrouter import OpenRouterClient
from campuspulse_ai.application.use_cases.act import ActUseCase
from campuspulse_ai.application.use_cases.announcement_ports import AnnouncementStore
from campuspulse_ai.application.use_cases.chat import ChatConfig, ChatUseCase
from campuspulse_ai.application.use_cases.chat_claims import ChatClaimStore
from campuspulse_ai.application.use_cases.chat_ports import ChatAgent
from campuspulse_ai.application.use_cases.journey_ports import JourneyStore
from campuspulse_ai.application.use_cases.knowledge_ports import KnowledgeSearch
from campuspulse_ai.application.use_cases.ports import Clarifier, TriageClassifier
from campuspulse_ai.application.use_cases.proposals import derive_key
from campuspulse_ai.application.use_cases.ticket_lifecycle import TicketLifecycleUseCase
from campuspulse_ai.application.use_cases.triage import TriageUseCase
from campuspulse_ai.composition.redteam import resolve
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.policy import DefaultDecisionPolicy
from campuspulse_ai.domain.ports import Clock, Repository, SentenceEncoder

log = logging.getLogger(__name__)


def load_chat_yaml(settings: Settings) -> dict[str, Any]:
    path = resolve(settings.chat_agent_config)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping")
    return data


def build_chat_agent(settings: Settings, raw: dict[str, Any]) -> ChatAgent | None:
    """`ChatAgentLLM` over a pinned, cached OpenRouter client, or None (no key, or disabled)."""
    key = settings.openrouter_api_key
    if not settings.chat_agent_enabled or key is None:
        return None
    if raw.get("temperature") != PINNED_PARAMS["temperature"]:
        raise ValueError("chat_agent.yaml: temperature must be 0 (project rule)")
    client = OpenRouterClient(
        key.get_secret_value(),
        timeout_s=float(raw["timeout_s"]),
        max_retries=1,
        retry_backoff_s=1.0,
        retry_on_rate_limit=True,
        total_deadline_s=float(raw["timeout_s"]),
        provider=settings.chat_provider_preferences(),
    )
    cache_path = resolve(Path(str(raw["cache_path"])))
    chat = CachedChat(
        client,
        str(raw["model"]),
        SqliteCache(cache_path),
        InMemoryCostLogger(),
        max_tokens=int(raw["max_tokens"]),
        daily_budget_usd=settings.llm_daily_budget_usd,
        extra_params={"reasoning": dict(raw["reasoning"])} if raw.get("reasoning") else None,
    )
    prompt = resolve(Path(str(raw["prompt_file"]))).read_text(encoding="utf-8")
    agent = ChatAgentLLM(chat, prompt, str(raw["prompt_version"]), history_turns=int(raw["history_turns"]))
    agent.preparer = IssueContextLLM(
        chat, resolve(Path(str(raw["issue_context_prompt"]))).read_text(encoding="utf-8")
    )
    return agent


def build_chat(
    settings: Settings,
    *,
    classifier: TriageClassifier,
    policy: DefaultDecisionPolicy,
    clarifier: Clarifier,
    act: ActUseCase,
    triage: TriageUseCase,
    repo: Repository,
    clock: Clock,
    lifecycle: TicketLifecycleUseCase | None,
    journey: JourneyStore | None,
    announcements: AnnouncementStore | None,
    encoder: SentenceEncoder,
    agent: ChatAgent | None = None,
    claims: ChatClaimStore | None = None,
    knowledge: KnowledgeSearch | None = None,
) -> ChatUseCase | None:
    """The chat use case, or None without `AI_SERVICE_TOKEN` (proposals could not be signed; every route
    answers 401 in that case anyway). `agent` overrides the LLM wiring (tests)."""
    token = settings.ai_service_token
    if token is None:
        return None
    raw = load_chat_yaml(settings)
    selected_agent = agent if agent is not None else build_chat_agent(settings, raw)
    return ChatUseCase(
        classifier=classifier,
        policy=policy,
        clarifier=clarifier,
        act=act,
        triage=triage,
        repo=repo,
        clock=clock,
        key=derive_key(token.get_secret_value()),
        config=ChatConfig.from_dict(raw),
        agent=selected_agent,
        preparer=(
            selected_agent.preparer
            if raw.get("issue_context_enabled", False) and isinstance(selected_agent, ChatAgentLLM)
            else None
        ),
        lifecycle=lifecycle,
        journey=journey,
        announcements=announcements,
        encoder=encoder,
        claims=claims,
        knowledge=knowledge,
    )
