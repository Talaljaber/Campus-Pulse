"""Liveness route: ``GET /health`` (and the ``/v1/health`` alias mounted by the app)."""

from __future__ import annotations

import logging
import os
from typing import Literal

import psutil
from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter()


class HealthResponse(BaseModel):
    """Body of ``GET /health``.

    ``artifact`` is ``Manifest.sha`` once a model container exists (P3/P4); ``None`` in P0.
    ``rss_mb`` is the process resident set size in MiB, or ``-1.0`` if psutil fails.
    """

    status: Literal["ok"]
    artifact: str | None
    rss_mb: float


def _rss_mb() -> float:
    try:
        return float(psutil.Process(os.getpid()).memory_info().rss) / (1024 * 1024)
    except Exception:  # psutil can fail on locked-down hosts; health must not 500
        log.exception("could not read RSS")
        return -1.0


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return 200 with status, loaded artifact sha (None until models exist) and RSS. No side effects."""
    return HealthResponse(status="ok", artifact=None, rss_mb=_rss_mb())
