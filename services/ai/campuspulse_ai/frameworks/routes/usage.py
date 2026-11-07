"""`GET /v1/admin/usage`: the LLM spend for the admin overview (P10.17)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from campuspulse_ai.application.dto import LlmUsageResponse
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()


@router.api_route(**route_kwargs("admin_usage"))
def admin_usage(
    services: Services,
    caller: Annotated[Principal, Depends(authorize("admin_usage"))],
) -> LlmUsageResponse:
    """The LLM key's spend, limit and expiry (admin)."""
    if services.usage is None:
        raise not_wired("LLM usage")
    return services.usage.run()
