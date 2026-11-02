"""FastAPI application factory (framework layer, entry-point side only), P0.7 + P3.12.

`create_app(services, settings, build=...)` mounts every contract route (`api_contract.ENDPOINTS`)
with the same declarations as the mock app, so `create_app().openapi()` equals
`create_mock_app().openapi()` (a test pins it) and `export_openapi` gives the same file for both.

- `services`: the wired use cases (`composition.api.ApiServices`). None = `build(settings)` runs at
  startup (the lifespan) when `build` is given, else nothing is wired (every use-case route answers
  `501 not_implemented`, `/health` says `degraded`).
- `settings`: defaults to `Settings()` from the env; stored on `app.state.settings`.

The lifespan also starts the SLA scanner (`background.sla_loop`) when `services.sla` and
`services.clock` are wired and `SLA_SCAN_MINUTES > 0`, and cancels it on shutdown.

Errors are mapped in `frameworks/errors.py`; auth is `frameworks/auth.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from campuspulse_ai import __version__
from campuspulse_ai.composition.api import ApiServices
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.frameworks.api_contract import API_DESCRIPTION, API_TITLE, ENDPOINTS
from campuspulse_ai.frameworks.background import SECONDS_PER_MINUTE, sla_loop
from campuspulse_ai.frameworks.errors import install_error_handlers
from campuspulse_ai.frameworks.heap import trim_heap
from campuspulse_ai.frameworks.routes import (
    announcements,
    chat,
    explain,
    feedback,
    health,
    incidents,
    integrations,
    lab,
    pending,
    redteam,
    reviews,
    tickets,
    triage,
)

log = logging.getLogger(__name__)

Builder = Callable[[Settings], ApiServices]

_ROUTERS = (
    triage.router,
    explain.router,
    feedback.router,
    tickets.router,
    reviews.router,
    integrations.router,
    lab.router,
    redteam.router,
    incidents.router,
    pending.router,
    health.router,
    announcements.router,
    chat.router,
)
_ORDER = {e.op_id: i for i, e in enumerate(ENDPOINTS)}


def create_app(
    services: ApiServices | None = None,
    settings: Settings | None = None,
    *,
    build: Builder | None = None,
) -> FastAPI:
    """Build the app. Raises `pydantic.ValidationError` on bad env values (startup failure)."""
    resolved = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if services is None and build is not None:
            app.state.services = build(resolved)
            log.info("services built: %s", _wired(app.state.services))
            trim_heap()  # the model load's temporary buffers go back to the OS (P4.13)
        wired: ApiServices = app.state.services
        task: asyncio.Task[None] | None = None
        if wired.sla is not None and wired.clock is not None and resolved.sla_scan_minutes > 0:
            interval_s = resolved.sla_scan_minutes * SECONDS_PER_MINUTE
            task = asyncio.create_task(sla_loop(wired.sla.run, wired.clock, interval_s))
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title=API_TITLE,
        version=__version__,
        description=API_DESCRIPTION,
        separate_input_output_schemas=False,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.services = services or ApiServices()
    app.include_router(contract_router())
    install_error_handlers(app)
    return app


def contract_router() -> APIRouter:
    """Every route module's routes in `ENDPOINTS` order (the mock app's order), so the exported
    document is byte-identical. Raises RuntimeError if a contract operation has no route."""
    by_op = {r.operation_id: r for router in _ROUTERS for r in router.routes if isinstance(r, APIRoute)}
    missing = sorted(set(_ORDER) - set(by_op))
    if missing:
        raise RuntimeError(f"contract operations without a route: {missing}")
    combined = APIRouter()
    combined.routes.extend(by_op[e.op_id] for e in ENDPOINTS)
    return combined


def _wired(services: ApiServices) -> list[str]:
    return [f.name for f in dataclasses.fields(services) if getattr(services, f.name) is not None]
