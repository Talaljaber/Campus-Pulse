"""Contract routes whose use cases are built by later tasks. They authenticate like every route and
then answer `501 not_implemented`, so the real app already exports the full contract (the same
OpenAPI document as the mock app) and clients get a typed error instead of a 404.

- `GET /v1/incidents`, `POST /v1/incidents/{id}/resolve`: Pulse (P4.10).
- `GET /v1/insights/recurring`: Recurring problems (P4.21).
- `POST /v1/redteam/run`: red team (P4.11).
- `POST /v1/admin/simulate`, `POST /v1/admin/reindex`: optional extras (P5.19, P4.20).
- `POST /v1/batch`, `GET /v1/metrics`: model lab (P4.12).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response

from campuspulse_ai.application.dto import (
    IncidentListQuery,
    RecurringQuery,
    RedTeamRunRequest,
    ReindexRequest,
    ResolveIncidentRequest,
    SimulateRequest,
)
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired

router = APIRouter()


@router.api_route(**route_kwargs("list_incidents"))
def list_incidents(
    query: Annotated[IncidentListQuery, Query()],
    request: Request,
    caller: Annotated[Principal, Depends(authorize("list_incidents"))],
) -> Any:
    """Pulse incidents (P4.10)."""
    raise not_wired("incidents")


@router.api_route(**route_kwargs("resolve_incident"))
def resolve_incident(
    incident_id: str,
    body: ResolveIncidentRequest,
    request: Request,
    caller: Annotated[Principal, Depends(authorize("resolve_incident"))],
) -> Any:
    """Resolve an incident (P4.10)."""
    raise not_wired("incidents")


@router.api_route(**route_kwargs("insights_recurring"))
def insights_recurring(
    query: Annotated[RecurringQuery, Query()],
    request: Request,
    caller: Annotated[Principal, Depends(authorize("insights_recurring"))],
) -> Any:
    """Recurring problems (P4.21)."""
    raise not_wired("recurring problems")


@router.api_route(**route_kwargs("batch"), response_class=Response)
def batch(
    file: Annotated[UploadFile, File(description="CSV with columns request_id,text (UTF-8).")],
    request: Request,
    caller: Annotated[Principal, Depends(authorize("batch"))],
    use_llm: Annotated[bool, Form()] = False,
) -> Response:
    """Batch predictions (P4.12)."""
    raise not_wired("batch predictions")


@router.api_route(**route_kwargs("redteam_run"))
def redteam_run(
    body: RedTeamRunRequest,
    request: Request,
    caller: Annotated[Principal, Depends(authorize("redteam_run"))],
) -> Any:
    """Red-team run (P4.11)."""
    raise not_wired("the red team")


@router.api_route(**route_kwargs("metrics"))
def metrics(
    request: Request,
    caller: Annotated[Principal, Depends(authorize("metrics"))],
) -> Any:
    """Model-lab metrics (P4.12)."""
    raise not_wired("metrics")


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
