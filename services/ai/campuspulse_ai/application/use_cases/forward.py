"""TicketForwardUseCase: staff hand a ticket to another office (UD-13, `POST /v1/tickets/{id}/forward`).

Two steps, like `SyncTicketUseCase`:
1. **forward** (the route waits for it): check the caller, re-route the ticket (office, the office's
   category, tag `forwarded`), save it and audit `ticket.forwarded`.
2. **propagate** (a background task after the response): mirror the ticket to the sinks (the Linear
   issue gets the new label, title and description) and notify the new office in-app
   (`ticket_forwarded` for `office:<office>`). Never raises.

A forward is an operational re-route, not a label correction: it does not touch the prediction or
live memory. Only a reviewer's forward of a review item (`ReviewsUseCase.forward`) teaches the model.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from campuspulse_ai.application.use_cases.messages import Messages
from campuspulse_ai.application.use_cases.mirror import RECORD_SINK, TicketMirror, relabelled
from campuspulse_ai.application.use_cases.offices import OfficeMap
from campuspulse_ai.application.use_cases.ports import Actor
from campuspulse_ai.application.use_cases.reviews import notify_forward
from campuspulse_ai.application.use_cases.sync_ticket import check_office_staff, ticket_title
from campuspulse_ai.domain.entities import Ticket
from campuspulse_ai.domain.errors import InvalidInput, StoreError
from campuspulse_ai.domain.ports import Repository, TicketSink

log = logging.getLogger(__name__)

FORWARDED_TAG = "forwarded"
"""Added to a forwarded ticket so staff and the Linear description show it changed hands."""
ACTOR = "forward"


@dataclass(frozen=True, slots=True)
class Forward:
    """One applied forward: the saved ticket, the office it left, the staff note and who did it."""

    ticket: Ticket
    from_office: str
    note: str
    by: str


class TicketForwardUseCase:
    """`forward(ticket_id, office, actor, note) -> Forward` and `propagate(forward)` (module docstring).

    Who: staff of the ticket's current office, or an admin (`Unauthorized` -> 403; staff only see
    their office's tickets, DB RLS). `office` must be a routed office other than the current one
    (`InvalidInput` -> 422). `NotFound` for an unknown ticket; `StoreError` from the save -> 503.
    Status, priority, SLA and links are kept.
    """

    def __init__(
        self, sinks: Sequence[TicketSink], repo: Repository, offices: OfficeMap, messages: Messages
    ) -> None:
        self._mirror = TicketMirror(sinks, repo)
        self._repo = repo
        self._offices = offices
        self._messages = messages

    def forward(self, ticket_id: str, office: str, actor: Actor, note: str | None = None) -> Forward:
        ticket = self._repo.get_ticket(ticket_id)
        check_office_staff(actor, ticket)
        target = office.strip()
        category = self._offices.category_for(target)
        if target == ticket.office:
            raise InvalidInput(f"ticket {ticket_id} is already in office {target!r}")
        tags = tuple(dict.fromkeys((*ticket.tags, FORWARDED_TAG)))
        updated = relabelled(ticket, category, ticket.priority, office=target, tags=tags)
        self._repo.save_ticket(updated)
        fwd = Forward(updated, ticket.office, (note or "").strip(), actor.alias or actor.role)
        self._audit(fwd)
        return fwd

    def propagate(self, fwd: Forward) -> None:
        try:
            self._mirror.push(fwd.ticket, skip=(RECORD_SINK,))
            notify_forward(
                self._repo, self._messages, ticket_id=fwd.ticket.id, title=ticket_title(fwd.ticket),
                from_office=fwd.from_office, office=fwd.ticket.office, note=fwd.note,
            )  # fmt: skip
        except Exception:  # background boundary: a failed side effect never surfaces to the caller
            log.exception("propagating the forward of ticket %s failed", fwd.ticket.id)

    def _audit(self, fwd: Forward) -> None:
        payload = {"from": fwd.from_office, "to": fwd.ticket.office, "note": fwd.note or None, "by": fwd.by}
        try:
            self._repo.append_event(ACTOR, "ticket.forwarded", f"ticket:{fwd.ticket.id}", payload)
        except StoreError as exc:
            log.warning("ticket.forwarded event not saved: %s", exc)
