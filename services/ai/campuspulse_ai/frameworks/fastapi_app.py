"""FastAPI application factory (framework layer, entry-point side only)."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from campuspulse_ai.config.settings import Settings
from campuspulse_ai.frameworks.routes import health


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app: ``/health`` at the root plus a ``/v1/health`` alias.

    Later tasks mount their routers under ``/v1``. ``settings`` is stored on
    ``app.state`` for routes; it defaults to ``Settings()`` read from the env.
    Raises ``pydantic.ValidationError`` on bad env values (startup failure).
    """
    app = FastAPI(title="CampusPulse AI", version="0.1.0")
    app.state.settings = settings or Settings()
    app.include_router(health.router)
    v1 = APIRouter(prefix="/v1")
    v1.include_router(health.router)
    app.include_router(v1)
    return app
