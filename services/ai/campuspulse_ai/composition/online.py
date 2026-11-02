"""`build_online(settings) -> ApiServices`: the production composition root of the API (P4.3, §1.5).

What `services/ai/api.py` runs at startup. It wires the **real** trained model from the frozen
artifacts and every online adapter:

1. `build_offline(<ARTIFACT_DIR>)` loads and checksums the frozen model (encoder included). The online
   `TriageCore` is the same class rebuilt with live memory (`PgVectorMemoryStore`); the offline
   container keeps `NullMemoryStore` and serves `/v1/batch`, so batch labels equal `predict.py`'s
   (§3.11).
2. Supabase (service role): `SupabaseRepository`, `PgVectorStore` (its constructor checks
   `vector_dim()` against the encoder) and `PgVectorMemoryStore`.
3. Sinks: `SupabaseSink` (the record) and, when `ENABLE_SINKS` and `LINEAR_API_KEY` are set,
   `RetryingSink(LinearSink)` (`config/integrations.yaml`).
4. Notifier chain: `AllowlistedNotifier(ChannelNotifier({email: GmailSmtpNotifier, in_app:
   InAppNotifier}))`; the email channel exists only with `GMAIL_SMTP_USER` + `GMAIL_APP_PASSWORD`.
5. Calendar: `FallbackCalendar([SlotsTableCalendar])`. FAQ: `VectorFAQRetriever` over pgvector.
6. LLM tier 1 and the LLM understander only when `ENABLE_LLM`, `OPENROUTER_API_KEY` and
   `OPENROUTER_TIER1_MODEL` are all set; otherwise tier 0 and the rule-based understander.
7. The use cases: triage, clarify, feedback (live learning), the ticket lifecycle and SLA scanner,
   Pulse (embedding upsert and incident detection), batch, metrics, the red team (live memory on),
   the identity verifier, and UD-13 advisor routing (review assignment, `GET /v1/reviews`, review
   and the P9.3 ticket lifecycle).

`wire_online(settings, offline, adapters, clock)` does steps 6-7 over any adapters, so tests run the
same wiring over `InMemoryRepository`, `LocalNumpyVectorStore` and fakes (`tests/unit/test_online.py`).

Startup errors are explicit (the process must not come up half-wired): `ArtifactMissing` (with the
fetch command) for a missing model or encoder, `ArtifactVersionMismatch` for a pgvector dimension
that differs from the encoder's, `StoreError` when Supabase is not configured or unreachable.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from campuspulse_ai.adapters.calendar.fallback import FallbackCalendar
from campuspulse_ai.adapters.calendar.slots_table import SlotsTableCalendar
from campuspulse_ai.adapters.clarify.bank import QuestionBank
from campuspulse_ai.adapters.clarify.info_gain import InfoGainStrategy
from campuspulse_ai.adapters.clock import SystemClock
from campuspulse_ai.adapters.faq.retriever import VectorFAQRetriever
from campuspulse_ai.adapters.integrations.supabase_sink import SupabaseSink
from campuspulse_ai.adapters.llm.cost import InMemoryCostLogger
from campuspulse_ai.adapters.llm.prompt import load_prompt
from campuspulse_ai.adapters.notify.allowlist import AllowlistedNotifier
from campuspulse_ai.adapters.notify.channels import ChannelNotifier
from campuspulse_ai.adapters.notify.email_templates import load_ticket_email_templates
from campuspulse_ai.adapters.notify.inapp import InAppNotifier
from campuspulse_ai.adapters.pulse.incident_detector import WindowedCentroidDetector
from campuspulse_ai.adapters.reports.json_reports import JsonReportsSource
from campuspulse_ai.adapters.understand.rule_understander import ReplyTemplates, RuleBasedUnderstander
from campuspulse_ai.adapters.understand.schema import UnderstandLimits
from campuspulse_ai.application.services.gaming import GamingDetector
from campuspulse_ai.application.services.llm_merge import LLMMerger
from campuspulse_ai.application.services.triage_core import TriageCore
from campuspulse_ai.application.use_cases.act import ActConfig, ActUseCase
from campuspulse_ai.application.use_cases.announcement_ports import AnnouncementStore
from campuspulse_ai.application.use_cases.announcements import AnnouncementsUseCase
from campuspulse_ai.application.use_cases.batch import BatchCsvUseCase
from campuspulse_ai.application.use_cases.clarify import ClarifyUseCase
from campuspulse_ai.application.use_cases.escalate_sla import EscalateSlaUseCase
from campuspulse_ai.application.use_cases.feedback import FeedbackUseCase
from campuspulse_ai.application.use_cases.incidents import IncidentActions, IncidentsUseCase
from campuspulse_ai.application.use_cases.journey_ports import JourneyStore
from campuspulse_ai.application.use_cases.messages import Messages
from campuspulse_ai.application.use_cases.metrics import MetricsUseCase
from campuspulse_ai.application.use_cases.offices import OfficeMap
from campuspulse_ai.application.use_cases.ports import (
    AdvisorDirectory,
    IdentityVerifier,
    LifecycleReads,
    ReviewReads,
    SimulationMarks,
)
from campuspulse_ai.application.use_cases.reviews import ReviewAssigner, ReviewRouter, ReviewsUseCase
from campuspulse_ai.application.use_cases.sync_ticket import SyncTicketUseCase
from campuspulse_ai.application.use_cases.ticket_emails import InboxBook, TicketMailer
from campuspulse_ai.application.use_cases.ticket_lifecycle import TicketLifecycleUseCase
from campuspulse_ai.application.use_cases.triage import DecisionFlow, LLMTiers, Pulse, TriageUseCase
from campuspulse_ai.composition.api import ApiServices, HealthInfo, build_identity
from campuspulse_ai.composition.offline import OfflineContainer, build_offline
from campuspulse_ai.composition.redteam import build_redteam, resolve
from campuspulse_ai.config.paths import CONFIG_DIR
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.errors import ArtifactMissing, StoreError
from campuspulse_ai.domain.policy import DefaultDecisionPolicy, RecipientPolicy
from campuspulse_ai.domain.ports import (
    CalendarProvider,
    Clock,
    LabelOracle,
    MemoryStore,
    Notifier,
    Repository,
    RequestUnderstander,
    TicketSink,
    VectorStore,
)
from campuspulse_ai.domain.routing import ActionsConfig, TableActionPlanner
from campuspulse_ai.domain.values import Tier

if TYPE_CHECKING:
    from campuspulse_ai.adapters.store.rest import RestApi as Client

log = logging.getLogger(__name__)

FETCH_HINT = "python scripts/fetch_models.py"
VECTOR_STORE_PGVECTOR = "pgvector"
SINK_LINEAR = "linear"
CHANNEL_EMAIL = "email"
CHANNEL_IN_APP = "in_app"
HAND_TUNED_YAML = CONFIG_DIR / "hand_tuned.yaml"
PROMPTS_DIR = CONFIG_DIR / "prompts"
TEMPLATES_DIR = CONFIG_DIR / "templates"
ORACLE_PROMPT = "oracle"
UNDERSTAND_PROMPT = "understand"
UNDERSTAND_PROMPT_VERSION = "v1"


@dataclass(frozen=True)
class OnlineAdapters:
    """The I/O adapters `wire_online` composes (Supabase and integrations in production, fakes in tests).

    - `reads`: the extra reads of feedback and Pulse; `marks`: `requests.simulated`; `reviews` and
      `directory`: the review queue and the student->advisor links of UD-13 (all four are the
      repository itself in production; without `reviews`/`directory` the review routes answer 501
      and HUMAN_REVIEW items are queued unassigned, as before UD-13).
    - `vectors` holds the live collections (`requests`, `faq`; `memory` behind `memory`).
    - `sinks`: the record sink first, then the mirrors (Linear), in push order.
    - `channels`: notifier per outbox kind (`in_app` always; `email` only when SMTP is configured).
    - `calendars`: providers for `FallbackCalendar`, in order.
    - `vector_store`: what `/health` reports (`pgvector` or `local`).
    - `journey`: the thread, hints and contacts of the ticket lifecycle (P9.3); without it the ticket
      routes answer 501.
    """

    repo: Repository
    reads: LifecycleReads
    marks: SimulationMarks | None
    vectors: VectorStore
    memory: MemoryStore
    sinks: tuple[TicketSink, ...]
    channels: Mapping[str, Notifier]
    calendars: tuple[CalendarProvider, ...] = ()
    identity: IdentityVerifier | None = None
    vector_store: str = VECTOR_STORE_PGVECTOR
    reviews: ReviewReads | None = None
    directory: AdvisorDirectory | None = None
    journey: JourneyStore | None = None
    announcements: AnnouncementStore | None = None  # P9.5; without it the routes answer 501


@dataclass(frozen=True, slots=True)
class HandTuned:
    """The thresholds no training data can set (LD-11): `tau_faq` (FAQ answer floor, P4.5) and
    `tau_inc` (incident clustering floor, D-015). Read from `config/hand_tuned.yaml` at startup so a
    hand-tuned value reaches the live service without re-freezing the model; `predict.py` and the
    scored labels use neither."""

    tau_faq: float
    tau_inc: float

    @classmethod
    def load(cls, path: Path, fallback: HandTuned) -> HandTuned:
        """The file's values; a missing file or key keeps `fallback` (the frozen config's values).
        Raises `ValueError` for a value outside (0, 1]."""
        data = _yaml(path) if path.is_file() else {}
        values = {key: float(data.get(key, getattr(fallback, key))) for key in ("tau_faq", "tau_inc")}
        for key, value in values.items():
            if not 0.0 < value <= 1.0:
                raise ValueError(f"{path}: {key} must be in (0, 1], got {value}")
        return cls(**values)


@dataclass(frozen=True)
class LLMWiring:
    """Tier-1 oracle and LLM understander, or none of them (tier 0 only)."""

    oracles: tuple[LabelOracle, ...] = ()
    understander: RequestUnderstander | None = None
    tiers: tuple[Tier, ...] = field(default_factory=tuple)


def build_online(settings: Settings | None = None) -> ApiServices:
    """Production wiring for `api.py` (module docstring). Raises at startup, never half-wires.

    Raises:
        ArtifactMissing / ArtifactChecksumMismatch / ArtifactVersionMismatch: unusable model artifacts.
        StoreError: Supabase not configured (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) or unreachable.
    """
    settings = settings or Settings()
    clock = SystemClock()
    offline = load_offline(settings)
    client = supabase_client(settings)
    adapters = supabase_adapters(settings, client, offline, clock)
    services = wire_online(settings, offline, adapters, clock, llm=llm_wiring(settings, offline, clock))
    log.info(
        "online services: artifact=%s sha=%s sinks=%s llm=%s",
        services.health.artifact,
        (services.health.sha or "")[:12],
        ",".join(services.health.sinks),
        ",".join(services.health.llm_tiers) or "off",
    )
    return services


def load_offline(settings: Settings) -> OfflineContainer:
    """`build_offline(ARTIFACT_DIR)` with a startup message that names the fix for a missing model."""
    model_dir = resolve(settings.artifact_dir)
    try:
        return build_offline(model_dir, settings=settings)
    except ArtifactMissing as exc:
        raise ArtifactMissing(
            f"model artifacts unusable under {model_dir}: {exc}. Fetch the encoder with `{FETCH_HINT}`"
        ) from exc


def supabase_client(settings: Settings) -> Client:
    """The service-role PostgREST client (`adapters/store/rest.PostgrestRest`: the PostgREST half of
    supabase-py, without the SDK's other modules, P4.13). Raises `StoreError` when it is not
    configured or the URL is malformed."""
    key = settings.supabase_service_role_key
    if not settings.supabase_url or key is None:
        raise StoreError("the API needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (server-side only)")
    from campuspulse_ai.adapters.store.rest import PostgrestRest  # online only

    try:
        secret = key.get_secret_value()
        return PostgrestRest(settings.supabase_url, secret, timeout_s=settings.store_timeout_s)
    except Exception as exc:  # a malformed URL; the key is never part of the message
        raise StoreError(f"cannot create the Supabase client: {type(exc).__name__}") from exc


def supabase_adapters(
    settings: Settings, client: Client, offline: OfflineContainer, clock: Clock
) -> OnlineAdapters:
    """The production adapters over one Supabase client (module docstring, steps 2-5)."""
    from campuspulse_ai.adapters.memory.cached import QueryCachingMemoryStore
    from campuspulse_ai.adapters.memory.pgvector_memory import PgVectorMemoryStore
    from campuspulse_ai.adapters.store.journey_supabase import SupabaseJourneyStore
    from campuspulse_ai.adapters.store.announcements_supabase import SupabaseAnnouncementStore
    from campuspulse_ai.adapters.store.supabase_store import SupabaseRepository
    from campuspulse_ai.adapters.vectors.pgvector import PgVectorStore

    repo = SupabaseRepository(client, clock)
    vectors = PgVectorStore(client, offline.config.encoder.dim)
    policy = RecipientPolicy(settings.demo_email_allowlist)
    return OnlineAdapters(
        repo=repo,
        reads=repo,
        marks=repo,
        vectors=vectors,
        memory=QueryCachingMemoryStore(
            PgVectorMemoryStore(vectors, client), clock, settings.memory_query_cache_s
        ),
        sinks=(SupabaseSink(repo), *mirror_sinks(settings, clock)),
        channels=notifier_channels(settings, repo, policy, clock),
        calendars=(SlotsTableCalendar(repo, clock, policy),),
        identity=build_identity(settings),
        vector_store=VECTOR_STORE_PGVECTOR,
        reviews=repo,
        directory=repo,
        journey=SupabaseJourneyStore(client, clock),
        announcements=SupabaseAnnouncementStore(client),
    )


def mirror_sinks(settings: Settings, clock: Clock) -> list[TicketSink]:
    """`RetryingSink(LinearSink)` when `ENABLE_SINKS` and `LINEAR_API_KEY` are set, else []."""
    enabled = _yaml(CONFIG_DIR / "integrations.yaml").get("enabled", [])
    if not settings.enable_sinks or settings.linear_api_key is None or SINK_LINEAR not in enabled:
        return []
    import httpx
    from pydantic import SecretStr

    from campuspulse_ai.adapters.integrations.linear import LinearMapping, LinearSink
    from campuspulse_ai.adapters.integrations.retrying import RetryingSink

    mapping = LinearMapping.load(CONFIG_DIR / "integrations.yaml")
    linear = LinearSink(
        settings.linear_api_key,
        settings.linear_webhook_secret or SecretStr(""),  # empty secret = every webhook is refused
        mapping,
        httpx.Client(timeout=mapping.timeout_s),
        clock,
    )
    return [RetryingSink(linear, settings.sink_retry_max, settings.sink_retry_base_s)]


def notifier_channels(
    settings: Settings, repo: Repository, policy: RecipientPolicy, clock: Clock
) -> dict[str, Notifier]:
    """In-app always; Gmail SMTP only with both `GMAIL_SMTP_USER` and `GMAIL_APP_PASSWORD`."""
    channels: dict[str, Notifier] = {CHANNEL_IN_APP: InAppNotifier(repo)}
    if settings.gmail_smtp_user and settings.gmail_app_password is not None:
        from campuspulse_ai.adapters.notify.gmail_smtp import GmailSmtpNotifier

        channels[CHANNEL_EMAIL] = GmailSmtpNotifier(
            settings.smtp_host,
            settings.smtp_port,
            settings.gmail_smtp_user,
            settings.gmail_app_password,
            policy=policy,
            clock=clock,
            timeout_s=settings.smtp_timeout_s,
            max_retries=settings.smtp_max_retries,
            backoff_s=settings.smtp_backoff_s,
            daily_cap=settings.smtp_daily_cap,
        )
    return channels


def llm_wiring(settings: Settings, offline: OfflineContainer, clock: Clock) -> LLMWiring:
    """Tier 1 (`OpenRouterOracle`) and `LLMUnderstander` when the LLM is enabled and configured.

    `ENABLE_LLM=false` (the default), or a missing key or tier-1 model id, gives `LLMWiring()`: the
    app runs on tier 0 and the rule-based understander, with no OpenRouter call ever made.
    """
    key, model = settings.openrouter_api_key, settings.openrouter_tier1_model
    if not settings.enable_llm or key is None or not model:
        if settings.enable_llm:
            log.warning("ENABLE_LLM is set but OPENROUTER_API_KEY or OPENROUTER_TIER1_MODEL is missing")
        return LLMWiring()
    from campuspulse_ai.adapters.llm.cache_sqlite import SqliteCache
    from campuspulse_ai.adapters.llm.openrouter import OpenRouterClient, OpenRouterOracle
    from campuspulse_ai.adapters.understand.llm_understander import LLMUnderstander

    config = offline.config
    http = OpenRouterClient(
        key.get_secret_value(),
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        retry_backoff_s=settings.llm_retry_backoff_s,
        provider=settings.llm_provider_preferences(),
        reasoning_off=settings.llm_reasoning_off,
    )
    settings.llm_cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = SqliteCache(settings.llm_cache_path)
    cost = InMemoryCostLogger(clock)
    oracle = OpenRouterOracle(
        Tier.TIER1,
        model,
        http,
        cache,
        cost,
        prompt=load_prompt(PROMPTS_DIR, ORACLE_PROMPT, config.llm.prompt_version),
        max_input_tokens=config.guards.max_tokens,
        daily_budget_usd=settings.llm_daily_budget_usd,
    )
    understander = LLMUnderstander(
        http,
        model,
        load_prompt(PROMPTS_DIR, UNDERSTAND_PROMPT, UNDERSTAND_PROMPT_VERSION),
        cache,
        cost,
        rule_understander(clock),
        clock=clock,
        max_input_tokens=config.guards.max_tokens,
        daily_budget_usd=settings.llm_daily_budget_usd,
    )
    return LLMWiring(oracles=(oracle,), understander=understander, tiers=(Tier.TIER1,))


def rule_understander(clock: Clock) -> RuleBasedUnderstander:
    """The offline understander (UD-10): templates and limits from `config/`."""
    prompt = load_prompt(PROMPTS_DIR, UNDERSTAND_PROMPT, UNDERSTAND_PROMPT_VERSION)
    limits = UnderstandLimits.from_prompt(prompt)
    return RuleBasedUnderstander(ReplyTemplates.load(TEMPLATES_DIR), clock, limits)


def with_memory(core: TriageCore, memory: MemoryStore) -> TriageCore:
    """The same core over another MemoryStore (§1.5: only the memory differs online)."""
    return TriageCore(
        normalizer=core.normalizer,
        guards=core.guards,
        ensemble=core.ensemble,
        evidence=core.evidence,
        head=core.head,
        finalizer=core.finalizer,
        conformal_cat=core.conformal_cat,
        conformal_pri=core.conformal_pri,
        memory=memory,
        clock=core.clock,
        config=core.config,
        artifact=core.artifact,
        urgency_floor=core.urgency_floor,
        cue_floor=core.cue_floor,
    )


def wire_online(
    settings: Settings,
    offline: OfflineContainer,
    adapters: OnlineAdapters,
    clock: Clock,
    *,
    llm: LLMWiring | None = None,
) -> ApiServices:
    """Compose the use cases over `adapters` (module docstring, steps 6-7). Pure wiring: no I/O
    beyond reading `config/*.yaml`. Raises `ValueError`/`KeyError` for a malformed config file."""
    llm = llm or LLMWiring()
    config = offline.config
    frozen = HandTuned(config.thresholds.tau_faq, config.thresholds.tau_inc)
    tuned = HandTuned.load(HAND_TUNED_YAML, frozen)
    if tuned != frozen:
        log.info("hand-tuned thresholds %s override the frozen %s", tuned, frozen)
    repo = adapters.repo
    core = with_memory(offline.core, adapters.memory)
    policy = DefaultDecisionPolicy(config.thresholds.tau_ood)
    recipients = RecipientPolicy(settings.demo_email_allowlist)
    messages = Messages.from_dict(_yaml(TEMPLATES_DIR / "messages.yaml"))
    act_config = ActConfig.from_dict(
        _yaml(CONFIG_DIR / "act.yaml"),
        student_inbox=settings.demo_student_inbox,
        office_inbox=settings.demo_office_inbox,
    )
    notifier = AllowlistedNotifier(ChannelNotifier(dict(adapters.channels)), recipients, repo)
    actions_config = ActionsConfig.from_dict(_yaml(CONFIG_DIR / "actions.yaml"))
    planner = TableActionPlanner(actions_config)
    offices = OfficeMap.from_actions(actions_config)
    sinks = adapters.sinks
    act = ActUseCase(
        planner,
        # FAQ vectors are seeded with the raw ONNX encoder (scripts/seed_faq.py): query in that space
        VectorFAQRetriever(adapters.vectors, offline.raw_encoder or offline.encoder),
        sinks,
        FallbackCalendar(list(adapters.calendars), recipients),
        notifier,
        recipients,
        repo,
        clock,
        tau_faq=tuned.tau_faq,
        config=act_config,
        messages=messages,
    )
    tiers = LLMTiers(
        oracles=llm.oracles,
        merger=LLMMerger(),
        conformal_cat=core.conformal_cat,
        conformal_pri=core.conformal_pri,
        w_llm=config.llm.w_llm,
        prompt_version=config.llm.prompt_version,
        enabled=bool(llm.oracles),
    )
    incident_actions = IncidentActions(act, sinks, repo, adapters.reads, notifier, clock, messages)
    directory = adapters.directory
    assigner = (
        ReviewAssigner(
            ReviewRouter(directory, settings.review_fallback_office),
            repo,
            notifier,
            clock,
            messages,
            email_advisor=settings.review_email_advisor,
        )
        if directory is not None
        else None
    )
    feedback = FeedbackUseCase(
        adapters.reads, repo, adapters.memory, act, offline.encoder, clock, sinks, directory=directory
    )
    reviews = (
        ReviewsUseCase(
            adapters.reviews,
            adapters.reads,
            feedback,
            offices,
            directory,
            repo,
            messages,
            limit=settings.review_list_limit,
        )
        if adapters.reviews is not None and directory is not None
        else None
    )
    flow = DecisionFlow(
        policy=policy,
        clarifier=InfoGainStrategy(QuestionBank.load(CONFIG_DIR / "clarify_questions.yaml")),
        tiers=tiers,
        explainer=None,  # P3.4 (ML) is not built: the flow explains with the core's evidence and neighbours
        gaming=GamingDetector(
            repo, settings.gaming_min_requests, settings.gaming_claim_ratio, settings.gaming_high_ratio_max
        ),
        understander=llm.understander or rule_understander(clock),
        act=act,
        repo=repo,
        clock=clock,
        messages=messages,
        pulse=Pulse(
            vectors=adapters.vectors,
            encoder=offline.encoder,
            incidents=WindowedCentroidDetector(
                repo, adapters.vectors, clock, tuned.tau_inc, settings.incident_window_min
            ),
            actions=incident_actions,
        ),
        reviews=assigner,
    )
    lifecycle = (
        TicketLifecycleUseCase(
            repo,
            adapters.journey,
            TicketMailer(
                load_ticket_email_templates(TEMPLATES_DIR / "email"),
                notifier,
                clock,
                InboxBook(
                    student_inbox=settings.demo_student_inbox,
                    office_inboxes=settings.demo_office_inboxes,
                    default_office_inbox=settings.demo_office_inbox,
                    admin_inbox=settings.demo_admin_inbox,
                ),
                settings.public_web_url,
            ),
            sinks,
            clock,
            actions_config.sla_hours,
            offices,
            messages,
            # the encoder the online core runs: hints and the chat preview live in the same space
            offline.encoder,
        )
        if adapters.journey is not None
        else None
    )
    manifest = offline.manifest
    return ApiServices(
        triage=TriageUseCase(core, flow, repo, clock, marks=adapters.marks),
        clarify=ClarifyUseCase(core, flow, repo, clock),
        feedback=feedback,
        tickets=SyncTicketUseCase(
            sinks, repo, notifier, clock, messages, student_inbox=act_config.student_inbox
        ),
        reviews=reviews,
        lifecycle=lifecycle,
        sla=EscalateSlaUseCase(sinks, repo, messages),
        clock=clock,
        incidents=IncidentsUseCase(
            adapters.reads,
            repo,
            sinks,
            notifier,
            clock,
            messages,
            marks=adapters.marks,
            student_inbox=act_config.student_inbox,
        ),
        batch=BatchCsvUseCase(offline.labeler, max_rows=settings.batch_max_rows),
        metrics=MetricsUseCase(
            JsonReportsSource(resolve(settings.reports_dir)), repo, adapters.memory, core.artifact
        ),
        redteam=build_redteam(core, policy, repo, clock, settings, memory=True),
        identity=adapters.identity,
        announcements=(
            AnnouncementsUseCase(adapters.announcements, clock, offices.offices)
            if adapters.announcements is not None
            else None
        ),
        health=HealthInfo(
            artifact=manifest.artifact_version,
            sha=manifest.sha,
            encoder_loaded=True,
            sinks=tuple(s.name for s in sinks),
            llm_tiers=llm.tiers,
            vector_store=adapters.vector_store,
        ),
    )


def _yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping")
    return data
