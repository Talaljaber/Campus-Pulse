"""Contract routes whose use cases are built by later tasks. They authenticate like every route and
then answer `501 not_implemented`, so the real app already exports the full contract (the same
OpenAPI document as the mock app) and clients get a typed error instead of a 404.

- `GET /v1/insights/recurring`: Recurring problems (P4.21).
- `POST /v1/admin/simulate`, `POST /v1/admin/reindex`: optional extras (P5.19, P4.20).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from campuspulse_ai.application.dto import (
    RecurringQuery,
    ReindexRequest,
    SimulateRequest,
)
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired

router = APIRouter()


@router.api_route(**route_kwargs("insights_recurring"))
def insights_recurring(
    query: Annotated[RecurringQuery, Query()],
    request: Request,
    caller: Annotated[Principal, Depends(authorize("insights_recurring"))],
) -> Any:
    """Recurring problems (P4.21)."""
    raise not_wired("recurring problems")


@router.api_route(**route_kwargs("admin_simulate"))
def admin_simulate(
    body: SimulateRequest,
    request: Request,
    caller: Annotated[Principal, Depends(authorize("admin_simulate"))],
) -> Any:
    """Optional extra: simulated Pulse traffic (P5.19)."""
    raise not_wired("simulated traffic")


@router.api_route(**route_kwargs("admin_reindex"))
def admin_reindex(
    body: ReindexRequest,
    request: Request,
    caller: Annotated[Principal, Depends(authorize("admin_reindex"))],
) -> Any:
    """Optional extra: re-embed the FAQ collection (P4.20)."""
    raise not_wired("re-indexing")
