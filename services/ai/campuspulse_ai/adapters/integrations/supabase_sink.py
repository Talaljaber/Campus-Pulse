"""SupabaseSink: the system of record for tickets (P4.6, SPEC §5.1 [12]).

Always on and always first in the sink order: the `tickets` row must exist before any external link
(`ticket_links` has a foreign key to it). Staff see the row through RLS on `tickets.office`.
"""

from __future__ import annotations

import dataclasses

from campuspulse_ai.domain.entities import Ticket
from campuspulse_ai.domain.errors import NotFound, SinkError, StoreError
from campuspulse_ai.domain.ports import Repository
from campuspulse_ai.domain.values import InboundEvent, TicketLink, TicketStatus

SINK_NAME = "supabase"


class SupabaseSink:
    """`TicketSink` over `Repository.save_ticket` (works on `SupabaseRepository` and `InMemoryRepository`).

    - `create(ticket)` upserts the row (and its links) and returns a link whose `external_id` is the
      ticket id. It is idempotent on `ticket.id`; pass a ticket with an id (an empty id makes the
      repository mint a new one each call). No `ticket_links` row is written for this sink: the
      ticket row itself is the record.
    - `update_status(ticket)` upserts the ticket as given (status, priority, escalation fields).
    - `close(ticket)` upserts it with status `closed`.
    - `handle_inbound` returns None: Supabase changes arrive through the dashboard route, not here.

    Errors: `SinkError(retryable=False)` for `NotFound`, `SinkError(retryable=True)` for any other
    `StoreError` (a PostgREST or network failure is usually transient).
    """

    def __init__(self, repo: Repository) -> None:
        self.name = SINK_NAME
        self._repo = repo

    def create(self, ticket: Ticket) -> TicketLink:
        saved = self._save(ticket)
        return TicketLink(ticket_id=saved.id, sink=SINK_NAME, external_id=saved.id, url=None)

    def update_status(self, ticket: Ticket) -> None:
        self._save(ticket)

    def close(self, ticket: Ticket) -> None:
        self._save(dataclasses.replace(ticket, status=TicketStatus.CLOSED))

    def handle_inbound(self, payload: bytes, signature: str) -> InboundEvent | None:
        return None

    def _save(self, ticket: Ticket) -> Ticket:
        try:
            return self._repo.save_ticket(ticket)
        except NotFound as exc:
            raise SinkError(f"ticket store: {exc}", retryable=False) from exc
        except StoreError as exc:
            raise SinkError(f"ticket store unavailable: {exc}", retryable=True) from exc
