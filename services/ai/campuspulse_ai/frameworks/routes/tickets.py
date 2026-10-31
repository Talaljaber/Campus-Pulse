"""Staff ticket actions from the dashboard: `POST /v1/tickets/{ticket_id}/status` (P4.9, LD-25) and
`POST /v1/tickets/{ticket_id}/forward` (UD-13)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from campuspulse_ai.application.dto import ForwardRequest, TicketOut, TicketStatusRequest
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired
from campuspulse_ai.frameworks.presenters import ticket_out
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()


@router.api_route(**route_kwargs("ticket_status"))
def ticket_status(
    ticket_id: str,
    body: TicketStatusRequest,
    request: Request,
    services: Services,
    background: BackgroundTasks,
    caller: Annotated[Principal, Depends(authorize("ticket_status"))],
) -> TicketOut:
    """Save the new status (staff of the ticket's office or admin; the use case checks the office),
    answer with the ticket, then mirror to Linear and notify the student after the response."""
    if services.tickets is None:
        raise not_wired("ticket status changes")
    change = services.tickets.change_status(ticket_id, body.status, caller, body.note)
    background.add_task(services.tickets.propagate, change)
    return ticket_out(change.ticket)


@router.api_route(**route_kwargs("ticket_forward"))
def ticket_forward(
    ticket_id: str,
    body: ForwardRequest,
    request: Request,
    services: Services,
    background: BackgroundTasks,
    caller: Annotated[Principal, Depends(authorize("ticket_forward"))],
) -> TicketOut:
    """Re-route the ticket to another office (staff of its office or admin; the use case checks),
    answer with it, then update Linear and notify the new office after the response."""
    if services.forward is None:
        raise not_wired("ticket forwards")
    fwd = services.forward.forward(ticket_id, body.office, caller, body.note)
    background.add_task(services.forward.propagate, fwd)
    return ticket_out(fwd.ticket)
