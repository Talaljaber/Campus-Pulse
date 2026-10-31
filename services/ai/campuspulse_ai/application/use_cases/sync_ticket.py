"""SyncTicketUseCase: ticket status changes from a sink webhook or the staff dashboard (SPEC §5.2, P4.9).

Two steps, so the webhook can answer Linear within its 5 s budget:
1. **apply** (`apply_inbound` / `change_status`): verify, find the ticket, save the new status, audit.
   Fast (one lookup, one write); the route waits for it and returns the result.
2. **propagate** (`propagate(change)`): mirror to the other sinks, tell the student (in-app
   `notifications` row, kind `ticket_status`), and email the student's demo inbox on `resolved`.
   Slow and failure-tolerant; the routes run it as a background task after the response.

`run` and `from_dashboard` do both steps (the plan interface, used by tests and scripts).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from campuspulse_ai.application.use_cases.messages import Messages
from campuspulse_ai.application.use_cases.mirror import RECORD_SINK, TicketMirror
from campuspulse_ai.application.use_cases.ports import ROLE_ADMIN, ROLE_STAFF, Actor
from campuspulse_ai.domain.entities import OutboxMessage, Ticket
from campuspulse_ai.domain.errors import (
    NotFound,
    NotificationError,
    RecipientNotAllowed,
    StoreError,
    Unauthorized,
)
from campuspulse_ai.domain.ports import Clock, Notifier, Repository, TicketSink
from campuspulse_ai.domain.values import TicketStatus

log = logging.getLogger(__name__)

DONE_STATUSES = frozenset({TicketStatus.RESOLVED, TicketStatus.CLOSED})
"""Statuses that set `resolved_at`; moving back to an open status clears it (a dashboard reopen)."""
OPEN_STATUSES = frozenset({TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.ESCALATED})
DASHBOARD = "dashboard"
"""`StatusChange.source` of a staff change made in the CampusPulse dashboard."""
NOTIFICATION_KIND = "ticket_status"
"""docs/api/README.md › Notifications payload: `{ticket_id, status, title, message?}`."""
ACTOR = "sync_ticket"


@dataclass(frozen=True, slots=True)
class StatusChange:
    """One applied status change: the saved ticket, its previous status, where the change came from
    (a sink name or `dashboard`) and the staff note, if any."""

    ticket: Ticket
    previous: TicketStatus
    source: str
    note: str | None = None

    @property
    def changed(self) -> bool:
        return self.ticket.status != self.previous


class SyncTicketUseCase:
    """Ticket lifecycle sync (ARCHITECTURE §2.2).

    - `apply_inbound(sink_name, payload, signature) -> StatusChange | None`: `TicketSink.handle_inbound`
      verifies and parses the delivery (`Unauthorized` for a bad signature or a stale timestamp, before
      anything is read or written; `InvalidInput` for a signed body that is not JSON). None (ignored,
      nothing written) when the event is not a state change, the issue is not linked to a ticket, or
      the change would not move the ticket forward (`TicketStatus.rank`). Moving forward only
      ignores our own pushes that come back through the webhook (a dashboard `closed` returns from
      Linear as `completed` -> `resolved`) and stale or replayed deliveries.
    - `change_status(ticket_id, status, actor, note=None) -> StatusChange`: a dashboard change. Staff
      of the ticket's office or an admin (`Unauthorized` otherwise); any direction is allowed (staff
      may reopen); the same status is a no-op. `NotFound` for an unknown ticket.
    - `propagate(change)`: see the module docstring. Never raises.
    - `run(...) -> Ticket | None` and `from_dashboard(...) -> Ticket`: apply + propagate.

    Writes: the `tickets` row (status, `resolved_at`), an `events` row `ticket.status`; then
    `ticket_links.last_error` on a sink failure, a `notifications` row for the student's alias, and an
    `outbox` row for the resolution email. `StoreError` from the apply step propagates (503).
    """

    def __init__(
        self,
        sinks: Sequence[TicketSink],
        repo: Repository,
        notifier: Notifier,
        clock: Clock,
        messages: Messages,
        *,
        student_inbox: str | None = None,
    ) -> None:
        self._sinks = {s.name: s for s in sinks}
        self._mirror = TicketMirror(sinks, repo)
        self._repo = repo
        self._notifier = notifier
        self._clock = clock
        self._messages = messages
        self._student_inbox = student_inbox or None

    # ------------------------------------------------------------------ plan interface

    def run(self, sink_name: str, payload: bytes, signature: str) -> Ticket | None:
        change = self.apply_inbound(sink_name, payload, signature)
        if change is None:
            return None
        self.propagate(change)
        return change.ticket

    def from_dashboard(
        self, ticket_id: str, new_status: TicketStatus, actor: Actor, note: str | None = None
    ) -> Ticket:
        change = self.change_status(ticket_id, new_status, actor, note)
        self.propagate(change)
        return change.ticket

    # ------------------------------------------------------------------ step 1: apply

    def apply_inbound(self, sink_name: str, payload: bytes, signature: str) -> StatusChange | None:
        sink = self._sinks.get(sink_name)
        if sink is None:
            raise Unauthorized(f"no {sink_name!r} sink is configured, so its webhook cannot be verified")
        event = sink.handle_inbound(payload, signature)
        if event is None:
            return None
        try:
            ticket = self._repo.ticket_by_link(event.sink, event.external_id)
        except NotFound:
            log.info("inbound %s event for unlinked issue %s ignored", event.sink, event.external_id)
            return None
        if event.status.rank <= ticket.status.rank:
            log.info(
                "inbound %s %s -> %s for ticket %s ignored (not forward)",
                event.sink,
                ticket.status,
                event.status,
                ticket.id,
            )
            return None
        return self._apply(ticket, event.status, source=event.sink, at=event.occurred_at)

    def change_status(
        self, ticket_id: str, new_status: TicketStatus, actor: Actor, note: str | None = None
    ) -> StatusChange:
        ticket = self._repo.get_ticket(ticket_id)
        _check_staff(actor, ticket)
        clean_note = (note or "").strip() or None
        if new_status == ticket.status:
            return StatusChange(ticket, ticket.status, DASHBOARD, clean_note)
        return self._apply(ticket, new_status, source=DASHBOARD, at=self._clock.now(), note=clean_note)

    def _apply(
        self, ticket: Ticket, status: TicketStatus, *, source: str, at: datetime, note: str | None = None
    ) -> StatusChange:
        resolved_at = ticket.resolved_at
        if status in DONE_STATUSES:
            resolved_at = resolved_at or at
        elif status in OPEN_STATUSES:
            resolved_at = None
        updated = dataclasses.replace(ticket, status=status, resolved_at=resolved_at)
        self._repo.save_ticket(updated)
        change = StatusChange(updated, ticket.status, source, note)
        self._audit(change)
        return change

    # ------------------------------------------------------------------ step 2: propagate

    def propagate(self, change: StatusChange) -> None:
        if not change.changed:
            return
        ticket = change.ticket
        try:
            self._mirror.push(ticket, skip={RECORD_SINK, change.source})
            self._notify_student(change)
            if ticket.status == TicketStatus.RESOLVED:
                self._email_resolution(change)
        except Exception:  # background boundary: a failed side effect never surfaces to the caller
            log.exception("propagating ticket %s -> %s failed", ticket.id, ticket.status)

    def _notify_student(self, change: StatusChange) -> None:
        ticket = change.ticket
        try:
            alias = self._repo.get_request(ticket.request_id).alias.strip()
        except StoreError as exc:
            log.warning("request of ticket %s not found, student not notified: %s", ticket.id, exc)
            return
        if not alias:
            return
        payload: dict[str, object] = {
            "ticket_id": ticket.id,
            "status": str(ticket.status),
            "title": ticket_title(ticket),
        }
        if change.note:
            payload["message"] = change.note
        try:
            self._repo.save_notification(alias, NOTIFICATION_KIND, payload)
        except StoreError as exc:
            log.warning("status notification for ticket %s not saved: %s", ticket.id, exc)

    def _email_resolution(self, change: StatusChange) -> None:
        inbox = self._student_inbox
        if inbox is None:
            return
        ticket = change.ticket
        email = self._messages.email
        msg = OutboxMessage(
            id="",
            kind="email",
            to_address=inbox,
            subject=email.resolved_subject.format(title=ticket_title(ticket)),
            body=email.resolved_body.format(
                title=ticket_title(ticket), ticket_id=ticket.id, note=change.note or "-"
            ),
            provider_id=None,
            status="queued",
            created_at=self._clock.now(),
            priority=ticket.priority,
        )
        try:
            self._notifier.send(msg)  # AllowlistedNotifier: refusals and failures land on the outbox row
        except (RecipientNotAllowed, NotificationError, StoreError) as exc:
            log.warning("resolution email for ticket %s not sent: %s", ticket.id, exc)

    def _audit(self, change: StatusChange) -> None:
        payload = {
            "from": str(change.previous),
            "to": str(change.ticket.status),
            "source": change.source,
            "note": change.note,
        }
        try:
            self._repo.append_event(ACTOR, "ticket.status", f"ticket:{change.ticket.id}", payload)
        except StoreError as exc:
            log.warning("ticket.status event not saved: %s", exc)


def ticket_title(ticket: Ticket) -> str:
    """The ticket's title, or `<category> request` when it has none (the chat prints it)."""
    return ticket.title or f"{ticket.category} request"


def _check_staff(actor: Actor, ticket: Ticket) -> None:
    """Admins, or staff of the ticket's office (D-005 codes); everyone else is `Unauthorized`."""
    if actor.role == ROLE_ADMIN:
        return
    if actor.role == ROLE_STAFF and actor.office is not None and actor.office == ticket.office:
        return
    raise Unauthorized(f"role {actor.role!r} of office {actor.office!r} may not change this ticket")
