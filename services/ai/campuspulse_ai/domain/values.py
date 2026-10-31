"""Immutable value objects shared by every layer (ARCHITECTURE §1.3, P0.4).

All are frozen, slotted dataclasses. Probability vectors are plain tuples so the
domain stays stdlib-only; adapters convert to and from numpy.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum
from typing import Literal

from campuspulse_ai.domain.labels import Category, Priority

PROB_SUM_TOLERANCE = 1e-6

# Flag strings (ARCHITECTURE §5). `empty_input` is debug-only (LD-17);
# `understanding_fallback` marks a rule-based understanding (UD-10).
FLAGS: frozenset[str] = frozenset(
    {
        "injection_attempt",
        "urgency_unsupported",
        "safety",
        "needs_review",
        "distress",
        "gibberish",
        "out_of_scope",
        "empty_set",
        "truncated",
        "llm_out_of_set",
        "staff_confirmed",
        "priority_gaming_suspected",
        "explanation_failed",
        "understanding_fallback",
        "empty_input",
    }
)

MetaValue = str | float | bool | None
ProbabilityTarget = Literal["category", "priority"]


class Lang(StrEnum):
    EN = "en"
    AR = "ar"
    ARABIZI = "arabizi"


class Tier(StrEnum):
    TIER0 = "tier0"
    TIER1 = "tier1"
    TIER2 = "tier2"
    HUMAN = "human"


class Outcome(StrEnum):
    ACCEPT = "accept"
    ASK = "ask"
    ESCALATE = "escalate"
    HUMAN_REVIEW = "human_review"
    OUT_OF_SCOPE = "out_of_scope"
    DISTRESS = "distress"


class RequestStatus(StrEnum):
    RECEIVED = "received"
    NEEDS_CLARIFICATION = "needs_clarification"
    CLARIFIED = "clarified"
    DECIDED = "decided"
    HUMAN_REVIEW = "human_review"
    OUT_OF_SCOPE = "out_of_scope"
    DISTRESS = "distress"
    ACTIONED = "actioned"
    RESOLVED = "resolved"
    MERGED = "merged"


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    ESCALATED = "escalated"
    MERGED = "merged"


class ActionType(StrEnum):
    FAQ_ANSWER = "faq_answer"
    TICKET = "ticket"
    BOOKING = "booking"
    SAFETY_ALERT = "safety_alert"
    INCIDENT_MERGE = "incident_merge"


@dataclass(frozen=True, slots=True)
class ProbVector:
    """A probability distribution over an ordered label tuple. Sums to 1 within 1e-6."""

    values: tuple[float, ...]
    labels: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.values) != len(self.labels) or not self.labels:
            raise ValueError("ProbVector values and labels must be non-empty and the same length")
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("ProbVector labels must be unique")
        if any(v < 0 or math.isnan(v) for v in self.values):
            raise ValueError("ProbVector values must be non-negative numbers")
        if abs(math.fsum(self.values) - 1.0) > PROB_SUM_TOLERANCE:
            raise ValueError(f"ProbVector must sum to 1 (got {math.fsum(self.values)!r})")

    def argmax(self) -> str:
        """Most probable label; ties go to the earliest label in `labels` order."""
        best = max(self.values)
        return self.labels[self.values.index(best)]

    def top(self, k: int) -> list[tuple[str, float]]:
        """The k most probable (label, p) pairs, ties broken by label order."""
        order = sorted(range(len(self.values)), key=lambda i: (-self.values[i], i))
        return [(self.labels[i], self.values[i]) for i in order[:k]]

    def as_dict(self) -> dict[str, float]:
        return dict(zip(self.labels, self.values, strict=True))

    def prob(self, label: str) -> float:
        return self.values[self.labels.index(label)]


@dataclass(frozen=True, slots=True)
class PredictionSet:
    """A conformal prediction set."""

    labels: frozenset[str]

    @property
    def size(self) -> int:
        return len(self.labels)

    @property
    def is_singleton(self) -> bool:
        return len(self.labels) == 1


@dataclass(frozen=True, slots=True)
class Evidence:
    """One urgency/evidence cue found in the text, e.g. ("deadline_today", "اليوم", AR)."""

    type: str
    span: str
    lang: Lang


@dataclass(frozen=True, slots=True)
class EvidenceVector:
    """Evidence flags ordered by EVIDENCE_FEATURES (domain/priority_rules.py), plus the matched spans."""

    flags: Mapping[str, bool]
    spans: tuple[Evidence, ...] = ()


@dataclass(frozen=True, slots=True)
class GuardVerdict:
    kind: Literal["none", "injection", "distress", "danger", "gibberish"]
    matched_spans: tuple[str, ...] = ()
    stripped_text: str = ""
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class Location:
    building: str
    room: str | None
    source: Literal["picked", "extracted"]


@dataclass(frozen=True, slots=True)
class NormalizedRequest:
    """The request after wrapper stripping, normalization and language ID.

    `model_text` is what models see: transliteration + original for Arabizi, else `text_norm`.
    """

    raw: str
    core: str
    text_norm: str
    model_text: str
    lang: Lang
    is_arabizi: bool
    stated_urgency: bool
    truncated: bool
    location: Location | None = None


@dataclass(frozen=True, slots=True)
class StripResult:
    prefix: str
    suffix: str
    core: str
    stated_urgency: bool


@dataclass(frozen=True, slots=True)
class ArtifactVersion:
    name: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Manifest:
    """MANIFEST.json of a frozen model dir: relpath -> sha256."""

    artifact_version: str
    files: Mapping[str, str]
    created_at: str

    @property
    def sha(self) -> str:
        """sha256 over sorted "relpath:sha" lines; reported by /health and predict.py."""
        lines = "\n".join(f"{path}:{digest}" for path, digest in sorted(self.files.items()))
        return hashlib.sha256(lines.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ClarificationConstraint:
    kind: Literal["category", "priority", "feature"]
    value: str


@dataclass(frozen=True, slots=True)
class ClarificationBudget:
    max_questions: int
    asked: int = 0

    @property
    def remaining(self) -> int:
        return max(self.max_questions - self.asked, 0)


@dataclass(frozen=True, slots=True)
class ClarificationOption:
    id: str
    text: str
    constraint: ClarificationConstraint | None = None


@dataclass(frozen=True, slots=True)
class ClarificationQuestion:
    """One question from the bank, rendered in the request language."""

    id: str
    target: Literal["category", "priority", "feature"]
    text: str
    lang: Lang
    options: tuple[ClarificationOption, ...]
    expected_info_gain: float = 0.0


@dataclass(frozen=True, slots=True)
class Money:
    usd: float


@dataclass(frozen=True, slots=True)
class VectorItem:
    id: str
    embedding: tuple[float, ...]
    text: str
    lang: Lang
    meta: Mapping[str, MetaValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VectorHit:
    """Cosine hit; `embedding` is filled only when filters["with_embedding"] is true (LD-14)."""

    id: str
    text: str
    sim: float
    lang: Lang
    meta: Mapping[str, MetaValue] = field(default_factory=dict)
    embedding: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class Neighbor:
    text: str
    category: Category
    priority: Priority
    sim: float
    source: Literal["train", "augmented", "memory"]
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EnsembleOutput:
    """`per_model` keys are "<member>.<target>", e.g. "m1.category" (LD-13)."""

    p_cat: ProbVector
    p_pri_model: ProbVector
    per_model: Mapping[str, ProbVector]
    ood_score: float
    neighbors: tuple[Neighbor, ...]
    embedding: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class MemoryStats:
    active: int
    total: int
    by_category: Mapping[str, int]
    last_added_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ActionPlan:
    kind: ActionType
    office: str
    sla_hours: int
    tags: tuple[str, ...] = ()
    also_ticket: bool = False


@dataclass(frozen=True, slots=True)
class FAQHit:
    id: str
    question: str
    answer: str
    source_url: str
    is_demo: bool
    score: float


@dataclass(frozen=True, slots=True)
class TicketLink:
    """A ticket mirrored in an external sink. `error` is the last push error (D-011): a link with an
    error is a failed push, stored in `ticket_links.last_error`, not a live mirror."""

    ticket_id: str
    sink: str
    external_id: str
    url: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class InboundEvent:
    """A verified inbound status change from an external sink (e.g. a Linear webhook)."""

    sink: str
    external_id: str
    status: TicketStatus
    occurred_at: datetime
    payload: Mapping[str, MetaValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OfficeHours:
    tz: str
    weekdays: tuple[int, ...]  # Monday=0
    start: time
    end: time


@dataclass(frozen=True, slots=True)
class Slot:
    id: str
    advisor_id: str
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True, slots=True)
class Booking:
    slot: Slot
    attendees: tuple[str, ...]
    title: str
    provider: str
    external_id: str | None = None


@dataclass(frozen=True, slots=True)
class Advisor:
    """Fictional advisor (seed data only)."""

    id: str
    name: str
    department: str
    email: str


@dataclass(frozen=True, slots=True)
class RouterStats:
    total: int
    by_tier: Mapping[str, int]
    resolved_tier0_pct: float
    cost_usd: float
    cached_calls: int


@dataclass(frozen=True, slots=True)
class StudentSignals:
    alias: str
    requests: int
    claimed_urgent: int
    claimed_urgent_not_high: int
    injection_attempts: int
    gaming_suspected: bool


@dataclass(frozen=True, slots=True)
class Counterfactual:
    drop: str
    category: Category
    priority: Priority


@dataclass(frozen=True, slots=True)
class Entities:
    """Entities extracted by the RequestUnderstander (UD-10)."""

    building: str | None = None
    room: str | None = None
    course_code: str | None = None
    deadline: date | None = None
    system: str | None = None


@dataclass(frozen=True, slots=True)
class Understanding:
    """Structured NLP understanding of a request (UD-10). Never changes the decided labels."""

    summary_en: str
    summary_ar: str
    entities: Entities
    student_reply: str
    ticket_title: str
    ticket_body: str
    source: Literal["llm", "rules"]
    prompt_version: str | None = None


@dataclass(frozen=True, slots=True)
class ProblemCluster:
    """A recurring problem: semantically similar requests in one category/building (UD-6)."""

    cluster_id: str
    category: Category
    building_id: str | None
    size: int
    first_seen: datetime
    last_seen: datetime
    representative_text: str
    sample_request_ids: tuple[str, ...]
