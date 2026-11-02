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
    AnnouncementOut,
    ChatConfirmResponse,
    ChatTurnResponse,
    CounterfactualResponse,
    ErrorCode,
    ErrorResponse,
    FeedbackResponse,
    HealthResponse,
    IncidentOut,
    MetricsResponse,
    ProblemClusterOut,
    ProposalOut,
    ReindexResponse,
    ResolveIncidentResponse,
    ReviewItemOut,
    ScorecardOut,
    SimulateResponse,
    SlaScanOut,
    TicketOut,
    TicketThreadOut,
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
            "human_review, distress: inserts a `review_queue` row; human_review assigns it to the "
            "student's advisor (UD-13) or an office queue and notifies the reviewer in-app (and by "
            "allow-listed email)",
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
        purpose=(
            "Status change by staff of the ticket's office or an admin (never on their own request). "
            "Only the transitions of the lifecycle table are allowed (`transition <from> -> <to> not "
            "allowed`, 422): new -> in_progress, new/in_progress -> solved, new/in_progress/solved -> "
            "closed, solved/closed -> in_progress (reopen, the clock restarts). The optional note becomes "
            "a public comment inside the status email. Same status = no-op."
        ),
        roles=("staff", "admin"),
        response_model=TicketOut,
        errors=(
            ErrorCode.INVALID_INPUT,
            ErrorCode.FORBIDDEN,
            ErrorCode.NOT_FOUND,
            ErrorCode.STORE_UNAVAILABLE,
        ),
        side_effects=(
            "updates the `tickets` row (status, `awaiting_student`, clock on a reopen); inserts a "
            "`ticket_activity` row `status`; appends an `events` row `ticket.status`",
            "after the response: updates the Linear issue; in-app notification to the requester; one "
            "allow-listed email to the requester (`in_progress`, `solved`, `closed` or `reopened`)",
        ),
        tag="staff",
    ),
    EndpointDoc(
        op_id="ticket_forward",
        method="POST",
        path="/v1/tickets/{ticket_id}/forward",
        summary="Forward a ticket to another office",
        purpose=(
            "Staff hand a ticket to another office (UD-13): the ticket takes that office and its "
            "category, goes back to `new`, keeps its priority, its SLA clock restarts, and the Linear "
            "issue is updated. Only `new` and `in_progress` tickets can be forwarded."
        ),
        roles=("staff", "admin"),
        response_model=TicketOut,
        errors=(
            ErrorCode.INVALID_INPUT,
            ErrorCode.FORBIDDEN,
            ErrorCode.NOT_FOUND,
            ErrorCode.STORE_UNAVAILABLE,
        ),
        side_effects=(
            "updates the `tickets` row (office, category, status `new`, tag `forwarded`, clock); inserts a "
            "`ticket_activity` row `forward` and a `ticket_hints` row; appends an `events` row "
            "`ticket.forwarded`",
            "after the response: updates the Linear issue (label, title, description); one in-app "
            "`ticket_forwarded` notification for `office:<new office>`; allow-listed emails to the "
            "requester and the new office (`forwarded`)",
            "no prediction change and no live-memory write",
        ),
        tag="staff",
    ),
    EndpointDoc(
        op_id="list_reviews",
        method="GET",
        path="/v1/reviews",
        summary="Review items for the caller",
        purpose=(
            "The unsure requests the caller may resolve (UD-13): an advisor gets their students' items "
            "and the unassigned items of their office; other staff their office's unassigned items; "
            "admins everything. Newest first."
        ),
        roles=("staff", "admin"),
        response_model=list[ReviewItemOut],
        errors=(ErrorCode.INVALID_INPUT, ErrorCode.FORBIDDEN, ErrorCode.STORE_UNAVAILABLE),
        side_effects=("none (read-only)",),
        tag="staff",
    ),
    EndpointDoc(
        op_id="review_forward",
        method="POST",
        path="/v1/reviews/{review_id}/forward",
        summary="Resolve a review by forwarding it to an office",
        purpose=(
            "The reviewer (the assigned advisor, staff of the item's office, or an admin) sends an "
            "unsure request to an office. The office's category becomes the final label, the "
            "correction enters live memory, and the ticket is finalized or opened for that office "
            "(UD-13). Forwarding to the predicted office is a confirmation. Confirming with a "
            "priority change stays `POST /v1/feedback`."
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
            "as `POST /v1/feedback`: updates the prediction and resolves the `review_queue` row; inserts "
            "a `memory_examples` row; finalizes the ticket (office re-routed, Linear updated, deferred "
            "booking/alert fire) or opens one",
            "one in-app `ticket_forwarded` notification for `office:<office>` when the office changed",
            "appends `events` rows `feedback.confirmed`/`feedback.corrected` and `review.forwarded`",
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
        errors=(
            ErrorCode.INVALID_INPUT,
            ErrorCode.FORBIDDEN,
            ErrorCode.ARTIFACT_UNAVAILABLE,
            ErrorCode.STORE_UNAVAILABLE,
        ),
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
    EndpointDoc(
        op_id="ticket_comment",
        method="POST",
        path="/v1/tickets/{ticket_id}/comments",
        summary="Comment on a ticket",
        purpose=(
            "The requester adds a public comment (a comment on a solved or closed ticket reopens it). "
            "Staff of the ticket's office or an admin reply publicly (the ticket moves to in_progress and "
            "waits for the requester), add an `internal` note the requester never sees, or send a reply "
            "that also sets `status` (one status email carries the comment). A caller who owns the "
            "request is always treated as the requester."
        ),
        roles=("student", "staff", "admin"),
        response_model=TicketThreadOut,
        errors=(
            ErrorCode.INVALID_INPUT,
            ErrorCode.FORBIDDEN,
            ErrorCode.NOT_FOUND,
            ErrorCode.STORE_UNAVAILABLE,
        ),
        side_effects=(
            "updates the `tickets` row (status, `awaiting_student`, clock on a reopen); inserts a "
            "`ticket_activity` row (`comment`, `note` or `status`); appends an `events` row",
            "after the response: allow-listed email (`staff_reply` to the requester, `requester_reply` "
            "to the office and, on a forwarded ticket, the admin inbox, or the status/`reopened` email); "
            "in-app notification to the requester on a staff reply; none for an internal note",
        ),
        tag="staff",
    ),
    EndpointDoc(
        op_id="ticket_priority",
        method="POST",
        path="/v1/tickets/{ticket_id}/priority",
        summary="Change a ticket's priority",
        purpose=(
            "Staff of the ticket's office or an admin (never on their own request) change the priority of "
            "a `new` or `in_progress` ticket. The SLA clock restarts with the new priority's period. Same "
            "priority = no-op. No email."
        ),
        roles=("staff", "admin"),
        response_model=TicketOut,
        errors=(
            ErrorCode.INVALID_INPUT,
            ErrorCode.FORBIDDEN,
            ErrorCode.NOT_FOUND,
            ErrorCode.STORE_UNAVAILABLE,
        ),
        side_effects=(
            "updates the `tickets` row (priority, clock); inserts a `ticket_activity` row `priority` and a "
            "`ticket_hints` row; appends an `events` row `ticket.priority`",
            "after the response: updates the Linear issue",
        ),
        tag="staff",
    ),
    EndpointDoc(
        op_id="ticket_student_action",
        method="POST",
        path="/v1/tickets/{ticket_id}/student-action",
        summary="Requester buttons: solved, close, keep open",
        purpose=(
            "The requester confirms the fix (`solved`), closes the ticket (`close`) or asks to keep it "
            "open (`keep_open`: back to in_progress, the clock restarts). Only the owner of the request "
            "may call it."
        ),
        roles=("student", "staff", "admin"),
        response_model=TicketOut,
        errors=(
            ErrorCode.INVALID_INPUT,
            ErrorCode.FORBIDDEN,
            ErrorCode.NOT_FOUND,
            ErrorCode.STORE_UNAVAILABLE,
        ),
        side_effects=(
            "updates the `tickets` row (status, `awaiting_student`, clock on keep open); inserts a "
            "`ticket_activity` row `student_action`; appends an `events` row `ticket.student_action`",
            "after the response: updates the Linear issue; allow-listed email to the office "
            "(`solved`, `closed` or `reopened`)",
        ),
        tag="staff",
    ),
    # --- P9.5 announcements (append new entries below this line) ---
    EndpointDoc(
        op_id="announcement_create",
        method="POST",
        path="/v1/announcements",
        summary="Post an announcement",
        purpose=(
            "Staff post a notice for their own office, admins for any office or campus-wide "
            "(`office` null). Students read live announcements on Home (Supabase read under RLS)."
        ),
        roles=("staff", "admin"),
        response_model=AnnouncementOut,
        errors=(ErrorCode.INVALID_INPUT, ErrorCode.FORBIDDEN, ErrorCode.STORE_UNAVAILABLE),
        side_effects=("inserts an `announcements` row (realtime to open Home pages)",),
        tag="staff",
    ),
    EndpointDoc(
        op_id="announcement_archive",
        method="POST",
        path="/v1/announcements/{announcement_id}/archive",
        summary="Archive an announcement",
        purpose="Staff of the announcement's office, or an admin, take it off Home (sets `archived_at`).",
        roles=("staff", "admin"),
        response_model=AnnouncementOut,
        errors=(ErrorCode.FORBIDDEN, ErrorCode.NOT_FOUND, ErrorCode.STORE_UNAVAILABLE),
        side_effects=("sets `announcements.archived_at`",),
        tag="staff",
    ),
    EndpointDoc(
        op_id="cron_sla",
        method="POST",
        path="/v1/cron/sla",
        summary="Run the SLA reminder scan",
        purpose=(
            "Scans the overdue `new` and `in_progress` tickets and sends at most two reminders per clock "
            "period (level 1 when overdue, level 2 one SLA period later, also to the admin inbox). Called "
            "every 10 minutes by `.github/workflows/sla-ping.yml`; the request also wakes a sleeping "
            "service. Safe to repeat: a reminder level is claimed once."
        ),
        roles=("service",),
        response_model=SlaScanOut,
        errors=(ErrorCode.FORBIDDEN, ErrorCode.NOT_IMPLEMENTED),
        side_effects=(
            "per reminded ticket: updates `reminder_count` and `reminder_sent_at`; inserts an internal "
            "`ticket_activity` row `reminder`, a `notifications` row for the office and an `events` row "
            "`sla.reminder`; allow-listed email to the office (level 2: and the admin inbox)",
        ),
        tag="staff",
    ),
    # --- P9.8 chat agent (append new entries below this line) ---
    EndpointDoc(
        op_id="chat_turn",
        method="POST",
        path="/v1/chat/turn",
        summary="One chat turn",
        purpose=(
            "The chat agent's next message for a conversation (1..20 messages, the last from the user). The "
            "language model only talks: it never decides category, priority, office or flags (the classifier "
            "does, on the requester's own words). A request becomes a proposal with a server-signed token; a "
            "ticket is created only when the user confirms it with that token. Distress is handled "
            "first with no LLM call. `mode: fallback` = no language model (no key, disabled or failing): "
            "the client shows the plain form and uses preview and confirm."
        ),
        roles=("student", "staff", "admin"),
        response_model=ChatTurnResponse,
        errors=(ErrorCode.INVALID_INPUT, ErrorCode.ARTIFACT_UNAVAILABLE, ErrorCode.STORE_UNAVAILABLE),
        side_effects=(
            "calls the language model through OpenRouter (pinned model, temperature 0, cached) unless in "
            "fallback mode",
            "a proposal writes nothing",
            "a confirmed proposal inserts `requests`, `predictions` and `events` rows, opens a ticket (as "
            "`POST /v1/chat/confirm`), and after the response writes the thread's `created` row and "
            "sends the allow-listed `received` emails",
            "distress: runs the full triage (`requests`, `predictions`, `review_queue` rows), no ticket, "
            "no LLM call",
        ),
        tag="chat",
    ),
    EndpointDoc(
        op_id="chat_preview",
        method="POST",
        path="/v1/chat/preview",
        summary="Preview a request (plain form)",
        purpose=(
            "No language model: classifies the text with the offline model, applies the decision policy "
            "with a one-question budget, and returns what would be recorded (department, priority, FAQ "
            "answer, a past staff correction if one is similar) with a signed token to confirm. When "
            "`question` is set, answer it by calling again with `asked` and `answer`. Used by the "
            "plain-form fallback and the Why this? view."
        ),
        roles=("student", "staff", "admin"),
        response_model=ProposalOut,
        errors=(ErrorCode.INVALID_INPUT, ErrorCode.ARTIFACT_UNAVAILABLE, ErrorCode.STORE_UNAVAILABLE),
        side_effects=(
            "writes nothing, except that a distress message is triaged and persisted (`requests`, "
            "`predictions`, `review_queue` rows) and answered through `question`",
        ),
        tag="chat",
    ),
    EndpointDoc(
        op_id="chat_confirm",
        method="POST",
        path="/v1/chat/confirm",
        summary="Confirm a proposal",
        purpose=(
            "Records the request of a proposal the caller received: the token must be signed by the server, "
            "unexpired and bound to the caller's alias (else 422). Runs the triage with the clarification "
            "budget at 0 (a FAQ cell opens a ticket instead of answering) and applies a similar past "
            "staff correction as a recorded re-route."
        ),
        roles=("student", "staff", "admin"),
        response_model=ChatConfirmResponse,
        errors=(ErrorCode.INVALID_INPUT, ErrorCode.ARTIFACT_UNAVAILABLE, ErrorCode.STORE_UNAVAILABLE),
        side_effects=(
            "inserts `requests`, `predictions` and `events` rows; opens a ticket (Supabase + Linear "
            "issue), may create or attach to an incident",
            "a hint re-route inserts a `ticket_activity` row `forward` (actor system, body `past "
            "correction`) and updates the Linear issue",
            "after the response: the thread's `created` row and the allow-listed `received` emails",
        ),
        tag="chat",
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
