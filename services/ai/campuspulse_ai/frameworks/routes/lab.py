"""Model lab: `POST /v1/batch` (CSV in, predictions CSV out) and `GET /v1/metrics` (P4.12)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response

from campuspulse_ai.application.dto import ErrorCode, MetricsResponse
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.frameworks.api_contract import route_kwargs
from campuspulse_ai.frameworks.auth import Principal, authorize
from campuspulse_ai.frameworks.errors import ApiError, not_wired
from campuspulse_ai.frameworks.routes.deps import Services

router = APIRouter()

CSV_MEDIA_TYPE = "text/csv"


@router.api_route(**route_kwargs("batch"), response_class=Response)
def batch(
    file: Annotated[UploadFile, File(description="CSV with columns request_id,text (UTF-8).")],
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("batch"))],
    use_llm: Annotated[bool, Form()] = False,
) -> Response:
    """Label an uploaded CSV with the same bytes as `predict.py`. The upload is capped at
    `BATCH_MAX_BYTES` (422 above it); rows are capped by the use case (`BATCH_MAX_ROWS`)."""
    if services.batch is None:
        raise not_wired("batch predictions")
    settings: Settings = request.app.state.settings
    data = file.file.read(settings.batch_max_bytes + 1)
    if len(data) > settings.batch_max_bytes:
        raise ApiError(
            ErrorCode.INVALID_INPUT,
            f"The file is larger than {settings.batch_max_bytes} bytes.",
            {"max_bytes": settings.batch_max_bytes},
        )
    return Response(content=services.batch.run(data, use_llm=use_llm), media_type=CSV_MEDIA_TYPE)


@router.api_route(**route_kwargs("metrics"))
def metrics(
    request: Request,
    services: Services,
    caller: Annotated[Principal, Depends(authorize("metrics"))],
) -> MetricsResponse:
    """Offline report sections plus live router and memory stats (admin)."""
    if services.metrics is None:
        raise not_wired("metrics")
    return services.metrics.run()
