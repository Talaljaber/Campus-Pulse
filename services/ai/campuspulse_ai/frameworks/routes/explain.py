"""`GET /v1/explain/{request_id}/counterfactual?drop=<token>` (P3.12): `CounterfactualUseCase`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from campuspulse_ai.application.dto import CounterfactualQuery, CounterfactualResponse
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired
from campuspulse_ai.frameworks.routes.deps import Services
from campuspulse_ai.frameworks.routes.triage import student_alias

router = APIRouter()


@router.api_route(**route_kwargs("explain_counterfactual"))
def explain_counterfactual(
    request_id: str,
    query: Annotated[CounterfactualQuery, Query()],
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("explain_counterfactual"))],
) -> CounterfactualResponse:
    """Re-classify the request without `drop` (a student only for their own request)."""
    if services.counterfactual is None:
        raise not_wired("counterfactual explanations")
    return services.counterfactual.run(request_id, query.drop, caller_alias=student_alias(caller))
