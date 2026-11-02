"""FeedbackUseCase: staff confirm or correct a prediction, and the system learns at once (P3.11).

SPEC §5.3, ARCHITECTURE §2.3. Implements the `FeedbackHandler` that `POST /v1/feedback` calls.
A correction becomes a live-memory example (`MemoryStore.add`), so the very next similar request has
it among its kNN neighbours (`source="memory"`, weighted at most `knn.memory_weight_cap`). The frozen
model and `predict.py` never see it (§3.11).
"""

from __future__ import annotations

import dataclasses
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases import responses as out
from campuspulse_ai.application.use_cases.act import ActUseCase
from campuspulse_ai.application.use_cases.mirror import INCIDENT_TAG, RECORD_SINK, TicketMirror
from campuspulse_ai.application.use_cases.mirror import relabelled as relabel
from campuspulse_ai.application.use_cases.ports import (
    ROLE_ADMIN,
    ROLE_STAFF,
    Actor,
    AdvisorDirectory,
    LifecycleReads,
)
from campuspulse_ai.application.use_cases.review_access import caller_profile_id, check_reviewer, user_id_of
from campuspulse_ai.domain.entities import MemoryExample, Prediction, Request, ReviewItem, Ticket
from campuspulse_ai.domain.errors import CampusPulseError, Unauthorized
from campuspulse_ai.domain.ports import Clock, MemoryStore, Repository, SentenceEncoder, TicketSink
from campuspulse_ai.domain.values import TicketStatus, Tier

log = logging.getLogger(__name__)

STAFF_CONFIRMED = "staff_confirmed"
NEEDS_REVIEW = "needs_review"
REASON_DISTRESS = "distress"
REVIEWER_ROLES = frozenset({ROLE_STAFF, ROLE_ADMIN})
NO_MEMORY_ID = ""
"""`memory.example_id` when nothing was written (a distress acknowledgement, or no text)."""
MSG_CORRECTED = "Corrected. The next similar request will use this correction."
MSG_CONFIRMED = "Confirmed. The prediction is now final."
MSG_DISTRESS = "Acknowledged. The distress report is closed; nothing was learned from it."


@dataclass(frozen=True, slots=True)
class _Decision:
    """What the reviewer decided about one prediction."""

    pred: Prediction
    request: Request
    corrected: bool
    review: ReviewItem | None


class FeedbackUseCase:
    """`run(cmd, reviewer) -> FeedbackResponse` (ARCHITECTURE §2.3 steps 1-5).

    1. The reviewer must be staff or admin (`Unauthorized` -> 403; the route checks it too). A
       `distress` review item is admin-only (DB migration 0011): staff get `Unauthorized`. An open
       review item may be resolved only by someone who can see it (UD-13, `review_access`): staff of
       its office, and for an item assigned to an advisor only that advisor (admins always).
    2. The prediction (`LifecycleReads.get_prediction`, `NotFound` -> 404) and its request. The final
       labels are the corrections, or the predicted ones for a plain confirmation.
    3. The prediction row is updated in place: the final labels, tier `human`, flag `staff_confirmed`
       (and `needs_review` removed). Its open review item is resolved (`confirmed` / `corrected`,
       reviewer, corrections, note).
    4. The request's own ticket (not an incident ticket): a provisional one is re-labelled (office
       re-routed from `config/actions.yaml`) and finalized by `ActUseCase.finalize` (deferred booking
       or alert fire now, the sinks are updated); a confirmed one that was corrected is saved and
       mirrored. No ticket (e.g. an FAQ answer) -> `ticket: null`, unless `apply(...,
       ensure_ticket=True)` (a review forwarded to an office, UD-13): then a ticket is opened for
       the final office.
    5. `MemoryStore.add` with the final labels, the request's `text_norm` and the embedding the core
       computed (`CoreResult.embedding`, D-012; re-encoded from `model_text` only when the stored
       prediction does not carry it, which gives the same vector), author = the reviewer's user id.
    6. One audit event: `feedback.confirmed`, `feedback.corrected` or `feedback.distress_ack`.

    Distress acknowledgement (admin): the review item is resolved `confirmed`; no label change, no
    ticket and **no memory write** (a distress message must never shape future predictions).

    Errors: `Unauthorized`, `NotFound`, `StoreError` (503). Sink, notifier and calendar failures inside
    `finalize` degrade as in `ActUseCase`.
    """

    def __init__(
        self,
        reads: LifecycleReads,
        repo: Repository,
        memory: MemoryStore,
        act: ActUseCase,
        encoder: SentenceEncoder,
        clock: Clock,
        sinks: tuple[TicketSink, ...],
        *,
        directory: AdvisorDirectory | None = None,
    ) -> None:
        self._reads = reads
        self._repo = repo
        self._memory = memory
        self._act = act
        self._encoder = encoder
        self._clock = clock
        self._mirror = TicketMirror(sinks, repo)
        self._directory = directory

    def run(self, cmd: dto.FeedbackRequest, reviewer: Actor) -> dto.FeedbackResponse:
        return self.apply(cmd, reviewer)

    def apply(
        self, cmd: dto.FeedbackRequest, reviewer: Actor, *, ensure_ticket: bool = False
    ) -> dto.FeedbackResponse:
        """`run` with `ensure_ticket`: open a ticket for the final office when the request has none."""
        if reviewer.role not in REVIEWER_ROLES:
            raise Unauthorized(f"role {reviewer.role!r} may not review predictions")
        pred = self._reads.get_prediction(cmd.prediction_id)
        review = self._reads.open_review_for(pred.id)
        if review is not None and review.reason == REASON_DISTRESS:
            return self._acknowledge_distress(pred, review, cmd, reviewer)
        if review is not None:
            check_reviewer(reviewer, review, caller_profile_id(reviewer, self._directory))
        category = cmd.corrected_category or pred.category
        priority = cmd.corrected_priority or pred.priority
        decision = _Decision(
            pred=pred,
            request=self._repo.get_request(pred.request_id),
            corrected=(category, priority) != (pred.category, pred.priority),
            review=review,
        )
        final = dataclasses.replace(
            pred,
            category=category,
            priority=priority,
            tier=Tier.HUMAN,
            flags=(set(pred.flags) - {NEEDS_REVIEW}) | {STAFF_CONFIRMED},
        )
        self._repo.save_prediction(final)
        self._resolve(decision, cmd, reviewer)
        ticket, actions = self._update_ticket(decision, final)
        if ticket is None and ensure_ticket:
            ticket = self._open_ticket(decision.request, final)
        memory = self._learn(decision.request, final, reviewer)
        self._audit(reviewer, "feedback.corrected" if decision.corrected else "feedback.confirmed", final,
                    {"memory_id": memory.example_id, "ticket_id": ticket.id if ticket else None})  # fmt: skip
        return dto.FeedbackResponse(
            prediction_id=final.id,
            request_id=final.request_id,
            category=final.category,
            priority=final.priority,
            tier=final.tier,
            flags=out.flags_out(final.flags),
            ticket=out.ticket_out(ticket) if ticket else None,
            memory=memory,
            actions=actions,
            message=MSG_CORRECTED if decision.corrected else MSG_CONFIRMED,
        )

    # ------------------------------------------------------------------ steps

    def _acknowledge_distress(
        self, pred: Prediction, review: ReviewItem, cmd: dto.FeedbackRequest, reviewer: Actor
    ) -> dto.FeedbackResponse:
        if reviewer.role != ROLE_ADMIN:
            raise Unauthorized("distress reports are handled by admins only")
        self._repo.resolve_review(
            dataclasses.replace(
                review, status="confirmed", reviewer_id=_user_id(reviewer), note=cmd.note or None
            )
        )
        self._audit(reviewer, "feedback.distress_ack", pred, {"review_id": review.id})
        return dto.FeedbackResponse(
            prediction_id=pred.id,
            request_id=pred.request_id,
            category=pred.category,
            priority=pred.priority,
            tier=pred.tier,
            flags=out.flags_out(pred.flags),
            ticket=None,
            memory=dto.MemoryWriteOut(example_id=NO_MEMORY_ID, active_examples=self._memory.stats().active),
            actions=[],
            message=MSG_DISTRESS,
        )

    def _resolve(self, d: _Decision, cmd: dto.FeedbackRequest, reviewer: Actor) -> None:
        if d.review is None:
            return
        self._repo.resolve_review(
            dataclasses.replace(
                d.review,
                status="corrected" if d.corrected else "confirmed",
                reviewer_id=_user_id(reviewer),
                corrected_category=cmd.corrected_category,
                corrected_priority=cmd.corrected_priority,
                note=cmd.note or None,
            )
        )

    def _update_ticket(self, d: _Decision, final: Prediction) -> tuple[Ticket | None, list[dto.ActionOut]]:
        own = [t for t in self._reads.tickets_for_requests([d.request.id]) if INCIDENT_TAG not in t.tags]
        if not own:
            return None, []
        ticket = own[-1]
        office = self._act.plan_for(final, provisional=False).office
        relabelled = relabel(ticket, final.category, final.priority, office=office)
        if ticket.provisional:
            actions = self._act.finalize(relabelled)
            return self._fresh(ticket.id, relabelled), actions
        if not d.corrected:
            return ticket, []
        saved = self._repo.save_ticket(relabelled)
        self._mirror.push(saved, skip=(RECORD_SINK,))
        return saved, []

    def _open_ticket(self, request: Request, final: Prediction) -> Ticket:
        """A confirmed ticket for the final labels' office (the request had none, e.g. an FAQ
        answer that a reviewer forwarded to an office)."""
        plan = self._act.plan_for(final, provisional=False)
        now = self._clock.now()
        ticket = Ticket(
            id=str(uuid.uuid4()),
            request_id=request.id,
            incident_id=None,
            office=plan.office,
            category=final.category,
            priority=final.priority,
            status=TicketStatus.NEW,
            provisional=False,
            sla_due_at=now + timedelta(hours=plan.sla_hours),
            clock_started_at=now,
            title="",
            body=request.raw_text,
            tags=plan.tags,
        )
        return self._act.open_ticket(ticket)

    def _fresh(self, ticket_id: str, fallback: Ticket) -> Ticket:
        try:
            return self._repo.get_ticket(ticket_id)
        except CampusPulseError as exc:  # the response still reports the ticket we sent
            log.warning("ticket %s not re-read after finalize: %s", ticket_id, exc)
            return dataclasses.replace(fallback, provisional=False)

    def _learn(self, request: Request, final: Prediction, reviewer: Actor) -> dto.MemoryWriteOut:
        normalized = request.normalized
        if normalized is None:
            return dto.MemoryWriteOut(example_id=NO_MEMORY_ID, active_examples=self._memory.stats().active)
        embedding = final.core.embedding or tuple(self._encoder.encode([normalized.model_text])[0])
        saved = self._memory.add(
            MemoryExample(
                id="",
                text_norm=normalized.text_norm,
                lang=normalized.lang,
                embedding=tuple(float(x) for x in embedding),
                category=final.category,
                priority=final.priority,
                author_id=_user_id(reviewer) or "",
                created_at=self._clock.now(),
            )
        )
        return dto.MemoryWriteOut(example_id=saved.id, active_examples=self._memory.stats().active)

    def _audit(self, reviewer: Actor, action: str, pred: Prediction, payload: dict[str, object]) -> None:
        actor = reviewer.alias or _user_id(reviewer) or reviewer.role
        try:
            self._repo.append_event(actor, action, f"prediction:{pred.id}", payload)
        except CampusPulseError as exc:
            log.warning("audit event %s not saved: %s", action, exc)


def _user_id(actor: Actor) -> str | None:
    return user_id_of(actor)
