"""ChatUseCase: the chat agent's turn, preview and confirm (P9.8, docs/plan/p9/PLAN.md section f).

The language model only talks (`ChatAgent`): it never decides a category, priority, office or flag. Routing
comes from the classifier on the requester's own words, and a ticket exists only after a valid server-signed
proposal token bound to the caller's alias (`proposals.py`).

`turn(cmd, caller, later)`:
1. validate (the last message is from the user, not blank);
2. safety first, no LLM: classify the last user message; a `distress` flag runs the full triage now
   (persisted, admin review, the existing distress reply) and returns it, even when the LLM is off;
3. no LLM wired, or the LLM fails or answers invalid JSON: `mode: "fallback"` (the web shows the form);
4. intent `request`: `request_text` = the user messages after the last assistant message of kind
   `proposal` or `ticket`, last 1000 chars -> `_propose` (a question to ask, or a proposal phrased by a
   second LLM call and post-checked: it must name the localized department and use none of the banned
   phrases, else the template sentence is used);
5. intent `confirm` with a valid token -> confirm, the reply is the template "Request recorded: #n for
   <department> (demo, no real department was contacted)"; without a valid token nothing is recorded;
6. `decline` -> `clear_proposal`; `chat` / `announcement` -> the LLM reply (banned phrases -> template).

`preview(cmd, caller)` is the plain-form path (no LLM): classify, decision policy with a one-question budget,
the route plan and FAQ answer, the staff-correction hint (raise-only priority). It writes nothing (except a
distress message, which is triaged and persisted like any other distress).

`confirm(cmd, caller, later)` runs `TriageUseCase.run(chat_confirmed=True)` on the token's text, applies the
hint as a "past correction" re-route (`TicketLifecycleUseCase.apply_hint`) and hands the follow-up work to
`later` (a list the route turns into background tasks: first the hint's delivery, then `on_created`).
Errors: `InvalidInput` (422) for a bad, expired or foreign token or an invalid conversation.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases import responses as out
from campuspulse_ai.application.use_cases.act import ActUseCase
from campuspulse_ai.application.use_cases.announcement_ports import AnnouncementStore
from campuspulse_ai.application.use_cases.chat_ports import (
    AgentReply,
    ChatAgent,
    ChatContext,
    ProposalFacts,
    ReplyLang,
    Turn,
)
from campuspulse_ai.application.use_cases.journey_ports import JourneyStore
from campuspulse_ai.application.use_cases.ports import Actor, Clarifier, TriageClassifier
from campuspulse_ai.application.use_cases.proposals import ProposalClaims, sign, verify
from campuspulse_ai.application.use_cases.ticket_lifecycle import TicketLifecycleUseCase
from campuspulse_ai.application.use_cases.triage import DISTRESS, TriageUseCase
from campuspulse_ai.domain.entities import CoreResult, Prediction
from campuspulse_ai.domain.errors import CampusPulseError, InvalidInput
from campuspulse_ai.domain.journey import HintMatch, ticket_number
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.policy import DefaultDecisionPolicy
from campuspulse_ai.domain.ports import Clock, Repository, SentenceEncoder
from campuspulse_ai.domain.values import (
    ActionType,
    ClarificationBudget,
    Lang,
    Money,
    NormalizedRequest,
    Outcome,
)

log = logging.getLogger(__name__)

REQUEST_TEXT_MAX = 1000
ASKED_IN_CHAT = "chat"
"""Placeholder question id counted once the requester wrote more than one message (one-question budget)."""
DISTRESS_QUESTION_ID = "distress"
MORE_DETAIL_ID = "more_detail"
ANNOUNCEMENTS_SHOWN = 5
ANNOUNCEMENT_CHARS = 300
FIRST_NAME_CHARS = 30
SHORT_MESSAGE_WORDS = 3
NEIGHBORS_SHOWN = 3
_ARABIC = re.compile("[؀-ۿ]")
_NAME = re.compile(r"[^\W\d_]+")
_TEMPLATE_KEYS = (
    "proposal", "proposal_faq", "more_detail", "confirmed", "confirmed_none", "no_proposal", "expired",
    "generic", "fallback", "declined",
)  # fmt: skip
_OFFICES = ("registrar", "it", "finance", "transport", "facilities", "academic")
Later = list[Callable[[], None]]
"""Follow-up work of one call (the hint's delivery); the route runs it after the response."""


@dataclass(frozen=True, slots=True)
class ChatConfig:
    """`config/chat_agent.yaml` as the use case needs it (the composition root parses the YAML)."""

    hint_min_sim: float
    proposal_ttl_min: int
    departments: Mapping[str, Mapping[str, str]]
    templates: Mapping[str, Mapping[str, str]]
    banned: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ChatConfig:
        """Validate a parsed `chat_agent.yaml`. Raises `ValueError` naming the bad key."""
        sim, ttl = data.get("hint_min_sim"), data.get("proposal_ttl_min")
        if isinstance(sim, bool) or not isinstance(sim, int | float) or not 0.0 < float(sim) <= 1.0:
            raise ValueError("chat_agent.yaml: hint_min_sim must be in (0, 1]")
        if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 1:
            raise ValueError("chat_agent.yaml: proposal_ttl_min must be a positive integer")
        departments: dict[str, dict[str, str]] = {}
        templates: dict[str, dict[str, str]] = {}
        for lang in ("en", "ar"):
            names = (data.get("departments") or {}).get(lang) or {}
            texts = (data.get("templates") or {}).get(lang) or {}
            for office in _OFFICES:
                if not isinstance(names.get(office), str):
                    raise ValueError(f"chat_agent.yaml: departments.{lang}.{office} is missing")
            for key in _TEMPLATE_KEYS:
                if not isinstance(texts.get(key), str):
                    raise ValueError(f"chat_agent.yaml: templates.{lang}.{key} is missing")
            departments[lang], templates[lang] = dict(names), dict(texts)
        banned = data.get("banned_phrases")
        if not isinstance(banned, list) or not banned or not all(isinstance(b, str) and b for b in banned):
            raise ValueError("chat_agent.yaml: banned_phrases must be a non-empty list of strings")
        return cls(float(sim), ttl, departments, templates, tuple(banned))


class ChatUseCase:
    """See the module docstring. `agent` is None when no key is set or `CHAT_AGENT_ENABLED=false`
    (every turn then answers in fallback mode; preview and confirm work without it)."""

    def __init__(
        self,
        *,
        classifier: TriageClassifier,
        policy: DefaultDecisionPolicy,
        clarifier: Clarifier,
        act: ActUseCase,
        triage: TriageUseCase,
        repo: Repository,
        clock: Clock,
        key: bytes,
        config: ChatConfig,
        agent: ChatAgent | None = None,
        lifecycle: TicketLifecycleUseCase | None = None,
        journey: JourneyStore | None = None,
        announcements: AnnouncementStore | None = None,
        encoder: SentenceEncoder | None = None,
    ) -> None:
        self._classifier = classifier
        self._policy = policy
        self._clarifier = clarifier
        self._act = act
        self._triage = triage
        self._repo = repo
        self._clock = clock
        self._key = key
        self._cfg = config
        self._agent = agent
        self._lifecycle = lifecycle
        self._journey = journey
        self._announcements = announcements
        self._encoder = encoder

    @property
    def llm_enabled(self) -> bool:
        """True when a language model is wired (else every turn answers in fallback mode)."""
        return self._agent is not None

    # ------------------------------------------------------------------ turn

    def turn(
        self, cmd: dto.ChatTurnRequest, caller: Actor, later: Later | None = None
    ) -> dto.ChatTurnResponse:
        messages = cmd.messages
        last = messages[-1]
        if last.role != "user" or not last.content.strip():
            raise InvalidInput("the last message must be a non-empty user message")
        alias = caller.alias or ""
        req, core = self._classifier.classify(last.content)
        lang = _reply_lang(messages, req)
        if DISTRESS in core.flags:
            return self._distress_turn(last.content, alias, lang)
        if self._agent is None:
            return self._fallback(lang)
        claims, token_bad = self._claims(cmd.proposal_token, alias)
        ctx = self._context(caller, lang, claims)
        turns = [Turn(role=m.role, content=m.content) for m in messages]
        agent_reply = self._agent.reply(ctx, turns)
        if agent_reply is None:
            return self._fallback(lang)
        return self._answer(agent_reply, messages, caller, lang, ctx, claims, token_bad, later)

    def _answer(
        self,
        reply: AgentReply,
        messages: Sequence[dto.ChatMessage],
        caller: Actor,
        lang: ReplyLang,
        ctx: ChatContext,
        claims: ProposalClaims | None,
        token_bad: bool,
        later: Later | None,
    ) -> dto.ChatTurnResponse:
        text = self._text(lang)
        if reply.intent == "request":
            return self._proposal_turn(_request_text(messages), caller, lang, ctx)
        if reply.intent == "confirm":
            if claims is None:  # nothing to confirm: never let the model's words claim a recorded request
                return self._plain(text["expired"] if token_bad else text["no_proposal"], clear=token_bad)
            done = self._confirm_claims(claims, caller, later)
            return dto.ChatTurnResponse(
                mode="agent",
                reply=self._confirmed_reply(done, lang),
                proposal=None,
                ticket_id=done.ticket_id,
                triage=done.triage,
                clear_proposal=True,
            )
        if reply.intent == "decline":
            return self._plain(self._safe(reply.reply, text["declined"]), clear=True)
        return self._plain(self._safe(reply.reply, text["generic"]), clear=False)

    def _proposal_turn(
        self, request_text: str, caller: Actor, lang: ReplyLang, ctx: ChatContext
    ) -> dto.ChatTurnResponse:
        asked = [ASKED_IN_CHAT] if "\n" in request_text else []
        proposal = self._propose(request_text, asked, None, caller)
        if proposal.question is not None:
            return self._plain(_question_text(proposal.question), clear=False)
        text = self._text(lang)
        department = self._department(proposal.office, lang)
        faq_answer = proposal.faq.answer if proposal.faq is not None else None
        facts = ProposalFacts(
            department=department,
            action_kind=str(proposal.action_kind),
            faq_answer=faq_answer,
            hint_used=proposal.hint is not None,
        )
        phrased = self._agent.phrase(ctx, facts) if self._agent is not None else None
        if phrased is not None and self._clean(phrased, department):
            reply = phrased
        elif faq_answer is not None:
            reply = text["proposal_faq"].format(answer=faq_answer, department=department)
        else:
            reply = text["proposal"].format(department=department)
        return dto.ChatTurnResponse(
            mode="agent", reply=reply, proposal=proposal, ticket_id=None, triage=None, clear_proposal=False
        )

    def _distress_turn(self, text: str, alias: str, lang: ReplyLang) -> dto.ChatTurnResponse:
        triage = self._triage.run(dto.TriageRequest(text=text, student_alias=alias))
        return dto.ChatTurnResponse(
            mode="agent" if self._agent is not None else "fallback",
            reply=triage.message or self._text(lang)["generic"],
            proposal=None,
            ticket_id=None,
            triage=triage,
            clear_proposal=False,
        )

    def _fallback(self, lang: ReplyLang) -> dto.ChatTurnResponse:
        return dto.ChatTurnResponse(
            mode="fallback",
            reply=self._text(lang)["fallback"],
            proposal=None,
            ticket_id=None,
            triage=None,
            clear_proposal=False,
        )

    @staticmethod
    def _plain(reply: str, *, clear: bool) -> dto.ChatTurnResponse:
        return dto.ChatTurnResponse(
            mode="agent", reply=reply, proposal=None, ticket_id=None, triage=None, clear_proposal=clear
        )

    # ------------------------------------------------------------------ preview

    def preview(self, cmd: dto.ChatPreviewRequest, caller: Actor) -> dto.ProposalOut:
        return self._propose(cmd.text, cmd.asked, cmd.answer, caller)

    def _propose(self, text: str, asked: Sequence[str], answer: str | None, caller: Actor) -> dto.ProposalOut:
        full = f"{text.strip()}\n{answer.strip()}" if answer and answer.strip() else text.strip()
        full = full[-REQUEST_TEXT_MAX:]
        req, core = self._classifier.classify(full)
        if DISTRESS in core.flags:
            return self._distress_proposal(full, caller, req, core)
        outcome, _ = self._policy.decide_with_path(
            core, ClarificationBudget(max_questions=1, asked=len(asked)), False
        )
        question: dto.ClarificationOut | None = None
        if outcome == Outcome.OUT_OF_SCOPE:
            question = self._topic_question(req)
        elif outcome == Outcome.ASK:
            picked = self._clarifier.select(core, req.lang, asked)
            if picked is not None:
                question = out.clarification_out(picked)
            else:
                outcome, _ = self._policy.decide_with_path(
                    core, ClarificationBudget(max_questions=1, asked=1), False
                )
        category, priority = out.decided_labels(core)
        hint = self._hint(req) if question is None else None
        if hint is not None:
            category = Category(hint.corrected_category)
            priority = max(priority, Priority(hint.corrected_priority), key=lambda p: p.rank)
        pred = Prediction(
            id="", request_id="", category=category, priority=priority, core=core, tier=core.tier,
            flags=set(core.flags), explanation=None, cost=Money(0.0), artifact_version=core.artifact.name,
        )  # fmt: skip
        plan = self._act.plan_for(pred, outcome == Outcome.HUMAN_REVIEW)
        kind, faq = plan.kind, None
        if kind == ActionType.FAQ_ANSWER:
            hit = self._act.faq_hit(req.core, req.lang)
            if hit is None:  # the real flow opens a ticket when no FAQ answer is good enough
                kind = ActionType.TICKET
            else:
                faq = dto.FaqAnswerOut(
                    question=hit.question, answer=hit.answer, source_url=hit.source_url,
                    is_demo=hit.is_demo, score=min(max(hit.score, 0.0), 1.0),
                )  # fmt: skip
        token = ""
        if question is None:
            exp = int(self._clock.now().timestamp()) + self._cfg.proposal_ttl_min * 60
            hint_id = hint.hint_id if hint is not None else None
            claims = ProposalClaims(
                caller.alias or "", full, str(category), str(priority), plan.office, hint_id, exp
            )
            token = sign(self._key, claims)
        return self._proposal_out(
            token, full, core, (category, priority), plan.office, kind, question, faq, hint
        )

    def _distress_proposal(
        self, text: str, caller: Actor, req: NormalizedRequest, core: CoreResult
    ) -> dto.ProposalOut:
        """A distress message in the plain form: triaged and persisted like any other distress; the
        supportive reply travels as a question without options (there is nothing to confirm)."""
        triage = self._triage.run(dto.TriageRequest(text=text, student_alias=caller.alias or ""))
        category, priority = out.decided_labels(core)
        message = triage.message or self._text(_lang_of(req))["generic"]
        question = dto.ClarificationOut(question_id=DISTRESS_QUESTION_ID, text=message, options=[])
        office = self._act.office_for(category, priority)
        return self._proposal_out(
            "", text, core, (category, priority), office, ActionType.TICKET, question, None, None
        )

    @staticmethod
    def _proposal_out(
        token: str,
        text: str,
        core: CoreResult,
        labels: tuple[Category, Priority],
        office: str,
        kind: ActionType,
        question: dto.ClarificationOut | None,
        faq: dto.FaqAnswerOut | None,
        hint: HintMatch | None,
    ) -> dto.ProposalOut:
        category, priority = labels
        neighbors = sorted(core.neighbors, key=lambda n: n.sim, reverse=True)[:NEIGHBORS_SHOWN]
        hint_out = (
            dto.HintOut(
                hint_id=hint.hint_id,
                category=Category(hint.corrected_category),
                priority=Priority(hint.corrected_priority),
                sim=min(max(hint.sim, 0.0), 1.0),
            )
            if hint is not None
            else None
        )
        return dto.ProposalOut(
            token=token,
            text=text,
            category=category,
            priority=priority,
            office=office,
            action_kind=kind,
            question=question,
            faq=faq,
            hint=hint_out,
            why=dto.ProposalWhyOut(
                category=out.category_out(core, category),
                priority=out.priority_out(core, priority),
                neighbors=[out.neighbor_out(n) for n in neighbors],
            ),
        )

    def _topic_question(self, req: NormalizedRequest) -> dto.ClarificationOut:
        try:
            topic = self._clarifier.topic_question(req.lang)
        except InvalidInput:
            topic = None
        if topic is not None:
            return out.clarification_out(topic)
        text = self._text(_lang_of(req))["more_detail"]
        return dto.ClarificationOut(question_id=MORE_DETAIL_ID, text=text, options=[])

    def _hint(self, req: NormalizedRequest) -> HintMatch | None:
        """The nearest staff correction at or above `hint_min_sim`, or None (also when it cannot be read)."""
        if self._journey is None or self._encoder is None:
            return None
        try:
            vector = tuple(float(x) for x in self._encoder.encode([req.text_norm or req.raw])[0])
            matches = self._journey.nearest_hints(vector, 1, self._cfg.hint_min_sim)
            if not matches:
                return None
            Category(matches[0].corrected_category)
            Priority(matches[0].corrected_priority)
            return matches[0]
        except Exception:  # noqa: BLE001 - hints are auxiliary: no hint means the model's own proposal
            log.warning("chat hint lookup failed", exc_info=True)
            return None

    # ------------------------------------------------------------------ confirm

    def confirm(
        self, cmd: dto.ChatConfirmRequest, caller: Actor, later: Later | None = None
    ) -> dto.ChatConfirmResponse:
        claims = verify(self._key, cmd.proposal_token, caller.alias or "", self._clock.now())
        return self._confirm_claims(claims, caller, later)

    def _confirm_claims(
        self, claims: ProposalClaims, caller: Actor, later: Later | None
    ) -> dto.ChatConfirmResponse:
        triage = self._triage.run(
            dto.TriageRequest(text=claims.text, student_alias=caller.alias or "", chat_confirmed=True)
        )
        action = triage.action
        ticket_id = action.ticket_id if action is not None else None
        applied = False
        if ticket_id and claims.hint_id and action is not None and action.type == ActionType.TICKET:
            applied = self._apply_hint(ticket_id, claims, later)
        return dto.ChatConfirmResponse(triage=triage, ticket_id=ticket_id, hint_applied=applied)

    def _apply_hint(self, ticket_id: str, claims: ProposalClaims, later: Later | None) -> bool:
        lifecycle = self._lifecycle
        if lifecycle is None:
            return False
        try:
            change = lifecycle.apply_hint(ticket_id, Category(claims.category), Priority(claims.priority))
        except (CampusPulseError, ValueError):
            log.warning("hint not applied to ticket %s", ticket_id, exc_info=True)
            return False
        if change.activity is None:
            return False

        def deliver() -> None:
            lifecycle.deliver(change)

        if later is None:
            deliver()
        else:
            later.append(deliver)
        return True

    def _confirmed_reply(self, done: dto.ChatConfirmResponse, lang: ReplyLang) -> str:
        text = self._text(lang)
        if done.ticket_id is None:
            return text["generic"]
        ticket = self._repo.get_ticket(done.ticket_id)
        return text["confirmed"].format(
            number=ticket_number(ticket.id), department=self._department(ticket.office, lang)
        )

    # ------------------------------------------------------------------ helpers

    def _claims(self, token: str | None, alias: str) -> tuple[ProposalClaims | None, bool]:
        """The verified claims, and whether a token was sent but is not valid (expired, forged, foreign)."""
        if not token:
            return None, False
        try:
            return verify(self._key, token, alias, self._clock.now()), False
        except InvalidInput:
            return None, True

    def _context(self, caller: Actor, lang: ReplyLang, claims: ProposalClaims | None) -> ChatContext:
        first_name: str | None = None
        if self._journey is not None and caller.alias:
            try:
                contact = self._journey.contact_for_alias(caller.alias)
            except CampusPulseError:
                contact = None
            words = _NAME.findall(contact.display_name) if contact is not None else []
            first_name = words[0][:FIRST_NAME_CHARS] if words else None
        proposal = None
        if claims is not None:
            proposal = f"{self._department(claims.office, 'en')}: {claims.text[:200]}"
        return ChatContext(
            role=caller.role,
            lang=lang,
            first_name=first_name,
            announcements=self._announcement_lines(),
            proposal=proposal,
        )

    def _announcement_lines(self) -> list[str]:
        if self._announcements is None:
            return []
        try:
            live = self._announcements.live_announcements(self._clock.now(), ANNOUNCEMENTS_SHOWN)
        except CampusPulseError:
            log.warning("announcements unavailable for the chat", exc_info=True)
            return []
        return [f"[{a.kind}] {a.title}: {a.body}"[:ANNOUNCEMENT_CHARS] for a in live]

    def _text(self, lang: ReplyLang) -> Mapping[str, str]:
        return self._cfg.templates[lang]

    def _department(self, office: str, lang: ReplyLang) -> str:
        return self._cfg.departments[lang].get(office, office)

    def _clean(self, reply: str, department: str | None = None) -> bool:
        """The reply post-check: no banned phrase and (for proposals) the department's name."""
        low = reply.lower()
        if any(phrase.lower() in low for phrase in self._cfg.banned):
            return False
        return department is None or department.lower() in low

    def _safe(self, reply: str, fallback: str) -> str:
        return reply if self._clean(reply) else fallback


def _request_text(messages: Sequence[dto.ChatMessage]) -> str:
    """The user messages after the last assistant message of kind proposal or ticket, last 1000 chars."""
    start = 0
    for i, m in enumerate(messages):
        if m.role == "assistant" and m.kind in ("proposal", "ticket"):
            start = i + 1
    joined = "\n".join(m.content.strip() for m in messages[start:] if m.role == "user")
    return joined[-REQUEST_TEXT_MAX:]


def _lang_of(req: NormalizedRequest) -> ReplyLang:
    return "en" if req.lang == Lang.EN else "ar"


def _reply_lang(messages: Sequence[dto.ChatMessage], req: NormalizedRequest) -> ReplyLang:
    """Arabic script or Arabizi in -> Arabic out. A very short English-looking message follows the last
    Arabic one ("yes", "ok")."""
    if _lang_of(req) == "ar" or _ARABIC.search(messages[-1].content):
        return "ar"
    if len(messages[-1].content.split()) <= SHORT_MESSAGE_WORDS:
        for m in reversed(messages[:-1]):
            if m.role == "user" and _ARABIC.search(m.content):
                return "ar"
    return "en"


def _question_text(q: dto.ClarificationOut) -> str:
    options = " / ".join(o.text for o in q.options)
    return f"{q.text}\n{options}" if options else q.text
