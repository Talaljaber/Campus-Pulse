"""`GET /v1/incidents` and `POST /v1/incidents/{incident_id}/resolve` (P4.10 Pulse).

Routes only: auth and the caller's office; the logic is `IncidentsUseCase`. Staff see their own
office's incidents (the office of the incident ticket); admins and the service token see all. Only
staff of that office and admins may resolve (the use case re-checks).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from campuspulse_ai.application.dto import (
    IncidentListQuery,
    IncidentOut,
    ResolveIncidentRequest,
    ResolveIncidentResponse,
)
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()

STAFF_ROLE = "staff"


@router.api_route(**route_kwargs("list_incidents"))
def list_incidents(
    query: Annotated[IncidentListQuery, Query()],
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("list_incidents"))],
) -> list[IncidentOut]:
    """Pulse incidents, newest first (`?open=1`: open only); staff get their office's."""
    if services.incidents is None:
        raise not_wired("incidents")
    office = caller.office if caller.role == STAFF_ROLE else None
    return services.incidents.list(open_only=bool(query.open), office=office)


@router.api_route(**route_kwargs("resolve_incident"))
def resolve_incident(
    incident_id: str,
    body: ResolveIncidentRequest,
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("resolve_incident"))],
) -> ResolveIncidentResponse:
    """Resolve an incident: its tickets close, the Linear issue moves to Done, reporters are told."""
    if services.incidents is None:
        raise not_wired("incidents")
    return services.incidents.resolve(incident_id, caller, body.note)
