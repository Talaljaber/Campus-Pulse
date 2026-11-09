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
   `ticket` or `declined` (P10.21; the issue preparer sees only these too), last 1000 chars ->
   `_propose` (a question to ask, or a proposal phrased by a
   second LLM call and post-checked: it must name the localized department and use none of the banned
   phrases, else the template sentence is used);
5. intent `confirm` with a valid token -> confirm, the reply is the template "Request recorded: #n for
   <department> (demo, no real department was contacted)"; without a valid token nothing is recorded;
6. `decline` -> `clear_proposal`; `chat` / `announcement` -> the LLM reply (banned phrases -> template).
7. P10.18 (docs/plan/p10/P10.18_chat_corrections.md). The agent sees the caller's recent tickets (open, or
   solved/closed in the last 30 days) as a DATA block, and its `ticket_refs` are only hints checked against
   that list, so another person's ticket is never shown or touched:
   - `status` -> `tickets` (status cards) for the refs, else for every listed ticket;
   - `correct` -> a proposal for the corrected text whose token carries `replaces` (the old open ticket),
     returned with `correction`; the reply is a template asking "replace #n or keep both";
   - `withdraw` -> `withdraw` (the open ticket to close; the client closes it with the student action);
   - `separate` with a pending correction -> confirm with `replace=false`; a typed "yes" (`confirm`) on a
     correction confirms with `replace=true`;
   - a repeat the issue preparer names (`duplicate_of`) whose text mentions another room or building than
     the open ticket becomes the same correction proposal instead of a follow-up comment.
   Confirming with `replace` opens the corrected ticket, then (only when the token's `replaces` is the
   caller's own open ticket) comments on the old ticket and closes it, and returns it as `closed_ticket`.
   Every reply that says something was recorded or closed is a server template.
8. P10.19 (docs/plan/p10/P10.19_knowledge_base.md). Every LLM turn searches the admin knowledge base with
   the last user message (`KnowledgeSearch`: top `KNOWLEDGE_HITS` passages at or above
   `KNOWLEDGE_MIN_SIM`) and offers the hits as CURRENT SOURCES (`knowledge:<document id>`). The response's
   `sources` are the announcements and documents the model cited in `source_ids`, kept only when the
   model's own words are the reply and the id was offered this turn. A failing knowledge read is logged
   and the turn goes on without it.

`preview(cmd, caller)` is the plain-form path (no LLM): classify, decision policy with a one-question budget,
the route plan and FAQ answer, the staff-correction hint (raise-only priority). It writes nothing (except a
distress message, which is triaged and persisted like any other distress).

`confirm(cmd, caller, later)` runs `TriageUseCase.run(chat_confirmed=True)` on the token's text, applies the
hint as a "past correction" re-route (`TicketLifecycleUseCase.apply_hint`) and hands the follow-up work to
`later` (a list the route turns into background tasks: first the hint's delivery, then `on_created`).
Errors: `InvalidInput` (422) for a bad, expired, foreign or already used token or an invalid conversation.

A token is single-use: the first confirm claims its signature (the part after the ".") in an in-process,
thread-safe record before triage runs, so a typed "yes" twice or a retried request cannot open two tickets;
a failed triage releases the claim so the user can retry. The record is pruned on each call and bounded
(`CONSUMED_MAX`). It relies on the single uvicorn worker (docs/ARCHITECTURE: one worker) and resets on a
restart (the token's own 30-minute expiry still applies).
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases import responses as out
from campuspulse_ai.application.use_cases.act import ActUseCase
from campuspulse_ai.application.use_cases.announcement_ports import AnnouncementStore
from campuspulse_ai.application.use_cases.chat_claims import ChatClaimStore, InMemoryChatClaimStore
from campuspulse_ai.application.use_cases.chat_ports import (
    AgentReply,
    ChatAgent,
    ChatContext,
    GroundingSource,
    ProposalFacts,
    ReplyLang,
    Turn,
)
from campuspulse_ai.application.use_cases.issue_context import (
    IssueContextPreparer,
    OpenTicket,
    PreparedIssue,
)
from campuspulse_ai.application.use_cases.journey_ports import JourneyStore
from campuspulse_ai.application.use_cases.knowledge_ports import KnowledgeHit, KnowledgeSearch
from campuspulse_ai.application.use_cases.ports import Actor, Clarifier, TriageClassifier
from campuspulse_ai.application.use_cases.proposals import ProposalClaims, sign, verify
from campuspulse_ai.application.use_cases.sync_ticket import ticket_title
from campuspulse_ai.application.use_cases.ticket_lifecycle import LifecycleChange, TicketLifecycleUseCase
from campuspulse_ai.application.use_cases.triage import DISTRESS, TriageUseCase
from campuspulse_ai.domain.entities import CoreResult, Prediction, Ticket
from campuspulse_ai.domain.errors import CampusPulseError, InvalidInput, StoreError
from campuspulse_ai.domain.journey import HintMatch, StudentAction, ticket_number
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
    TicketStatus,
)

log = logging.getLogger(__name__)

REQUEST_TEXT_MAX = 1000
CONSUMED_MAX = 10_000
ALREADY_SENT = "this proposal was already sent"
ASKED_IN_CHAT = "chat"
"""Placeholder question id counted once the requester wrote more than one message (one-question budget)."""
ADVICE_BLOCKING_FLAGS = frozenset({"injection", "queue_jump"})
"""A message with one of these flags never gets a priority raise from the issue preparer."""
DISTRESS_QUESTION_ID = "distress"
MORE_DETAIL_ID = "more_detail"
ANNOUNCEMENTS_SHOWN = 5
OPEN_TICKETS_SHOWN = 5
OPEN_TICKET_TEXT_CHARS = 300
ANNOUNCEMENT_CHARS = 300
KNOWLEDGE_HITS = 3
"""P10.19: the closest knowledge-base passages offered to the model per turn (at or above the floor)."""
SOURCES_SHOWN = 5
"""P10.19: at most this many cited sources on a reply ("From: <title>")."""
SOURCE_TITLE_CHARS = 200
FIRST_NAME_CHARS = 30
SHORT_MESSAGE_WORDS = 3
NEIGHBORS_SHOWN = 3
MY_TICKETS_SHOWN = 8
"""P10.18: the caller's recent tickets the agent sees (open, or solved/closed within `RECENT_DAYS`)."""
RECENT_DAYS = 30
MY_TICKET_LINE_CHARS = 200
CARDS_MAX = 10
RUNNING = frozenset({TicketStatus.NEW, TicketStatus.IN_PROGRESS})
REPLACED_COMMENT = "Closed by the requester: replaced by #{number} (corrected details)."
"""The public comment on a ticket a confirmed correction closes (staff read it, so it is in English)."""
_ARABIC = re.compile("[؀-ۿ]")
_NAME = re.compile(r"[^\W\d_]+")
_TEMPLATE_KEYS = (
    "proposal", "proposal_faq", "more_detail", "confirmed", "confirmed_none", "no_proposal", "expired",
    "generic", "fallback", "declined", "already_open", "priority_raised",
    "correction", "withdraw", "withdraw_which", "withdraw_none", "status", "status_none",
    "confirmed_replaced",
)  # fmt: skip
_ROOM = re.compile(r"(?<![A-Za-z0-9])([A-Za-z])-?(\d{3,4})(?!\d)")
"""A room code such as H302 or M-204 (a Latin building letter and the room number)."""
_ROOM_WORD = re.compile(
    r"(?:\broom|\bga3a|\bghorfe|قاعة|غرفة|قاعه|غرفه)\s*#?\s*(\d{2,4})(?!\d)", re.IGNORECASE
)
_BUILDING = re.compile(r"(?:\bbuilding|\bbldg|\bmabna|مبنى|مبنا)\s*([A-Za-z])(?![A-Za-z])", re.IGNORECASE)
_NUMBER_IN_REPLY = re.compile(r"(?<![0-9A-Za-z])(?=[A-F]*[0-9])[0-9A-F]{8}(?![0-9A-Za-z])", re.IGNORECASE)
_ACTION_CLAIM = re.compile(
    r"\bI(?:'ve| have| just)? (?:closed|cancell?ed|withdrawn|recorded|opened|submitted)\b|"
    r"\b(?:has|have) been (?:closed|cancell?ed|withdrawn|recorded)\b|"
    r"تم (?:إغلاق|اغلاق|تسجيل|إلغاء|الغاء)",
    re.IGNORECASE,
)
"""A model reply of a `chat` or `decline` turn must not claim a ticket was recorded or closed: nothing was."""
_OFFICES = ("registrar", "it", "finance", "transport", "facilities", "academic")
Later = list[Callable[[], None]]
"""Follow-up work of one call (the hint's delivery); the route runs it after the response."""


def _norm(text: str) -> str:
    """Words only, lower case: two texts that differ in case, spacing or punctuation compare equal."""
    return " ".join(re.findall(r"\w+", text.casefold()))


@dataclass(frozen=True, slots=True)
class _Open:
    """One open ticket of the requester with the text it was opened from."""

    ticket: Ticket
    text: str
    created_at: datetime | None = None

    @property
    def number(self) -> str:
        return ticket_number(self.ticket.id)

    @property
    def running(self) -> bool:
        return self.ticket.status in RUNNING

    def card(self) -> dto.ChatTicketOut:
        """The ticket as a chat status card (P10.18)."""
        t = self.ticket
        return dto.ChatTicketOut(
            ticket_id=t.id,
            number=self.number,
            title=ticket_title(t),
            office=t.office,
            category=t.category,
            priority=t.priority,
            status=cast(dto.ChatTicketStatus, str(t.status)),
            awaiting_student=t.awaiting_student,
            created_at=self.created_at or t.clock_started_at or t.sla_due_at,
            resolved_at=t.resolved_at,
        )

    def for_preparer(self) -> OpenTicket:
        return OpenTicket(self.number, self.text, str(self.ticket.priority), str(self.ticket.status))


@dataclass(frozen=True, slots=True)
class _Issue:
    """What the issue preparation gave one turn: a clean request text, a priority recommendation, the open
    ticket it says this message is about, and the requester's open tickets."""

    text: str | None = None
    advice: Priority | None = None
    duplicate_of: str | None = None
    open_tickets: Sequence[_Open] = ()
    mine: Sequence[_Open] = ()
    """P10.18: the caller's recent tickets (the agent's "THE PERSON'S REQUESTS" block)."""


class DuplicateOpenTicket(InvalidInput):
    """The requester already has an open ticket with this very text (a second confirmation of it)."""

    def __init__(self, ticket: Ticket) -> None:
        super().__init__(f"you already have an open request #{ticket_number(ticket.id)} for this")
        self.ticket = ticket


@dataclass(frozen=True, slots=True)
class ChatConfig:
    """`config/chat_agent.yaml` as the use case needs it (the composition root parses the YAML)."""

    hint_min_sim: float
    proposal_ttl_min: int
    departments: Mapping[str, Mapping[str, str]]
    templates: Mapping[str, Mapping[str, str]]
    banned: tuple[str, ...]
    priorities: Mapping[str, Mapping[str, str]]

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
        priorities: dict[str, dict[str, str]] = {}
        for lang in ("en", "ar"):
            names = (data.get("departments") or {}).get(lang) or {}
            texts = (data.get("templates") or {}).get(lang) or {}
            words = (data.get("priorities") or {}).get(lang) or {}
            for level in ("low", "medium", "high"):
                if not isinstance(words.get(level), str):
                    raise ValueError(f"chat_agent.yaml: priorities.{lang}.{level} is missing")
            priorities[lang] = dict(words)
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
        return cls(float(sim), ttl, departments, templates, tuple(banned), priorities)


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
        claims: ChatClaimStore | None = None,
        preparer: IssueContextPreparer | None = None,
        knowledge: KnowledgeSearch | None = None,
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
        self._claims_store = claims or InMemoryChatClaimStore()
        self._preparer = preparer
        self._knowledge = knowledge

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
        mine = self._my_tickets(alias)
        ctx = self._context(caller, lang, claims, mine, question=last.content)
        turns = [Turn(role=m.role, content=m.content) for m in messages]
        open_tickets = self._open_tickets(alias, mine)
        # The preparer writes the request text, so it sees only the current request: a dropped one (declined,
        # cleared) or an already recorded one must not leak into it (P10.21). The agent keeps the whole talk.
        current = turns[_request_start(messages):]
        agent_reply, prepared = self._reply_and_prepare(ctx, turns, open_tickets, current)
        if agent_reply is None:
            return self._fallback(lang)
        issue = _Issue(open_tickets=open_tickets, mine=mine)
        if prepared is not None:
            advice = Priority(prepared.priority_recommendation) if prepared.priority_recommendation else None
            issue = _Issue(prepared.classifier_text, advice, prepared.duplicate_of, open_tickets, mine)
        response = self._answer(
            agent_reply,
            cmd.proposal_token or "",
            messages,
            caller,
            lang,
            ctx,
            claims,
            token_bad,
            later,
            issue,
        )
        return _with_sources(response, agent_reply, ctx)

    def _open_tickets(self, alias: str, known: Sequence[_Open] = ()) -> list[_Open]:
        """The requester's open tickets with their texts, newest first. A failing read gives none. `known`
        tickets (already read this turn) are reused instead of reading their request again."""
        if not alias:
            return []
        by_id = {o.ticket.id: o for o in known}
        try:
            tickets = self._repo.open_tickets_for_alias(alias, OPEN_TICKETS_SHOWN)
            found: list[_Open] = []
            for t in tickets:
                seen = by_id.get(t.id)
                if seen is not None:
                    found.append(_Open(t, seen.text, seen.created_at))
                    continue
                request = self._repo.get_request(t.request_id)
                found.append(_Open(t, request.raw_text[:OPEN_TICKET_TEXT_CHARS], request.created_at))
            return found
        except CampusPulseError:
            log.warning("open tickets unavailable for the chat", exc_info=True)
            return []

    def _my_tickets(self, alias: str) -> list[_Open]:
        """P10.18: the caller's recent tickets (open, or solved/closed in the last `RECENT_DAYS` days),
        newest first, at most `MY_TICKETS_SHOWN`. Only tickets whose request is the caller's own. A failing
        read gives none, never an error."""
        if not alias:
            return []
        since = self._clock.now() - timedelta(days=RECENT_DAYS)
        try:
            tickets = self._repo.recent_tickets_for_alias(alias, since, MY_TICKETS_SHOWN)
            mine: list[_Open] = []
            for t in tickets:
                request = self._repo.get_request(t.request_id)
                if request.alias == alias:
                    mine.append(_Open(t, request.raw_text[:OPEN_TICKET_TEXT_CHARS], request.created_at))
            return mine
        except CampusPulseError:
            log.warning("recent tickets unavailable for the chat", exc_info=True)
            return []

    def _reply_and_prepare(
        self,
        ctx: ChatContext,
        turns: Sequence[Turn],
        open_tickets: Sequence[_Open] = (),
        current: Sequence[Turn] | None = None,
    ) -> tuple[AgentReply | None, PreparedIssue | None]:
        """The agent's reply and, when enabled, the issue preparation. They run side by side so one slow
        model call does not double the wait. The preparation only enriches the turn (a clean request text
        and a priority recommendation), so when it fails the turn goes on without it."""
        agent = self._agent
        if agent is None:
            return None, None
        if self._preparer is None:
            return agent.reply(ctx, turns), None
        now = self._clock.now().isoformat()
        with ThreadPoolExecutor(max_workers=1) as pool:
            known = [o.for_preparer() for o in open_tickets]
            future = pool.submit(self._preparer.prepare, turns if current is None else current, now, known)
            reply = agent.reply(ctx, turns)
            try:
                prepared = future.result()
            except Exception:  # an advisory step must never take the chat down
                log.warning("issue preparation crashed; continuing without it", exc_info=True)
                prepared = None
        if prepared is None:
            log.info("issue preparation gave no usable result; using the plain request text")
        return reply, prepared

    def _answer(
        self,
        reply: AgentReply,
        cmd_token: str,
        messages: Sequence[dto.ChatMessage],
        caller: Actor,
        lang: ReplyLang,
        ctx: ChatContext,
        claims: ProposalClaims | None,
        token_bad: bool,
        later: Later | None,
        issue: _Issue | None = None,
    ) -> dto.ChatTurnResponse:
        issue = issue or _Issue()
        text = self._text(lang)
        intent: str = reply.intent
        if intent == "status":
            return self._status_turn(reply, issue.mine, lang)
        if intent == "withdraw":
            return self._withdraw_turn(reply, issue.mine, lang)
        if intent == "correct":
            target = _first_running(reply.ticket_refs, issue.mine)
            if target is not None:
                corrected = reply.corrected_text.strip() or _merged_text(target.text, _last_user(messages))
                return self._correction_turn(target, corrected, caller, lang, issue.advice)
            intent = "request"  # no open ticket of the caller to fix: an ordinary request
        if intent == "separate":
            if claims is not None and claims.replaces:
                return self._confirm_turn(cmd_token, claims, caller, lang, later, replace=False)
            intent = "request"
        if intent == "request":
            if issue.text is not None and not issue.text:
                return self._plain(text["more_detail"], clear=False)
            request_text = issue.text if issue.text is not None else _request_text(messages)
            repeat = self._repeat_turn(request_text, caller, lang, issue, later, _last_user(messages))
            if repeat is not None:
                return repeat
            return self._proposal_turn(request_text, caller, lang, ctx, issue.advice)
        if intent == "confirm":
            if claims is None:  # nothing to confirm: never let the model's words claim a recorded request
                return self._plain(text["expired"] if token_bad else text["no_proposal"], clear=token_bad)
            # A typed "yes" on a correction replaces the old ticket (the token says which one).
            return self._confirm_turn(cmd_token, claims, caller, lang, later, replace=bool(claims.replaces))
        if intent == "decline":
            return self._plain(self._unclaimed(reply.reply, text["declined"]), clear=True)
        return self._plain(self._unclaimed(reply.reply, text["generic"]), clear=False)

    def _confirm_turn(
        self,
        cmd_token: str,
        claims: ProposalClaims,
        caller: Actor,
        lang: ReplyLang,
        later: Later | None,
        *,
        replace: bool,
    ) -> dto.ChatTurnResponse:
        text = self._text(lang)
        try:
            done = self._confirm_claims(cmd_token, claims, caller, later, replace=replace)
        except DuplicateOpenTicket as dup:  # the same request is already open
            return self._plain(self._already_open(dup.ticket, lang), clear=True)
        except InvalidInput:  # the proposal was already sent
            return self._plain(text["expired"], clear=True)
        return dto.ChatTurnResponse(
            mode="agent",
            reply=self._confirmed_reply(done, lang),
            proposal=None,
            ticket_id=done.ticket_id,
            triage=done.triage,
            clear_proposal=True,
            tickets=[done.closed_ticket] if done.closed_ticket is not None else [],
        )

    def _status_turn(self, reply: AgentReply, mine: Sequence[_Open], lang: ReplyLang) -> dto.ChatTurnResponse:
        """Status cards of the caller's own tickets: the ones the agent named, else all of them. The agent's
        words are kept only when they pass the post-check and name no ticket number outside the list."""
        text = self._text(lang)
        if not mine:
            return self._plain(text["status_none"], clear=False)
        picked = _pick(reply.ticket_refs, mine) or list(mine)
        known = {o.number for o in mine}
        named = {m.upper() for m in _NUMBER_IN_REPLY.findall(reply.reply)}
        words = reply.reply if self._clean(reply.reply) and named <= known else text["status"]
        return dto.ChatTurnResponse(
            mode="agent",
            reply=words,
            proposal=None,
            ticket_id=None,
            triage=None,
            clear_proposal=False,
            tickets=[o.card() for o in picked[:CARDS_MAX]],
        )

    def _withdraw_turn(
        self, reply: AgentReply, mine: Sequence[_Open], lang: ReplyLang
    ) -> dto.ChatTurnResponse:
        """Ask to confirm closing one open ticket of the caller. Nothing is closed here: the client calls the
        student-action endpoint after the requester confirms. Without a valid ref the open tickets are
        shown as cards so the requester can pick one."""
        text = self._text(lang)
        target = _first_running(reply.ticket_refs, mine)
        if target is None:
            running = [o for o in mine if o.running]
            if not running:
                return self._plain(text["withdraw_none"], clear=False)
            return dto.ChatTurnResponse(
                mode="agent",
                reply=text["withdraw_which"],
                proposal=None,
                ticket_id=None,
                triage=None,
                clear_proposal=False,
                tickets=[o.card() for o in running[:CARDS_MAX]],
            )
        return dto.ChatTurnResponse(
            mode="agent",
            reply=text["withdraw"].format(number=target.number),
            proposal=None,
            ticket_id=None,
            triage=None,
            clear_proposal=False,
            withdraw=target.card(),
        )

    def _correction_turn(
        self,
        target: _Open,
        corrected: str,
        caller: Actor,
        lang: ReplyLang,
        advice: Priority | None = None,
    ) -> dto.ChatTurnResponse:
        """A proposal for the corrected request whose token says it replaces `target`, plus the
        `correction` card. The classifier and the decision policy still decide; a question may come first.
        A "correction" with the very same words as the open ticket is a repeat: nothing new is proposed."""
        if _norm(corrected) == _norm(target.text):
            return self._plain(self._already_open(target.ticket, lang), clear=True)
        asked = [ASKED_IN_CHAT] if "\n" in corrected else []
        proposal = self._propose(corrected, asked, None, caller, advice, replaces=target.ticket.id)
        if proposal.question is not None:
            return self._plain(_question_text(proposal.question), clear=False)
        reply = self._text(lang)["correction"].format(
            number=target.number, department=self._department(proposal.office, lang)
        )
        return dto.ChatTurnResponse(
            mode="agent",
            reply=reply,
            proposal=proposal,
            ticket_id=None,
            triage=None,
            clear_proposal=False,
            correction=dto.ChatCorrectionOut(
                ticket=target.card(), old_text=target.text[:OPEN_TICKET_TEXT_CHARS]
            ),
        )

    def _repeat_turn(
        self,
        request_text: str,
        caller: Actor,
        lang: ReplyLang,
        issue: _Issue,
        later: Later | None,
        said: str = "",
    ) -> dto.ChatTurnResponse | None:
        """The requester already has an open ticket for this issue: no new ticket. When the message adds
        urgency (an exam, a deadline) the existing ticket is raised to the new priority, otherwise the
        requester is told which ticket is already open. None = not a repeat, go on with a proposal."""
        match = self._match_open(request_text, issue)
        if match is None:
            return None
        proposal = self._propose(request_text, [], None, caller, issue.advice)
        if proposal.question is not None or str(proposal.category) != str(match.ticket.category):
            return None  # unclear, or a different kind of problem: treat it as a new request
        new_words = said.strip() or request_text
        if _place_changed(match.text, new_words):  # same problem, other room: a fix, not a follow-up
            return self._correction_turn(
                match, _merged_text(match.text, new_words), caller, lang, issue.advice
            )
        wanted = Priority(proposal.priority)
        text = self._text(lang)
        lifecycle = self._lifecycle
        raised = False
        if lifecycle is not None and wanted.rank > match.ticket.priority.rank:
            try:
                change = lifecycle.raise_priority(match.ticket.id, wanted)
            except (CampusPulseError, ValueError):
                log.warning("priority not raised on ticket %s", match.ticket.id, exc_info=True)
                change = None
            if change is not None and change.activity is not None:
                raised = True
                self._later(lifecycle, change, later)
        if lifecycle is not None and said.strip() and _norm(said) != _norm(match.text):
            self._comment_follow_up(lifecycle, match.ticket.id, caller, said, later)
        if raised:
            word = self._priority_word(wanted, lang)
            reply = text["priority_raised"].format(number=match.number, priority=word)
            return self._plain(reply, clear=True)
        return self._plain(self._already_open(match.ticket, lang), clear=True)

    @staticmethod
    def _later(lifecycle: TicketLifecycleUseCase, change: LifecycleChange, later: Later | None) -> None:
        def deliver() -> None:
            lifecycle.deliver(change)

        if later is None:
            deliver()
        else:
            later.append(deliver)

    def _comment_follow_up(
        self, lifecycle: TicketLifecycleUseCase, ticket_id: str, caller: Actor, said: str, later: Later | None
    ) -> None:
        """The student's own follow-up words go on the open ticket as a public comment, which also emails
        the office the way any requester reply does. Best effort: a failure never breaks the chat."""
        try:
            change = lifecycle.comment(ticket_id, caller, said.strip())
        except (CampusPulseError, ValueError):
            log.warning("follow-up not added to ticket %s", ticket_id, exc_info=True)
            return
        self._later(lifecycle, change, later)

    @staticmethod
    def _match_open(request_text: str, issue: _Issue) -> _Open | None:
        """The open ticket the preparer named, else one opened from this very text."""
        if issue.duplicate_of:
            named = next((o for o in issue.open_tickets if o.number == issue.duplicate_of), None)
            if named is not None:
                return named
        wanted = _norm(request_text)
        return next((o for o in issue.open_tickets if wanted and _norm(o.text) == wanted), None)

    def _already_open(self, ticket: Ticket, lang: ReplyLang) -> str:
        return self._text(lang)["already_open"].format(
            number=ticket_number(ticket.id), priority=self._priority_word(ticket.priority, lang)
        )

    def _priority_word(self, priority: Priority, lang: ReplyLang) -> str:
        return self._cfg.priorities[lang].get(str(priority), str(priority))

    def _guard_duplicate(self, alias: str, text: str, request_id: str, replaces: str | None = None) -> None:
        """Refuses a confirmation whose text is already open as another ticket of the requester. The ticket
        this very confirmation made (same request id) never counts, so a repeated confirm still returns it;
        neither does the ticket a correction replaces (`replaces`)."""
        wanted = _norm(text)
        if not wanted:
            return
        for open_ticket in self._open_tickets(alias):
            if open_ticket.ticket.id == replaces:
                continue
            if open_ticket.ticket.request_id != request_id and _norm(open_ticket.text) == wanted:
                raise DuplicateOpenTicket(open_ticket.ticket)

    def _proposal_turn(
        self,
        request_text: str,
        caller: Actor,
        lang: ReplyLang,
        ctx: ChatContext,
        advice: Priority | None = None,
    ) -> dto.ChatTurnResponse:
        asked = [ASKED_IN_CHAT] if "\n" in request_text else []
        proposal = self._propose(request_text, asked, None, caller, advice)
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

    def _propose(
        self,
        text: str,
        asked: Sequence[str],
        answer: str | None,
        caller: Actor,
        advice: Priority | None = None,
        replaces: str | None = None,
    ) -> dto.ProposalOut:
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
        if advice is not None and question is None and ADVICE_BLOCKING_FLAGS.isdisjoint(core.flags):
            # The preparer's recommendation (evidence-backed) can only raise the priority; a message that
            # looks like an injection or a queue-jump never gets a raise from it.
            priority = max(priority, advice, key=lambda p: p.rank)
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
                caller.alias or "", full, str(category), str(priority), plan.office, hint_id, exp, replaces
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
        return self._confirm_claims(cmd.proposal_token, claims, caller, later, replace=cmd.replace)

    def _confirm_claims(
        self,
        token: str,
        claims: ProposalClaims,
        caller: Actor,
        later: Later | None,
        *,
        replace: bool = False,
    ) -> dto.ChatConfirmResponse:
        """Claim the token durably; repeated completed confirms return the stored result.

        `replace` (P10.18) closes the token's `replaces` ticket after the new ticket is opened; it is ignored
        for a token without that claim."""
        signature = token.partition(".")[2]
        digest = hashlib.sha256(signature.encode("ascii")).hexdigest()
        request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"campuspulse-chat:{digest}"))
        self._guard_duplicate(caller.alias or "", claims.text, request_id, claims.replaces)
        claim = self._claims_store.claim(
            digest, caller.alias or "", request_id, datetime.fromtimestamp(claims.exp, tz=UTC)
        )
        if claim.status == "completed" and claim.result is not None:
            return claim.result
        if claim.status != "claimed":
            raise InvalidInput(ALREADY_SENT if claim.status == "in_progress" else "invalid proposal claim")
        triage = self._triage.run(
            dto.TriageRequest(text=claims.text, student_alias=caller.alias or "", chat_confirmed=True),
            request_id=request_id,
        )
        action = triage.action
        ticket_id = action.ticket_id if action is not None else None
        applied = False
        if ticket_id and claims.hint_id and action is not None and action.type == ActionType.TICKET:
            applied = self._apply_hint(ticket_id, claims, later)
        closed: dto.ChatTicketOut | None = None
        if ticket_id and action is not None and action.type == ActionType.TICKET:
            self._raise_to_reviewed(ticket_id, claims, triage, later)
            if replace and claims.replaces:
                closed = self._close_replaced(claims.replaces, ticket_id, caller, later)
        result = dto.ChatConfirmResponse(
            triage=triage, ticket_id=ticket_id, hint_applied=applied, closed_ticket=closed
        )
        if not self._claims_store.complete(digest, result):
            raise StoreError("chat confirmation result could not be recorded")
        return result

    def _close_replaced(
        self, old_id: str, new_id: str, caller: Actor, later: Later | None
    ) -> dto.ChatTicketOut | None:
        """Close the ticket a confirmed correction replaces, only when it is the caller's own and still open.
        The public comment goes first: a requester comment on a closed ticket would reopen it. Best effort:
        a failure leaves the old ticket as it is and the new one stays recorded."""
        lifecycle, alias = self._lifecycle, caller.alias or ""
        if lifecycle is None or not alias or old_id == new_id:
            return None
        try:
            ticket = self._repo.get_ticket(old_id)
            request = self._repo.get_request(ticket.request_id)
        except CampusPulseError:
            log.warning("replaced ticket %s could not be read", old_id, exc_info=True)
            return None
        if request.alias != alias or ticket.status not in RUNNING:
            return None
        note = REPLACED_COMMENT.format(number=ticket_number(new_id))
        self._comment_follow_up(lifecycle, old_id, caller, note, later)
        try:
            change = lifecycle.student_action(old_id, caller, StudentAction.CLOSE)
        except (CampusPulseError, ValueError):
            log.warning("replaced ticket %s was not closed", old_id, exc_info=True)
            return None
        self._later(lifecycle, change, later)
        return _Open(change.ticket, request.raw_text, request.created_at).card()

    def _raise_to_reviewed(
        self, ticket_id: str, claims: ProposalClaims, triage: dto.TriageResponse, later: Later | None
    ) -> None:
        """The priority the requester reviewed is a floor. Confirmation triages the same text again, which can
        rate it lower than the proposal (the proposal was raised from what the requester described), so the
        ticket is raised to match. Never lowers anything."""
        lifecycle = self._lifecycle
        decided = triage.priority.label if triage.priority is not None else None
        reviewed = Priority(claims.priority)
        if lifecycle is None or decided is None or reviewed.rank <= decided.rank:
            return
        try:
            change = lifecycle.raise_priority(ticket_id, reviewed)
        except (CampusPulseError, ValueError):
            log.warning("reviewed priority not applied to ticket %s", ticket_id, exc_info=True)
            return
        if change.activity is None:
            return

        def deliver() -> None:
            lifecycle.deliver(change)

        if later is None:
            deliver()
        else:
            later.append(deliver)

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
        number, department = ticket_number(ticket.id), self._department(ticket.office, lang)
        if done.closed_ticket is not None:
            return text["confirmed_replaced"].format(
                number=number, department=department, old=done.closed_ticket.number
            )
        return text["confirmed"].format(number=number, department=department)

    # ------------------------------------------------------------------ helpers

    def _claims(self, token: str | None, alias: str) -> tuple[ProposalClaims | None, bool]:
        """The verified claims, and whether a token was sent but is not valid (expired, forged, foreign)."""
        if not token:
            return None, False
        try:
            return verify(self._key, token, alias, self._clock.now()), False
        except InvalidInput:
            return None, True

    def _context(
        self,
        caller: Actor,
        lang: ReplyLang,
        claims: ProposalClaims | None,
        mine: Sequence[_Open] = (),
        question: str = "",
    ) -> ChatContext:
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
            if claims.replaces:
                proposal += f" (a correction: it replaces request #{ticket_number(claims.replaces)})"
        announcements, sources = self._announcement_context()
        return ChatContext(
            role=caller.role,
            lang=lang,
            first_name=first_name,
            announcements=announcements,
            proposal=proposal,
            sources=(*sources, *self._knowledge_context(question)),
            requests=[self._request_line(o) for o in mine],
        )

    def _request_line(self, o: _Open) -> str:
        """One line of the "THE PERSON'S REQUESTS" block: number, status, office, created date, text."""
        created = o.created_at.date().isoformat() if o.created_at is not None else "unknown"
        words = " ".join(o.text.split())[:MY_TICKET_LINE_CHARS]
        office = self._department(o.ticket.office, "en")
        status = o.ticket.status
        return f"#{o.number} | status: {status} | office: {office} | created: {created} | text: {words}"

    def _announcement_lines(self) -> list[str]:
        return self._announcement_context()[0]

    def _announcement_context(self) -> tuple[list[str], tuple[GroundingSource, ...]]:
        if self._announcements is None:
            return [], ()
        try:
            live = self._announcements.live_announcements(self._clock.now(), ANNOUNCEMENTS_SHOWN)
        except CampusPulseError:
            log.warning("announcements unavailable for the chat", exc_info=True)
            return [], ()
        lines = [f"[{a.kind}] {a.title}: {a.body}"[:ANNOUNCEMENT_CHARS] for a in live]
        sources = tuple(
            GroundingSource(
                id=f"announcement:{a.id}",
                kind="announcement",
                text=line,
                scope=_notice_scope(line),
                title=a.title,
            )
            for a, line in zip(live, lines, strict=True)
        )
        return lines, sources

    def _knowledge_context(self, question: str) -> tuple[GroundingSource, ...]:
        """P10.19: the knowledge-base passages closest to the person's last message, one source per
        document (its best passages joined, best first). Any failure (store, encoder) gives none: the
        knowledge base only enriches a turn, it never breaks one."""
        if self._knowledge is None or not question.strip():
            return ()
        try:
            hits = list(self._knowledge.search(question, KNOWLEDGE_HITS))
        except Exception:  # an advisory read must never take the chat down
            log.warning("knowledge base unavailable for the chat", exc_info=True)
            return ()
        by_doc: dict[str, list[KnowledgeHit]] = {}
        for hit in hits:
            by_doc.setdefault(hit.document_id, []).append(hit)
        return tuple(
            GroundingSource(
                id=f"knowledge:{doc_id}",
                kind="knowledge",
                text=f"{group[0].title}: " + "\n...\n".join(h.text for h in group),
                title=group[0].title,
            )
            for doc_id, group in by_doc.items()
        )

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

    def _unclaimed(self, reply: str, fallback: str) -> str:
        """`_safe`, and the reply must not claim that a ticket was recorded or closed (nothing was)."""
        return fallback if _ACTION_CLAIM.search(reply) else self._safe(reply, fallback)


def _with_sources(
    response: dto.ChatTurnResponse, reply: AgentReply, ctx: ChatContext
) -> dto.ChatTurnResponse:
    """P10.19: `sources` = the announcements and knowledge documents the model cited, but only when its
    own words are the reply (a server template cites nothing) and only ids really offered this turn; an id
    the model made up is dropped. In citation order, without repeats, at most `SOURCES_SHOWN`."""
    if response.reply != reply.reply or not reply.source_ids:
        return response
    offered = {s.id: s for s in ctx.sources if s.kind in ("announcement", "knowledge")}
    cited: list[dto.ChatSourceOut] = []
    for source_id in dict.fromkeys(reply.source_ids):
        source = offered.get(source_id)
        if source is None:
            continue
        kind: Literal["announcement", "knowledge"] = (
            "knowledge" if source.kind == "knowledge" else "announcement"
        )
        title = " ".join(source.title.split())[:SOURCE_TITLE_CHARS] or kind
        cited.append(dto.ChatSourceOut(id=source.id, kind=kind, title=title))
        if len(cited) == SOURCES_SHOWN:
            break
    return response.model_copy(update={"sources": cited}) if cited else response


def _notice_scope(text: str) -> str:
    """Recognize only explicit place words; an unrecognized place stays unscoped."""
    low = text.casefold()
    for place in ("library", "المكتبة", "building m", "building c", "building a", "مبنى m", "مبنى c"):
        if place in low:
            return place
    return ""


def _request_start(messages: Sequence[dto.ChatMessage]) -> int:
    """Where the current request starts: after the last assistant message that ended one (a recorded ticket,
    or a proposal the person declined or the server cleared, P10.21)."""
    start = 0
    for i, m in enumerate(messages):
        if m.role == "assistant" and m.kind in ("ticket", "declined"):
            start = i + 1
    return start


def _request_text(messages: Sequence[dto.ChatMessage]) -> str:
    """The user messages of the current request (`_request_start`), last 1000 chars."""
    joined = "\n".join(m.content.strip() for m in messages[_request_start(messages):] if m.role == "user")
    return joined[-REQUEST_TEXT_MAX:]


def _ref(raw: str) -> str:
    return raw.strip().lstrip("#").strip().upper()


def _pick(refs: Sequence[str], mine: Sequence[_Open]) -> list[_Open]:
    """The caller's tickets the refs name, in ref order; refs to anything else are ignored."""
    by_number = {o.number: o for o in mine}
    picked: list[_Open] = []
    for raw in refs:
        found = by_number.get(_ref(raw))
        if found is not None and found not in picked:
            picked.append(found)
    return picked


def _first_running(refs: Sequence[str], mine: Sequence[_Open]) -> _Open | None:
    """The first ref that is an open (new or in progress) ticket of the caller."""
    return next((o for o in _pick(refs, mine) if o.running), None)


def _places(text: str) -> frozenset[str]:
    """Room codes (H302), room numbers and building letters a text names, normalized."""
    found = {f"{m.group(1).upper()}{m.group(2)}" for m in _ROOM.finditer(text)}
    found |= {f"room:{m.group(1)}" for m in _ROOM_WORD.finditer(text)}
    found |= {f"building:{m.group(1).upper()}" for m in _BUILDING.finditer(text)}
    return frozenset(found)


def _place_changed(old: str, new: str) -> bool:
    """The new words name a room or building the old request does not, and the old one named a place."""
    before = _places(old)
    return bool(before) and bool(_places(new) - before)


def _merged_text(old: str, new: str) -> str:
    """The corrected request: the old text with its one room code swapped for the one new room code, else
    the old text followed by the new words."""
    old_rooms = {f"{m.group(1).upper()}{m.group(2)}" for m in _ROOM.finditer(old)}
    new_rooms = {f"{m.group(1).upper()}{m.group(2)}" for m in _ROOM.finditer(new)} - old_rooms
    if len(old_rooms) == 1 and len(new_rooms) == 1:
        [room] = new_rooms
        return _ROOM.sub(room, old)
    new = new.strip()
    return f"{old.strip()}\n{new}" if new and _norm(new) not in _norm(old) else old.strip()


def _last_user(messages: Sequence[dto.ChatMessage]) -> str:
    """The student's latest message, in their own words."""
    return next((m.content for m in reversed(messages) if m.role == "user"), "")


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
