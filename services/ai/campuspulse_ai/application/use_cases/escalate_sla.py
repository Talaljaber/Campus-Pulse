"""EscalateSlaUseCase: the SLA scanner (SPEC §5.2, ARCHITECTURE §2.2, P4.9).

Runs every `SLA_SCAN_MINUTES` from the API lifespan (`frameworks/background.py`; one uvicorn worker,
so one scanner). pg_cron is not used.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Sequence
from datetime import datetime

from campuspulse_ai.application.use_cases.messages import Messages
from campuspulse_ai.application.use_cases.mirror import RECORD_SINK, TicketMirror
from campuspulse_ai.application.use_cases.sync_ticket import NOTIFICATION_KIND, ticket_title
from campuspulse_ai.domain.entities import Ticket
from campuspulse_ai.domain.errors import StoreError
from campuspulse_ai.domain.ports import Repository, TicketSink

log = logging.getLogger(__name__)

STAFF_ALIAS_PREFIX = "office:"
"""Staff notifications go to the alias `office:<office code>` (D-005), one inbox per office."""
ACTOR = "sla"
TIME_FORMAT = "%Y-%m-%d %H:%M"


class EscalateSlaUseCase:
    """`run(now) -> list[str]`: flag every overdue open ticket once; returns the flagged ids.

    TEMPORARY until P9.4 replaces this with the reminder scanner: priority and status are no longer
    changed. For each ticket from `Repository.overdue_open_tickets(now)` (status `new`/`in_progress`,
    SLA due before `now`) that was never flagged (`escalated_at` is None):
    - `escalated_at = now`, saved (priority and status unchanged);
    - mirrored to the external sinks;
    - an in-app note for the office's staff: a `notifications` row for `office:<office>`, kind
      `ticket_status`, `{ticket_id, status, title, message}`;
    - an `events` row `sla.escalated`.

    Errors: none escape. A failed scan (`StoreError`) returns [] and the next scan retries; a ticket
    whose save fails is skipped and retried next time.
    """

    def __init__(self, sinks: Sequence[TicketSink], repo: Repository, messages: Messages) -> None:
        self._mirror = TicketMirror(sinks, repo)
        self._repo = repo
        self._messages = messages

    def run(self, now: datetime) -> list[str]:
        try:
            overdue = self._repo.overdue_open_tickets(now)
        except StoreError as exc:
            log.warning("SLA scan skipped: %s", exc)
            return []
        escalated: list[str] = []
        for ticket in overdue:
            if ticket.escalated_at is not None:
                continue  # exactly once, even if staff moved it back to in_progress
            updated = dataclasses.replace(ticket, escalated_at=now)
            try:
                self._repo.save_ticket(updated)
            except StoreError as exc:
                log.warning("ticket %s not escalated (retried next scan): %s", ticket.id, exc)
                continue
            self._mirror.push(updated, skip={RECORD_SINK})
            self._notify_staff(ticket, updated)
            self._audit(ticket, updated)
            escalated.append(ticket.id)
        return escalated

    def _notify_staff(self, before: Ticket, after: Ticket) -> None:
        note = self._messages.staff.escalated.format(
            old=before.priority, new=after.priority, sla_due_at=before.sla_due_at.strftime(TIME_FORMAT)
        )
        payload: dict[str, object] = {
            "ticket_id": after.id,
            "status": str(after.status),
            "title": ticket_title(after),
            "message": note,
        }
        try:
            self._repo.save_notification(f"{STAFF_ALIAS_PREFIX}{after.office}", NOTIFICATION_KIND, payload)
        except StoreError as exc:
            log.warning("escalation note for ticket %s not saved: %s", after.id, exc)

    def _audit(self, before: Ticket, after: Ticket) -> None:
        payload = {"from_priority": str(before.priority), "to_priority": str(after.priority)}
        try:
            self._repo.append_event(ACTOR, "sla.escalated", f"ticket:{after.id}", payload)
        except StoreError as exc:
            log.warning("sla.escalated event not saved: %s", exc)
