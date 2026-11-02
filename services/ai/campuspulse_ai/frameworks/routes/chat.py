"""Chat agent (P9.8): `POST /v1/chat/turn`, `/v1/chat/preview` and `/v1/chat/confirm`. Routes only: auth and
the caller; the decisions are in `ChatUseCase`. A recorded ticket gets its follow-up (the thread's `created`
row and the received emails) as background tasks, after any re-route delivery."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from campuspulse_ai.application.dto import (
    ChatConfirmRequest,
    ChatConfirmResponse,
    ChatPreviewRequest,
    ChatTurnRequest,
    ChatTurnResponse,
    ProposalOut,
)
from campuspulse_ai.composition.api import ApiServices
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()


def _schedule(
    services: ApiServices,
    background: BackgroundTasks,
    later: list[Callable[[], None]],
    ticket_id: str | None,
) -> None:
    for task in later:
        background.add_task(task)
    if services.lifecycle is not None and ticket_id:
        background.add_task(services.lifecycle.on_created, ticket_id)


@router.api_route(**route_kwargs("chat_turn"))
def chat_turn(
    body: ChatTurnRequest,
    request: Request,
    services: Services,
    background: BackgroundTasks,
    caller: Annotated[Principal, Depends(authorize("chat_turn"))],
) -> ChatTurnResponse:
    """One chat turn (see the contract). `mode: fallback` when no language model is available."""
    if services.chat is None:
        raise not_wired("chat")
    later: list[Callable[[], None]] = []
    response = services.chat.turn(body, caller, later)
    _schedule(services, background, later, response.ticket_id)
    return response


@router.api_route(**route_kwargs("chat_preview"))
def chat_preview(
    body: ChatPreviewRequest,
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("chat_preview"))],
) -> ProposalOut:
    """What would be recorded for this text, with a signed token (no language model)."""
    if services.chat is None:
        raise not_wired("chat")
    return services.chat.preview(body, caller)


@router.api_route(**route_kwargs("chat_confirm"))
def chat_confirm(
    body: ChatConfirmRequest,
    request: Request,
    services: Services,
    background: BackgroundTasks,
    caller: Annotated[Principal, Depends(authorize("chat_confirm"))],
) -> ChatConfirmResponse:
    """Record the request of a signed proposal (the token must be the caller's, unexpired and untampered)."""
    if services.chat is None:
        raise not_wired("chat")
    later: list[Callable[[], None]] = []
    response = services.chat.confirm(body, caller, later)
    _schedule(services, background, later, response.ticket_id)
    return response
