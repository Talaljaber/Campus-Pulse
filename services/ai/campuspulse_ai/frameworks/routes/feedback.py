"""`POST /v1/feedback` (P3.12 route; the use case is P3.11 `FeedbackUseCase`)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from campuspulse_ai.application.dto import FeedbackRequest, FeedbackResponse
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()


@router.api_route(**route_kwargs("feedback"))
def feedback(
    body: FeedbackRequest,
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("feedback"))],
) -> FeedbackResponse:
    """Staff confirm or correct a prediction. The reviewer is the caller, never a body field; the use
    case re-checks the role (ARCHITECTURE §2.3 step 1)."""
    if services.feedback is None:
        raise not_wired("feedback")
    return services.feedback.run(body, caller)
