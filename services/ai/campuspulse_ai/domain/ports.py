"""Ports: the interfaces every adapter implements (ARCHITECTURE §1.4).

All are runtime-checkable Protocols. Ports pass tuples and value objects, never
numpy arrays; adapters convert. Each docstring names its concrete implementations
and the domain errors it may raise.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from campuspulse_ai.domain.entities import (
    Case,
    Clarification,
    CoreResult,
    Explanation,
    Incident,
    IncidentDecision,
    LLMCall,
    MemoryExample,
    OracleAnswer,
    OracleContext,
    OutboxMessage,
    Prediction,
    RedTeamItem,
    Request,
    ReviewItem,
    Scorecard,
    Ticket,
)
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import (
    ActionPlan,
    ActionType,
    Advisor,
    Booking,
    ClarificationBudget,
    ClarificationConstraint,
    ClarificationQuestion,
    EnsembleOutput,
    EvidenceVector,
    FAQHit,
    GuardVerdict,
    InboundEvent,
    Lang,
    Location,
    Manifest,
    MemoryStats,
    Neighbor,
    NormalizedRequest,
    OfficeHours,
    Outcome,
    PredictionSet,
    ProbabilityTarget,
    ProblemCluster,
    ProbVector,
    RequestStatus,
    RouterStats,
    Slot,
    StudentSignals,
    TicketLink,
    Tier,
    Understanding,
    VectorHit,
    VectorItem,
)

# --- preprocessing and guards -------------------------------------------------------------


@runtime_checkable
class Normalizer(Protocol):
    """impl: adapters/preprocess/normalizer.py::DefaultNormalizer. Raises InvalidInput on empty text."""

    def normalize(self, raw: str, picked_location: Location | None = None) -> NormalizedRequest: ...


@runtime_checkable
class Guard(Protocol):
    """One concern per guard, run in order Gibberish, Injection, Safety. Never raises.

    impls: GibberishGuard, InjectionGuard (mode strip_regex_only offline / full online),
    SafetyGuard (offline "danger" from the lexicon only, LD-19).
    """

    name: str

    def inspect(self, req: NormalizedRequest) -> GuardVerdict: ...


@runtime_checkable
class ExemplarSimilarity(Protocol):
    """impl: StoreExemplarSimilarity over a VectorStore collection (bank = collection name)."""

    def max_similarity(self, text: str, bank: str) -> tuple[float, str]: ...


# --- models ---------------------------------------------------------------------------------


@runtime_checkable
class SentenceEncoder(Protocol):
    """impls: OnnxEncoder (int8, "query: " prefix), CachingEncoder, HashingEncoder (tests).

    Raises ArtifactMissing.
    """

    dim: int
    model_id: str

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


@runtime_checkable
class ProbabilisticClassifier(Protocol):
    """One per target.

    impls: TfidfLR (m1), EmbedLR (m2lr), KnnClassifier (m2knn), TransformerFT (m3, not built, UD-4).
    """

    name: str
    target: ProbabilityTarget

    def fit(
        self, texts: Sequence[str], y: Sequence[str], sample_weight: Sequence[float] | None = None
    ) -> None: ...

    def predict_proba(self, texts: Sequence[str]) -> list[ProbVector]: ...

    def save(self, dir: Path) -> None: ...

    @classmethod
    def load(cls, dir: Path) -> ProbabilisticClassifier: ...


@runtime_checkable
class VectorStore(Protocol):
    """Named collections: train, injection_exemplars, safety_exemplars, requests, memory, faq.

    Cosine similarity, descending, deterministic tie-break on id. VectorHit.embedding only
    when filters["with_embedding"] is true. impls: LocalNumpyVectorStore, PgVectorStore.
    Errors: StoreError, ArtifactMissing; dim mismatch -> ArtifactVersionMismatch at construction.
    """

    dim: int

    def upsert(self, collection: str, items: Sequence[VectorItem]) -> None: ...

    def search(
        self,
        collection: str,
        query: Sequence[float],
        k: int,
        min_sim: float = 0.0,
        filters: Mapping[str, object] | None = None,
    ) -> list[VectorHit]: ...

    def set_active(self, collection: str, id: str, active: bool) -> None: ...

    def count(self, collection: str, filters: Mapping[str, object] | None = None) -> int: ...


@runtime_checkable
class Ensemble(Protocol):
    """impl: WeightedEnsemble (members and weights from FrozenConfig). ArtifactVersionMismatch."""

    members: tuple[str, ...]

    def predict(self, texts: Sequence[str], memory: MemoryStore | None) -> list[EnsembleOutput]: ...


@runtime_checkable
class EvidenceExtractor(Protocol):
    """impl: LexiconEvidenceExtractor. `stated_urgency` is never a feature."""

    def extract(self, req: NormalizedRequest) -> EvidenceVector: ...


@runtime_checkable
class PriorityHead(Protocol):
    """impl: LogisticPriorityHead. Floors are applied outside, by PriorityFinalizer."""

    def fit(
        self,
        p_pri_oof: Sequence[ProbVector],
        evidence: Sequence[EvidenceVector],
        y: Sequence[str],
        sample_weight: Sequence[float] | None,
    ) -> None: ...

    def predict(
        self,
        p_pri_model: ProbVector,
        evidence: EvidenceVector,
        constraints: Sequence[ClarificationConstraint] = (),
    ) -> ProbVector: ...

    def save(self, dir: Path) -> None: ...

    @classmethod
    def load(cls, dir: Path) -> PriorityHead: ...


@runtime_checkable
class ConformalPredictor(Protocol):
    """impl: LACConformal; optional MondrianByLang. ValueError if calibration n is too small."""

    target: ProbabilityTarget
    alpha: float

    def calibrate(self, probs: Sequence[ProbVector], y: Sequence[str], groups: Sequence[str]) -> None: ...

    def predict_set(self, p: ProbVector) -> PredictionSet: ...

    def save(self, dir: Path) -> None: ...

    @classmethod
    def load(cls, dir: Path) -> ConformalPredictor: ...


# --- decisions, clarification, LLM tiers, understanding --------------------------------------


@runtime_checkable
class DecisionPolicy(Protocol):
    """Pure; the implementation lives in domain/policy.py."""

    def decide(self, core: CoreResult, budget: ClarificationBudget, llm_allowed: bool) -> Outcome: ...


@runtime_checkable
class ClarificationStrategy(Protocol):
    """impl: InfoGainStrategy(QuestionBank).

    apply() returns constraints; ClarifyUseCase re-runs the core with them (LD-29).

    Raises ClarificationBudgetExceeded.
    """

    def select(self, core: CoreResult, lang: Lang, asked: Sequence[str]) -> ClarificationQuestion | None: ...

    def apply(
        self, core: CoreResult, question_id: str, option_id: str
    ) -> tuple[CoreResult, Sequence[ClarificationConstraint]]: ...


@runtime_checkable
class LabelOracle(Protocol):
    """LLM tier, constrained to the allowed sets. impls: OpenRouterOracle, NullOracle, ScriptedOracle.

    Errors: LLMUnavailable (fall back to tier 0), LLMOutputOutOfSet (discard and fall back).
    """

    tier: Tier
    model_id: str

    def choose(
        self,
        req: NormalizedRequest,
        allowed_cat: PredictionSet,
        allowed_pri: PredictionSet,
        context: OracleContext,
    ) -> OracleAnswer: ...


@runtime_checkable
class RequestUnderstander(Protocol):
    """Structured understanding of a request (UD-10). Never changes the labels in `decided`.

    impls: LLMUnderstander (Haiku, schema-enforced, cached), RuleBasedUnderstander (fallback).
    """

    def understand(
        self, req: NormalizedRequest, decided: CoreResult, action_hint: ActionType | None
    ) -> Understanding: ...


@runtime_checkable
class ResponseCache(Protocol):
    """impls: SqliteCache, SupabaseCache, DictCache."""

    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...


@runtime_checkable
class CostLogger(Protocol):
    """impls: InMemoryCostLogger, SupabaseCostLogger. totals() -> {"usd", "calls", "cached"}."""

    def log(self, call: LLMCall) -> None: ...

    def totals(self) -> dict[str, float]: ...


@runtime_checkable
class Explainer(Protocol):
    """impl: OcclusionExplainer. On failure, sets flag explanation_failed; never fails triage."""

    def explain(
        self, req: NormalizedRequest, core: CoreResult, decided: tuple[Category, Priority]
    ) -> Explanation: ...

    def counterfactual(
        self, req: NormalizedRequest, drop_token: str
    ) -> tuple[Category, Priority, ProbVector, ProbVector]: ...


@runtime_checkable
class MemoryStore(Protocol):
    """impls: NullMemoryStore (offline; add raises StoreError), InMemoryMemoryStore,
    PgVectorMemoryStore.
    """

    def add(self, ex: MemoryExample) -> MemoryExample: ...

    def active(self, since: datetime | None = None) -> list[MemoryExample]: ...

    def deactivate(self, id: str) -> None: ...

    def stats(self) -> MemoryStats: ...

    def neighbors(self, embedding: Sequence[float], k: int, min_sim: float) -> list[Neighbor]: ...


# --- actions and integrations ----------------------------------------------------------------


@runtime_checkable
class ActionPlanner(Protocol):
    """Routing table -> ActionPlan; pure implementation in domain/routing.py over config/actions.yaml."""

    def plan(
        self, category: Category, priority: Priority, flags: frozenset[str], provisional: bool
    ) -> ActionPlan: ...


@runtime_checkable
class FAQRetriever(Protocol):
    """impl: VectorFAQRetriever over the VectorStore "faq" collection. StoreError."""

    def search(self, text: str, lang: Lang, k: int) -> list[FAQHit]: ...


@runtime_checkable
class TicketSink(Protocol):
    """impls: SupabaseSink, LinearSink, WebhookSink (future), FakeSink; RetryingSink wrapper. SinkError."""

    name: str

    def create(self, ticket: Ticket) -> TicketLink: ...

    def update_status(self, ticket: Ticket) -> None: ...

    def close(self, ticket: Ticket) -> None: ...

    def handle_inbound(self, payload: bytes, signature: str) -> InboundEvent | None: ...


@runtime_checkable
class Notifier(Protocol):
    """impls: GmailSmtpNotifier, InAppNotifier, FakeNotifier; decorator AllowlistedNotifier.

    Errors: NotificationError(retryable), RecipientNotAllowed.
    """

    def send(self, msg: OutboxMessage) -> OutboxMessage: ...


@runtime_checkable
class CalendarProvider(Protocol):
    """impls: SlotsTableCalendar (default), GoogleCalendarProvider (future), FakeCalendar.

    Raises CalendarUnavailable.
    """

    def find_slot(
        self, advisor_ids: Sequence[str], window: tuple[datetime, datetime], office_hours: OfficeHours
    ) -> Slot | None: ...

    def book(self, slot: Slot, attendees: Sequence[str], title: str) -> Booking: ...


@runtime_checkable
class Repository(Protocol):
    """One persistence port. impls: InMemoryRepository, SupabaseRepository (service role).

    Raises StoreError, NotFound.
    """

    # requests
    def save_request(self, r: Request) -> Request: ...

    def get_request(self, id: str) -> Request: ...

    def set_request_status(self, id: str, status: RequestStatus) -> None: ...

    # predictions / clarifications / review
    def save_prediction(self, p: Prediction) -> Prediction: ...

    def latest_prediction(self, request_id: str) -> Prediction: ...

    def save_clarification(self, c: Clarification) -> Clarification: ...

    def clarifications_for(self, request_id: str) -> list[Clarification]: ...

    def enqueue_review(self, item: ReviewItem) -> ReviewItem: ...

    def resolve_review(self, item: ReviewItem) -> None: ...

    # tickets / incidents / outbox / signals / audit
    def save_ticket(self, t: Ticket) -> Ticket: ...

    def get_ticket(self, id: str) -> Ticket: ...

    def overdue_open_tickets(self, now: datetime) -> list[Ticket]: ...

    def save_ticket_link(self, link: TicketLink) -> None: ...

    def save_incident(self, i: Incident) -> Incident: ...

    # Open incidents of `building` opened at or after `since`; `category` None = any category (D-017).
    def open_incidents(self, building: str, category: Category | None, since: datetime) -> list[Incident]: ...

    def save_outbox(self, m: OutboxMessage) -> OutboxMessage: ...

    def bump_student_signals(
        self, alias: str, claimed_urgent: bool, was_high: bool, injection: bool
    ) -> StudentSignals: ...

    def append_event(self, actor: str, action: str, entity: str, payload: Mapping[str, object]) -> None: ...

    def save_redteam_run(self, scorecard: Scorecard) -> str: ...

    # LD-16 additions
    def ticket_by_link(self, sink: str, external_id: str) -> Ticket: ...

    def incident_members(self, incident_id: str) -> list[tuple[Ticket, Request]]: ...

    def free_slots(self, advisor_ids: Sequence[str], window: tuple[datetime, datetime]) -> list[Slot]: ...

    def claim_slot(self, slot: Slot, booked_by: str) -> bool: ...

    def save_case(self, c: Case) -> Case: ...

    def save_notification(self, alias: str, kind: str, payload: Mapping[str, object]) -> None: ...

    def advisors_for(self, department: str) -> list[Advisor]: ...

    def router_stats(self, since: datetime | None = None) -> RouterStats: ...

    def redteam_history(self, limit: int = 20) -> list[Scorecard]: ...


# --- pulse, insights, red team, infrastructure ------------------------------------------------


@runtime_checkable
class IncidentDetector(Protocol):
    """impl: WindowedCentroidDetector over the VectorStore "requests" collection. StoreError."""

    def detect(self, req: Request, pred: Prediction, embedding: Sequence[float]) -> IncidentDecision: ...


@runtime_checkable
class ProblemClusterer(Protocol):
    """Groups stored request embeddings into recurring problems (UD-6). impl: GreedyCentroidClusterer."""

    def cluster(self, items: Sequence[VectorHit], tau: float, min_size: int) -> list[ProblemCluster]: ...


@runtime_checkable
class RedTeamGenerator(Protocol):
    """impls: PerturbationGenerator (default, offline), LLMRedTeamGenerator (future)."""

    def generate(self, n: int, styles: Sequence[str], seed: int) -> list[RedTeamItem]: ...


@runtime_checkable
class Clock(Protocol):
    """impls: SystemClock, FrozenClock. now() is tz-aware, Asia/Amman."""

    def now(self) -> datetime: ...


@runtime_checkable
class ArtifactStore(Protocol):
    """impl: FileArtifactStore. ArtifactMissing / ArtifactChecksumMismatch / ArtifactVersionMismatch."""

    def load_manifest(self, model_dir: Path) -> Manifest: ...

    def write_manifest(self, model_dir: Path, files: Sequence[Path]) -> Manifest: ...


ALL_PORTS: tuple[type, ...] = (
    Normalizer,
    Guard,
    ExemplarSimilarity,
    SentenceEncoder,
    ProbabilisticClassifier,
    VectorStore,
    Ensemble,
    EvidenceExtractor,
    PriorityHead,
    ConformalPredictor,
    DecisionPolicy,
    ClarificationStrategy,
    LabelOracle,
    RequestUnderstander,
    ResponseCache,
    CostLogger,
    Explainer,
    MemoryStore,
    ActionPlanner,
    FAQRetriever,
    TicketSink,
    Notifier,
    CalendarProvider,
    Repository,
    IncidentDetector,
    ProblemClusterer,
    RedTeamGenerator,
    Clock,
    ArtifactStore,
)

__all__ = [p.__name__ for p in ALL_PORTS] + ["ALL_PORTS"]
