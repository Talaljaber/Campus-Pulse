"""What the FastAPI app needs from the composition root: `ApiServices` (P3.12, P4.9, P4.11, P4.12).

The routes in `frameworks/` may import only `composition`, `application.dto`, `config` and `domain`
(tests/test_architecture.py), so the use cases reach them through this container. Every use-case
field is optional: a route whose use case is not wired answers `501 not_implemented`, and `/health`
reports `degraded` until triage is wired.

The production builder is `composition.online.build_online(settings)` (P4.3), which `services/ai/api.py`
passes to `create_app`: the real frozen model, Supabase, the sinks and the notifier chain.
`build_api(settings)` wires only the identity verifier (no models, no repository); it is kept for
tools that need the contract without the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from campuspulse_ai.application.use_cases.announcements import AnnouncementsUseCase
from campuspulse_ai.application.use_cases.batch import BatchCsvUseCase
from campuspulse_ai.application.use_cases.clarify import ClarifyUseCase
from campuspulse_ai.application.use_cases.escalate_sla import SlaReminderUseCase
from campuspulse_ai.application.use_cases.explain import CounterfactualUseCase
from campuspulse_ai.application.use_cases.incidents import IncidentsUseCase
from campuspulse_ai.application.use_cases.metrics import MetricsUseCase
from campuspulse_ai.application.use_cases.ports import FeedbackHandler, IdentityVerifier
from campuspulse_ai.application.use_cases.reviews import ReviewsUseCase
from campuspulse_ai.application.use_cases.run_redteam import RunRedTeamUseCase
from campuspulse_ai.application.use_cases.sync_ticket import SyncTicketUseCase
from campuspulse_ai.application.use_cases.ticket_lifecycle import TicketLifecycleUseCase
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

    - `tickets` serves the inbound Linear webhook; `lifecycle` serves the ticket routes (status, forward,
      priority, comments, requester actions) and the `created` follow-up of triage (P9.3); `sla` is
      the SLA reminder scanner (loop every `SLA_SCAN_MINUTES`, sweep after responses, `POST
      /v1/cron/sla`; needs `clock`).
    - `incidents` serves the Pulse routes (`GET /v1/incidents`, `POST /v1/incidents/{id}/resolve`).
    - `reviews` serves `GET /v1/reviews` and `POST /v1/reviews/{id}/forward` (UD-13 advisor routing).
    - `batch`, `metrics` and `redteam` serve the model lab (`composition.redteam.build_redteam` builds
      `redteam` from the online core, its policy and the repository, with live memory on).
    - `identity` verifies user tokens in `AUTH_MODE=supabase_jwt`; without it a request carrying a
      user token gets `503 store_unavailable`.
    """

    triage: TriageUseCase | None = None
    clarify: ClarifyUseCase | None = None
    counterfactual: CounterfactualUseCase | None = None
    feedback: FeedbackHandler | None = None
    tickets: SyncTicketUseCase | None = None
    reviews: ReviewsUseCase | None = None
    sla: SlaReminderUseCase | None = None
    clock: Clock | None = None
    incidents: IncidentsUseCase | None = None
    batch: BatchCsvUseCase | None = None
    metrics: MetricsUseCase | None = None
    redteam: RunRedTeamUseCase | None = None
    identity: IdentityVerifier | None = None
    announcements: AnnouncementsUseCase | None = None
    health: HealthInfo = field(default_factory=HealthInfo)
    lifecycle: TicketLifecycleUseCase | None = None


def build_identity(settings: Settings) -> IdentityVerifier | None:
    """The Supabase identity verifier, or None when the mode or the credentials do not call for one."""
    if (
        settings.auth_mode != "supabase_jwt"
        or not settings.supabase_url
        or settings.supabase_service_role_key is None
    ):
        return None
    import httpx  # only the API process needs it; predict.py never imports this module

    from campuspulse_ai.adapters.integrations.supabase_auth import SupabaseIdentityVerifier

    return SupabaseIdentityVerifier(
        settings.supabase_url,
        settings.supabase_service_role_key,
        httpx.Client(timeout=settings.auth_timeout_s),
        ttl_s=settings.auth_cache_s,
    )


def build_api(settings: Settings) -> ApiServices:
    """Production wiring for `api.py` (see the module docstring)."""
    return ApiServices(identity=build_identity(settings))
