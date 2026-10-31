"""`POST /v1/redteam/run` (admin, P4.11): generate, run and score red-team items, store the scorecard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from campuspulse_ai.application.dto import RedTeamRunRequest, ScorecardOut
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import not_wired
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()


@router.api_route(**route_kwargs("redteam_run"))
def redteam_run(
    body: RedTeamRunRequest,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("redteam_run"))],
) -> ScorecardOut:
    """Run `body.n` items (≤ `REDTEAM_MAX_N`, else 422) over `body.styles` (null = all) with
    `body.seed`; the stored scorecard is returned and appears in `/v1/metrics` `redteam`. A sync
    route: FastAPI runs it in its threadpool while the core classifies."""
    if services.redteam is None:
        raise not_wired("the red team")
    return services.redteam.api(body)
