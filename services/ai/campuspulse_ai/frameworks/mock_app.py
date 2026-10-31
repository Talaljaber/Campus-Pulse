"""Mock `/v1` API that serves the contract fixtures (P0.13), so the UI can build before the backend exists.

Run: `uvicorn campuspulse_ai.frameworks.mock_app:app --port 8000` (from the venv).

Every route is declared with `api_contract.route_kwargs`, the same metadata the real app uses, so this
app's OpenAPI document *is* the contract (`export_openapi --mock`). Requests are validated against the
DTOs exactly as the real app will validate them; responses come from
`services/ai/tests/fixtures/api/*.json` (override the directory with `MOCK_FIXTURES_DIR`).

Fixture selection for a call, first hit wins:
1. header `X-Mock-Fixture: <fixture name>` (mock only; not part of the contract);
2. a fixture whose path params, query and request body match the call (`match` narrows the body keys
   compared; strings compare case- and whitespace-insensitively);
3. the endpoint's 2xx fixture flagged `default` (else its first 2xx fixture).

Auth is mimicked, not enforced for real: a service-token route without `Authorization: Bearer ...`
answers 401 (if `MOCK_SERVICE_TOKEN` is set, the token must equal it); `X-CP-Role` outside the
endpoint's roles answers 403; the Linear webhook answers 401 without a `Linear-Signature` header.
No network, no database, no secrets.
"""

from __future__ import annotations

import hmac
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials
from starlette.exceptions import HTTPException as StarletteHTTPException

from campuspulse_ai import __version__
from campuspulse_ai.application.dto import (
    ERROR_HTTP_STATUS,
    ClarifyRequest,
    CounterfactualQuery,
    ErrorBody,
    ErrorCode,
    ErrorResponse,
    FeedbackRequest,
    ForwardRequest,
    IncidentListQuery,
    PrincipalHeaders,
    RecurringQuery,
    RedTeamRunRequest,
    ReindexRequest,
    ResolveIncidentRequest,
    ReviewListQuery,
    SimulateRequest,
    TicketStatusRequest,
    TriageQuery,
    TriageRequest,
)
from campuspulse_ai.frameworks.api_contract import (
    API_DESCRIPTION,
    API_TITLE,
    ENDPOINTS,
    ENDPOINTS_BY_ID,
    SERVICE_TOKEN_SCHEME,
    EndpointDoc,
    route_kwargs,
)

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "api"
MOCK_FIXTURE_HEADER = "X-Mock-Fixture"


class MockError(Exception):
    """An error the mock answers with the standard error body."""

    def __init__(self, code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def error_response(code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    """The standard `{"error": {...}}` body with the HTTP status of `code`."""
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=ERROR_HTTP_STATUS[code], content=body.model_dump(mode="json"))


def load_fixtures(fixtures_dir: Path) -> list[dict[str, Any]]:
    """Read every `*.json` fixture in name order. Raises FileNotFoundError if the directory is missing."""
    if not fixtures_dir.is_dir():
        raise FileNotFoundError(f"fixtures directory not found: {fixtures_dir}")
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(fixtures_dir.glob("*.json"))]


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    return value


def _matches(
    fixture: Mapping[str, Any], path_params: Mapping[str, str], query: Mapping[str, str], body: Any
) -> bool:
    for key, expected in fixture.get("path_params", {}).items():
        if _norm(path_params.get(key)) != _norm(expected):
            return False
    for key, expected in fixture.get("query", {}).items():
        if _norm(query.get(key)) != _norm(str(expected)):
            return False
    request = fixture.get("request")
    if not isinstance(request, dict) or not isinstance(body, dict):
        return True
    keys = fixture.get("match", list(request))
    return all(_norm(body.get(k)) == _norm(request.get(k)) for k in keys)


class FixtureStore:
    """Fixtures grouped by endpoint, with the selection rules described in the module docstring."""

    def __init__(self, fixtures: list[dict[str, Any]]) -> None:
        self._by_name = {f["name"]: f for f in fixtures}
        self._by_endpoint: dict[str, list[dict[str, Any]]] = {e.op_id: [] for e in ENDPOINTS}
        for f in fixtures:
            for e in ENDPOINTS:
                if e.method == f["method"] and e.path in (f["path"], *f.get("alias_paths", [])):
                    self._by_endpoint[e.op_id].append(f)

    def for_endpoint(self, op_id: str) -> list[dict[str, Any]]:
        """All fixtures of one endpoint (by operation id)."""
        return list(self._by_endpoint[op_id])

    def pick(self, op_id: str, request: Request, body: Any) -> dict[str, Any]:
        """Select the fixture for this call. Raises MockError(not_found) if none fits."""
        candidates = self._by_endpoint[op_id]
        wanted = request.headers.get(MOCK_FIXTURE_HEADER)
        if wanted:
            chosen = self._by_name.get(wanted)
            if chosen is None or chosen not in candidates:
                raise MockError(ErrorCode.NOT_FOUND, f"No mock fixture {wanted!r} for {op_id}.")
            return chosen
        path_params = {k: str(v) for k, v in request.path_params.items()}
        query = dict(request.query_params)
        specific = [f for f in candidates if f.get("path_params") or f.get("query") or f.get("match")]
        for f in specific:
            if _matches(f, path_params, query, body):
                return f
        ok = [f for f in candidates if f["status_code"] < 400]
        defaults = [f for f in ok if f.get("default")]
        if defaults or ok:
            return (defaults or ok)[0]
        raise MockError(ErrorCode.NOT_FOUND, f"No mock fixture for {op_id}.")


def _respond(fixture: Mapping[str, Any]) -> Any:
    if fixture["status_code"] >= 400:
        return JSONResponse(status_code=fixture["status_code"], content=fixture["response"])
    return fixture["response"]


def _guard(op_id: str) -> Callable[..., None]:
    """Dependency for service-token routes: 401 without a bearer token, 403 for a role not allowed."""
    endpoint: EndpointDoc = ENDPOINTS_BY_ID[op_id]

    def check(
        principal: Annotated[PrincipalHeaders, Header()],
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(SERVICE_TOKEN_SCHEME)],
    ) -> None:
        expected = os.environ.get("MOCK_SERVICE_TOKEN")
        if credentials is None or (
            expected is not None and not hmac.compare_digest(credentials.credentials, expected)
        ):
            raise MockError(ErrorCode.UNAUTHENTICATED, "Missing or invalid service token.")
        role = principal.x_cp_role
        if role is not None and role not in endpoint.roles:
            raise MockError(ErrorCode.FORBIDDEN, "This role may not use this endpoint.", {"role": role})

    return check


def build_router(store: FixtureStore) -> APIRouter:
    """Every contract route, answered from `store`."""
    router = APIRouter()

    @router.api_route(**route_kwargs("triage"), dependencies=[Depends(_guard("triage"))])
    def triage(body: TriageRequest, query: Annotated[TriageQuery, Query()], request: Request) -> Any:
        """Triage one request (fixture-backed)."""
        return _respond(store.pick("triage", request, body.model_dump(mode="json")))

    @router.api_route(**route_kwargs("clarify"), dependencies=[Depends(_guard("clarify"))])
    def clarify(request_id: str, body: ClarifyRequest, request: Request) -> Any:
        """Answer a clarifying question (fixture-backed)."""
        return _respond(store.pick("clarify", request, body.model_dump(mode="json")))

    @router.api_route(
        **route_kwargs("explain_counterfactual"), dependencies=[Depends(_guard("explain_counterfactual"))]
    )
    def explain_counterfactual(
        request_id: str, query: Annotated[CounterfactualQuery, Query()], request: Request
    ) -> Any:
        """Live counterfactual (fixture-backed)."""
        return _respond(store.pick("explain_counterfactual", request, None))

    @router.api_route(**route_kwargs("feedback"), dependencies=[Depends(_guard("feedback"))])
    def feedback(body: FeedbackRequest, request: Request) -> Any:
        """Staff confirm or correct (fixture-backed)."""
        return _respond(store.pick("feedback", request, body.model_dump(mode="json")))

    @router.api_route(**route_kwargs("ticket_status"), dependencies=[Depends(_guard("ticket_status"))])
    def ticket_status(ticket_id: str, body: TicketStatusRequest, request: Request) -> Any:
        """Dashboard ticket status change (fixture-backed)."""
        return _respond(store.pick("ticket_status", request, body.model_dump(mode="json")))

    @router.api_route(**route_kwargs("ticket_forward"), dependencies=[Depends(_guard("ticket_forward"))])
    def ticket_forward(ticket_id: str, body: ForwardRequest, request: Request) -> Any:
        """Forward a ticket to another office (fixture-backed)."""
        return _respond(store.pick("ticket_forward", request, body.model_dump(mode="json")))

    @router.api_route(**route_kwargs("list_reviews"), dependencies=[Depends(_guard("list_reviews"))])
    def list_reviews(query: Annotated[ReviewListQuery, Query()], request: Request) -> Any:
        """Review items for the caller (fixture-backed)."""
        return _respond(store.pick("list_reviews", request, None))

    @router.api_route(**route_kwargs("review_forward"), dependencies=[Depends(_guard("review_forward"))])
    def review_forward(review_id: str, body: ForwardRequest, request: Request) -> Any:
        """Forward a review item to an office (fixture-backed)."""
        return _respond(store.pick("review_forward", request, body.model_dump(mode="json")))

    @router.api_route(**route_kwargs("list_incidents"), dependencies=[Depends(_guard("list_incidents"))])
    def list_incidents(query: Annotated[IncidentListQuery, Query()], request: Request) -> Any:
        """List incidents (fixture-backed)."""
        return _respond(store.pick("list_incidents", request, None))

    @router.api_route(**route_kwargs("resolve_incident"), dependencies=[Depends(_guard("resolve_incident"))])
    def resolve_incident(incident_id: str, body: ResolveIncidentRequest, request: Request) -> Any:
        """Resolve an incident (fixture-backed)."""
        return _respond(store.pick("resolve_incident", request, body.model_dump(mode="json")))

    @router.api_route(
        **route_kwargs("insights_recurring"), dependencies=[Depends(_guard("insights_recurring"))]
    )
    def insights_recurring(query: Annotated[RecurringQuery, Query()], request: Request) -> Any:
        """Recurring problems (fixture-backed)."""
        return _respond(store.pick("insights_recurring", request, None))

    @router.api_route(**route_kwargs("linear_webhook"))
    async def linear_webhook(
        request: Request,
        linear_signature: Annotated[str | None, Header(alias="Linear-Signature")] = None,
    ) -> Any:
        """Inbound Linear sync. The mock only checks that a signature header is present."""
        raw = await request.body()
        if not linear_signature:
            raise MockError(ErrorCode.UNAUTHENTICATED, "Invalid webhook signature.")
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError as exc:
            raise MockError(ErrorCode.INVALID_INPUT, "Body is not JSON.") from exc
        return _respond(store.pick("linear_webhook", request, payload))

    @router.api_route(
        **route_kwargs("batch"), response_class=Response, dependencies=[Depends(_guard("batch"))]
    )
    def batch(
        file: Annotated[UploadFile, File(description="CSV with columns request_id,text (UTF-8).")],
        request: Request,
        use_llm: Annotated[bool, Form()] = False,
    ) -> Response:
        """Batch predictions (fixture-backed CSV)."""
        fixture = store.pick("batch", request, None)
        if fixture["status_code"] >= 400:
            return JSONResponse(status_code=fixture["status_code"], content=fixture["response"])
        return Response(content=fixture["response"], media_type="text/csv")

    @router.api_route(**route_kwargs("redteam_run"), dependencies=[Depends(_guard("redteam_run"))])
    def redteam_run(body: RedTeamRunRequest, request: Request) -> Any:
        """Red-team run (fixture-backed)."""
        return _respond(store.pick("redteam_run", request, body.model_dump(mode="json")))

    @router.api_route(**route_kwargs("metrics"), dependencies=[Depends(_guard("metrics"))])
    def metrics(request: Request) -> Any:
        """Model-lab metrics (fixture-backed)."""
        return _respond(store.pick("metrics", request, None))

    @router.api_route(**route_kwargs("health"))
    def health(request: Request) -> Any:
        """Health (fixture-backed)."""
        return _respond(store.pick("health", request, None))

    @router.api_route(**route_kwargs("health_root"))
    def health_root(request: Request) -> Any:
        """Health at the root path (Render health check)."""
        return _respond(store.pick("health_root", request, None))

    @router.api_route(**route_kwargs("admin_simulate"), dependencies=[Depends(_guard("admin_simulate"))])
    def admin_simulate(body: SimulateRequest, request: Request) -> Any:
        """Optional extra: simulated traffic (fixture-backed)."""
        return _respond(store.pick("admin_simulate", request, body.model_dump(mode="json")))

    @router.api_route(**route_kwargs("admin_reindex"), dependencies=[Depends(_guard("admin_reindex"))])
    def admin_reindex(body: ReindexRequest, request: Request) -> Any:
        """Optional extra: re-embed a collection (fixture-backed)."""
        return _respond(store.pick("admin_reindex", request, body.model_dump(mode="json")))

    return router


def create_mock_app(fixtures_dir: Path | None = None) -> FastAPI:
    """Build the mock app over `fixtures_dir` (default: `MOCK_FIXTURES_DIR` env, else the repo fixtures)."""
    directory = fixtures_dir or Path(os.environ.get("MOCK_FIXTURES_DIR", DEFAULT_FIXTURES_DIR))
    fixtures = load_fixtures(directory)
    store = FixtureStore(fixtures)
    app = FastAPI(
        title=API_TITLE,
        version=__version__,
        description=API_DESCRIPTION,
        separate_input_output_schemas=False,
    )
    app.include_router(build_router(store))

    @app.exception_handler(MockError)
    async def _mock_error(_: Request, exc: MockError) -> JSONResponse:
        return error_response(exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return error_response(ErrorCode.INVALID_INPUT, "Request validation failed.", {"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.INVALID_INPUT
        body = ErrorResponse(error=ErrorBody(code=code, message=str(exc.detail), details=None))
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))

    @app.get("/mock/fixtures", include_in_schema=False)
    def list_fixtures() -> list[dict[str, Any]]:
        """Mock only: every fixture's name, endpoint, status and description."""
        return [
            {k: f.get(k) for k in ("name", "method", "path", "status_code", "description")} for f in fixtures
        ]

    return app


app = create_mock_app()
