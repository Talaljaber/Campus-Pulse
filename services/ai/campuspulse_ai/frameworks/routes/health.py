"""Liveness: `GET /health` (Render's health check) and `GET /v1/health` (P0.7, contract shape P3.12).

No auth, no side effects, never 5xx for a wiring gap: `status` is `degraded` while triage is not
wired (no model or no database yet), so Render keeps the instance up and the gap stays visible.
"""

from __future__ import annotations

import logging
import os

import psutil
from fastapi import APIRouter, Request

from campuspulse_ai import __version__
from campuspulse_ai.application.dto import HealthResponse
from campuspulse_ai.composition.api import ApiServices
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.routes.deps import Services

log = logging.getLogger(__name__)
router = APIRouter()

BYTES_PER_MIB = 1024 * 1024
RSS_UNKNOWN = -1.0


def _rss_mb() -> float:
    try:
        return float(psutil.Process(os.getpid()).memory_info().rss) / BYTES_PER_MIB
    except Exception:  # psutil can fail on locked-down hosts; health must not 500
        log.exception("could not read RSS")
        return RSS_UNKNOWN


def health_of(services: ApiServices) -> HealthResponse:
    """The health body for the wired services (pure apart from reading the RSS)."""
    info = services.health
    return HealthResponse(
        status="ok" if services.triage is not None else "degraded",
        version=__version__,
        artifact=info.artifact,
        sha=info.sha,
        rss_mb=_rss_mb(),
        encoder_loaded=info.encoder_loaded,
        sinks=list(info.sinks),
        llm_tiers=list(info.llm_tiers),
        vector_store=info.vector_store,
    )


@router.api_route(**route_kwargs("health"))
def health(request: Request, services: Services) -> HealthResponse:
    """Liveness, version, artifact identity and wiring."""
    return health_of(services)


@router.api_route(**route_kwargs("health_root"))
def health_root(request: Request, services: Services) -> HealthResponse:
    """Same as `/v1/health`, at Render's health-check path."""
    return health_of(services)
