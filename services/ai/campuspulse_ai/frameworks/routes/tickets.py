"""Ticket actions: status, forward, priority, comments and the requester buttons (P9.3, PLAN (c)/(d)).

`POST /v1/tickets/{ticket_id}/status|forward|priority|comments|student-action`. Routes only: the caller
comes from `authorize`, every decision is in `TicketLifecycleUseCase`, whose `deliver` (mirror to Linear,
in-app notes, emails) runs as a background task after the response.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from campuspulse_ai.application.dto import (
    ActivityOut,
    CommentRequest,
    ForwardRequest,
    PriorityRequest,
    StudentActionRequest,
    TicketOut,
    TicketStatusRequest,
    TicketThreadOut,
)
from campuspulse_ai.domain.journey import StudentAction, TicketActivity
from campuspulse_ai.domain.values import TicketStatus
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired
from campuspulse_ai.frameworks.presenters import ticket_out
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()


def activity_out(a: TicketActivity) -> ActivityOut:
    return ActivityOut.model_validate(
        {
            "id": a.id,
            "ticket_id": a.ticket_id,
            "kind": a.kind.value,
            "visibility": a.visibility.value,
            "actor_role": a.actor_role,
            "actor_alias": a.actor_alias,
            "actor_office": a.actor_office,
            "body": a.body,
            "from_status": a.from_status,
            "to_status": a.to_status,
            "from_office": a.from_office,
            "to_office": a.to_office,
            "from_priority": a.from_priority,
            "to_priority": a.to_priority,
            "created_at": a.created_at,
        }
    )


@router.api_route(**route_kwargs("ticket_status"))
def ticket_status(
    ticket_id: str,
    body: TicketStatusRequest,
    request: Request,
    services: Services,
    background: BackgroundTasks,
    caller: Annotated[Principal, Depends(authorize("ticket_status"))],
) -> TicketOut:
    """Save the new status (staff of the ticket's office or admin; the use case checks the office and
    the transition), answer with the ticket, then mirror, notify and email after the response."""
    if services.lifecycle is None:
        raise not_wired("ticket status changes")
    change = services.lifecycle.change_status(ticket_id, caller, TicketStatus(body.status), body.note)
    background.add_task(services.lifecycle.deliver, change)
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
    answer with it, then update Linear, notify and email after the response."""
    if services.lifecycle is None:
        raise not_wired("ticket forwards")
    change = services.lifecycle.forward(ticket_id, caller, body.office, body.note)
    background.add_task(services.lifecycle.deliver, change)
    return ticket_out(change.ticket)


@router.api_route(**route_kwargs("ticket_priority"))
def ticket_priority(
    ticket_id: str,
    body: PriorityRequest,
    request: Request,
    services: Services,
    background: BackgroundTasks,
    caller: Annotated[Principal, Depends(authorize("ticket_priority"))],
) -> TicketOut:
    """Change the priority (staff of the ticket's office or admin); the SLA clock restarts."""
    if services.lifecycle is None:
        raise not_wired("ticket priority changes")
    change = services.lifecycle.change_priority(ticket_id, caller, body.priority, body.note)
    background.add_task(services.lifecycle.deliver, change)
    return ticket_out(change.ticket)


@router.api_route(**route_kwargs("ticket_comment"))
def ticket_comment(
    ticket_id: str,
    body: CommentRequest,
    request: Request,
    services: Services,
    background: BackgroundTasks,
    caller: Annotated[Principal, Depends(authorize("ticket_comment"))],
) -> TicketThreadOut:
    """Add a comment or an internal note (the requester, staff of the ticket's office, or admin)."""
    if services.lifecycle is None:
        raise not_wired("ticket comments")
    status = TicketStatus(body.status) if body.status else None
    change = services.lifecycle.comment(ticket_id, caller, body.body, body.internal, status)
    background.add_task(services.lifecycle.deliver, change)
    assert change.activity is not None  # a comment always writes a thread row
    return TicketThreadOut(ticket=ticket_out(change.ticket), activity=activity_out(change.activity))


@router.api_route(**route_kwargs("ticket_student_action"))
def ticket_student_action(
    ticket_id: str,
    body: StudentActionRequest,
    request: Request,
    services: Services,
    background: BackgroundTasks,
    caller: Annotated[Principal, Depends(authorize("ticket_student_action"))],
) -> TicketOut:
    """The requester's Solved / Close / Keep open buttons (only for their own request)."""
    if services.lifecycle is None:
        raise not_wired("ticket requester actions")
    change = services.lifecycle.student_action(ticket_id, caller, StudentAction(body.action))
    background.add_task(services.lifecycle.deliver, change)
    return ticket_out(change.ticket)
