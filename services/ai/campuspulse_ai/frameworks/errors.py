"""Error mapping at the HTTP boundary (P3.12): every non-2xx answer is `dto.ErrorResponse`.

| Raised | HTTP / `code` | `message` |
| --- | --- | --- |
| `ApiError(code, ...)` (auth, role, unwired component) | `ERROR_HTTP_STATUS[code]` | as given |
| `InvalidInput` / `NotFound` | 422 / 404 | the domain message |
| `Unauthorized` / `ClarificationBudgetExceeded` | 403 / 409 | the domain message |
| `ArtifactError` | 503 `artifact_unavailable` | fixed text; details only in the log |
| `StoreError` | 503 `store_unavailable` | fixed text; details only in the log |
| request validation (body, query, path, headers) | 422 `invalid_input` | `details.errors` |
| unknown route / method | 404 `not_found` / 405 `invalid_input` | Starlette's text |
| anything else | 500 `internal_error` | fixed text; `details.request_id` = the log ref |

`details.errors` is `[{loc, msg, type}]`. The 503 and 500 bodies carry `details.request_id`, the
reference printed in the server log line.

Stack traces are never returned.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from campuspulse_ai.application.dto import (
    ERROR_HTTP_STATUS,
    ErrorBody,
    ErrorCode,
    ErrorResponse,
    error_code_for,
)
from campuspulse_ai.domain.errors import CampusPulseError

log = logging.getLogger(__name__)

_FIXED_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.ARTIFACT_UNAVAILABLE: "The model artifact is unavailable.",
    ErrorCode.STORE_UNAVAILABLE: "Supabase or the vector store is unreachable.",
    ErrorCode.INTERNAL_ERROR: "Unexpected server error.",
}
"""Codes whose domain message may carry internals (SQL, paths): a fixed text is returned instead."""


class ApiError(Exception):
    """An error the routes raise directly (no domain equivalent): 401, 403 on a role, 501."""

    def __init__(self, code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def error_response(code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    """The standard `{"error": {code, message, details}}` body with the HTTP status of `code`."""
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=ERROR_HTTP_STATUS[code], content=body.model_dump(mode="json"))


def not_wired(component: str) -> ApiError:
    """501 for a route whose use case is not wired into this deployment (yet)."""
    return ApiError(
        ErrorCode.NOT_IMPLEMENTED,
        f"{component} is not available in this deployment.",
        {"component": component},
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register the mapping above on `app`."""

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.code, exc.message, exc.details)

    @app.exception_handler(CampusPulseError)
    async def _domain_error(request: Request, exc: CampusPulseError) -> JSONResponse:
        code = error_code_for(exc)
        if code in _FIXED_MESSAGES:
            ref = str(uuid.uuid4())
            log.error("%s %s -> %s (ref %s): %r", request.method, request.url.path, code, ref, exc)
            return error_response(code, _FIXED_MESSAGES[code], {"request_id": ref})
        return error_response(code, str(exc) or code.value, None)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return error_response(ErrorCode.INVALID_INPUT, "Request validation failed.", {"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.INVALID_INPUT
        body = ErrorResponse(error=ErrorBody(code=code, message=str(exc.detail), details=None))
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        ref = str(uuid.uuid4())
        log.exception("unhandled error on %s %s (ref %s)", request.method, request.url.path, ref)
        code = ErrorCode.INTERNAL_ERROR
        return error_response(code, _FIXED_MESSAGES[code], {"request_id": ref})
