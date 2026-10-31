"""Mutable domain entities with UUID string ids (ARCHITECTURE §1.3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import (
    ArtifactVersion,
    Booking,
    ClarificationOption,
    Counterfactual,
    Evidence,
    EvidenceVector,
    GuardVerdict,
    Lang,
    Money,
    Neighbor,
    NormalizedRequest,
    PredictionSet,
    ProbVector,
    RequestStatus,
    TicketLink,
    TicketStatus,
    Tier,
)


@dataclass
class Request:
    id: str
    alias: str
    raw_text: str
    normalized: NormalizedRequest | None
    input_mode: Literal["text", "voice"]
    status: RequestStatus
    created_at: datetime
    conversation_id: str | None = None


@dataclass
class CoreResult:
    """Output of TriageCore.classify: the only path that produces labels.

    `per_model` keys are "<member>.<target>", e.g. "m1.category" (LD-13).
    """

    p_cat: ProbVector
    p_pri: ProbVector
    per_model: dict[str, ProbVector]
    flags: frozenset[str]
    set_cat: PredictionSet
    set_pri: PredictionSet
    ood_score: float
    neighbors: tuple[Neighbor, ...]
    evidence: EvidenceVector
    guard: GuardVerdict
    safety: bool
    floors_applied: tuple[str, ...]
    tier: Tier
    latency_ms: int
    artifact: ArtifactVersion
    # The request's frozen-encoder vector (D-012), so Pulse and memory never re-encode; () when no model ran.
    embedding: tuple[float, ...] = ()


@dataclass
class Explanation:
    top_tokens: list[tuple[str, float]]
    urgency_reasons: list[Evidence]
    neighbors: list[Neighbor]
    counterfactual: Counterfactual | None
    trace: dict[str, object] = field(default_factory=dict)


@dataclass
class Prediction:
    id: str
    request_id: str
    category: Category
    priority: Priority
    core: CoreResult
    tier: Tier
    flags: set[str]
    explanation: Explanation | None
    cost: Money
    artifact_version: str


@dataclass
class Clarification:
    id: str
    request_id: str
    question_id: str
    options: tuple[ClarificationOption, ...]
    answer: str | None
    asked_at: datetime
    answered_at: datetime | None = None


@dataclass
class Ticket:
    """A CampusPulse ticket (system of record: the `tickets` table).

    `tags` come from the routing plan (`config/actions.yaml`): e.g. `safety` (Linear priority 1),
    `exam-in-progress`, `transport-alert`, `unconfirmed` and `deferred:<kind>` on provisional tickets
    (D-011). `links` are the external mirrors; a link with `error` set is a failed sink push.
    """

    id: str
    request_id: str
    incident_id: str | None
    office: str
    category: Category
    priority: Priority
    status: TicketStatus
    provisional: bool
    sla_due_at: datetime
    title: str = ""
    body: str = ""
    escalated_at: datetime | None = None
    resolved_at: datetime | None = None
    links: list[TicketLink] = field(default_factory=list)
    tags: tuple[str, ...] = ()


@dataclass
class Incident:
    id: str
    building: str
    category: Category
    title: str
    priority: Priority
    report_count: int
    status: Literal["open", "resolved"]
    member_ticket_ids: list[str]
    opened_at: datetime
    resolved_at: datetime | None = None


@dataclass
class IncidentDecision:
    kind: Literal["none", "new", "attach"]
    incident: Incident | None
    members: list[str] = field(default_factory=list)


@dataclass
class MemoryExample:
    id: str
    text_norm: str
    lang: Lang
    embedding: tuple[float, ...]
    category: Category
    priority: Priority
    author_id: str
    created_at: datetime
    active: bool = True


@dataclass
class ReviewItem:
    """One `review_queue` row: a prediction a person must confirm (or a distress report).

    `assignee` is the profile id of the advisor the item is assigned to (UD-13; None = the office
    queue) and `office` the D-005 office whose queue holds it (None = filled by the database from
    the prediction's category). Both are additive (D-020).
    """

    id: str
    prediction_id: str
    reason: str
    status: Literal["open", "confirmed", "corrected"]
    reviewer_id: str | None = None
    corrected_category: Category | None = None
    corrected_priority: Priority | None = None
    note: str | None = None
    assignee: str | None = None
    office: str | None = None


@dataclass
class OutboxMessage:
    """Every outgoing message is recorded here, including rejected ones.

    Status: `queued` (built, not sent), `sent`, `failed` (provider error), `rejected` (allow-list),
    `deferred` (held back, e.g. the daily email cap; D-011). `error` carries the reason for
    `failed`, `rejected` and `deferred` (D-011); None otherwise.
    """

    id: str
    kind: Literal["email", "in_app", "whatsapp"]
    to_address: str
    subject: str
    body: str
    provider_id: str | None
    status: Literal["queued", "sent", "failed", "rejected", "deferred"]
    created_at: datetime
    priority: Priority | None = None
    flags: frozenset[str] = frozenset()
    error: str | None = None


@dataclass
class LLMCall:
    id: str
    request_id: str | None
    tier: Tier
    model: str
    prompt_hash: str
    tokens_in: int
    tokens_out: int
    cost: Money
    latency_ms: int
    cached: bool


@dataclass
class OracleAnswer:
    """An LLM tier's choice, always inside the allowed conformal sets (or None)."""

    category: Category | None
    priority: Priority | None
    rationale: str
    call: LLMCall


@dataclass
class OracleContext:
    lang: Lang
    neighbors: tuple[Neighbor, ...]
    prompt_version: str


@dataclass
class Case:
    """Advisor-booking case (B-list; a no-op write when cut)."""

    id: str
    request_id: str
    ticket_id: str | None
    booking: Booking | None
    created_at: datetime


@dataclass
class RedTeamItem:
    """One red-team input (ARCHITECTURE §2.4).

    `base_text` is the unperturbed text it was made from (None for fixed-list and two-issue items):
    the injection and fake-urgency rules compare against the base's prediction (D-013). `base_id` is
    the seed row's id, carried into the failure candidates for a human to trace.
    """

    text: str
    style: str
    lang: Lang
    intended_category: Category
    intended_priority: Priority
    expected_flags: frozenset[str] = frozenset()
    base_text: str | None = None
    base_id: str | None = None


@dataclass
class Scorecard:
    """A red-team run (ARCHITECTURE §2.4): pass rates in [0, 1] per style, per language and overall.

    `created_at`, `n` (items scored) and `seed` (generator seed) were added by D-013 so the stored
    history can be shown by `/v1/metrics`. They are keyword-only to keep the positional order of the
    original fields. `failures` rows carry the keys of `dto.RedTeamFailureOut`.
    """

    run_id: str
    by_style: dict[str, float]
    by_lang: dict[str, float]
    overall: float
    failures: list[Mapping[str, object]] = field(default_factory=list)
    created_at: datetime = field(kw_only=True)
    n: int = field(kw_only=True)
    seed: int = field(kw_only=True)
