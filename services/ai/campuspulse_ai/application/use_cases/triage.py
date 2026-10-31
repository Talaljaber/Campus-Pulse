"""TriageUseCase and the decision flow it shares with ClarifyUseCase (SPEC §5.1, ARCHITECTURE §2.1).

`TriageUseCase.run` is steps [1]-[6] (classify, save the request); `DecisionFlow.run` is [4'] and
[7]-[14] (distress, policy, question, LLM tiers, final labels, anti-gaming, explanation,
understanding, actions, Pulse, audit). `ClarifyUseCase` re-enters `DecisionFlow.run` at [7] after an
answer (2.1b), so both routes return the same `TriageResponse` contract.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from campuspulse_ai.application import dto
from campuspulse_ai.application.services.gaming import GamingDetector
from campuspulse_ai.application.services.llm_merge import LLMMerger
from campuspulse_ai.application.services.understanding import understanding_flags
from campuspulse_ai.application.use_cases import responses as out
from campuspulse_ai.application.use_cases.act import ActUseCase
from campuspulse_ai.application.use_cases.messages import Messages
from campuspulse_ai.application.use_cases.ports import Clarifier, TriageClassifier
from campuspulse_ai.domain.entities import (
    Clarification,
    CoreResult,
    Explanation,
    OracleContext,
    Prediction,
    Request,
    ReviewItem,
)
from campuspulse_ai.domain.errors import (
    ArtifactError,
    CampusPulseError,
    InvalidInput,
    LLMOutputOutOfSet,
    LLMUnavailable,
    StoreError,
)
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.policy import DefaultDecisionPolicy
from campuspulse_ai.domain.ports import (
    Clock,
    ConformalPredictor,
    Explainer,
    IncidentDetector,
    LabelOracle,
    Repository,
    RequestUnderstander,
    SentenceEncoder,
    VectorStore,
)
from campuspulse_ai.domain.values import (
    ClarificationBudget,
    ClarificationQuestion,
    Location,
    MetaValue,
    Money,
    NormalizedRequest,
    Outcome,
    RequestStatus,
    Tier,
    VectorItem,
)

log = logging.getLogger(__name__)

# SPEC §5.1 [8]: at most one question, or two when the first answer is "not sure" (rule structure,
# not a tuned threshold).
DEFAULT_MAX_QUESTIONS = 1
MAX_QUESTIONS_IF_UNSURE = 2

REQUESTS_COLLECTION = "requests"
"""VectorStore collection of every live request embedding (UD-6, ARCHITECTURE §2.1 [12b])."""
ACTOR = "triage"

INJECTION = "injection_attempt"
DISTRESS = "distress"
GIBBERISH = "gibberish"
OUT_OF_SCOPE = "out_of_scope"
NEEDS_REVIEW = "needs_review"
SAFETY = "safety"
LLM_OUT_OF_SET = "llm_out_of_set"
EXPLANATION_FAILED = "explanation_failed"
REVIEW_DISTRESS = "distress"
REVIEW_NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True, slots=True)
class LLMTiers:
    """The escalation tiers (SPEC §5.1 [7e], UD-5): tier 1 only for this submission (UD-3).

    `enabled` is `Settings.enable_llm` and a key being present; the conformal predictors are the core's
    (the merged sets are recomputed with the same quantiles and never grow).
    """

    oracles: Sequence[LabelOracle]
    merger: LLMMerger
    conformal_cat: ConformalPredictor
    conformal_pri: ConformalPredictor
    w_llm: float
    prompt_version: str
    enabled: bool

    @property
    def usable(self) -> bool:
        return self.enabled and bool(self.oracles)


@dataclass(frozen=True, slots=True)
class Pulse:
    """Online-only wiring for [12b]/[13]: store the request embedding, then detect incidents.

    The embedding is the one the core computed (`CoreResult.embedding`, D-012); `encoder` embeds
    `model_text` only when the core has none (e.g. a request that was entirely an injection).
    `incidents` may be None (embeddings are still stored).
    """

    vectors: VectorStore
    encoder: SentenceEncoder
    incidents: IncidentDetector | None = None


class DecisionFlow:
    """Steps [4'] and [7]-[14] of ARCHITECTURE §2.1 for one classified request.

    `run(request, req, core, budget=..., asked=..., path=..., clarified=..., debug_members=...)`:
    - [4'] flag `distress` -> no LLM, no explanation, no action: a prediction row (for the review FK),
      a `distress` review item, status `distress`, the supportive message with the counselling
      placeholder and 911.
    - [7] `DefaultDecisionPolicy.decide_with_path`; the last rule id of each evaluation is appended to
      `explanation.trace.policy_path`. The LLM is allowed only when the tiers are usable and the request
      has no `injection_attempt` flag.
    - OUT_OF_SCOPE -> topic chips (`question_id: "topic"`, saved as the pending question).
    - ASK -> the clarifier's question, saved as pending; status `needs_clarification`. If no bank
      question applies, the policy is re-run with the budget spent.
    - ESCALATE -> each tier in order: `LLMUnavailable` stops, `LLMOutputOutOfSet` adds
      `llm_out_of_set` and tries the next tier, an answer is merged (`LLMMerger`) and the loop stops
      once both sets are singletons; then rules c/f only (`after_escalation=True`).
    - ACCEPT / HUMAN_REVIEW -> final labels (a safety core is always high), anti-gaming flags,
      explanation (a failure adds `explanation_failed`), the prediction row, a review item and a
      provisional plan for HUMAN_REVIEW, the understanding (UD-10), the actions (`ActUseCase.run`),
      then [12b]/[13] when `pulse` is wired, the request status and one audit event.

    Errors: `StoreError` from the core writes (request, prediction, clarification) propagates (503);
    the explainer, LLM tiers, sinks, notifier, calendar and Pulse degrade and never fail the request.
    """

    def __init__(
        self,
        *,
        policy: DefaultDecisionPolicy,
        clarifier: Clarifier,
        tiers: LLMTiers,
        explainer: Explainer | None,
        gaming: GamingDetector,
        understander: RequestUnderstander,
        act: ActUseCase,
        repo: Repository,
        clock: Clock,
        messages: Messages,
        pulse: Pulse | None = None,
    ) -> None:
        self._policy = policy
        self._clarifier = clarifier
        self._tiers = tiers
        self._explainer = explainer
        self._gaming = gaming
        self._understander = understander
        self._act = act
        self._repo = repo
        self._clock = clock
        self._messages = messages
        self._pulse = pulse

    def run(
        self,
        request: Request,
        req: NormalizedRequest,
        core: CoreResult,
        *,
        budget: ClarificationBudget,
        asked: Sequence[str] = (),
        path: Sequence[str] = (),
        clarified: bool = False,
        debug_members: bool = False,
    ) -> dto.TriageResponse:
        if DISTRESS in core.flags:
            return self._distress(request, req, core)
        policy_path = list(path)
        llm_allowed = self._tiers.usable and INJECTION not in core.flags
        outcome = self._decide(core, budget, llm_allowed, policy_path)

        if outcome == Outcome.OUT_OF_SCOPE:
            return self._out_of_scope(request, req, core)
        if outcome == Outcome.ASK:
            question = self._clarifier.select(core, req.lang, asked)
            if question is not None:
                return self._ask(request, req, core, question)
            spent = ClarificationBudget(max_questions=budget.max_questions, asked=budget.max_questions)
            outcome = self._decide(core, spent, llm_allowed, policy_path)

        extra_flags: set[str] = set()
        cost_usd = 0.0
        if outcome == Outcome.ESCALATE:
            core, extra_flags, cost_usd = self._escalate(req, core)
            outcome = self._decide(core, budget, False, policy_path, after_escalation=True)

        return self._decided(
            request,
            req,
            core,
            provisional=outcome == Outcome.HUMAN_REVIEW,
            extra_flags=extra_flags,
            cost_usd=cost_usd,
            policy_path=policy_path,
            clarified=clarified,
            debug_members=debug_members,
        )

    # ------------------------------------------------------------------ outcomes

    def _decide(
        self,
        core: CoreResult,
        budget: ClarificationBudget,
        llm_allowed: bool,
        policy_path: list[str],
        *,
        after_escalation: bool = False,
    ) -> Outcome:
        outcome, rules = self._policy.decide_with_path(
            core, budget, llm_allowed, after_escalation=after_escalation
        )
        policy_path.append(rules[-1])
        return outcome

    def _distress(self, request: Request, req: NormalizedRequest, core: CoreResult) -> dto.TriageResponse:
        category, priority = out.decided_labels(core)
        flags = {DISTRESS} | (set(core.flags) & {INJECTION})
        pred = self._repo.save_prediction(
            Prediction(
                id="",
                request_id=request.id,
                category=category,
                priority=priority,
                core=core,
                tier=Tier.HUMAN,
                flags=flags,
                explanation=None,
                cost=Money(0.0),
                artifact_version=core.artifact.name,
            )
        )
        self._repo.enqueue_review(
            ReviewItem(id="", prediction_id=pred.id, reason=REVIEW_DISTRESS, status="open")
        )
        self._repo.set_request_status(request.id, RequestStatus.DISTRESS)
        self._audit("triage.distress", request, {"prediction_id": pred.id})
        return _response(
            request,
            req,
            RequestStatus.DISTRESS,
            tier=Tier.HUMAN,
            flags=flags,
            message=self._messages.for_lang(req.lang).distress,
        )

    def _out_of_scope(self, request: Request, req: NormalizedRequest, core: CoreResult) -> dto.TriageResponse:
        clarification: dto.ClarificationOut | None = None
        try:
            topic = self._clarifier.topic_question(req.lang)
        except InvalidInput:
            topic = None
        if topic is not None:
            self._save_question(request, topic)
            clarification = out.clarification_out(topic)
        self._repo.set_request_status(request.id, RequestStatus.OUT_OF_SCOPE)
        self._audit("triage.out_of_scope", request, {"flags": sorted(core.flags)})
        return _response(
            request,
            req,
            RequestStatus.OUT_OF_SCOPE,
            tier=core.tier,
            flags=set(core.flags) | {OUT_OF_SCOPE},
            message=self._messages.for_lang(req.lang).out_of_scope,
            clarification=clarification,
        )

    def _ask(
        self, request: Request, req: NormalizedRequest, core: CoreResult, question: ClarificationQuestion
    ) -> dto.TriageResponse:
        self._save_question(request, question)
        self._repo.set_request_status(request.id, RequestStatus.NEEDS_CLARIFICATION)
        self._audit("triage.ask", request, {"question_id": question.id})
        category, priority = out.decided_labels(core)
        return _response(
            request,
            req,
            RequestStatus.NEEDS_CLARIFICATION,
            tier=core.tier,
            flags=set(core.flags),
            category=out.category_out(core, category),
            priority=out.priority_out(core, priority),
            clarification=out.clarification_out(question),
        )

    def _escalate(self, req: NormalizedRequest, core: CoreResult) -> tuple[CoreResult, set[str], float]:
        tiers = self._tiers
        flags: set[str] = set()
        cost = 0.0
        context = OracleContext(lang=req.lang, neighbors=core.neighbors, prompt_version=tiers.prompt_version)
        for oracle in tiers.oracles:
            try:
                answer = oracle.choose(req, core.set_cat, core.set_pri, context)
                cost += answer.call.cost.usd
                core = tiers.merger.merge(core, answer, tiers.w_llm, tiers.conformal_cat, tiers.conformal_pri)
            except LLMUnavailable as exc:
                log.info("LLM tier %s unavailable, staying at %s: %s", oracle.tier, core.tier, exc)
                break
            except LLMOutputOutOfSet as exc:
                log.info("LLM tier %s answered outside the set: %s", oracle.tier, exc)
                flags.add(LLM_OUT_OF_SET)
                continue
            if core.set_cat.is_singleton and core.set_pri.is_singleton:
                break
        return core, flags, cost

    def _decided(
        self,
        request: Request,
        req: NormalizedRequest,
        core: CoreResult,
        *,
        provisional: bool,
        extra_flags: set[str],
        cost_usd: float,
        policy_path: list[str],
        clarified: bool,
        debug_members: bool,
    ) -> dto.TriageResponse:
        category, priority = out.decided_labels(core)
        flags = set(core.flags) | extra_flags
        if core.safety:
            flags.add(SAFETY)
        if provisional:
            flags.add(NEEDS_REVIEW)
        flags |= self._gaming.check(req, priority, core.evidence, request.alias, INJECTION in flags).flags

        explanation = self._explain(req, core, category, priority)
        if explanation is None:
            flags.add(EXPLANATION_FAILED)
        else:
            explanation.trace = {
                **explanation.trace,
                "policy_path": list(policy_path),
                "clarified": clarified,
            }
        pred = Prediction(
            id="",
            request_id=request.id,
            category=category,
            priority=priority,
            core=core,
            tier=core.tier,
            flags=flags,
            explanation=explanation,
            cost=Money(cost_usd),
            artifact_version=core.artifact.name,
        )
        plan = self._act.plan_for(pred, provisional)
        understanding = self._understander.understand(req, core, plan.kind)
        flags |= understanding_flags(understanding)
        pred = self._repo.save_prediction(pred)
        if provisional:
            self._repo.enqueue_review(
                ReviewItem(id="", prediction_id=pred.id, reason=REVIEW_NEEDS_REVIEW, status="open")
            )

        action = self._act.run(pred, request, provisional, understanding)
        incident_id = self._pulse_step(request, req, pred)
        if incident_id is not None:
            action = action.model_copy(update={"incident_id": incident_id})

        status = RequestStatus.HUMAN_REVIEW if provisional else RequestStatus.DECIDED
        self._repo.set_request_status(request.id, status)
        self._audit(
            "triage.decided",
            request,
            {
                "prediction_id": pred.id,
                "status": str(status),
                "action": str(action.type),
                "tier": str(core.tier),
            },
        )

        trace = out.trace_out(
            core,
            category,
            policy_path=policy_path,
            clarified=clarified,
            cost_usd=cost_usd,
            debug_members=debug_members,
        )
        msgs = self._messages.for_lang(req.lang)
        return _response(
            request,
            req,
            status,
            tier=core.tier,
            flags=flags,
            category=out.category_out(core, category),
            priority=out.priority_out(core, priority),
            explanation=out.explanation_out(explanation, trace) if explanation else None,
            action=action,
            understanding=out.understanding_out(understanding),
            message=msgs.human_review.format(category=category) if provisional else None,
        )

    # ------------------------------------------------------------------ helpers

    def _explain(
        self, req: NormalizedRequest, core: CoreResult, category: Category, priority: Priority
    ) -> Explanation | None:
        if self._explainer is None:
            # P3.4 (ML) not wired yet: the core's own evidence and neighbours, no token attribution.
            return Explanation(
                top_tokens=[],
                urgency_reasons=list(core.evidence.spans),
                neighbors=list(core.neighbors),
                counterfactual=None,
                trace={},
            )
        try:
            return self._explainer.explain(req, core, (category, priority))
        except Exception as exc:  # degrade boundary: an explanation never fails triage (§2.1 [14])
            log.warning("explainer failed: %s", exc)
            return None

    def _save_question(self, request: Request, question: ClarificationQuestion) -> Clarification:
        return self._repo.save_clarification(
            Clarification(
                id="",
                request_id=request.id,
                question_id=question.id,
                options=question.options,
                answer=None,
                asked_at=self._clock.now(),
            )
        )

    def _pulse_step(self, request: Request, req: NormalizedRequest, pred: Prediction) -> str | None:
        """[12b] store the request embedding; [13] incident detection. Never fails the request."""
        pulse = self._pulse
        if pulse is None:
            return None
        location = req.location
        try:
            embedding = pred.core.embedding or tuple(pulse.encoder.encode([req.model_text])[0])
            meta: dict[str, MetaValue] = {
                "building_id": location.building if location else None,
                "room": location.room if location else None,
                "category": str(pred.category),
                "priority": str(pred.priority),
                "created_at": request.created_at.isoformat(),
            }
            pulse.vectors.upsert(
                REQUESTS_COLLECTION, [VectorItem(request.id, embedding, req.text_norm, req.lang, meta)]
            )
            if pulse.incidents is None or location is None:
                return None
            decision = pulse.incidents.detect(request, pred, embedding)
        except (StoreError, ArtifactError) as exc:
            log.warning("pulse step skipped for request %s: %s", request.id, exc)
            return None
        if decision.kind == "none" or decision.incident is None:
            return None
        self._audit(f"incident.{decision.kind}", request, {"incident_id": decision.incident.id})
        return decision.incident.id

    def _audit(self, action: str, request: Request, payload: dict[str, object]) -> None:
        try:
            self._repo.append_event(request.alias or ACTOR, action, f"request:{request.id}", payload)
        except CampusPulseError as exc:
            log.warning("audit event %s not saved: %s", action, exc)


class TriageUseCase:
    """`POST /v1/triage` (ARCHITECTURE §2.1): classify, save the request, then `DecisionFlow`.

    `run(cmd, debug_members=False)`:
    1. `TriageClassifier.classify(text, picked location)` (raises `InvalidInput` for blank text, before
       anything is written, so invalid input leaves no row);
    2. `Repository.save_request` (status `received`, the normalized request, alias, input mode,
       conversation id);
    3. `DecisionFlow.run` with a fresh one-question budget.
    `debug_members` fills `explanation.trace.per_model` (admin `?debug=members`; the route checks the
    role). Errors: `InvalidInput` (422), `StoreError` (503), `ArtifactError` (503).
    """

    def __init__(
        self,
        core: TriageClassifier,
        flow: DecisionFlow,
        repo: Repository,
        clock: Clock,
        *,
        max_questions: int = DEFAULT_MAX_QUESTIONS,
    ) -> None:
        self._core = core
        self._flow = flow
        self._repo = repo
        self._clock = clock
        self._max_questions = max_questions

    def run(self, cmd: dto.TriageRequest, *, debug_members: bool = False) -> dto.TriageResponse:
        picked = Location(cmd.location.building, cmd.location.room, "picked") if cmd.location else None
        req, core = self._core.classify(cmd.text, picked)
        request = self._repo.save_request(
            Request(
                id="",
                alias=cmd.student_alias,
                raw_text=cmd.text,
                normalized=req,
                input_mode=cmd.input_mode,
                status=RequestStatus.RECEIVED,
                created_at=self._clock.now(),
                conversation_id=cmd.conversation_id,
            )
        )
        return self._flow.run(
            request,
            req,
            core,
            budget=ClarificationBudget(max_questions=self._max_questions),
            debug_members=debug_members,
        )


def _response(
    request: Request,
    req: NormalizedRequest,
    status: RequestStatus,
    *,
    tier: Tier,
    flags: set[str],
    category: dto.CategoryOut | None = None,
    priority: dto.PriorityOut | None = None,
    clarification: dto.ClarificationOut | None = None,
    explanation: dto.ExplanationOut | None = None,
    action: dto.ActionOut | None = None,
    understanding: dto.UnderstandingOut | None = None,
    message: str | None = None,
) -> dto.TriageResponse:
    return dto.TriageResponse(
        request_id=request.id,
        status=status,  # type: ignore[arg-type]  # one of the five TRIAGE_STATUSES by construction
        lang=req.lang,
        is_arabizi=req.is_arabizi,
        understood_as=out.understood_as(req),
        category=category,
        priority=priority,
        tier=tier,
        clarification=clarification,
        explanation=explanation,
        flags=out.flags_out(flags),
        action=action,
        message=message,
        understanding=understanding,
    )


def with_flags(core: CoreResult, remove: frozenset[str]) -> CoreResult:
    """`core` without the given flags (ClarifyUseCase drops `gibberish` once a topic is picked)."""
    return dataclasses.replace(core, flags=core.flags - remove)
