"""Use-case-level interfaces for collaborators that are concrete classes elsewhere.

They are structural (Protocols), so the real classes satisfy them without importing this module:
- `TriageClassifier` is the surface of `application/services/triage_core.py::TriageCore` (ML, P1.15,
  not merged yet); `tests/fixtures/backend_fakes.FakeCore` implements it for the use-case tests.
- `Clarifier` is `ClarificationStrategy` plus the out-of-scope topic chips;
  `adapters/clarify/info_gain.InfoGainStrategy` implements it.
- `Actor` is the caller of a role-checked action. `frameworks/auth.Principal` satisfies it, so use
  cases check roles without importing the web layer.
- `FeedbackHandler` is the `/v1/feedback` surface that `FeedbackUseCase` (P3.11) implements.
- `IdentityVerifier` turns a Supabase access token into a `UserIdentity` (P4.12);
  `adapters/integrations/supabase_auth.SupabaseIdentityVerifier` implements it.
- `BatchLabeler` labels `(request_id, text)` rows for `/v1/batch`; the composition root adapts the ML
  stream's `BatchPredictUseCase` (P1.15) to it.
- `ReportsSource` reads the offline model-lab report for `/v1/metrics`;
  `adapters/reports/json_reports.JsonReportsSource` implements it.
- `RedTeamJudge` scores one red-team item (P4.11); `adapters/redteam/scorer.RedTeamScorer`
  implements it.
- `LifecycleReads` are the reads feedback and Pulse need beyond the `Repository` port (a prediction
  by id, a pending review, the tickets of requests, incidents); both store adapters implement it.
- `Identified` is an `Actor` that also carries its auth user id (`frameworks/auth.Principal`).
- `SimulationMarks` writes and reads `requests.simulated` (simulator traffic, P4.10).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from campuspulse_ai.application import dto
from campuspulse_ai.domain.entities import CoreResult, Incident, Prediction, RedTeamItem, ReviewItem, Ticket
from campuspulse_ai.domain.values import (
    ClarificationConstraint,
    ClarificationQuestion,
    Lang,
    Location,
    NormalizedRequest,
    Outcome,
)

ROLE_STUDENT = "student"
ROLE_STAFF = "staff"
ROLE_ADMIN = "admin"
ROLE_SERVICE = "service"
"""`service` is the bare service token (a server script), never a signed-in user."""
USER_ROLES: frozenset[str] = frozenset({ROLE_STUDENT, ROLE_STAFF, ROLE_ADMIN})
"""Roles a `profiles` row may carry."""


@runtime_checkable
class TriageClassifier(Protocol):
    """ARCHITECTURE §2.0: the only path that produces labels.

    `classify` normalizes, runs the guards, the ensemble, the priority head with `constraints`, the
    floors and the conformal sets, and always returns probabilities. Raises `InvalidInput` for empty
    text and `ArtifactError` if the model is unusable.
    """

    def classify(
        self,
        raw: str,
        picked_location: Location | None = None,
        constraints: Sequence[ClarificationConstraint] = (),
        memory: bool = True,
    ) -> tuple[NormalizedRequest, CoreResult]: ...


@runtime_checkable
class Clarifier(Protocol):
    """`ClarificationStrategy` (select/apply) plus `topic_question` for status `out_of_scope`."""

    def select(self, core: CoreResult, lang: Lang, asked: Sequence[str]) -> ClarificationQuestion | None: ...

    def apply(
        self, core: CoreResult, question_id: str, option_id: str
    ) -> tuple[CoreResult, Sequence[ClarificationConstraint]]: ...

    def topic_question(self, lang: Lang) -> ClarificationQuestion: ...


@runtime_checkable
class Actor(Protocol):
    """Who performs an action: a role (`student`, `staff`, `admin`, `service`), the staff office
    (a D-005 code) and the student alias. Read-only."""

    @property
    def role(self) -> str: ...

    @property
    def office(self) -> str | None: ...

    @property
    def alias(self) -> str | None: ...


@runtime_checkable
class FeedbackHandler(Protocol):
    """`POST /v1/feedback` (P3.11 `FeedbackUseCase`): staff confirm or correct a prediction.

    Raises `Unauthorized` unless the reviewer is staff or admin, `NotFound` for an unknown prediction.
    """

    def run(self, cmd: dto.FeedbackRequest, reviewer: Actor) -> dto.FeedbackResponse: ...


@dataclass(frozen=True, slots=True)
class UserIdentity:
    """A verified signed-in user: the auth user id and their `profiles` row (role, office, alias)."""

    user_id: str
    role: str
    office: str | None
    alias: str | None


@runtime_checkable
class IdentityVerifier(Protocol):
    """Verifies an end user's Supabase access token (P4.12, `AUTH_MODE=supabase_jwt`).

    `verify(token)` returns the user's identity read from `profiles` (never from the token's claims or
    a client header), or None when the token is invalid or expired, the user has no profile, or the
    profile's role is not one of `USER_ROLES`. Raises `StoreError` when Supabase cannot be reached.
    """

    def verify(self, token: str) -> UserIdentity | None: ...


@runtime_checkable
class BatchLabeler(Protocol):
    """Labels rows in input order: `[(request_id, text)] -> [(request_id, category, priority)]`.

    The same labels as `predict.py` (tier 0 unless `use_llm`); empty text still gets a label (LD-17).
    Raises `ArtifactError` if the model is unusable.
    """

    def label(self, rows: Sequence[tuple[str, str]], *, use_llm: bool) -> list[tuple[str, str, str]]: ...


@runtime_checkable
class RedTeamJudge(Protocol):
    """The pass rule of a red-team item (P4.11); `adapters/redteam/scorer.RedTeamScorer` implements it.

    `base` is the core result of `item.base_text` (None without one). Returns `(passed, reason)`.
    Pure; never raises.
    """

    def score(
        self, item: RedTeamItem, core: CoreResult, outcome: Outcome, base: CoreResult | None
    ) -> tuple[bool, str]: ...


@runtime_checkable
class ReportsSource(Protocol):
    """The offline model-lab report written by `evaluate.py` (`REPORTS_DIR/model_lab.json`).

    `load()` returns the parsed JSON object, or None when no report exists yet. Raises `InvalidInput`
    when the file exists but is not a JSON object.
    """

    def load(self) -> Mapping[str, object] | None: ...


@runtime_checkable
class Identified(Protocol):
    """An actor with its Supabase auth user id (None for the service token or trusted headers)."""

    @property
    def user_id(self) -> str | None: ...


@runtime_checkable
class LifecycleReads(Protocol):
    """Reads beyond the `Repository` port (P3.11 feedback, P4.10 Pulse); `SupabaseRepository` and
    `InMemoryRepository` implement it with the same semantics.

    - `get_prediction(id)`: that prediction; `NotFound` if absent.
    - `open_review_for(prediction_id)`: its oldest `open` review item, or None.
    - `tickets_for_requests(ids)`: the tickets of those requests (links included), oldest first.
    - `get_incident(id)`: that incident; `NotFound` if absent.
    - `list_incidents(open_only=..., limit=...)`: incidents newest first (`opened_at`, then id).
    Raises `StoreError` when the store is unreachable.
    """

    def get_prediction(self, id: str) -> Prediction: ...

    def open_review_for(self, prediction_id: str) -> ReviewItem | None: ...

    def tickets_for_requests(self, request_ids: Sequence[str]) -> list[Ticket]: ...

    def get_incident(self, id: str) -> Incident: ...

    def list_incidents(self, *, open_only: bool, limit: int) -> list[Incident]: ...


@runtime_checkable
class SimulationMarks(Protocol):
    """`requests.simulated` (P4.10): `scripts/simulate_pulse.py` traffic is marked so the UI can label
    it. `mark_simulated(id)` sets the flag (`NotFound` for an unknown request); `simulated(ids)` returns
    the subset of `ids` that are marked. Both store adapters implement it; `StoreError` when unreachable.
    """

    def mark_simulated(self, request_id: str) -> None: ...

    def simulated(self, request_ids: Sequence[str]) -> set[str]: ...
