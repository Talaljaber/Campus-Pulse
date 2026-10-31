"""Backend-stream test fakes (P3.2, P3.3, P3.3a, P4.4, P4.6, P4.7).

Kept apart from `tests/fixtures/fakes.py` (created by the ML stream in P1.4) so the two streams do not
edit the same file; P3.8 re-exports these from `fakes.py` for `build_test()`.

- `make_core(...)`: a `CoreResult` with chosen probabilities, sets and flags.
- `FakeLAC`: a tiny LAC-style `ConformalPredictor` (set = labels with p ≥ 1 − q) until the ML
  stream's `LACConformal` (P1.14) exists.
- `FrozenClock`: a `Clock` fixed at one Asia/Amman instant.
- `ScriptedOracle`: a `LabelOracle` that replays scripted answers or errors and records its calls.
- `make_request(...)`: a `NormalizedRequest` without running the normalizer.
- `FakeNotifier`: a `Notifier` that records every message and can be scripted to fail.
- `make_outbox(...)`: an `OutboxMessage` ready to send.
- `FakeSink`, `make_ticket(...)`: a scripted `TicketSink` and a ticket builder.
- `FakeCalendar`: a `CalendarProvider` with one fixed slot that records `book` calls.
- `FakeCore` (P3.8): a `TriageClassifier` that returns scripted cores per text and applies
  clarification constraints like the real `TriageCore` (P1.15).
- `FakeFAQ`: a `FAQRetriever` that returns scripted hits.
"""

from __future__ import annotations

import dataclasses
import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from campuspulse_ai.domain.entities import (
    CoreResult,
    LLMCall,
    OracleAnswer,
    OracleContext,
    OutboxMessage,
    Ticket,
)
from campuspulse_ai.domain.errors import CalendarUnavailable, InvalidInput
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS, Category, Priority
from campuspulse_ai.domain.values import (
    ArtifactVersion,
    Booking,
    ClarificationConstraint,
    EvidenceVector,
    FAQHit,
    GuardVerdict,
    InboundEvent,
    Lang,
    Location,
    Money,
    NormalizedRequest,
    OfficeHours,
    PredictionSet,
    ProbabilityTarget,
    ProbVector,
    Slot,
    TicketLink,
    TicketStatus,
    Tier,
)

AMMAN = timezone(timedelta(hours=3), "Asia/Amman")


def prob_vector(labels: tuple[str, ...], given: Mapping[str, float] | None) -> ProbVector:
    """A ProbVector over `labels`; labels missing from `given` share the remaining mass equally."""
    given = dict(given or {})
    rest = [lab for lab in labels if lab not in given]
    remaining = max(0.0, 1.0 - math.fsum(given.values()))
    values = [given.get(lab, remaining / len(rest) if rest else 0.0) for lab in labels]
    total = math.fsum(values)
    return ProbVector(tuple(v / total for v in values), labels)


def make_core(
    p_cat: Mapping[str, float] | None = None,
    p_pri: Mapping[str, float] | None = None,
    *,
    set_cat: Sequence[str] | None = None,
    set_pri: Sequence[str] | None = None,
    flags: frozenset[str] = frozenset(),
    safety: bool = False,
    tier: Tier = Tier.TIER0,
) -> CoreResult:
    """A CoreResult; sets default to the argmax singleton of each vector."""
    pc = prob_vector(CATEGORY_LABELS, p_cat)
    pp = prob_vector(PRIORITY_LABELS, p_pri)
    return CoreResult(
        p_cat=pc,
        p_pri=pp,
        per_model={},
        flags=flags,
        set_cat=PredictionSet(frozenset(set_cat or [pc.argmax()])),
        set_pri=PredictionSet(frozenset(set_pri or [pp.argmax()])),
        ood_score=0.9,
        neighbors=(),
        evidence=EvidenceVector(flags={}),
        guard=GuardVerdict(kind="injection" if "injection_attempt" in flags else "none"),
        safety=safety,
        floors_applied=(),
        tier=tier,
        latency_ms=0,
        artifact=ArtifactVersion(name="v1", sha256="0" * 64),
    )


def make_request(
    text: str,
    *,
    core: str | None = None,
    lang: Lang = Lang.EN,
    is_arabizi: bool = False,
    model_text: str | None = None,
    location: Location | None = None,
    stated_urgency: bool = False,
) -> NormalizedRequest:
    """A NormalizedRequest with raw `text`; core/text_norm default to `text`, model_text to the core."""
    stripped = text if core is None else core
    return NormalizedRequest(
        raw=text,
        core=stripped,
        text_norm=stripped,
        model_text=model_text or stripped,
        lang=lang,
        is_arabizi=is_arabizi,
        stated_urgency=stated_urgency,
        truncated=False,
        location=location,
    )


@dataclass
class FakeLAC:
    """LAC-style conformal predictor: S = {l : p(l) ≥ 1 − q}; an empty set becomes the argmax singleton."""

    target: ProbabilityTarget
    q: float
    alpha: float = 0.1

    def predict_set(self, p: ProbVector) -> PredictionSet:
        chosen = frozenset(lab for lab, v in zip(p.labels, p.values, strict=True) if v >= 1.0 - self.q)
        return PredictionSet(chosen or frozenset({p.argmax()}))

    def calibrate(self, probs: Sequence[ProbVector], y: Sequence[str], groups: Sequence[str]) -> None:
        raise NotImplementedError

    def save(self, dir: Path) -> None:
        raise NotImplementedError

    @classmethod
    def load(cls, dir: Path) -> FakeLAC:
        raise NotImplementedError


@dataclass
class FrozenClock:
    """A Clock that always returns `at` (tz-aware, Asia/Amman by default)."""

    at: datetime = field(default_factory=lambda: datetime(2026, 11, 5, 9, 5, tzinfo=AMMAN))

    def now(self) -> datetime:
        return self.at


def fake_call(tier: Tier = Tier.TIER1, model: str = "scripted/model", *, cached: bool = False) -> LLMCall:
    return LLMCall(
        id=str(uuid.uuid4()),
        request_id=None,
        tier=tier,
        model=model,
        prompt_hash="0" * 64,
        tokens_in=0,
        tokens_out=0,
        cost=Money(0.0),
        latency_ms=0,
        cached=cached,
    )


ScriptStep = tuple[Category | None, Priority | None] | Exception


@dataclass
class ScriptedOracle:
    """A LabelOracle that replays `script` in order (a label pair or an exception to raise).

    Every call is recorded in `calls` as (request, allowed_cat, allowed_pri). When the script runs out,
    the last step repeats.
    """

    script: Sequence[ScriptStep]
    tier: Tier = Tier.TIER1
    model_id: str = "scripted/model"
    calls: list[tuple[NormalizedRequest, PredictionSet, PredictionSet]] = field(default_factory=list)

    def choose(
        self,
        req: NormalizedRequest,
        allowed_cat: PredictionSet,
        allowed_pri: PredictionSet,
        context: OracleContext,
    ) -> OracleAnswer:
        self.calls.append((req, allowed_cat, allowed_pri))
        step = self.script[min(len(self.calls), len(self.script)) - 1]
        if isinstance(step, Exception):
            raise step
        cat, pri = step
        return OracleAnswer(
            category=cat, priority=pri, rationale="scripted", call=fake_call(self.tier, self.model_id)
        )


def make_outbox(
    to_address: str,
    *,
    kind: Literal["email", "in_app", "whatsapp"] = "email",
    subject: str = "Your CampusPulse request",
    body: str = "We opened a ticket for you.",
    created_at: datetime | None = None,
) -> OutboxMessage:
    """A queued OutboxMessage (empty id: the repository assigns one)."""
    return OutboxMessage(
        id="",
        kind=kind,
        to_address=to_address,
        subject=subject,
        body=body,
        provider_id=None,
        status="queued",
        created_at=created_at or datetime(2026, 11, 5, 9, 5, tzinfo=AMMAN),
    )


@dataclass
class FakeNotifier:
    """A Notifier that records each message in `sent` and returns it as delivered.

    If `fail_with` is set, every call records the message and raises that error instead.
    """

    fail_with: Exception | None = None
    sent: list[OutboxMessage] = field(default_factory=list)

    @property
    def calls(self) -> int:
        return len(self.sent)

    def send(self, msg: OutboxMessage) -> OutboxMessage:
        self.sent.append(msg)
        if self.fail_with is not None:
            raise self.fail_with
        return dataclasses.replace(msg, status="sent", provider_id=f"fake:{len(self.sent)}")


SinkStep = Exception | None


@dataclass
class FakeSink:
    """A TicketSink that records every call as (method, ticket id) and replays `script`.

    Each create/update_status/close call takes the next `script` step: an exception is raised, None
    succeeds. When the script runs out every call succeeds. `create` returns a link whose
    external_id is `<name>-<ticket id>`, so repeated creates are idempotent like the real sinks.
    """

    name: str = "fake"
    script: list[SinkStep] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)
    inbound: InboundEvent | None = None

    def _step(self, method: str, ticket: Ticket) -> None:
        self.calls.append((method, ticket.id))
        step = self.script.pop(0) if self.script else None
        if step is not None:
            raise step

    def create(self, ticket: Ticket) -> TicketLink:
        self._step("create", ticket)
        return TicketLink(ticket_id=ticket.id, sink=self.name, external_id=f"{self.name}-{ticket.id}")

    def update_status(self, ticket: Ticket) -> None:
        self._step("update_status", ticket)

    def close(self, ticket: Ticket) -> None:
        self._step("close", ticket)

    def handle_inbound(self, payload: bytes, signature: str) -> InboundEvent | None:
        self.calls.append(("handle_inbound", signature))
        return self.inbound


def make_ticket(
    request_id: str,
    *,
    id: str = "",
    office: str = "registrar",
    category: Category = Category.REGISTRATION,
    priority: Priority = Priority.HIGH,
    status: TicketStatus = TicketStatus.OPEN,
    provisional: bool = False,
    sla_due_at: datetime | None = None,
    title: str = "Registration portal error on the last add/drop day",
    body: str = "The student cannot register CS 201; the portal shows an error and today is the deadline.",
) -> Ticket:
    """A Ticket for tests (defaults: an open Registration x high ticket due 6 Nov 09:05 Amman)."""
    return Ticket(
        id=id,
        request_id=request_id,
        incident_id=None,
        office=office,
        category=category,
        priority=priority,
        status=status,
        provisional=provisional,
        sla_due_at=sla_due_at or datetime(2026, 11, 6, 9, 5, tzinfo=AMMAN),
        title=title,
        body=body,
    )


@dataclass
class FakeCalendar:
    """A CalendarProvider: `find_slot` returns `slot`, `book` records the call and books it.

    `unavailable` makes `find_slot` raise CalendarUnavailable; `book_unavailable` does the same
    for `book`. Attendees are NOT checked here: the allow-list must be enforced before this point.
    """

    slot: Slot | None = None
    unavailable: bool = False
    book_unavailable: bool = False
    finds: int = 0
    booked: list[tuple[Slot, tuple[str, ...], str]] = field(default_factory=list)

    def find_slot(
        self, advisor_ids: Sequence[str], window: tuple[datetime, datetime], office_hours: OfficeHours
    ) -> Slot | None:
        self.finds += 1
        if self.unavailable:
            raise CalendarUnavailable("fake calendar down")
        return self.slot

    def book(self, slot: Slot, attendees: Sequence[str], title: str) -> Booking:
        if self.book_unavailable:
            raise CalendarUnavailable("fake calendar down")
        self.booked.append((slot, tuple(attendees), title))
        return Booking(
            slot=slot, attendees=tuple(attendees), title=title, provider="fake", external_id=slot.id
        )


@dataclass(frozen=True)
class _Scripted:
    core: CoreResult
    lang: Lang
    is_arabizi: bool
    model_text: str | None
    stated_urgency: bool
    location: Location | None


# Priority a feature constraint implies in FakeCore (the real priority head decides from the evidence).
FEATURE_PRIORITY: dict[str, Priority] = {"deadline_today": Priority.HIGH, "safety_risk": Priority.HIGH}


@dataclass
class FakeCore:
    """A `TriageClassifier` (the `TriageCore.classify` surface, P1.15) with scripted results.

    - `add(text, core, ...)` scripts the result for one raw text (exact match after `strip()`); any
      other text gets `default` (an IT Support x medium singleton by default).
    - Constraints are applied the way §2.0 step 7 does: a `category` constraint fixes `S_cat` and puts
      the probability mass on that label, a `priority` constraint does the same for priority, and a
      `feature` constraint sets that evidence flag and, per `FEATURE_PRIORITY`, fixes the priority.
    - A safety core is floored to high (step 6). Every call is recorded in `calls` as
      (raw, picked_location, constraints, memory).
    """

    default: CoreResult = field(default_factory=lambda: make_core({"IT Support": 0.9}, {"medium": 0.9}))
    script: dict[str, _Scripted] = field(default_factory=dict)
    calls: list[tuple[str, Location | None, tuple[ClarificationConstraint, ...], bool]] = field(
        default_factory=list
    )

    def add(
        self,
        text: str,
        core: CoreResult,
        *,
        lang: Lang = Lang.EN,
        is_arabizi: bool = False,
        model_text: str | None = None,
        stated_urgency: bool = False,
        location: Location | None = None,
    ) -> FakeCore:
        self.script[text.strip()] = _Scripted(core, lang, is_arabizi, model_text, stated_urgency, location)
        return self

    def classify(
        self,
        raw: str,
        picked_location: Location | None = None,
        constraints: Sequence[ClarificationConstraint] = (),
        memory: bool = True,
    ) -> tuple[NormalizedRequest, CoreResult]:
        self.calls.append((raw, picked_location, tuple(constraints), memory))
        if not raw.strip():
            raise InvalidInput("empty request text")
        entry = self.script.get(raw.strip())
        core = entry.core if entry else self.default
        for c in constraints:
            core = _constrain(core, c)
        if core.safety:
            core = _constrain(core, ClarificationConstraint("priority", Priority.HIGH.value))
        req = make_request(
            raw,
            lang=entry.lang if entry else Lang.EN,
            is_arabizi=entry.is_arabizi if entry else False,
            model_text=entry.model_text if entry else None,
            stated_urgency=entry.stated_urgency if entry else False,
            location=picked_location or (entry.location if entry else None),
        )
        return req, core


def _constrain(core: CoreResult, c: ClarificationConstraint) -> CoreResult:
    if c.kind == "category":
        return dataclasses.replace(
            core,
            set_cat=PredictionSet(frozenset({c.value})),
            p_cat=prob_vector(CATEGORY_LABELS, {c.value: 0.95}),
        )
    if c.kind == "priority":
        return dataclasses.replace(
            core,
            set_pri=PredictionSet(frozenset({c.value})),
            p_pri=prob_vector(PRIORITY_LABELS, {c.value: 0.95}),
        )
    flags = {**core.evidence.flags, c.value: True}
    core = dataclasses.replace(core, evidence=EvidenceVector(flags=flags, spans=core.evidence.spans))
    implied = FEATURE_PRIORITY.get(c.value)
    return _constrain(core, ClarificationConstraint("priority", implied.value)) if implied else core


@dataclass
class FakeFAQ:
    """A `FAQRetriever` returning `hits` (best first) and recording each query; `error` is raised."""

    hits: list[FAQHit] = field(default_factory=list)
    error: Exception | None = None
    queries: list[tuple[str, Lang, int]] = field(default_factory=list)

    def search(self, text: str, lang: Lang, k: int) -> list[FAQHit]:
        self.queries.append((text, lang, k))
        if self.error is not None:
            raise self.error
        return self.hits[:k]
