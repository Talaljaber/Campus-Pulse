"""`build_test(**overrides)`: the Backend use cases wired over in-memory adapters and fakes (P3.8).

No network, no model files: `FakeCore` stands in for `TriageCore` until the ML stream's
`tiny_model_dir` fixture lands (P1.16); then a test can pass `core=<the real core>`. The container is a
plain dataclass, not the `OnlineContainer` of `composition/online.py` (that module and `build_online`
do not exist yet, LD-37); its field names follow ARCHITECTURE §1.5 so the swap is mechanical.

Real classes: `InMemoryRepository`, `DefaultDecisionPolicy` (tau_ood from a valid FrozenConfig),
`InfoGainStrategy` over `config/clarify_questions.yaml`, `LLMMerger`, `GamingDetector`,
`RuleBasedUnderstander`, `TableActionPlanner` over `config/actions.yaml`, the allow-listed notifier
chain (`AllowlistedNotifier` -> `ChannelNotifier` -> `FakeNotifier` for email + `InAppNotifier`), and
`FallbackCalendar([SlotsTableCalendar])` over one seeded fictional advisor with free slots, and the
ticket lifecycle (`SyncTicketUseCase`, `EscalateSlaUseCase`, P4.9) over the same sinks and notifier.
Fakes: `FakeCore`, `ScriptedOracle` (empty script = LLM off), `FakeSink`, `FakeFAQ`, `FakeLAC`,
`FrozenClock`. Every email address is a `*.invalid` demo address on the test allow-list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from campuspulse_ai.adapters.calendar.fallback import FallbackCalendar
from campuspulse_ai.adapters.calendar.slots_table import SlotsTableCalendar
from campuspulse_ai.adapters.clarify.bank import QuestionBank
from campuspulse_ai.adapters.clarify.info_gain import InfoGainStrategy
from campuspulse_ai.adapters.integrations.supabase_sink import SupabaseSink
from campuspulse_ai.adapters.llm.prompt import load_prompt
from campuspulse_ai.adapters.notify.allowlist import AllowlistedNotifier
from campuspulse_ai.adapters.notify.channels import ChannelNotifier
from campuspulse_ai.adapters.notify.inapp import InAppNotifier
from campuspulse_ai.adapters.pulse.incident_detector import WindowedCentroidDetector
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.adapters.understand.rule_understander import ReplyTemplates, RuleBasedUnderstander
from campuspulse_ai.adapters.understand.schema import UnderstandLimits
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.application.services.gaming import GamingDetector
from campuspulse_ai.application.services.llm_merge import LLMMerger
from campuspulse_ai.application.use_cases.act import ActConfig, ActUseCase
from campuspulse_ai.application.use_cases.clarify import ClarifyUseCase
from campuspulse_ai.application.use_cases.escalate_sla import EscalateSlaUseCase
from campuspulse_ai.application.use_cases.incidents import IncidentActions, IncidentsUseCase
from campuspulse_ai.application.use_cases.messages import Messages
from campuspulse_ai.application.use_cases.reviews import ReviewAssigner, ReviewRouter
from campuspulse_ai.application.use_cases.sync_ticket import SyncTicketUseCase
from campuspulse_ai.application.use_cases.triage import DecisionFlow, LLMTiers, Pulse, TriageUseCase
from campuspulse_ai.config.frozen import FrozenConfig
from campuspulse_ai.config.paths import CONFIG_DIR
from campuspulse_ai.domain.policy import DefaultDecisionPolicy, RecipientPolicy
from campuspulse_ai.domain.ports import (
    CalendarProvider,
    Explainer,
    LabelOracle,
    RequestUnderstander,
    SentenceEncoder,
    TicketSink,
)
from campuspulse_ai.domain.routing import ActionsConfig, TableActionPlanner
from campuspulse_ai.domain.values import Advisor
from fixtures.backend_fakes import (
    FakeCore,
    FakeFAQ,
    FakeLAC,
    FakeNotifier,
    FakeSink,
    FrozenClock,
    ScriptedOracle,
)
from fixtures.frozen_config import valid_config_dict

STUDENT_INBOX = "student-inbox@campuspulse.invalid"
OFFICE_INBOX = "office-inbox@campuspulse.invalid"
ADVISOR_EMAIL = "advisor@campuspulse.invalid"
ALLOWLIST = frozenset({STUDENT_INBOX, OFFICE_INBOX, ADVISOR_EMAIL})
ADVISOR_NAME = "Dr. Test Advisor (fictional)"
INCIDENT_WINDOW_MIN = 30
FALLBACK_OFFICE = "academic"  # REVIEW_FALLBACK_OFFICE default (UD-13)
SLOT_COUNT = 3  # free 30-minute slots seeded from the next office-hours morning


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), path
    return data


def frozen_config() -> FrozenConfig:
    return FrozenConfig.from_dict(valid_config_dict(), source="tests")


def messages() -> Messages:
    return Messages.from_dict(load_yaml(CONFIG_DIR / "templates" / "messages.yaml"))


def act_config(
    *, student_inbox: str | None = STUDENT_INBOX, office_inbox: str | None = OFFICE_INBOX
) -> ActConfig:
    return ActConfig.from_dict(
        load_yaml(CONFIG_DIR / "act.yaml"), student_inbox=student_inbox, office_inbox=office_inbox
    )


def understander(clock: FrozenClock) -> RuleBasedUnderstander:
    prompt = load_prompt(CONFIG_DIR / "prompts", "understand", "v1")
    return RuleBasedUnderstander(
        ReplyTemplates.load(CONFIG_DIR / "templates"), clock, UnderstandLimits.from_prompt(prompt)
    )


@dataclass
class BackendTestContainer:
    """The wired use cases plus every fake, so tests can script inputs and inspect side effects."""

    repo: InMemoryRepository
    clock: FrozenClock
    core: FakeCore
    oracle: ScriptedOracle
    sink: FakeSink
    email: FakeNotifier
    faq: FakeFAQ
    config: FrozenConfig
    messages: Messages
    act_config: ActConfig
    advisor: Advisor
    act: ActUseCase
    flow: DecisionFlow
    triage: TriageUseCase
    clarify: ClarifyUseCase
    sync: SyncTicketUseCase
    sla: EscalateSlaUseCase
    extras: dict[str, Any] = field(default_factory=dict)

    def outbox(self, status: str | None = None) -> list[dict[str, Any]]:
        rows = list(self.repo.tables["outbox"].values())
        return [r for r in rows if status is None or r["status"] == status]

    def notifications(self) -> list[dict[str, Any]]:
        return list(self.repo.tables["notifications"].values())

    def events(self, action: str | None = None) -> list[dict[str, Any]]:
        rows = list(self.repo.tables["events"].values())
        return [r for r in rows if action is None or r["action"] == action]


def build_test(
    *,
    core: FakeCore | None = None,
    oracle: ScriptedOracle | None = None,
    llm_enabled: bool | None = None,
    sinks: list[TicketSink] | None = None,
    record_sink: bool = False,
    email: FakeNotifier | None = None,
    faq: FakeFAQ | None = None,
    calendar: CalendarProvider | None = None,
    explainer: Explainer | None = None,
    understander_override: RequestUnderstander | None = None,
    allowlist: frozenset[str] = ALLOWLIST,
    student_inbox: str | None = STUDENT_INBOX,
    office_inbox: str | None = OFFICE_INBOX,
    advisor_email: str = ADVISOR_EMAIL,
    pulse: Pulse | None = None,
    pulse_encoder: SentenceEncoder | None = None,
    advisor_routing: bool = True,
    tau_inc: float = 0.92,
    q_category: float = 0.5,
    q_priority: float = 0.5,
) -> BackendTestContainer:
    """Wire the Backend use cases for a test. Every argument overrides one collaborator.

    `oracle` defaults to an empty `ScriptedOracle`; the LLM tier is enabled when the oracle has a
    script (or `llm_enabled=True`). `record_sink=True` puts `SupabaseSink(repo)` first, as production
    does (it writes to this container's repository). `q_*` are the FakeLAC quantiles used when an LLM
    answer is merged. `advisor_routing` wires the UD-13 `ReviewAssigner` over the repository (no
    student is linked to an advisor until a test calls `link_student_advisor`).
    """
    clock = FrozenClock()
    repo = InMemoryRepository(clock)
    config = frozen_config()
    msgs = messages()
    acfg = act_config(student_inbox=student_inbox, office_inbox=office_inbox)
    policy = RecipientPolicy(allowlist)
    core = core or FakeCore()
    oracle = oracle or ScriptedOracle(script=[])
    email = email or FakeNotifier()
    faq = faq or FakeFAQ()
    sink = FakeSink(name="linear")
    advisor = repo.add_advisor(ADVISOR_NAME, acfg.booking_department, advisor_email)
    _seed_slots(repo, advisor, clock.at, acfg)
    notifier = AllowlistedNotifier(
        ChannelNotifier({"email": email, "in_app": InAppNotifier(repo)}), policy, repo
    )
    planner = TableActionPlanner(ActionsConfig.from_dict(load_yaml(CONFIG_DIR / "actions.yaml")))
    chosen: list[TicketSink] = sinks if sinks is not None else [sink]
    if record_sink:
        chosen = [SupabaseSink(repo), *chosen]
    act = ActUseCase(
        planner,
        faq,
        chosen,
        calendar or FallbackCalendar([SlotsTableCalendar(repo, clock, policy)], policy),
        notifier,
        policy,
        repo,
        clock,
        tau_faq=config.thresholds.tau_faq,
        config=acfg,
        messages=msgs,
    )
    oracles: list[LabelOracle] = [oracle]
    tiers = LLMTiers(
        oracles=oracles,
        merger=LLMMerger(),
        conformal_cat=FakeLAC("category", q_category),
        conformal_pri=FakeLAC("priority", q_priority),
        w_llm=config.llm.w_llm,
        prompt_version=config.llm.prompt_version,
        enabled=bool(oracle.script) if llm_enabled is None else llm_enabled,
    )
    incidents: IncidentsUseCase | None = None
    if pulse_encoder is not None:  # P4.10: the real detector and incident actions over local stores
        vectors = LocalNumpyVectorStore(pulse_encoder.dim, collections=("requests",))
        detector = WindowedCentroidDetector(repo, vectors, clock, tau_inc, INCIDENT_WINDOW_MIN)
        actions = IncidentActions(act, chosen, repo, repo, notifier, clock, msgs)
        pulse = Pulse(vectors=vectors, encoder=pulse_encoder, incidents=detector, actions=actions)
        incidents = IncidentsUseCase(repo, repo, chosen, notifier, clock, msgs, marks=repo,
                                     student_inbox=acfg.student_inbox)  # fmt: skip
    assigner = (
        ReviewAssigner(ReviewRouter(repo, FALLBACK_OFFICE), repo, notifier, clock, msgs, email_advisor=True)
        if advisor_routing
        else None
    )
    flow = DecisionFlow(
        policy=DefaultDecisionPolicy(config.thresholds.tau_ood),
        clarifier=InfoGainStrategy(QuestionBank.load(CONFIG_DIR / "clarify_questions.yaml")),
        tiers=tiers,
        explainer=explainer,
        gaming=GamingDetector(repo, min_requests=5, claim_ratio=0.8, high_ratio_max=0.2),
        understander=understander_override or understander(clock),
        act=act,
        repo=repo,
        clock=clock,
        messages=msgs,
        pulse=pulse,
        reviews=assigner,
    )
    return BackendTestContainer(
        repo=repo,
        clock=clock,
        core=core,
        oracle=oracle,
        sink=sink,
        email=email,
        faq=faq,
        config=config,
        messages=msgs,
        act_config=acfg,
        advisor=advisor,
        act=act,
        flow=flow,
        triage=TriageUseCase(core, flow, repo, clock, marks=repo),
        clarify=ClarifyUseCase(core, flow, repo, clock),
        sync=SyncTicketUseCase(chosen, repo, notifier, clock, msgs, student_inbox=acfg.student_inbox),
        sla=EscalateSlaUseCase(chosen, repo, msgs),
        extras={"incidents": incidents} if incidents else {},
    )


def _seed_slots(repo: InMemoryRepository, advisor: Advisor, now: datetime, cfg: ActConfig) -> None:
    """Free 30-minute slots from the next office-hours start (within the 24 h SLA window)."""
    hours = cfg.office_hours
    day = now
    while day.weekday() not in hours.weekdays or day.time() >= hours.end:
        day = (day + timedelta(days=1)).replace(hour=hours.start.hour, minute=hours.start.minute)
    start = max(day, day.replace(hour=hours.start.hour, minute=hours.start.minute, second=0, microsecond=0))
    start = start.replace(minute=0 if start.minute == 0 else 30, second=0, microsecond=0)
    if start < now:
        start += timedelta(minutes=30)
    for i in range(SLOT_COUNT):
        begins = start + timedelta(minutes=30 * i)
        repo.add_slot(advisor.id, begins, begins + timedelta(minutes=30))


def link_student_advisor(
    c: BackendTestContainer, student_alias: str = "demo-17", advisor_alias: str = "advisor"
) -> str:
    """UD-13 seed: a staff login (office `academic`) for the container's advisor, and a student
    profile with that advisor (`seed_demo_users.py` does this online). Returns the advisor's profile id."""
    profile_id = c.repo.add_profile(advisor_alias, "staff", FALLBACK_OFFICE)
    c.repo.tables["advisors"][c.advisor.id]["profile_id"] = profile_id
    c.repo.add_profile(student_alias, "student", advisor_id=c.advisor.id)
    return profile_id
