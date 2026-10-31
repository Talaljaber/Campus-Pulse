"""Role-dependent views of use-case results (presentation only; no decisions are made here)."""

from __future__ import annotations

from campuspulse_ai.application.dto import ExternalRefOut, TicketOut, TriageResponse, to_student_view
from campuspulse_ai.domain.entities import Ticket

ADMIN_ONLY_FLAGS: frozenset[str] = frozenset({"priority_gaming_suspected"})
"""docs/api/README.md › Flags: visible to admin (and the service token) only."""


def triage_view(response: TriageResponse, role: str) -> TriageResponse:
    """What `role` may see of a triage/clarify response.

    student: `to_student_view` (no staff-only flags); staff: without the admin-only flags; admin and
    service: everything.
    """
    if role == "student":
        return to_student_view(response)
    if role == "staff":
        return response.model_copy(update={"flags": [f for f in response.flags if f not in ADMIN_ONLY_FLAGS]})
    return response


def ticket_out(ticket: Ticket) -> TicketOut:
    """`TicketOut` of a ticket. Links that record a failed push (`error` set, D-011) are not mirrors,
    so they are left out, as in `action.external`."""
    return TicketOut(
        id=ticket.id,
        request_id=ticket.request_id,
        incident_id=ticket.incident_id,
        office=ticket.office,
        category=ticket.category,
        priority=ticket.priority,
        status=ticket.status,
        provisional=ticket.provisional,
        sla_due_at=ticket.sla_due_at,
        escalated_at=ticket.escalated_at,
        resolved_at=ticket.resolved_at,
        title=ticket.title,
        links=[
            ExternalRefOut(sink=link.sink, external_id=link.external_id, url=link.url)
            for link in ticket.links
            if link.error is None
        ],
    )
