"""What the FastAPI app needs from the composition root: `ApiServices` (P3.12).

The routes in `frameworks/` may import only `composition`, `application.dto`, `config` and `domain`
(tests/test_architecture.py), so the use cases reach them through this container. Every field is
optional: a route whose use case is not wired answers `501 not_implemented`, and `/health` reports
`degraded` until triage is wired.

`build_api(settings)` is the production builder used by `services/ai/api.py`. It wires what exists
without models or Supabase today; `build_online` (P4.3, assigned by the lead) will fill the rest of
the fields from the `OnlineContainer` (ARCHITECTURE §1.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from campuspulse_ai.application.use_cases.clarify import ClarifyUseCase
from campuspulse_ai.application.use_cases.escalate_sla import EscalateSlaUseCase
from campuspulse_ai.application.use_cases.explain import CounterfactualUseCase
from campuspulse_ai.application.use_cases.ports import FeedbackHandler
from campuspulse_ai.application.use_cases.sync_ticket import SyncTicketUseCase
from campuspulse_ai.application.use_cases.triage import TriageUseCase
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.ports import Clock
from campuspulse_ai.domain.values import Tier


@dataclass(frozen=True, slots=True)
class HealthInfo:
    """Wiring facts reported by `/health` (`dto.HealthResponse`).

    `artifact`/`sha`: the loaded `Manifest` (None before models exist); `sinks`: enabled ticket sinks
    in push order; `llm_tiers`: tiers with a key and a pinned model; `vector_store`: `pgvector`,
    `local` or None.
    """

    artifact: str | None = None
    sha: str | None = None
    encoder_loaded: bool = False
    sinks: tuple[str, ...] = ()
    llm_tiers: tuple[Tier, ...] = ()
    vector_store: str | None = None


@dataclass(frozen=True, slots=True)
class ApiServices:
    """The use cases behind the `/v1` routes. None = not wired here (the route answers 501).

    `tickets` serves the Linear webhook and the dashboard status route; `sla` is the SLA scanner the
    lifespan runs every `SLA_SCAN_MINUTES` with `clock` (both must be set for it to run).
    """

    triage: TriageUseCase | None = None
    clarify: ClarifyUseCase | None = None
    counterfactual: CounterfactualUseCase | None = None
    feedback: FeedbackHandler | None = None
    tickets: SyncTicketUseCase | None = None
    sla: EscalateSlaUseCase | None = None
    clock: Clock | None = None
    health: HealthInfo = field(default_factory=HealthInfo)


def build_api(settings: Settings) -> ApiServices:
    """Production wiring for `api.py`. Nothing model- or database-backed is built here yet."""
    del settings  # read by the builders added in later tasks
    return ApiServices()
