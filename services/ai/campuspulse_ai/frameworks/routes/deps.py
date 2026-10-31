"""Shared route dependencies: the wired `ApiServices` and the caller per endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from campuspulse_ai.composition.api import ApiServices


def get_services(request: Request) -> ApiServices:
    """The `ApiServices` the app was built with (`app.state.services`)."""
    services: ApiServices = request.app.state.services
    return services


Services = Annotated[ApiServices, Depends(get_services)]
