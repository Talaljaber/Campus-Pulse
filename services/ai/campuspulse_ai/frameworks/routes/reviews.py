"""`GET /v1/reviews` and `POST /v1/reviews/{review_id}/forward` (UD-13 hybrid advisor routing).

Routes only: auth and the caller; `ReviewsUseCase` decides what the caller may see and resolve (the
same rule as the 0012 `review_queue_read` policy). Confirming an item (or changing its priority) stays
`POST /v1/feedback`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from campuspulse_ai.application.dto import FeedbackResponse, ForwardRequest, ReviewItemOut, ReviewListQuery
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()


@router.api_route(**route_kwargs("list_reviews"))
def list_reviews(
    query: Annotated[ReviewListQuery, Query()],
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("list_reviews"))],
) -> list[ReviewItemOut]:
    """The review items the caller may resolve, newest first (`?status=open` by default)."""
    if services.reviews is None:
        raise not_wired("advisor review")
    return services.reviews.queue(caller, query.status)


@router.api_route(**route_kwargs("review_forward"))
def review_forward(
    review_id: str,
    body: ForwardRequest,
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("review_forward"))],
) -> FeedbackResponse:
    """Resolve a review item by sending the request to `office` (a correction the model learns)."""
    if services.reviews is None:
        raise not_wired("advisor review")
    return services.reviews.forward(review_id, body.office, caller, body.note)
