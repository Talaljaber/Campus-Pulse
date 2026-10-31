"""`POST /v1/integrations/linear/webhook`: inbound Linear status sync (P4.9).

No service token: the HMAC signature over the raw body is the auth (`LinearSink.handle_inbound`,
docs/integrations.md §2). The route answers once the status is saved (Linear wants a 2xx within 5 s);
the slow part (notifications, email) runs as a background task after the response.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, Request
from starlette.concurrency import run_in_threadpool

from campuspulse_ai.application.dto import ErrorCode, WebhookAck
from campuspulse_ai.domain.errors import Unauthorized
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.errors import ApiError, not_wired
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()

LINEAR = "linear"


@router.api_route(**route_kwargs("linear_webhook"))
async def linear_webhook(
    request: Request,
    services: Services,
    background: BackgroundTasks,
    linear_signature: Annotated[str | None, Header(alias="Linear-Signature")] = None,
) -> WebhookAck:
    """Verify, apply a forward state change to the linked ticket, ack.

    401 for a missing or bad signature or a stale `webhookTimestamp` (nothing is written); 422 for a
    signed body that is not JSON; `accepted: false` for anything ignored (not a state change, an
    issue we do not know, or a change that would move the ticket backwards).
    """
    if services.tickets is None:
        raise not_wired("ticket sync")
    raw = await request.body()
    try:
        change = await run_in_threadpool(services.tickets.apply_inbound, LINEAR, raw, linear_signature or "")
    except Unauthorized as exc:
        raise ApiError(ErrorCode.UNAUTHENTICATED, "Invalid webhook signature.") from exc
    if change is None:
        return WebhookAck(accepted=False, ticket_id=None, status=None)
    background.add_task(services.tickets.propagate, change)
    return WebhookAck(accepted=True, ticket_id=change.ticket.id, status=change.ticket.status)
