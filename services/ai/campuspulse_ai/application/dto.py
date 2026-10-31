"""HTTP data-transfer objects for the `/v1` API (SPEC §7 + LD-25 + UD-6 + UD-10), frozen at P0.13.

These Pydantic v2 models are the single source of the HTTP contract:
- `frameworks/mock_app.py` serves fixtures through them (P0.13);
- the real FastAPI app (P3.12, P4.9-P4.12, P4.21) returns them;
- `services/ai/openapi.json` is exported from them and the UI generates its TS types from that file.

Rules:
- Label and enum strings come from the domain (`Category`, `Priority`, `Tier`, `Lang`, `ActionType`,
  `RequestStatus`, `TicketStatus`, `Outcome`, `values.FLAGS`). Nothing here re-spells a label.
- DTOs import the domain; the domain never imports DTOs.
- Every model forbids unknown keys, and every response key is always present (nullable rather than
  optional), so the "exact key set" contract test (P3.12, X3.1) can hold.
- Changing anything here is a contract change: lead approval, re-export `openapi.json`, regenerate
  `docs/api/endpoints.md` (`python scripts/gen_api_docs.py`).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, WithJsonSchema, model_validator

from campuspulse_ai.domain.errors import (
    ArtifactError,
    CampusPulseError,
    ClarificationBudgetExceeded,
    InvalidInput,
    NotFound,
    StoreError,
    Unauthorized,
)
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import (
    FLAGS,
    ActionType,
    Lang,
    Outcome,
    RequestStatus,
    TicketStatus,
    Tier,
)

# --- shared field types -----------------------------------------------------------------------------

Probability = Annotated[float, Field(ge=0.0, le=1.0)]

# Mirrors of domain Literals. tests/contracts/test_dto_contract.py asserts each equals the domain hint,
# so they cannot drift.
InputMode = Literal["text", "voice"]
"""Mirrors `entities.Request.input_mode`."""
NeighborSource = Literal["train", "augmented", "memory"]
"""Mirrors `values.Neighbor.source`."""
UnderstandingSource = Literal["llm", "rules"]
"""Mirrors `values.Understanding.source`."""
IncidentStatus = Literal["open", "resolved"]
"""Mirrors `entities.Incident.status`."""
ReviewStatus = Literal["open", "confirmed", "corrected"]
"""Mirrors `entities.ReviewItem.status`."""
ReviewReason = Literal["needs_review", "distress"]
"""`review_queue.reason` codes (docs/api/README.md › review reasons)."""

TriageStatus = Literal[
    RequestStatus.DECIDED,
    RequestStatus.NEEDS_CLARIFICATION,
    RequestStatus.HUMAN_REVIEW,
    RequestStatus.OUT_OF_SCOPE,
    RequestStatus.DISTRESS,
]
"""The five `/v1/triage` outcomes (SPEC §7): a subset of `RequestStatus`."""

TRIAGE_STATUSES: tuple[RequestStatus, ...] = (
    RequestStatus.DECIDED,
    RequestStatus.NEEDS_CLARIFICATION,
    RequestStatus.HUMAN_REVIEW,
    RequestStatus.OUT_OF_SCOPE,
    RequestStatus.DISTRESS,
)

Role = Literal["student", "staff", "admin", "service"]
"""Caller roles (P3.12 `Principal.role`). `service` = service token without a user JWT (scripts)."""


def _check_flag(value: str) -> str:
    if value not in FLAGS:
        raise ValueError(f"unknown flag {value!r}; allowed: {sorted(FLAGS)}")
    return value


Flag = Annotated[
    str,
    AfterValidator(_check_flag),
    WithJsonSchema({"type": "string", "enum": sorted(FLAGS), "title": "Flag"}),
]
"""One of `domain.values.FLAGS` (meanings in docs/api/README.md)."""

STAFF_ONLY_FLAGS: frozenset[str] = frozenset({"urgency_unsupported", "priority_gaming_suspected"})
"""Flags removed by `to_student_view` (SPEC §5.1 [9b]: neutral, staff-only notes)."""

DEBUG_ONLY_FLAGS: frozenset[str] = frozenset({"empty_input"})
"""Flags that exist only in `predict.py --debug` output; the API never returns them (LD-17)."""

BATCH_CSV_COLUMNS: tuple[str, ...] = ("request_id", "category", "priority")
"""Exact header of the `/v1/batch` CSV response (same bytes as `predict.py`)."""

BATCH_INPUT_COLUMNS: tuple[str, ...] = ("request_id", "text")
"""Columns required in the `/v1/batch` upload; extra columns are ignored."""


class _Model(BaseModel):
    """Base for every DTO: unknown keys are rejected, enums serialize as their values."""

    model_config = ConfigDict(extra="forbid")


# --- caller identity --------------------------------------------------------------------------------


class PrincipalHeaders(BaseModel):
    """Caller-identity headers on role-checked routes (P3.12 `principal()`).

    Production (`AUTH_MODE=supabase_jwt`, P4.12): the Next.js server forwards the user's Supabase access
    token in `X-CP-User-JWT`, and FastAPI reads role/office/alias from `profiles`. The `X-CP-Role`,
    `X-CP-Alias` and `X-CP-Office` headers are honoured only in `AUTH_MODE=trusted_headers` (tests,
    local dev, the mock app) and ignored in production.
    """

    model_config = ConfigDict(extra="ignore")

    x_cp_user_jwt: str | None = Field(default=None, description="Supabase access token of the end user.")
    x_cp_role: Role | None = Field(default=None, description="trusted_headers mode only.")
    x_cp_alias: str | None = Field(default=None, description="trusted_headers mode only.")
    x_cp_office: str | None = Field(default=None, description="trusted_headers mode only.")


# --- errors -----------------------------------------------------------------------------------------


class ErrorCode(StrEnum):
    """Machine-readable error codes. HTTP status per code is in `ERROR_HTTP_STATUS`."""

    INVALID_INPUT = "invalid_input"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CLARIFICATION_BUDGET_EXCEEDED = "clarification_budget_exceeded"
    NOT_IMPLEMENTED = "not_implemented"
    ARTIFACT_UNAVAILABLE = "artifact_unavailable"
    STORE_UNAVAILABLE = "store_unavailable"
    INTERNAL_ERROR = "internal_error"


ERROR_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.INVALID_INPUT: 422,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CLARIFICATION_BUDGET_EXCEEDED: 409,
    ErrorCode.NOT_IMPLEMENTED: 501,
    ErrorCode.ARTIFACT_UNAVAILABLE: 503,
    ErrorCode.STORE_UNAVAILABLE: 503,
    ErrorCode.INTERNAL_ERROR: 500,
}

# Most specific first: NotFound is a StoreError.
DOMAIN_ERROR_CODES: tuple[tuple[type[CampusPulseError], ErrorCode], ...] = (
    (NotFound, ErrorCode.NOT_FOUND),
    (StoreError, ErrorCode.STORE_UNAVAILABLE),
    (InvalidInput, ErrorCode.INVALID_INPUT),
    (Unauthorized, ErrorCode.FORBIDDEN),
    (ClarificationBudgetExceeded, ErrorCode.CLARIFICATION_BUDGET_EXCEEDED),
    (ArtifactError, ErrorCode.ARTIFACT_UNAVAILABLE),
)


def error_code_for(exc: BaseException) -> ErrorCode:
    """Map a raised exception to its API error code; anything unmapped is `internal_error`."""
    for exc_type, code in DOMAIN_ERROR_CODES:
        if isinstance(exc, exc_type):
            return code
    return ErrorCode.INTERNAL_ERROR


class ErrorBody(_Model):
    """The inside of every error response. `details` is free-form JSON (validation errors, request_id)."""

    code: ErrorCode
    message: str
    details: dict[str, Any] | None


class ErrorResponse(_Model):
    """Standard error body for every non-2xx response: `{"error": {"code", "message", "details"}}`."""

    error: ErrorBody


# --- triage -----------------------------------------------------------------------------------------


class LocationIn(_Model):
    """A building (and optional room) the student picked on the map."""

    building: str = Field(min_length=1, description="Fictional building code, e.g. `M`.")
    room: str | None = Field(default=None, description="Room code, e.g. `M 214`.")


class TriageRequest(_Model):
    """Body of `POST /v1/triage` (SPEC §7)."""

    text: str = Field(min_length=1, description="The student's message (or the confirmed voice transcript).")
    input_mode: InputMode = "text"
    student_alias: str = Field(default="", description="Pseudonymous alias such as `demo-17`; never a name.")
    location: LocationIn | None = None
    conversation_id: str | None = None
    simulated: bool = Field(
        default=False, description="True only for `scripts/simulate_pulse.py` traffic (P4.10)."
    )


class CategoryOut(_Model):
    """Category decision: the label, its probability and the conformal set."""

    label: Category
    prob: Probability
    set: list[Category] = Field(description="Conformal prediction set (1-alpha = 0.90).")


class EvidenceOut(_Model):
    """An urgency evidence cue found in the text, e.g. `deadline_today` on `اليوم`."""

    type: str = Field(description="Evidence feature name (`EVIDENCE_FEATURES`, P1.12).")
    span: str = Field(description="The matched text span.")


class PriorityOut(_Model):
    """Priority decision: label, probability, conformal set and the evidence that drove it."""

    label: Priority
    prob: Probability
    set: list[Priority]
    evidence: list[EvidenceOut]


class ClarificationOptionOut(_Model):
    """One answer chip."""

    id: str
    text: str


class ClarificationOut(_Model):
    """The clarifying question asked when the request is ambiguous, in the request language."""

    question_id: str = Field(description="Question-bank id, e.g. `cat:Registration|IT Support`.")
    text: str
    options: list[ClarificationOptionOut]


class NeighborOut(_Model):
    """A similar past example (training data or a staff correction in live memory)."""

    text: str
    label: Category = Field(description="The neighbour's category.")
    priority: Priority
    sim: Probability = Field(description="Cosine similarity to the request.")
    source: NeighborSource
    created_at: datetime | None = Field(description="Set for memory items ('learned N s ago').")


class CounterfactualOut(_Model):
    """The smallest single-token deletion that flips category or priority."""

    drop: str
    category: Category
    priority: Priority


class SetSizesOut(_Model):
    """Conformal set sizes."""

    cat: int = Field(ge=0)
    pri: int = Field(ge=0)


class TraceOut(_Model):
    """Decision trace (SPEC §5.1 [10])."""

    sets: SetSizesOut
    models_agree: bool
    cost_usd: float = Field(ge=0.0)
    latency_ms: int = Field(ge=0)
    policy_path: list[str] = Field(
        description="DecisionPolicy rule ids in evaluation order, e.g. `a_gibberish`..`f_human` (P3.1)."
    )
    clarified: bool = Field(description="Whether a clarification answer was applied.")
    artifact_version: str
    per_model: dict[str, dict[str, float]] | None = Field(
        description="`<member>.<target>` -> {label: p}; only with `?debug=members` (admin, P5.16)."
    )


class ExplanationOut(_Model):
    """Why the system decided what it did. Null when the explainer failed (flag `explanation_failed`)."""

    top_tokens: list[tuple[str, float]] = Field(description="[token, importance] pairs, top 5.")
    neighbors: list[NeighborOut]
    counterfactual: CounterfactualOut | None
    trace: TraceOut


class ExternalRefOut(_Model):
    """A ticket mirrored in an external sink (e.g. a Linear issue)."""

    sink: str = Field(description="Sink name, e.g. `linear`.")
    external_id: str
    url: str | None


class BookingOut(_Model):
    """An advisor slot booked for Academic Support x high (UD-1). Advisors are fictional."""

    advisor_name: str
    starts_at: datetime
    ends_at: datetime
    room: str | None


class FaqAnswerOut(_Model):
    """A retrieved FAQ answer (never generated). `is_demo` marks placeholder entries."""

    question: str
    answer: str
    source_url: str
    is_demo: bool
    score: Probability


class ActionOut(_Model):
    """What happened next (SPEC §5.1 [11])."""

    type: ActionType
    ticket_id: str | None
    external: list[ExternalRefOut]
    sla_due_at: datetime | None
    message: str = Field(description="Student-facing sentence about the action.")
    provisional: bool = Field(description="True for `needs_review` items: ticket labelled unconfirmed.")
    tags: list[str] = Field(description="Ticket tags, e.g. `exam-in-progress`.")
    booking: BookingOut | None
    faq: FaqAnswerOut | None
    incident_id: str | None = Field(description="Set when the request was merged into an incident.")


class EntitiesOut(_Model):
    """Entities extracted from the request (UD-10)."""

    building: str | None
    room: str | None
    course_code: str | None
    deadline: date | None
    system: str | None


class UnderstandingOut(_Model):
    """Structured understanding (UD-10). Never changes the decided labels."""

    summary_en: str
    summary_ar: str
    entities: EntitiesOut
    student_reply: str
    ticket_title: str
    ticket_body: str
    source: UnderstandingSource
    prompt_version: str | None


class TriageResponse(_Model):
    """Response of `POST /v1/triage` and `POST /v1/triage/{request_id}/clarify` (SPEC §7 + LD-25 + UD-10).

    Which keys are null depends on `status` (docs/api/README.md › Status values).
    """

    request_id: str
    status: TriageStatus
    lang: Lang
    is_arabizi: bool
    understood_as: str | None = Field(description="Arabic transliteration shown for Arabizi input (LD-25).")
    category: CategoryOut | None
    priority: PriorityOut | None
    tier: Tier
    clarification: ClarificationOut | None
    explanation: ExplanationOut | None
    flags: list[Flag]
    action: ActionOut | None
    message: str | None = Field(description="Top-level student message (distress, out-of-scope, review).")
    understanding: UnderstandingOut | None


class TriageQuery(_Model):
    """Query parameters of `POST /v1/triage`."""

    debug: Literal["members"] | None = Field(
        default=None, description="`members` fills `explanation.trace.per_model` (admin only, P5.16)."
    )


def to_student_view(r: TriageResponse) -> TriageResponse:
    """Copy of `r` without staff-only flags (returned to the student role)."""
    return r.model_copy(update={"flags": [f for f in r.flags if f not in STAFF_ONLY_FLAGS]})


class ClarifyRequest(_Model):
    """Body of `POST /v1/triage/{request_id}/clarify`: exactly one of `option_id` or `free_text`."""

    question_id: str = Field(min_length=1)
    option_id: str | None = None
    free_text: str | None = None

    @model_validator(mode="after")
    def _exactly_one_answer(self) -> ClarifyRequest:
        if (self.option_id is None) == (self.free_text is None):
            raise ValueError("send exactly one of option_id or free_text")
        return self


# --- explain ----------------------------------------------------------------------------------------


class CounterfactualQuery(_Model):
    """Query parameters of `GET /v1/explain/{request_id}/counterfactual`."""

    drop: str = Field(min_length=1, description="The token to delete from the request text.")


class CounterfactualResponse(_Model):
    """Live counterfactual: the labels the core gives with `drop` removed."""

    request_id: str
    drop: str
    original_category: Category
    original_priority: Priority
    category: Category
    priority: Priority
    category_prob: Probability
    priority_prob: Probability
    flipped: bool = Field(description="True when category or priority changed.")


# --- feedback and tickets ---------------------------------------------------------------------------


class FeedbackRequest(_Model):
    """Body of `POST /v1/feedback`: staff confirm (both null) or correct a prediction."""

    prediction_id: str = Field(min_length=1)
    corrected_category: Category | None = None
    corrected_priority: Priority | None = None
    note: str = ""


class TicketOut(_Model):
    """A CampusPulse ticket (system of record in Supabase)."""

    id: str
    request_id: str
    incident_id: str | None
    office: str
    category: Category
    priority: Priority
    status: TicketStatus
    provisional: bool
    sla_due_at: datetime
    escalated_at: datetime | None
    resolved_at: datetime | None
    title: str
    links: list[ExternalRefOut]


class MemoryWriteOut(_Model):
    """The live-memory example written by a staff correction."""

    example_id: str
    active_examples: int = Field(ge=0, description="Active memory size after the write.")


class FeedbackResponse(_Model):
    """Result of `POST /v1/feedback`."""

    prediction_id: str
    request_id: str
    category: Category
    priority: Priority
    tier: Tier
    flags: list[Flag]
    ticket: TicketOut | None
    memory: MemoryWriteOut
    actions: list[ActionOut] = Field(description="Deferred actions that fired on confirmation.")
    message: str


class TicketStatusRequest(_Model):
    """Body of `POST /v1/tickets/{ticket_id}/status` (dashboard status change, LD-25)."""

    status: TicketStatus
    note: str | None = None


class ForwardRequest(_Model):
    """Body of `POST /v1/tickets/{ticket_id}/forward` and `POST /v1/reviews/{review_id}/forward` (UD-13).

    `office` is a D-005 office code; the category follows it (one office per category).
    """

    office: str = Field(
        min_length=1,
        description="D-005 office code: registrar, it, finance, transport, facilities or academic.",
    )
    note: str | None = None


# --- advisor review (UD-13) -------------------------------------------------------------------------


class ReviewListQuery(_Model):
    """Query parameters of `GET /v1/reviews`."""

    status: ReviewStatus = Field(default="open", description="Which items: open (default) or resolved ones.")


class ReviewItemOut(_Model):
    """One review item the caller may act on (UD-13): an unsure request and its best guess."""

    id: str
    prediction_id: str
    request_id: str
    reason: ReviewReason
    status: ReviewStatus
    office: str | None = Field(description="The D-005 office whose queue holds the item.")
    assignee: str | None = Field(description="Profile id of the assigned advisor; null = the office queue.")
    assigned_to_me: bool
    student_alias: str
    text: str = Field(description="The student's request as written.")
    lang: Lang
    category: Category = Field(description="The model's best guess (or the reviewer's correction).")
    priority: Priority
    set_cat: list[Category]
    set_pri: list[Priority]
    flags: list[Flag]
    ticket_id: str | None = Field(description="The request's own (provisional) ticket, if any.")
    requested_at: datetime
    corrected_category: Category | None
    corrected_priority: Priority | None
    note: str | None


# --- incidents and insights -------------------------------------------------------------------------


class IncidentOut(_Model):
    """A Pulse incident: several reports of the same problem in one building."""

    id: str
    building: str
    category: Category
    title: str
    priority: Priority
    report_count: int = Field(ge=0)
    status: IncidentStatus
    member_ticket_ids: list[str]
    ticket_id: str | None = Field(description="The one incident ticket (linked to Linear).")
    opened_at: datetime
    resolved_at: datetime | None
    simulated: bool = Field(
        default=False, description="True when every member report is `simulate_pulse.py` traffic (P4.10)."
    )


class IncidentListQuery(_Model):
    """Query parameters of `GET /v1/incidents`."""

    open: bool | None = Field(default=None, description="`1` = only open incidents (LD-25).")


class ResolveIncidentRequest(_Model):
    """Body of `POST /v1/incidents/{incident_id}/resolve` (optional note to reporters)."""

    note: str | None = None


class ResolveIncidentResponse(_Model):
    """Result of resolving an incident."""

    incident: IncidentOut
    closed_ticket_ids: list[str]
    notified_reporters: int = Field(ge=0)


class RecurringQuery(_Model):
    """Query parameters of `GET /v1/insights/recurring` (UD-6). Null = config default."""

    window_days: int | None = Field(default=None, ge=1, description="Null = all time.")
    category: Category | None = None
    building: str | None = None
    top_k: int | None = Field(default=None, ge=1, description="Null = `insights.top_k` (10).")


class ProblemClusterOut(_Model):
    """A recurring problem (UD-6): semantically similar requests in one category/building."""

    cluster_id: str
    category: Category
    building_id: str | None
    size: int = Field(ge=1)
    first_seen: datetime
    last_seen: datetime
    representative_text: str
    sample_request_ids: list[str]


# --- integrations -----------------------------------------------------------------------------------


class WebhookAck(_Model):
    """Result of an inbound sink webhook. `accepted=false` = ignored event (not ours)."""

    accepted: bool
    ticket_id: str | None
    status: TicketStatus | None


# --- batch, red team, metrics -----------------------------------------------------------------------


class BatchRow(_Model):
    """One row of the `/v1/batch` CSV response (validation helper; the wire format is CSV)."""

    request_id: str
    category: Category
    priority: Priority


class RedTeamRunRequest(_Model):
    """Body of `POST /v1/redteam/run`. `n` is capped by Settings `REDTEAM_MAX_N` (200)."""

    n: int = Field(ge=1)
    styles: list[str] | None = Field(
        default=None,
        description=(
            "Subset of: fake_urgency, calm_emergency, typos, arabizi, mixed_language, two_issues, "
            "very_long, injection, off_topic, distress_adjacent. Null = all."
        ),
    )
    seed: int = 42


class RedTeamFailureOut(_Model):
    """A red-team item that failed its pass rule."""

    text: str
    style: str
    lang: Lang
    intended_category: Category
    intended_priority: Priority
    got_category: Category | None
    got_priority: Priority | None
    outcome: Outcome
    reason: str


class ScorecardOut(_Model):
    """A red-team run's scorecard (pass rates in [0, 1])."""

    run_id: str
    created_at: datetime
    n: int = Field(ge=0)
    seed: int
    overall: Probability
    by_style: dict[str, float]
    by_lang: dict[str, float]
    failures: list[RedTeamFailureOut]


EvalDataset = Literal[
    "oof_official", "oof_all", "our_test", "our_test_set1", "our_test_set2", "our_test_set3", "probes"
]
MetricTarget = Literal["category", "priority"]


class ArtifactOut(_Model):
    """The frozen model artifact in use."""

    version: str
    sha: str


class BenchmarkRowOut(_Model):
    """One benchmark cell (SPEC §6.2). Null metrics = `n/a` (no key) or `cut` (M3)."""

    model: str
    target: MetricTarget
    dataset: EvalDataset
    macro_f1: Probability | None
    accuracy: Probability | None
    n_rows: int = Field(ge=0)
    n_groups: int | None
    status: Literal["ok", "n/a", "cut"]


class CoverageRowOut(_Model):
    """Conformal coverage for one target/dataset/language slice (approximate; effective n ~ 30)."""

    target: MetricTarget
    dataset: EvalDataset
    lang: str = Field(description="`all`, `en`, `ar` or `arabizi`.")
    coverage: Probability
    mean_set_size: float = Field(ge=0.0)
    singleton_rate: Probability
    n_rows: int = Field(ge=0)
    n_groups: int | None


class CalibrationBinOut(_Model):
    """One reliability-diagram bin."""

    lower: Probability
    upper: Probability
    confidence: Probability
    accuracy: Probability
    count: int = Field(ge=0)


class CalibrationOut(_Model):
    """Calibration of one target (ECE + reliability bins)."""

    target: MetricTarget
    ece: float = Field(ge=0.0)
    bins: list[CalibrationBinOut]


class FairnessSliceOut(_Model):
    """Macro-F1 on one language slice, with counts (LD-32, LD-33)."""

    slice: str = Field(description="`en`, `ar` or `arabizi`.")
    target: MetricTarget
    dataset: EvalDataset
    macro_f1: Probability | None
    n_rows: int = Field(ge=0)
    n_groups: int | None


class AblationRowOut(_Model):
    """One ablation arm (P2.9), scored on the same rows as the full system."""

    arm: str
    target: MetricTarget
    dataset: EvalDataset
    macro_f1: Probability | None
    delta: float | None = Field(description="macro_f1 minus the full system's.")


class ConfusionOut(_Model):
    """A confusion matrix: rows = true label, columns = predicted, in `labels` order."""

    model: str
    target: MetricTarget
    dataset: EvalDataset
    labels: list[str]
    matrix: list[list[int]]


class RouterStatsOut(_Model):
    """Live router stats (`RouterStats`)."""

    total: int = Field(ge=0)
    by_tier: dict[str, int]
    resolved_tier0_pct: float = Field(ge=0.0, le=100.0)
    cost_usd: float = Field(ge=0.0)
    cost_per_1k_usd: float = Field(ge=0.0)
    cached_calls: int = Field(ge=0)


class MemoryStatsOut(_Model):
    """Live memory stats (`MemoryStats`)."""

    active: int = Field(ge=0)
    total: int = Field(ge=0)
    by_category: dict[str, int]
    last_added_at: datetime | None


class MetricsResponse(_Model):
    """`GET /v1/metrics`: offline reports (`reports/*.json`) plus live router/memory/red-team stats."""

    artifact: ArtifactOut
    generated_at: datetime | None = Field(description="When `evaluate.py` wrote the reports.")
    benchmark: list[BenchmarkRowOut]
    coverage: list[CoverageRowOut]
    ask_rate: Probability | None
    ask_rate_is_proxy: bool = Field(description="True while the rate is the P2 proxy (LD-24).")
    calibration: list[CalibrationOut]
    fairness: list[FairnessSliceOut]
    ablations: list[AblationRowOut]
    confusions: list[ConfusionOut]
    router: RouterStatsOut
    memory: MemoryStatsOut
    redteam: list[ScorecardOut]


# --- health -----------------------------------------------------------------------------------------


class HealthResponse(_Model):
    """`GET /health` (and `/v1/health`): liveness, artifact identity and wiring."""

    status: Literal["ok", "degraded"]
    version: str = Field(description="`campuspulse_ai.__version__`.")
    artifact: str | None = Field(description="Artifact version, e.g. `v1`; null before models exist.")
    sha: str | None = Field(description="`Manifest.sha` of the loaded artifact.")
    rss_mb: float
    encoder_loaded: bool
    sinks: list[str]
    llm_tiers: list[Tier]
    vector_store: str | None


# --- admin (optional extras, B-list) ----------------------------------------------------------------


class SimulateRequest(_Model):
    """Body of `POST /v1/admin/simulate` (optional extra, P5.19)."""

    scenario: str = Field(default="wifi_m", description="A `config/simulation/<name>.yaml` scenario.")
    interval_s: float = Field(default=4.0, gt=0.0)


class SimulateResponse(_Model):
    """A started simulated burst. All its requests carry `simulated=true`."""

    run_id: str
    scenario: str
    queued: int = Field(ge=0)
    interval_s: float
    label: Literal["SIMULATED TRAFFIC"]


class ReindexRequest(_Model):
    """Body of `POST /v1/admin/reindex` (optional extra, P4.20)."""

    collection: Literal["faq"] = "faq"


class ReindexResponse(_Model):
    """Result of re-embedding a vector collection."""

    collection: str
    reindexed: int = Field(ge=0)
    dim: int = Field(ge=1)
    duration_ms: int = Field(ge=0)
