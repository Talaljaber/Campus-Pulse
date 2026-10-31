"""Route metadata for every `/v1` endpoint: one registry shared by the mock app and the real app.

`route_kwargs(op_id)` returns the keyword arguments for `APIRouter.api_route`, so the mock app
(P0.13) and the real FastAPI app (P3.12+) declare identical paths, response models, status codes,
error responses and OpenAPI extensions. The extensions carry the documentation that is not in the
schema itself and are read by `scripts/gen_api_docs.py`:

- `x-roles`: roles allowed (`student`, `staff`, `admin`, `service`; `public` = no auth at all);
- `x-auth`: `service_token`, `hmac` or `none`;
- `x-side-effects`: rows written, tickets, emails;
- `x-optional`: true for B-list extras that may answer 501 `not_implemented` when cut.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi.security import HTTPBearer

from campuspulse_ai.application.dto import (
    ERROR_HTTP_STATUS,
    CounterfactualResponse,
    ErrorCode,
    ErrorResponse,
    FeedbackResponse,
    HealthResponse,
    IncidentOut,
    MetricsResponse,
    ProblemClusterOut,
    ReindexResponse,
    ResolveIncidentResponse,
    ScorecardOut,
    SimulateResponse,
    TicketOut,
    TriageResponse,
    WebhookAck,
)

API_TITLE = "CampusPulse AI API"
API_DESCRIPTION = (
    "Bilingual (EN / Jordanian Arabic / Arabizi) campus-request triage. Called only by the Next.js "
    "server with the service token; see docs/api/README.md."
)
"""OpenAPI `info` of both apps (the version is `campuspulse_ai.__version__`)."""

SERVICE_TOKEN_SCHEME = HTTPBearer(
    auto_error=False,
    scheme_name="ServiceToken",
    description="`Authorization: Bearer <AI_SERVICE_TOKEN>`, sent only by the Next.js server.",
)
"""The one security scheme. Both apps use this instance so `openapi.json` is identical."""

Method = Literal["GET", "POST"]
Auth = Literal["service_token", "hmac", "none"]

_COMMON_ERRORS: tuple[ErrorCode, ...] = (
    ErrorCode.INVALID_INPUT,
    ErrorCode.UNAUTHENTICATED,
    ErrorCode.INTERNAL_ERROR,
)

_ERROR_DESCRIPTIONS: dict[ErrorCode, str] = {
    ErrorCode.INVALID_INPUT: "Body, query or path failed validation, or the use case raised InvalidInput.",
    ErrorCode.UNAUTHENTICATED: "Missing or wrong service token (or a bad webhook signature).",
    ErrorCode.FORBIDDEN: "The caller's role may not use this endpoint (or this office's resource).",
    ErrorCode.NOT_FOUND: "The referenced request, prediction, ticket or incident does not exist.",
    ErrorCode.CLARIFICATION_BUDGET_EXCEEDED: "No clarification question is pending for this request.",
    ErrorCode.NOT_IMPLEMENTED: "Optional extra that is not built in this deployment.",
    ErrorCode.ARTIFACT_UNAVAILABLE: "The frozen model artifact is missing or failed its checksum.",
    ErrorCode.STORE_UNAVAILABLE: "Supabase or the vector store is unreachable.",
    ErrorCode.INTERNAL_ERROR: "Unexpected failure; no stack trace is returned.",
}


@dataclass(frozen=True, slots=True)
class EndpointDoc:
    """Contract metadata of one endpoint (one HTTP method + path)."""

    op_id: str
    method: Method
    path: str
    summary: str
    purpose: str
    roles: tuple[str, ...]
    response_model: type[Any] | None
    errors: tuple[ErrorCode, ...]
    side_effects: tuple[str, ...]
    auth: Auth = "service_token"
    status_code: int = 200
    optional: bool = False
    tag: str = "triage"
    extra_openapi: dict[str, Any] = field(default_factory=dict)


ENDPOINTS: tuple[EndpointDoc, ...] = (
    EndpointDoc(
        op_id="triage",
        method="POST",
        path="/v1/triage",
        summary="Triage one request",
        purpose=(
            "Runs the main flow (SPEC §5.1) for one student message: normalize, guards, ensemble, "
            "conformal sets, decision policy, then either a clarifying question or a decision with "
            "explanation, understanding and action."
        ),
        roles=("student", "staff", "admin", "service"),
        response_model=TriageResponse,
        errors=(ErrorCode.INVALID_INPUT, ErrorCode.ARTIFACT_UNAVAILABLE, ErrorCode.STORE_UNAVAILABLE),
        side_effects=(
            "inserts `requests`, `predictions` and `events` rows; upserts the request embedding into "
            "the `requests` vector collection",
            "needs_clarification: inserts a `clarifications` row",
            "decided/human_review: opens a ticket (Supabase + Linear issue), may book an advisor slot, "
            "sends allow-listed email and in-app notifications (`outbox` rows), may create or attach "
            "to an incident",
            "human_review, out_of_scope, distress: inserts a `review_queue` row",
            "distress: no ticket, no email, no LLM call",
            "LLM tiers (if escalated) write `llm_calls` rows",
        ),
    ),
    EndpointDoc(
        op_id="clarify",
        method="POST",
        path="/v1/triage/{request_id}/clarify",
        summary="Answer a clarifying question",
        purpose=(
            "Applies the student's answer (an option chip or free text) to a request in "
            "`needs_clarification` and re-runs the core (LD-29). Returns the same shape as /v1/triage."
        ),
        roles=("student", "service"),
        response_model=TriageResponse,
        errors=(
            ErrorCode.INVALID_INPUT,
            ErrorCode.FORBIDDEN,
            ErrorCode.NOT_FOUND,
            ErrorCode.CLARIFICATION_BUDGET_EXCEEDED,
            ErrorCode.STORE_UNAVAILABLE,
        ),
        side_effects=(
            "updates the `clarifications` row (answer, answered_at)",
            "then the same side effects as /v1/triage for the new status",
        ),
    ),
    EndpointDoc(
        op_id="explain_counterfactual",
        method="GET",
        path="/v1/explain/{request_id}/counterfactual",
        summary="Live counterfactual",
        purpose="Re-classifies the request with one token removed, for the clickable words in the UI.",
        roles=("student", "staff", "admin"),
        response_model=CounterfactualResponse,
        errors=(ErrorCode.INVALID_INPUT, ErrorCode.FORBIDDEN, ErrorCode.NOT_FOUND),
        side_effects=("none (read-only; no rows written)",),
        tag="explain",
    ),
    EndpointDoc(
        op_id="feedback",
        method="POST",
        path="/v1/feedback",
        summary="Staff confirm or correct a prediction",
        purpose=(
            "Staff confirm or correct category/priority. The prediction becomes final (tier `human`), "
            "deferred actions fire, and the example enters live memory immediately (SPEC §5.3)."
        ),
        roles=("staff", "admin"),
        response_model=FeedbackResponse,
        errors=(
            ErrorCode.INVALID_INPUT,
            ErrorCode.FORBIDDEN,
            ErrorCode.NOT_FOUND,
            ErrorCode.STORE_UNAVAILABLE,
        ),
        side_effects=(
            "updates the prediction and its `review_queue` row; ticket `provisional` -> false",
            "inserts a `memory_examples` row (vector collection `memory`, active)",
            "fires deferred booking/alert actions (allow-listed email, `outbox` rows)",
            "appends an `events` row",
        ),
        tag="staff",
    ),
    EndpointDoc(
        op_id="ticket_status",
        method="POST",
        path="/v1/tickets/{ticket_id}/status",
        summary="Change a ticket's status from the dashboard",
        purpose="Dashboard status change (LD-25); same path as the inbound Linear sync.",
        roles=("staff", "admin"),
        response_model=TicketOut,
        errors=(
            ErrorCode.INVALID_INPUT,
            ErrorCode.FORBIDDEN,
            ErrorCode.NOT_FOUND,
            ErrorCode.STORE_UNAVAILABLE,
        ),
        side_effects=(
            "updates the `tickets` row; updates the Linear issue",
            "in-app notification to the student; email on `resolved` if allow-listed",
        ),
        tag="staff",
    ),
    EndpointDoc(
        op_id="list_incidents",
        method="GET",
        path="/v1/incidents",
        summary="List incidents",
        purpose="Pulse incidents, newest first; `?open=1` returns only open ones (LD-25).",
        roles=("staff", "admin", "service"),
        response_model=list[IncidentOut],
        errors=(ErrorCode.INVALID_INPUT, ErrorCode.FORBIDDEN, ErrorCode.STORE_UNAVAILABLE),
        side_effects=("none (read-only)",),
        tag="pulse",
    ),
    EndpointDoc(
        op_id="resolve_incident",
        method="POST",
        path="/v1/incidents/{incident_id}/resolve",
        summary="Resolve an incident and notify reporters",
        purpose="Closes the incident, its merged tickets and the Linear issue; notifies every reporter once.",
        roles=("staff", "admin"),
        response_model=ResolveIncidentResponse,
        errors=(
            ErrorCode.INVALID_INPUT,
            ErrorCode.FORBIDDEN,
            ErrorCode.NOT_FOUND,
            ErrorCode.STORE_UNAVAILABLE,
        ),
        side_effects=(
            "updates `incidents` and the member `tickets` rows (status resolved/closed)",
            "closes the Linear issue",
            "one broadcast per reporter (in-app; email if allow-listed) -> `outbox` rows",
        ),
        tag="pulse",
    ),
    EndpointDoc(
        op_id="insights_recurring",
        method="GET",
        path="/v1/insights/recurring",
        summary="Recurring problems",
        purpose=(
            "Clusters stored request embeddings by meaning, building and category and ranks them by "
            "size, so staff can fix root causes (UD-6, P4.21)."
        ),
        roles=("staff", "admin"),
        response_model=list[ProblemClusterOut],
        errors=(ErrorCode.INVALID_INPUT, ErrorCode.FORBIDDEN, ErrorCode.STORE_UNAVAILABLE),
        side_effects=("none (read-only)",),
        tag="staff",
    ),
    EndpointDoc(
        op_id="linear_webhook",
        method="POST",
        path="/v1/integrations/linear/webhook",
        summary="Inbound Linear status sync",
        purpose=(
            "Receives Linear issue updates. The raw body is verified with HMAC-SHA256 "
            "(`LINEAR_WEBHOOK_SECRET`) against the `Linear-Signature` header; no service token."
        ),
        roles=("public",),
        response_model=WebhookAck,
        errors=(ErrorCode.UNAUTHENTICATED, ErrorCode.INVALID_INPUT, ErrorCode.STORE_UNAVAILABLE),
        side_effects=(
            "updates the linked `tickets` row status",
            "in-app notification to the student",
        ),
        auth="hmac",
        tag="integrations",
        extra_openapi={
            "requestBody": {
                "required": True,
                "description": "Linear's webhook payload, verified byte-for-byte (not our schema).",
                "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}},
            }
        },
    ),
    EndpointDoc(
        op_id="batch",
        method="POST",
        path="/v1/batch",
        summary="Batch predictions from a CSV",
        purpose=(
            "Upload a CSV with `request_id,text`; returns `request_id,category,priority` with the same "
            "bytes as `predict.py` (tier 0 by default)."
        ),
        roles=("staff", "admin"),
        response_model=None,
        errors=(ErrorCode.INVALID_INPUT, ErrorCode.FORBIDDEN, ErrorCode.ARTIFACT_UNAVAILABLE),
        side_effects=("none (no rows written; LLM calls logged only with use_llm=true)",),
        tag="lab",
        extra_openapi={
            "responses": {
                "200": {
                    "description": "Predictions CSV (UTF-8, no BOM, LF).",
                    "content": {"text/csv": {"schema": {"type": "string"}}},
                }
            }
        },
    ),
    EndpointDoc(
        op_id="redteam_run",
        method="POST",
        path="/v1/redteam/run",
        summary="Run the red team",
        purpose="Generates tricky requests per style, runs them through the real pipeline, scores them.",
        roles=("admin",),
        response_model=ScorecardOut,
        errors=(ErrorCode.INVALID_INPUT, ErrorCode.FORBIDDEN, ErrorCode.ARTIFACT_UNAVAILABLE),
        side_effects=("inserts a `redteam_runs` row; no tickets, no notifications",),
        tag="lab",
    ),
    EndpointDoc(
        op_id="metrics",
        method="GET",
        path="/v1/metrics",
        summary="Model lab metrics",
        purpose="Benchmark, coverage, calibration, fairness, ablations, confusions, router/memory stats.",
        roles=("admin",),
        response_model=MetricsResponse,
        errors=(ErrorCode.FORBIDDEN, ErrorCode.STORE_UNAVAILABLE),
        side_effects=("none (read-only)",),
        tag="lab",
    ),
    EndpointDoc(
        op_id="health",
        method="GET",
        path="/v1/health",
        summary="Health",
        purpose="Liveness, version, artifact hash, enabled sinks and LLM tiers. Also served at `/health`.",
        roles=("public",),
        response_model=HealthResponse,
        errors=(ErrorCode.INTERNAL_ERROR,),
        side_effects=("none",),
        auth="none",
        tag="ops",
    ),
    EndpointDoc(
        op_id="health_root",
        method="GET",
        path="/health",
        summary="Health (root alias)",
        purpose="Same as `/v1/health`; Render's health check path.",
        roles=("public",),
        response_model=HealthResponse,
        errors=(ErrorCode.INTERNAL_ERROR,),
        side_effects=("none",),
        auth="none",
        tag="ops",
    ),
    EndpointDoc(
        op_id="admin_simulate",
        method="POST",
        path="/v1/admin/simulate",
        summary="Start simulated Pulse traffic (optional extra)",
        purpose="Starts the scripted burst of `scripts/simulate_pulse.py` from the server (P5.19, B-list).",
        roles=("admin",),
        response_model=SimulateResponse,
        errors=(ErrorCode.INVALID_INPUT, ErrorCode.FORBIDDEN, ErrorCode.NOT_IMPLEMENTED),
        side_effects=("posts each scenario line through /v1/triage with `simulated=true`",),
        status_code=202,
        optional=True,
        tag="admin",
    ),
    EndpointDoc(
        op_id="admin_reindex",
        method="POST",
        path="/v1/admin/reindex",
        summary="Re-embed a vector collection (optional extra)",
        purpose="Re-embeds the FAQ collection with the deployed encoder (P4.20, B-list).",
        roles=("admin",),
        response_model=ReindexResponse,
        errors=(
            ErrorCode.INVALID_INPUT,
            ErrorCode.FORBIDDEN,
            ErrorCode.NOT_IMPLEMENTED,
            ErrorCode.STORE_UNAVAILABLE,
        ),
        side_effects=("rewrites every `faq.embedding`",),
        optional=True,
        tag="admin",
    ),
)

ENDPOINTS_BY_ID: dict[str, EndpointDoc] = {e.op_id: e for e in ENDPOINTS}


def endpoint_errors(e: EndpointDoc) -> tuple[ErrorCode, ...]:
    """The endpoint's error codes plus the common ones (401 only when a credential is required)."""
    common = _COMMON_ERRORS if e.auth != "none" else (ErrorCode.INTERNAL_ERROR,)
    seen: dict[ErrorCode, None] = dict.fromkeys((*e.errors, *common))
    return tuple(seen)


def route_kwargs(op_id: str) -> dict[str, Any]:
    """Keyword arguments for `APIRouter.api_route(**route_kwargs(op_id))`."""
    e = ENDPOINTS_BY_ID[op_id]
    responses: dict[int | str, dict[str, Any]] = {}
    for code in endpoint_errors(e):
        status = ERROR_HTTP_STATUS[code]
        entry = responses.setdefault(status, {"model": ErrorResponse, "description": ""})
        line = f"`{code.value}`: {_ERROR_DESCRIPTIONS[code]}"
        entry["description"] = f"{entry['description']} {line}".strip()
    extra: dict[str, Any] = {
        "x-roles": list(e.roles),
        "x-auth": e.auth,
        "x-side-effects": list(e.side_effects),
        "x-optional": e.optional,
    }
    extra.update(e.extra_openapi)
    description = e.purpose + (
        " **Optional extra (B-list): may return 501 when not built.**" if e.optional else ""
    )
    return {
        "path": e.path,
        "methods": [e.method],
        "response_model": e.response_model,
        "status_code": e.status_code,
        "summary": e.summary,
        "description": description,
        "operation_id": e.op_id,
        "tags": [e.tag],
        "responses": responses,
        "openapi_extra": extra,
    }
