"""Hybrid advisor routing (UD-13): who reviews an unsure request, and how they resolve it.

- `ReviewRouter.route` decides where a HUMAN_REVIEW item goes:
  1. **urgent** (flag `safety`, or a final priority of `high`, i.e. a same-day request): the predicted
     office's queue. It never waits for an advisor; its ticket and safety alert already fired.
  2. the student's **advisor** (`profiles.advisor_id` -> `advisors.profile_id`): assigned to that
     advisor's profile, in the advisor's office queue (`academic`);
  3. otherwise the **fallback office** queue (`REVIEW_FALLBACK_OFFICE`, `academic`), unassigned.
- `ReviewAssigner.enqueue` writes the item and tells the reviewer: an in-app `notifications` row
  (kind `review_assigned`) for the advisor's alias, or for `office:<office>` when it is a queue item,
  plus an email to the advisor's allow-listed demo inbox (`REVIEW_EMAIL_ADVISOR`).
- `ReviewsUseCase.queue` is `GET /v1/reviews` (what the caller may resolve, the 0012 RLS rule) and
  `ReviewsUseCase.forward` is `POST /v1/reviews/{id}/forward`: a correction to the office's category
  through `FeedbackUseCase` (so live memory learns it), the ticket finalized or opened for that
  office, and the new office notified.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases import responses as out
from campuspulse_ai.application.use_cases.feedback import FeedbackUseCase
from campuspulse_ai.application.use_cases.messages import Messages
from campuspulse_ai.application.use_cases.mirror import INCIDENT_TAG
from campuspulse_ai.application.use_cases.offices import OfficeMap
from campuspulse_ai.application.use_cases.ports import (
    ROLE_ADMIN,
    ROLE_STAFF,
    Actor,
    AdvisorContact,
    AdvisorDirectory,
    LifecycleReads,
    ReviewReads,
)
from campuspulse_ai.application.use_cases.review_access import (
    REASON_DISTRESS,
    caller_profile_id,
    check_reviewer,
    may_review,
)
from campuspulse_ai.domain.entities import OutboxMessage, Prediction, Request, ReviewItem, Ticket
from campuspulse_ai.domain.errors import (
    CampusPulseError,
    InvalidInput,
    NotificationError,
    RecipientNotAllowed,
    StoreError,
    Unauthorized,
)
from campuspulse_ai.domain.labels import CATEGORY_ORDER, PRIORITY_ORDER, Priority
from campuspulse_ai.domain.ports import Clock, Notifier, Repository
from campuspulse_ai.domain.routing import SAFETY_FLAG
from campuspulse_ai.domain.values import Lang

log = logging.getLogger(__name__)

REASON_NEEDS_REVIEW: Final = "needs_review"
STATUS_OPEN: Final = "open"
KIND_REVIEW_ASSIGNED = "review_assigned"
"""`notifications.kind` for a new review item: `{review_id, request_id, office, assigned, message}`."""
KIND_TICKET_FORWARDED = "ticket_forwarded"
"""`notifications.kind` for a forwarded ticket: `{ticket_id, title, from_office, office, message}`."""
OFFICE_ALIAS_PREFIX = "office:"
"""Staff of an office read notifications addressed to `office:<office>` (DB 0010)."""
ADMIN_ONLY_FLAGS = frozenset({"priority_gaming_suspected"})
ACTOR = "reviews"


def office_alias(office: str) -> str:
    return f"{OFFICE_ALIAS_PREFIX}{office}"


@dataclass(frozen=True, slots=True)
class ReviewRoute:
    """Where one review item goes: the office queue, the advisor (None = unassigned) and whether the
    request was urgent (urgent items stay with the predicted office)."""

    office: str
    advisor: AdvisorContact | None
    urgent: bool


class ReviewRouter:
    """The UD-13 rule (module docstring). `route` never raises: a directory failure is logged and the
    item goes to the fallback queue."""

    def __init__(self, directory: AdvisorDirectory, fallback_office: str) -> None:
        self._directory = directory
        self._fallback = fallback_office

    def route(self, student_alias: str, pred: Prediction, predicted_office: str) -> ReviewRoute:
        if is_urgent(pred):
            return ReviewRoute(office=predicted_office, advisor=None, urgent=True)
        advisor = self._advisor(student_alias)
        if advisor is None:
            return ReviewRoute(office=self._fallback, advisor=None, urgent=False)
        return ReviewRoute(office=advisor.office or self._fallback, advisor=advisor, urgent=False)

    def _advisor(self, alias: str) -> AdvisorContact | None:
        if not alias.strip():
            return None
        try:
            return self._directory.advisor_of(alias)
        except StoreError as exc:
            log.warning("advisor of %s not found, using the %s queue: %s", alias, self._fallback, exc)
            return None


def is_urgent(pred: Prediction) -> bool:
    """Safety, or a final priority of high (same-day): never waits for an advisor (UD-13)."""
    return SAFETY_FLAG in pred.flags or pred.core.safety or pred.priority == Priority.HIGH


class ReviewAssigner:
    """`enqueue(request, pred, predicted_office) -> ReviewItem` for a HUMAN_REVIEW outcome.

    Writes the `review_queue` row (reason `needs_review`, `assignee`, `office`), then notifies the
    reviewer (module docstring) and appends a `review.assigned` event. `StoreError` from the row write
    propagates (as the old direct `enqueue_review` did); notification failures are logged only.
    """

    def __init__(
        self,
        router: ReviewRouter,
        repo: Repository,
        notifier: Notifier,
        clock: Clock,
        messages: Messages,
        *,
        email_advisor: bool,
    ) -> None:
        self._router = router
        self._repo = repo
        self._notifier = notifier
        self._clock = clock
        self._messages = messages
        self._email_advisor = email_advisor

    def enqueue(self, request: Request, pred: Prediction, predicted_office: str) -> ReviewItem:
        route = self._router.route(request.alias, pred, predicted_office)
        item = self._repo.enqueue_review(
            ReviewItem(
                id="",
                prediction_id=pred.id,
                reason=REASON_NEEDS_REVIEW,
                status=STATUS_OPEN,
                assignee=route.advisor.profile_id if route.advisor else None,
                office=route.office,
            )
        )
        self._notify(item, route, request, pred)
        self._audit(item, route, request)
        return item

    def _notify(self, item: ReviewItem, route: ReviewRoute, request: Request, pred: Prediction) -> None:
        staff = self._messages.staff
        advisor = route.advisor
        labels = {"category": str(pred.category), "priority": str(pred.priority)}
        if advisor is not None and advisor.alias:
            to = advisor.alias
            message = staff.review_assigned.format(alias=request.alias or "-", **labels)
        else:
            to = office_alias(item.office or route.office)
            message = staff.review_queued.format(**labels)
        payload: dict[str, object] = {
            "review_id": item.id,
            "request_id": request.id,
            "office": item.office,
            "assigned": advisor is not None,
            "message": message,
        }
        try:
            self._repo.save_notification(to, KIND_REVIEW_ASSIGNED, payload)
        except StoreError as exc:
            log.warning("review notification for %s not saved: %s", item.id, exc)
        if advisor is not None and advisor.email and self._email_advisor:
            self._email(advisor, request, pred)

    def _email(self, advisor: AdvisorContact, request: Request, pred: Prediction) -> None:
        email = self._messages.email
        text = request.normalized.core if request.normalized else request.raw_text
        msg = OutboxMessage(
            id="",
            kind="email",
            to_address=advisor.email,
            subject=email.review_subject.format(category=pred.category, priority=pred.priority),
            body=email.review_body.format(
                alias=request.alias or "-", category=pred.category, priority=pred.priority, text=text
            ),
            provider_id=None,
            status="queued",
            created_at=self._clock.now(),
            priority=pred.priority,
        )
        try:
            self._notifier.send(msg)  # AllowlistedNotifier: refusals and failures land on the outbox row
        except (RecipientNotAllowed, NotificationError, StoreError) as exc:
            log.warning("review email to the advisor not sent: %s", exc)

    def _audit(self, item: ReviewItem, route: ReviewRoute, request: Request) -> None:
        payload = {
            "review_id": item.id,
            "office": item.office,
            "assignee": item.assignee,
            "urgent": route.urgent,
        }
        try:
            self._repo.append_event(ACTOR, "review.assigned", f"request:{request.id}", payload)
        except CampusPulseError as exc:
            log.warning("review.assigned event not saved: %s", exc)


class ReviewsUseCase:
    """`GET /v1/reviews` and `POST /v1/reviews/{review_id}/forward` (UD-13).

    - `queue(actor, status) -> list[ReviewItemOut]`: newest first, at most `limit`; admins get every
      item, staff the items `review_access.may_review` allows (their office's unassigned items and
      their own). Students and the service token get `Unauthorized` (the route checks the role too).
    - `forward(review_id, office, actor, note) -> FeedbackResponse`: the item must be open and not a
      distress report (`InvalidInput`), the caller must be allowed to resolve it (`Unauthorized`), and
      `office` a routed office (`InvalidInput`). It runs `FeedbackUseCase.apply` with the office's
      category as the correction (none when it is the predicted category: a confirmation), so the
      prediction becomes final, the review is resolved, live memory learns the label, and the ticket
      is finalized for that office (or opened, if the request had none). The new office gets a
      `ticket_forwarded` notification and an `events` row `review.forwarded` is written.
    Errors: `NotFound` (unknown review), `Unauthorized`, `InvalidInput`, `StoreError` (503).
    """

    def __init__(
        self,
        reviews: ReviewReads,
        lifecycle: LifecycleReads,
        feedback: FeedbackUseCase,
        offices: OfficeMap,
        directory: AdvisorDirectory,
        repo: Repository,
        messages: Messages,
        *,
        limit: int,
    ) -> None:
        self._reviews = reviews
        self._lifecycle = lifecycle
        self._feedback = feedback
        self._offices = offices
        self._directory = directory
        self._repo = repo
        self._messages = messages
        self._limit = limit

    def queue(self, actor: Actor, status: dto.ReviewStatus = STATUS_OPEN) -> list[dto.ReviewItemOut]:
        if actor.role not in {ROLE_ADMIN, ROLE_STAFF}:
            raise Unauthorized(f"role {actor.role!r} may not list review items")
        office = None if actor.role == ROLE_ADMIN else actor.office
        if actor.role != ROLE_ADMIN and not office:
            return []
        me = caller_profile_id(actor, self._directory)
        items = [
            i
            for i in self._reviews.list_reviews(status=status, office=office, limit=self._limit)
            if may_review(actor, i, me)
        ]
        return self._present(items, actor, me)

    def forward(
        self, review_id: str, office: str, actor: Actor, note: str | None = None
    ) -> dto.FeedbackResponse:
        item = self._reviews.get_review(review_id)
        if item.reason == REASON_DISTRESS:
            raise InvalidInput("a distress report cannot be forwarded to an office")
        if item.status != STATUS_OPEN:
            raise InvalidInput(f"review item {review_id} is already {item.status}")
        check_reviewer(actor, item, caller_profile_id(actor, self._directory))
        category = self._offices.category_for(office)
        pred = self._lifecycle.get_prediction(item.prediction_id)
        clean_note = (note or "").strip()
        cmd = dto.FeedbackRequest(
            prediction_id=pred.id,
            corrected_category=category if category != pred.category else None,
            note=clean_note,
        )
        response = self._feedback.apply(cmd, actor, ensure_ticket=True)
        target = self._offices.office_for(category)
        if response.ticket is not None:
            self._notify_office(response.ticket, item.office or "", target, clean_note)
        self._audit(actor, item, pred, target, response)
        return response

    # ------------------------------------------------------------------ helpers

    def _present(self, items: Sequence[ReviewItem], actor: Actor, me: str | None) -> list[dto.ReviewItemOut]:
        if not items:
            return []
        preds = {p.id: p for p in self._reviews.predictions_by_ids([i.prediction_id for i in items])}
        requests = {r.id: r for r in self._reviews.requests_by_ids([p.request_id for p in preds.values()])}
        tickets: dict[str, Ticket] = {}
        for t in self._lifecycle.tickets_for_requests(list(requests)):
            if INCIDENT_TAG not in t.tags:
                tickets[t.request_id] = t  # oldest first, so the newest own ticket wins
        hidden = frozenset() if actor.role == ROLE_ADMIN else ADMIN_ONLY_FLAGS
        result: list[dto.ReviewItemOut] = []
        for item in items:
            pred = preds.get(item.prediction_id)
            request = requests.get(pred.request_id) if pred else None
            if pred is None or request is None:
                log.warning("review item %s has no prediction or request; skipped", item.id)
                continue
            ticket = tickets.get(request.id)
            result.append(
                dto.ReviewItemOut(
                    id=item.id,
                    prediction_id=pred.id,
                    request_id=request.id,
                    reason="distress" if item.reason == REASON_DISTRESS else REASON_NEEDS_REVIEW,
                    status=item.status,
                    office=item.office,
                    assignee=item.assignee,
                    assigned_to_me=me is not None and item.assignee == me,
                    student_alias=request.alias,
                    text=request.raw_text,
                    lang=request.normalized.lang if request.normalized else Lang.EN,
                    category=pred.category,
                    priority=pred.priority,
                    set_cat=[c for c in CATEGORY_ORDER if c.value in pred.core.set_cat.labels],
                    set_pri=[p for p in PRIORITY_ORDER if p.value in pred.core.set_pri.labels],
                    flags=[f for f in out.flags_out(pred.flags) if f not in hidden],
                    ticket_id=ticket.id if ticket else None,
                    requested_at=request.created_at,
                    corrected_category=item.corrected_category,
                    corrected_priority=item.corrected_priority,
                    note=item.note,
                )
            )
        return result

    def _notify_office(self, ticket: dto.TicketOut, from_office: str, office: str, note: str) -> None:
        if from_office == office:
            return
        title = ticket.title or f"{ticket.category} request"
        notify_forward(
            self._repo, self._messages, ticket_id=ticket.id, title=title,
            from_office=from_office, office=office, note=note,
        )  # fmt: skip

    def _audit(
        self, actor: Actor, item: ReviewItem, pred: Prediction, office: str, response: dto.FeedbackResponse
    ) -> None:
        payload = {
            "review_id": item.id,
            "from_office": item.office,
            "to_office": office,
            "category": str(response.category),
            "ticket_id": response.ticket.id if response.ticket else None,
        }
        try:
            self._repo.append_event(
                actor.alias or actor.role, "review.forwarded", f"prediction:{pred.id}", payload
            )
        except CampusPulseError as exc:
            log.warning("review.forwarded event not saved: %s", exc)


def notify_forward(
    repo: Repository,
    messages: Messages,
    *,
    ticket_id: str,
    title: str,
    from_office: str,
    office: str,
    note: str,
) -> None:
    """One `ticket_forwarded` notification for `office:<office>`. Never raises (logged)."""
    payload: dict[str, object] = {
        "ticket_id": ticket_id,
        "title": title,
        "from_office": from_office,
        "office": office,
        "message": messages.staff.ticket_forwarded.format(
            title=title, from_office=from_office or "-", note=note
        ).strip(),
    }
    try:
        repo.save_notification(office_alias(office), KIND_TICKET_FORWARDED, payload)
    except StoreError as exc:
        log.warning("forward notification for ticket %s not saved: %s", ticket_id, exc)
