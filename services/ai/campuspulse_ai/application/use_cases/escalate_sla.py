"""SlaReminderUseCase: the SLA reminder scanner (PLAN P9 (d) rows 16/16b and (g), P9.4).

Three triggers call `run(now)` (all idempotent through `JourneyStore.claim_reminder`): the in-process loop
every `SLA_SCAN_MINUTES`, the throttled sweep after API responses, and `POST /v1/cron/sla`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta

from campuspulse_ai.application.use_cases.journey_ports import JourneyStore
from campuspulse_ai.application.use_cases.messages import Messages
from campuspulse_ai.application.use_cases.sync_ticket import NOTIFICATION_KIND, ticket_title
from campuspulse_ai.application.use_cases.ticket_emails import EmailContext, EmailEvent, TicketMailer
from campuspulse_ai.domain.entities import Ticket
from campuspulse_ai.domain.errors import NotFound, StoreError
from campuspulse_ai.domain.journey import ActivityKind, TicketActivity, Visibility
from campuspulse_ai.domain.labels import Priority
from campuspulse_ai.domain.ports import Repository

log = logging.getLogger(__name__)

STAFF_ALIAS_PREFIX = "office:"
"""Staff notifications go to the alias `office:<office code>` (D-005), one inbox per office."""
ACTOR = "sla"
SYSTEM = "system"
TIME_FORMAT = "%Y-%m-%d %H:%M"
FIRST_LEVEL = 1
SECOND_LEVEL = 2


class SlaReminderUseCase:
    """`run(now) -> list[str]`: send at most two reminders per clock period; returns the reminded ids.

    For each ticket from `Repository.overdue_open_tickets(now)` (status `new`/`in_progress`, `sla_due_at`
    before `now`) the due level is 1 when `reminder_count == 0`, 2 when `reminder_count == 1` and
    `now > sla_due_at + sla_hours[priority]`; otherwise it is skipped. The level is claimed with
    `JourneyStore.claim_reminder` (a conditional update, so concurrent scans never send twice); only a
    claimed ticket gets: the `reminder` email to the office inbox (level 2: `reminder_2` to the office and
    the admin inbox), an in-app note for `office:<office>` (kind `ticket_status`), an internal `reminder`
    activity row and an `events` row `sla.reminder` with the level. Priority and status never change.
    A forward, keep open, reopen or priority change restarts the clock and resets the count (lifecycle).

    Errors: none escape. A failed scan (`StoreError`) returns [] and the next scan retries; a ticket whose
    claim fails is skipped; a failed email, note or audit never undoes the claim.
    """

    def __init__(
        self,
        repo: Repository,
        journey: JourneyStore,
        mailer: TicketMailer,
        messages: Messages,
        sla_hours: Mapping[Priority, int],
    ) -> None:
        self._repo = repo
        self._journey = journey
        self._mailer = mailer
        self._messages = messages
        self._sla = dict(sla_hours)

    def run(self, now: datetime) -> list[str]:
        try:
            overdue = self._repo.overdue_open_tickets(now)
        except StoreError as exc:
            log.warning("SLA scan skipped: %s", exc)
            return []
        reminded: list[str] = []
        for ticket in overdue:
            level = self._level_due(ticket, now)
            if level is None:
                continue
            try:
                claimed = self._journey.claim_reminder(ticket.id, level, now)
            except StoreError as exc:
                log.warning("reminder %d of ticket %s not claimed (retried): %s", level, ticket.id, exc)
                continue
            if not claimed:
                continue  # another scan got it, or the ticket changed meanwhile
            self._deliver(ticket, level, now)
            reminded.append(ticket.id)
        return reminded

    def _level_due(self, ticket: Ticket, now: datetime) -> int | None:
        if ticket.reminder_count == 0:
            return FIRST_LEVEL
        if ticket.reminder_count == 1:
            period = timedelta(hours=self._sla[ticket.priority])
            return SECOND_LEVEL if now > ticket.sla_due_at + period else None
        return None

    def _deliver(self, ticket: Ticket, level: int, now: datetime) -> None:
        try:
            self._email(ticket, level)
        except Exception:  # noqa: BLE001 - the claim stands; a delivery problem must not stop the scan
            log.exception("reminder %d email for ticket %s failed", level, ticket.id)
        self._notify_staff(ticket, level)
        self._activity(ticket, level, now)
        self._audit(ticket, level)

    def _email(self, ticket: Ticket, level: int) -> None:
        try:
            request_text = self._repo.get_request(ticket.request_id).raw_text
        except (NotFound, StoreError):
            request_text = ""
        ctx = EmailContext(ticket=ticket, request_text=request_text, lang="en")
        inboxes = self._mailer.inboxes
        if level == FIRST_LEVEL:
            self._mailer.send(EmailEvent.REMINDER, "office", ctx, inboxes.office(ticket.office))
            return
        self._mailer.send(EmailEvent.REMINDER_2, "office", ctx, inboxes.office(ticket.office))
        self._mailer.send(EmailEvent.REMINDER_2, "admin", ctx, inboxes.admin())

    def _notify_staff(self, ticket: Ticket, level: int) -> None:
        note = self._messages.staff.escalated.format(
            old=ticket.priority, new=ticket.priority, sla_due_at=ticket.sla_due_at.strftime(TIME_FORMAT)
        )
        if level == SECOND_LEVEL:
            note = f"{note} Second reminder: the admin was informed."
        payload: dict[str, object] = {
            "ticket_id": ticket.id,
            "status": str(ticket.status),
            "title": ticket_title(ticket),
            "message": note,
        }
        try:
            self._repo.save_notification(f"{STAFF_ALIAS_PREFIX}{ticket.office}", NOTIFICATION_KIND, payload)
        except StoreError as exc:
            log.warning("reminder note for ticket %s not saved: %s", ticket.id, exc)

    def _activity(self, ticket: Ticket, level: int, now: datetime) -> None:
        body = "Reminder 1" if level == FIRST_LEVEL else "Reminder 2, admin informed"
        try:
            self._journey.add_activity(
                TicketActivity(
                    ticket_id=ticket.id,
                    kind=ActivityKind.REMINDER,
                    actor_role=SYSTEM,
                    created_at=now,
                    visibility=Visibility.INTERNAL,
                    body=body,
                )
            )
        except StoreError as exc:
            log.warning("reminder activity for ticket %s not saved: %s", ticket.id, exc)

    def _audit(self, ticket: Ticket, level: int) -> None:
        try:
            self._repo.append_event(ACTOR, "sla.reminder", f"ticket:{ticket.id}", {"level": level})
        except StoreError as exc:
            log.warning("sla.reminder event not saved: %s", exc)
