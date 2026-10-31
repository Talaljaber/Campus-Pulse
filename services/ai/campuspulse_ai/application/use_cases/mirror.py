"""TicketMirror: push a changed ticket to the ticket sinks (ActUseCase, SyncTicketUseCase, EscalateSla).

A sink failure never fails the caller: it is logged and kept on that sink's link as `error`
(`ticket_links.last_error`, D-011). The record sink (`supabase`) is the ticket row itself, so it has
no link to record a failure on.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Collection, Sequence

from campuspulse_ai.domain.entities import Ticket
from campuspulse_ai.domain.errors import SinkError, StoreError
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.ports import Repository, TicketSink
from campuspulse_ai.domain.values import TicketLink

log = logging.getLogger(__name__)

RECORD_SINK = "supabase"
"""The system-of-record sink (`adapters/integrations/supabase_sink.SINK_NAME`): its link is the ticket
row itself, so it is not stored in `ticket_links` nor shown in `action.external`."""
INCIDENT_TAG = "incident"
"""Tag of the one ticket that tracks a Pulse incident (P4.10); its `request_id` is the report that
opened the incident, so lookups of a request's own ticket skip it."""
FAILED_LINK_PREFIX = "error:"
"""`external_id` of a link that records a failed push (`ticket_links.external_id` is not null)."""


class TicketMirror:
    """`push(ticket, skip=())` calls `update_status(ticket)` on every sink not named in `skip`.

    Errors: none escape. A `SinkError` is kept on the sink's link (its current link with `error`
    set, or a placeholder `error:<ticket id>` link); a `StoreError` while saving that link is logged.
    """

    def __init__(self, sinks: Sequence[TicketSink], repo: Repository) -> None:
        self._sinks = tuple(sinks)
        self._repo = repo

    @property
    def sinks(self) -> tuple[TicketSink, ...]:
        return self._sinks

    def push(self, ticket: Ticket, *, skip: Collection[str] = ()) -> None:
        for sink in self._sinks:
            if sink.name in skip:
                continue
            try:
                sink.update_status(ticket)
            except SinkError as exc:
                log.warning("sink %s update failed for ticket %s: %s", sink.name, ticket.id, exc)
                if sink.name != RECORD_SINK:
                    self._record_failure(ticket, sink.name, str(exc))

    def _record_failure(self, ticket: Ticket, sink: str, error: str) -> None:
        current = next((x for x in ticket.links if x.sink == sink), None)
        failed = (
            dataclasses.replace(current, error=error)
            if current
            else TicketLink(ticket.id, sink, f"{FAILED_LINK_PREFIX}{ticket.id}", None, error)
        )
        try:
            self._repo.save_ticket_link(failed)
        except StoreError as exc:
            log.warning("link %s/%s not saved: %s", sink, ticket.id, exc)


def relabelled(
    ticket: Ticket,
    category: Category,
    priority: Priority,
    *,
    office: str | None = None,
    tags: tuple[str, ...] | None = None,
) -> Ticket:
    """`ticket` with new labels (and a new `office`/`tags` when given). A title that starts with the old
    labels (the rule-based understander writes `"<category>/<priority>: <gist>"`) is re-prefixed, so a
    corrected or forwarded ticket never shows its old category in the dashboard or Linear."""
    old = f"{ticket.category}/{ticket.priority}: "
    title = ticket.title
    if title.startswith(old):
        title = f"{category}/{priority}: {title[len(old) :]}"
    return dataclasses.replace(
        ticket,
        category=category,
        priority=priority,
        title=title,
        office=ticket.office if office is None else office,
        tags=ticket.tags if tags is None else tags,
    )
