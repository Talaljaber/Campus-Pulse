"""Use-case-level interfaces for collaborators that are concrete classes elsewhere.

They are structural (Protocols), so the real classes satisfy them without importing this module:
- `TriageClassifier` is the surface of `application/services/triage_core.py::TriageCore` (ML, P1.15,
  not merged yet); `tests/fixtures/backend_fakes.FakeCore` implements it for the use-case tests.
- `Clarifier` is `ClarificationStrategy` plus the out-of-scope topic chips;
  `adapters/clarify/info_gain.InfoGainStrategy` implements it.
- `Actor` is the caller of a role-checked action. `frameworks/auth.Principal` satisfies it, so use
  cases check roles without importing the web layer.
- `FeedbackHandler` is the `/v1/feedback` surface that `FeedbackUseCase` (P3.11) implements.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from campuspulse_ai.application import dto
from campuspulse_ai.domain.entities import CoreResult
from campuspulse_ai.domain.values import (
    ClarificationConstraint,
    ClarificationQuestion,
    Lang,
    Location,
    NormalizedRequest,
)

ROLE_STUDENT = "student"
ROLE_STAFF = "staff"
ROLE_ADMIN = "admin"
ROLE_SERVICE = "service"
"""`service` is the bare service token (a server script), never a signed-in user."""


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
