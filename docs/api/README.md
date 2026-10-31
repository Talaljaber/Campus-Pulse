# CampusPulse AI API (`/v1`)

The HTTP contract of the FastAPI AI service. It was frozen at P0.13 and is owned by the Backend stream; the DTOs in `application/dto.py` are lead-owned.

- **Per-endpoint reference:** [endpoints.md](endpoints.md). It is generated and lists every endpoint with its request schema, a `curl.exe` example, a full example response, error codes and side effects.
- **Machine-readable contract:** [`services/ai/openapi.json`](../../services/ai/openapi.json) (OpenAPI 3.1). The UI generates its TypeScript types from this file.
- **Source of truth:**
  - `services/ai/campuspulse_ai/application/dto.py`: the Pydantic v2 models.
  - `services/ai/campuspulse_ai/frameworks/api_contract.py`: roles, auth, error codes and side effects per route.
  - `services/ai/tests/fixtures/api/*.json`: one example per file.

## Base URLs

| Environment | Base URL | How to run |
| --- | --- | --- |
| Local mock (fixtures, no models) | `http://localhost:8000` | `uvicorn campuspulse_ai.frameworks.mock_app:create_mock_app --factory --port 8000` |
| Local real service (from P3.12) | `http://localhost:8000` | `uvicorn api:app --app-dir services/ai --port 8000` (see [The real app](#real-app) for what is wired today) |
| Render | `https://<render-service>.onrender.com` | Deployed in P0.11 / P4.13. The real hostname is recorded in [docs/ops/README.md](../ops/README.md). |

Every route lives under `/v1`. The only exception is `GET /health`, the root alias of `GET /v1/health` that Render's health check uses. The browser never calls this service directly; it calls the Next.js route handler `/api/ai/...`, which forwards the request server-side (P5.6).

<a id="auth"></a>
## Auth

**Service token.**
- Every route except `/health`, `/v1/health` and the Linear webhook requires `Authorization: Bearer <AI_SERVICE_TOKEN>`.
- Only the Next.js server holds the token: Netlify runtime env, never in the browser bundle (LD-25).
- A missing or wrong token gets `401 unauthenticated`. The comparison is constant-time
  (`hmac.compare_digest`). If `AI_SERVICE_TOKEN` is not set on the server, **every** such route
  answers 401 (fail closed).
- The token is checked before anything else: a request without it never reaches validation, the role
  check or a use case.

**User identity and roles.**
- The Next.js server forwards the signed-in user's Supabase access token in `X-CP-User-JWT`.
- In production (`AUTH_MODE=supabase_jwt`, the default since P4.12), FastAPI verifies the JWT and reads `role`, `office` and `alias` from the `profiles` row.
- The role never comes from a client-controlled header.
- A role outside an endpoint's allowed roles gets `403 forbidden`. So does staff acting on another office's ticket or incident.

**`AUTH_MODE=supabase_jwt` in detail** (`adapters/integrations/supabase_auth.py`,
`frameworks/auth.py`):
1. `GET {SUPABASE_URL}/auth/v1/user` with the user token (and the service-role key as `apikey`)
   verifies it, so expired and signed-out sessions fail too.
2. `GET {SUPABASE_URL}/rest/v1/profiles?id=eq.<user id>&select=role,office,alias` with the service
   role reads the caller. `role` must be `student`, `staff` or `admin`.
3. The answer (also a negative one) is cached by the token's sha256 for `AUTH_CACHE_S` (60 s): one
   Supabase round trip per user per minute, and a revoked session keeps working for at most 60 s.

| Situation | Result |
| --- | --- |
| no `X-CP-User-JWT` | the caller is the `service` role (a script holding only the service token); `X-CP-Role/Alias/Office` are ignored |
| token rejected by Supabase Auth, no `profiles` row, or a role outside the three | `401 unauthenticated` "Invalid or expired user token." |
| Supabase unreachable, 5xx, or the profiles read refused (wrong service-role key) | `503 store_unavailable` |
| no verifier wired (no `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`) and a user token is sent | `503 store_unavailable` "User token verification is not configured." |

| Role | Who | Notes |
| --- | --- | --- |
| `student` | a signed-in student (alias only, e.g. `demo-17`) | gets the student view: staff-only flags removed |
| `staff` | office staff (`office` from `profiles`) | review queue, tickets and incidents of their office, insights |
| `admin` | administrators | everything, including `/metrics`, `/redteam/run`, `/admin/*` and `?debug=members` |
| `service` | the service token with no user JWT | scripts such as `simulate_pulse.py` |
| `public` | nobody needs a credential | `/health`, `/v1/health`. The Linear webhook is authenticated by its HMAC signature instead. |

**Trusted headers (tests, local dev and the mock only).**
- With `AUTH_MODE=trusted_headers`, the caller identity comes from `X-CP-Role`, `X-CP-Alias` and `X-CP-Office`.
  No `X-CP-Role` means the `service` role.
- These headers are ignored in production.

**What the identity changes** (`frameworks/auth.py`, `frameworks/routes/*`):

| Rule | Where |
| --- | --- |
| A caller with an alias (a student, or any user whose profile has one) triages under **their** alias; `student_alias` in the body is used only for the bare service token (scripts). | `POST /v1/triage` |
| A student may answer the questions of, and ask counterfactuals about, **their own** requests only (`403 forbidden` otherwise). Staff and admin may ask counterfactuals about any request. | `/clarify`, `/explain/.../counterfactual` |
| `?debug=members` is admin-only (`403` for anyone else). | `POST /v1/triage` |
| The reviewer of `/v1/feedback` is the caller; no body field names the reviewer. | `POST /v1/feedback` |
| Flags per role: students get `to_student_view` (no `urgency_unsupported`, no `priority_gaming_suspected`); staff get everything except `priority_gaming_suspected`; admin and the service token get every flag. | `/triage`, `/clarify` |

**Linear webhook.** `POST /v1/integrations/linear/webhook` carries no service token.
- The raw body is verified with HMAC-SHA256 (`LINEAR_WEBHOOK_SECRET`) against the `Linear-Signature` header.
- A bad signature gets `401 unauthenticated` and nothing is written.

## Conventions

- JSON keys are `snake_case`.
- Category and priority strings are exactly the domain labels:
  - categories: `Registration`, `IT Support`, `Finance`, `Transportation`, `Facilities`, `Academic Support`;
  - priorities: `low`, `medium`, `high`.
- Probabilities are floats in [0, 1].
- Timestamps are ISO 8601 with an offset. The service uses Asia/Amman (`+03:00`).
- **Every response key is always present.** Keys that do not apply are `null` (or `[]`), never omitted. Unknown request keys are rejected (`422`).
- Ids are UUID strings.
- Text is UTF-8. Arabic is returned as-is (no escaping).

## `/v1/triage` status values

`status` is one of five values. The table shows which keys are filled for each.

| `status` | Meaning | `category` / `priority` | `clarification` | `explanation` | `action` | `understanding` | `message` | `tier` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `decided` | Accepted, possibly after a clarification or an LLM tier. | final labels, singleton sets | `null` | filled (`null` + flag `explanation_failed` if the explainer failed) | filled | filled | usually `null` | `tier0` / `tier1` / `tier2` |
| `needs_clarification` | Ambiguous (a set of size 2) and the question budget is unused. The answer goes to `POST /v1/triage/{request_id}/clarify`. | provisional best guess plus the ambiguous sets | the question and its option chips | `null` | `null` | `null` | `null` | `tier0` |
| `human_review` | Still ambiguous after clarification and LLM tiers. Staff confirm it via `/v1/feedback`. | best guess | `null` | filled | provisional ticket (`provisional: true`, labelled unconfirmed); booking and alerts are deferred, except safety | filled | "A staff member will confirm this; we've opened it as {best guess}." | the last model tier |
| `out_of_scope` | Off-topic (OOD) or gibberish. | `null` | topic chips (`question_id: "topic"`, option ids = category values) | `null` | `null` | `null` | a rephrase prompt | `tier0` |
| `distress` | A distress or self-harm signal. No classification, no ticket, no email and no LLM; a human-review item is queued immediately. | `null` | `null` | `null` | `null` | `null` | supportive text, the counselling service (placeholder) and 911 | `human` |

The status machine is `received → (needs_clarification ⇄ clarified) → decided | human_review | out_of_scope | distress → actioned → (resolved | merged)` (SPEC §5.1 [14]). Only the five values above are ever returned by `/v1/triage`.

Other `/v1/triage` fields:
- **`understood_as`:** the Arabic transliteration shown for Arabizi input, e.g. "Understood as: …" (LD-25).
- **`understanding`:** the structured NLP output (UD-10). `source` is `llm` or `rules`. It never changes the labels.
- **`explanation.trace.policy_path`:** the DecisionPolicy rule that fired at each policy evaluation, in order.
  - Rule ids: `a_gibberish`, `b_ood`, `c_accept`, `d_ask`, `e_escalate`, `f_human`.
  - Examples: `["d_ask", "c_accept"]` means a question was asked, then the request was accepted. `["e_escalate", "f_human"]` means it went to tier 1 and then to human review.
- **`explanation.trace.per_model`:** filled only with `?debug=members` (admin). Keys are `<member>.<target>`, e.g. `m1.category`.

## Flags

`flags` is a list of strings from `domain.values.FLAGS`. Any other value is rejected by the DTOs.

| Flag | Meaning | Visible to |
| --- | --- | --- |
| `injection_attempt` | Prompt injection or manipulation was detected. The span was stripped before classification, the LLM tiers were skipped, and the request's own instructions can never raise the priority. | all |
| `urgency_unsupported` | Urgency was claimed (e.g. "URGENT", "عاجل") but the content does not support `high`. A neutral note that never changes the label. | staff, admin |
| `safety` | Physical danger (fire, a leak near electricity, people trapped). Priority is forced to `high`, and a safety alert fires immediately, even on provisional items. | all |
| `needs_review` | Sent to human review: the ticket is provisional, and booking and alerts wait for staff confirmation. | all |
| `distress` | Distress signal: no classification and no actions (see status `distress`). | all |
| `gibberish` | Empty, no letters, or fewer than 2 tokens: `out_of_scope`. | all |
| `out_of_scope` | Off-topic or out of distribution: `out_of_scope`. | all |
| `empty_set` | The conformal set was empty, so the argmax singleton was used. | all |
| `truncated` | The input was longer than `guards.max_tokens`; only the first tokens were classified. | all |
| `llm_out_of_set` | An LLM tier answered outside the allowed set. The answer was discarded and the next tier or tier 0 was used. | all |
| `staff_confirmed` | Staff confirmed or corrected the labels via `/v1/feedback` (tier `human`). | all |
| `priority_gaming_suspected` | This alias persistently claims urgency that the content does not support. There is no automatic penalty. | admin |
| `explanation_failed` | The explainer failed: `explanation` is `null`. Triage is unaffected. | all |
| `understanding_fallback` | The rule-based understanding was used (no key, an error, a schema violation, or an injection-flagged request). | all |
| `empty_input` | Debug-only in `predict.py --debug` (LD-17). **Never returned by the API.** | — |

`to_student_view()` in `dto.py` removes `urgency_unsupported` and `priority_gaming_suspected` for the student role.

## Errors

Every non-2xx response has the same body:

```json
{"error": {"code": "not_found", "message": "Incident not found.", "details": {"incident_id": "..."}}}
```

`details` is free-form JSON or `null`. For validation errors it is `{"errors": [{"loc": [...], "msg": "...", "type": "..."}]}`. It may carry the `request_id`. Stack traces are never returned.

| HTTP | `code` | Raised by |
| --- | --- | --- |
| 401 | `unauthenticated` | a missing or wrong service token; a bad webhook signature |
| 403 | `forbidden` | domain `Unauthorized`: the role or office is not allowed |
| 404 | `not_found` | domain `NotFound`: unknown request, prediction, ticket or incident |
| 409 | `clarification_budget_exceeded` | domain `ClarificationBudgetExceeded`: no question pending for this request (also a third answer) |
| 422 | `invalid_input` | body, query or path validation; domain `InvalidInput` (e.g. blank text, bad CSV columns, a clarify `question_id` that is not the pending question, blank `free_text`) |
| 500 | `internal_error` | anything unexpected |
| 501 | `not_implemented` | an optional extra (`/v1/admin/*`) that is not built in this deployment, or a route whose use case is not wired into this process yet (`details.component` names it; see [The real app](#real-app)) |
| 503 | `artifact_unavailable` | domain `ArtifactError`: the model artifact is missing or failed its checksum |
| 503 | `store_unavailable` | domain `StoreError`: Supabase or pgvector is unreachable |

The mapping lives in `dto.DOMAIN_ERROR_CODES` and `dto.error_code_for(exc)`, and the HTTP status per code in `dto.ERROR_HTTP_STATUS`. The handlers are in `frameworks/errors.py`:
- 4xx domain errors return the domain message (it names the request, option or question).
- 503 and 500 return a **fixed** message, because the underlying error may carry SQL, URLs or file
  paths. `details.request_id` is a reference that appears in the server log line with the real error.
- Unknown paths are `404 not_found`, a wrong method is `405 invalid_input`, both in the same shape.

These errors are degraded inside the use cases and never reach the client:
- `LLMUnavailable`: falls back to tier 0.
- `SinkError`: recorded in `ticket_links.last_error` (D-011); the next sink still runs.
- `NotificationError` and `RecipientNotAllowed`: recorded as outbox `failed` / `rejected`, with the reason in `outbox.error` (D-011).
- `CalendarUnavailable` (or no free slot, or a refused attendee): the ticket alone, `action.type: ticket`, "couldn't book" message.
- `StoreError` from the FAQ search: a ticket instead of an answer. From the Pulse step (embedding upsert, incident detection): skipped.
- Any explainer failure: `explanation: null` + flag `explanation_failed`.

<a id="clarification-llm-understanding"></a>
## Clarification, LLM tier and understanding

These three pieces decide what the student sees after the model has labelled a request (P3.2, P3.3, P3.3a). The trained ensemble always labels first (UD-5): the clarifier and the LLM tier only narrow its conformal sets, and the understander only describes the decided labels. The use cases that wire them into `/v1/triage` are P3.9 and P3.10.

### Clarifying question (`status: needs_clarification`)

When a set holds two labels and no question has been used, the response carries one question from `config/clarify_questions.yaml`.

- **Language.** `en` requests get English text; `ar` and `arabizi` requests get Jordanian Arabic in Arabic script.
- **Choice.** The question with the smallest expected set size after the answer wins. Category questions go before priority questions, ties follow the bank order, and a question is never asked twice. If no bank question splits the set (for example `{low, high}`), no question is asked and the policy moves on.
- **Answer.** `POST /v1/triage/{request_id}/clarify` with `option_id` (or `free_text`, which is appended to the request and re-classified). The answer becomes a constraint and the core is re-run with it (LD-29).
- **`not_sure`.** It applies nothing and allows one more question (at most two in total).
- **Errors.** An unknown request or `option_id` is `404 not_found`; a `question_id` that is not the
  pending question is `422 invalid_input`; no pending question (e.g. a third answer) is
  `409 clarification_budget_exceeded`; another student's request is `403 forbidden`.

| `question_id` | Splits | Asked when | Options (`id` → effect) |
| --- | --- | --- | --- |
| `cat:Registration\|IT Support` | category | the category set contains both | `registration` → Registration, `it` → IT Support, `not_sure` |
| `cat:Academic Support\|IT Support` | category | the category set contains both | `content` → Academic Support, `platform` → IT Support, `not_sure` |
| `cat:Finance\|Registration` | category | the category set contains both | `payment` → Finance, `registration` → Registration, `not_sure` |
| `cat:Facilities\|IT Support` | category | the category set contains both | `room_equipment` → Facilities, `computer_network` → IT Support, `not_sure` |
| `pri:deadline` | priority | `{medium, high}`; top category Registration, IT Support, Finance or Academic Support | `yes_today` → evidence `deadline_today`, `no_deadline` → medium, `not_sure` |
| `pri:safety` | priority | `{medium, high}`; top category Facilities or Transportation | `yes_danger` → evidence `safety_risk`, `no_danger` → medium, `not_sure` |
| `pri:low\|medium` | priority | `{low, medium}` | `broken_now` → medium, `information` → low, `not_sure` |

A category or priority effect fixes that set to one label. An evidence effect sets the feature and lets the priority head decide. The safety floor still wins over any answer (ARCHITECTURE §2.1 [9]).

### Topic chips (`status: out_of_scope`)

Off-topic or gibberish requests get `clarification.question_id: "topic"` with six chips whose ids are the category labels ("Which of these topics is closest?" / "أي موضوع من هدول أقرب لطلبك؟"). Answering one through the clarify route fixes the category to that label.

### LLM tier (`tier: tier1`)

- **When.** Only when the policy escalates: a set still has two or more labels after the question budget, `ENABLE_LLM=true`, `OPENROUTER_API_KEY` and `OPENROUTER_TIER1_MODEL` are set, and the request has no `injection_attempt` flag. Tier 2 is not wired (UD-3).
- **What it can do.** The model sees only the allowed labels, and the response schema's enums are exactly the current sets. An answer outside them is discarded and the flag `llm_out_of_set` is added. A valid answer is merged as one more ensemble member, `p' = (1 − w_llm)·p_S + w_llm·onehot` with `w_llm = 0.5`, and the sets are recomputed and never grow. The coverage guarantee holds for tier 0 only.
- **What the student sees.** `tier` becomes `tier1`. With `?debug=members` (admin), `explanation.trace.per_model` also holds `tier1.category` and `tier1.priority`.
- **Failures.** No key, a timeout, 5xx after two retries, 402/429 or a spent daily budget all leave the request at tier 0, then `human_review`. They never return an error to the client.
- **Pinned calls.** `temperature 0`, `top_p 1`, `seed 42`, `max_tokens 80`, prompt `config/prompts/oracle_v1.md`. The request text sent is the wrapper-stripped original plus the normalized text, cut at `guards.max_tokens`.

### Understanding (`understanding`)

Filled for `decided` and `human_review` responses (UD-10).

| Field | Content |
| --- | --- |
| `summary_en`, `summary_ar` | one sentence each, in English and in Jordanian Arabic |
| `entities` | `building`, `room`, `course_code`, `deadline` (ISO date: "today"/"اليوم" is today in Asia/Amman, "tomorrow"/"بكرا" the day after), `system` (e.g. `registration portal`, `e-learning`, `wifi`) |
| `student_reply` | in the request language (Arabic script for Arabic and Arabizi); it says only what the planned action really does |
| `ticket_title`, `ticket_body` | English text for staff (at most 80 and 1,200 characters) |
| `source` | `llm` (tier-1 model, `prompt_version: "v1"`) or `rules` (templates, `prompt_version: null`) |

- **It never changes the labels.** The model must echo the decided category and priority, and a reply with other labels is rejected.
- **Grounding.** A reply is rejected, and the rules are used instead, when it breaks the schema or a limit, replies in the wrong language, or names a course code, room or building that is not in the request.
- **`understanding_fallback`.** Set whenever `source` is `rules`: no key, an LLM error, a rejected reply, a spent budget, or an `injection_attempt` request (those never reach the model).
- **Pinned calls.** `temperature 0`, prompt `config/prompts/understand_v1.md`, cached per text, labels, action, location and date.

### Cost logging

Every LLM call (oracle and understander) is logged through the `CostLogger` port as an `LLMCall`.

| Field | Value |
| --- | --- |
| `tier`, `model` | `tier1` and the pinned model id from `OPENROUTER_TIER1_MODEL` |
| `prompt_hash` | the cache key: sha256 of the model id, prompt version, text and allowed sets (oracle) or decided labels (understander) |
| `tokens_in`, `tokens_out` | from OpenRouter `usage`; `0` on a failure |
| `cost.usd` | OpenRouter `usage.cost` when reported, else the pinned price table (`adapters/llm/cost.py`, Appendix B); `0` for cache hits and failures |
| `cached` | `true` for a cache hit (no HTTP call) |

- **Budget.** Before each network call, the day's total (Asia/Amman) is compared with `LLM_DAILY_BUDGET_USD` (default 5). At or above it, no call is made.
- **Failures are logged too**, with zero tokens and cost.
- **Where it shows.** `explanation.trace.cost_usd`, and `router` in `/v1/metrics`. Online, `SupabaseCostLogger` writes the `llm_calls` rows (P4); offline and in tests it is `InMemoryCostLogger`.
- **Caches.** `SqliteCache` (offline `--use-llm`) or `SupabaseCache` (online, P4) keep the raw validated reply under the same key. A second identical request makes no call.

<a id="actions-side-effects"></a>
## Actions and side effects (tickets, emails, bookings)

What `/v1/triage` (and `/v1/feedback` after a confirmation) *does* once the labels are decided.
`ActUseCase` (P4.8) implements this; the routes arrive in P3.12 and the webhook route in P4.9.
Integration details: [docs/integrations.md](../integrations.md). Use-case reference:
[Use cases](#use-cases).

### Routing (`action.type`, `action.tags`) — `config/actions.yaml`, UD-1

| Category | low | medium | high |
| --- | --- | --- | --- |
| Academic Support (`academic`) | `faq_answer` | `ticket` + `office-hours-queue` | `booking` + a ticket (the **only** booking cell) |
| Registration (`registrar`) | `faq_answer` | `ticket` | `ticket` + `same-day-escalation` (no booking) |
| IT Support (`it`) | `faq_answer` + `self-help` | `ticket` | `ticket` (+ `exam-in-progress` when the `exam_now` evidence fired) |
| Finance (`finance`) | `faq_answer` | `ticket` | `ticket` + `escalation` |
| Transportation (`transport`) | `faq_answer` + `timetable` | `ticket` | `ticket` + `transport-alert` (also alerts the transport office) |
| Facilities (`facilities`) | `ticket` | `ticket` | `safety_alert` + a ticket, tag `safety` |

- **Office** (in brackets) is the D-005 code written to `tickets.office`; staff see their office's tickets.
- **SLA:** `action.sla_due_at` = creation + 24 h (high), 72 h (medium), 336 h = 14 days (low).
- **Flag `safety`** (any category): `safety_alert` + ticket, priority high, fires immediately, even
  for `human_review`.
- **`human_review` (provisional):** a ticket only, `action.provisional: true`, tag `unconfirmed`;
  the cell's own action is kept as tag `deferred:<kind>` (e.g. `deferred:booking`) and runs only
  after staff confirm via `/v1/feedback`.
- **`faq_answer`:** answered from the FAQ when the best match ≥ `tau_faq` (`action.faq`, `action.message` =
  the retrieved answer, "Source: <url>" and `[demo]` for placeholder entries; no ticket), otherwise a
  ticket with "I'm not sure. I've opened a ticket so a person can answer." (`action.type: ticket`).
- **`booking`:** `action.booking` `{advisor_name, starts_at, ends_at, room: null}`; if no slot can be
  booked, `action.type` is `ticket` and the message says an advisor will contact the student.
- **`action.message`:** `understanding.student_reply` for tickets; the FAQ answer; the booking
  confirmation; for a safety alert always the safety instruction ("…call campus security now (demo) or
  911…"). Texts live in `config/templates/messages.yaml` (EN + Jordanian Arabic).

### Side effects

| Effect | When | Where it shows |
| --- | --- | --- |
| `tickets` row | every `ticket`, `booking`, `safety_alert` (and an unanswered FAQ) | `action.ticket_id`; staff dashboard (RLS by office) |
| Linear issue | each ticket, when `LINEAR_API_KEY` is set (team CDP, label = category, due date = SLA date) | `action.external[]` `{sink: "linear", external_id, url}`. A Linear failure never fails triage. |
| Ticket status from Linear | a signed `POST /v1/integrations/linear/webhook` that moves the issue's state forward | ticket status (+ `resolved_at`); the student gets an in-app `notifications` row; see [Ticket lifecycle](#ticket-lifecycle) |
| Ticket status from the dashboard | `POST /v1/tickets/{id}/status` by staff of the ticket's office or an admin | ticket status; the Linear issue state; the student's `notifications` row (with the staff note) |
| SLA escalation | the SLA scanner, every `SLA_SCAN_MINUTES` | priority bumped one level, status `escalated`, `escalated_at`; Linear priority; a `notifications` row for `office:<office>` |
| Advisor booking | Academic Support × high, not provisional | `action.booking`; the slot's `booked_by`; a `cases` row |
| Email | booking confirmation (to `DEMO_STUDENT_INBOX` + the advisor's demo inbox); safety and transport alerts (to `DEMO_OFFICE_INBOX`); resolution notice when a ticket becomes `resolved` (to `DEMO_STUDENT_INBOX`, P4.9) | `outbox` row (`sent` + `provider_id` = Message-ID, `rejected`/`failed` + `error`, or `deferred` + `error` over the daily cap) |
| In-app message | one per action with a ticket or booking: `understanding.student_reply` (D-006), kind `message` + an `outbox` row `in_app`; ticket status changes (P4.9), kind `ticket_status`, written directly (no outbox row) | `notifications` row for the alias (Realtime), payload below |
| Audit events | every triage outcome, action and status change | `events` (`triage.decided`, `triage.ask`, `triage.out_of_scope`, `triage.distress`, `act.ticket`, `act.booking`, `act.booking_refused`, `act.safety_alert`, `act.transport_alert`, `act.finalized`, `incident.new`/`incident.attach`, `ticket.status`, `sla.escalated`) |

### Allow-list behaviour (never contacting real people)

- Every email recipient and every booking attendee must be on `DEMO_EMAIL_ALLOWLIST`: an exact,
  case-insensitive match with no plus-address or subdomain wildcards. **An empty list rejects all.**
- A rejected email is **not sent**: an `outbox` row with `status: "rejected"` is written with the
  reason in `error` (and in the `events` audit log, `action: outbox.rejected`). A provider failure is an
  `outbox` row with `status: "failed"` and `error` (`events` `outbox.failed`). Neither changes the HTTP
  response: the triage still succeeds.
- A booking with a non-allow-listed attendee is refused before the slot is claimed.
- In-app messages go to an alias inside our database and are not checked, but are recorded in
  `outbox` the same way.

<a id="notifications-payload"></a>
### Notifications payload (`notifications` rows the student chat reads)

Students receive updates through Realtime on `notifications` (RLS: their alias), never through
`outbox`. Each row is `(alias, kind, payload jsonb)`. The chat (`noticeFromNotification`) prints
`{status, title}` as "Your ticket <title> is now <status>", prints `message` verbatim, and shows
"new update" for anything else. The backend keeps to those keys:

| `kind` | Written by | `payload` keys | Chat shows |
| --- | --- | --- | --- |
| `message` | `InAppNotifier` (every in-app `Notifier.send`; today: `ActUseCase` replies) | `ref` (uuid, also in `outbox.provider_id` as `inapp:<ref>`), `message` (the text), `subject`, `priority` (`low`/`medium`/`high` or null), `flags` (list) | `message` verbatim. There is **never** a `status` key. |
| `ticket_status` | `SyncTicketUseCase` (Linear webhook or dashboard status change, P4.9) to the student's alias; `EscalateSlaUseCase` to the office alias `office:<office>` | `ticket_id`, `status` (a `tickets.status` value), `title` (the ticket title, or "<category> request"), `message` (only when there is text: the staff note of a dashboard change; the escalation note for staff) | "Your ticket <title> is now <status>" |
| `incident` | incident broadcast (**P4.10**) | `incident_id`, `message` | `message` verbatim |

Free text always goes in `message`; only ticket-status updates carry `status`.

<a id="ticket-lifecycle"></a>
### Ticket lifecycle (P4.9): webhook, dashboard and SLA scanner

`open → in_progress → resolved → closed`, with `escalated` (SLA) and `merged` (incident) on the side
(ARCHITECTURE §2.2). Code: `use_cases/sync_ticket.py`, `use_cases/escalate_sla.py`,
`frameworks/routes/{integrations,tickets}.py`, `frameworks/background.py`.

**Linear webhook, `POST /v1/integrations/linear/webhook`** (no service token):
1. `LinearSink.handle_inbound` checks the HMAC of the raw body (`Linear-Signature`) and that
   `webhookTimestamp` is within ±60 s. A missing or bad signature, or a stale timestamp, is
   `401 unauthenticated` **before anything is read or written**. A signed body that is not a JSON
   object is `422`. If Linear is not configured (no `LINEAR_WEBHOOK_SECRET` sink), every delivery is 401.
2. Only an `Issue` `update` with `updatedFrom.stateId` is a state change; the Linear state type maps
   to a ticket status (docs/integrations.md §2).
3. The ticket is found by its `linear` link. The change is applied **only if it moves the ticket
   forward** in the order `open (0) < escalated (1) < in_progress (2) < resolved (3) < closed = merged (4)`.
   An equal or backward change is ignored. This is how our own pushes come back: closing a ticket on
   the dashboard sets the issue to Done, whose webhook says `resolved`, which is behind `closed`.
4. Applied: status saved, `resolved_at` set (on `resolved`/`closed`), an `events` row `ticket.status`
   (`{from, to, source: "linear", note}`); the response is
   `{"accepted": true, "ticket_id", "status"}`. Ignored (not a state change, an issue we never linked,
   or not forward): `{"accepted": false, "ticket_id": null, "status": null}` with 200, so Linear does
   not retry.
5. **After the response** (a background task, so Linear's 5 s budget only covers steps 1–4): the
   other sinks are updated (never Linear itself), the student gets a `ticket_status` notification, and
   on `resolved` an email goes to `DEMO_STUDENT_INBOX` through the allow-listed notifier. Failures
   there are logged and recorded (link `last_error`, outbox `failed`/`rejected`) and never retried.

**Dashboard, `POST /v1/tickets/{id}/status`** (staff, admin):
- Staff only for tickets of **their own office** (`office` from the profile; trusted headers in tests);
  admins for any ticket. Anyone else `403 forbidden`; unknown ticket `404`.
- Any direction is allowed (staff may reopen; reopening clears `resolved_at`); the same status is a
  no-op. The response is the saved `TicketOut` (links with a push error are omitted).
- After the response: Linear (and any other sink) gets the new status, the student gets a
  `ticket_status` notification with the staff `note` as `message`, and `resolved` emails the
  student's demo inbox.

**SLA scanner** (`EscalateSlaUseCase`, lifespan task `background.sla_loop`):
- Starts with the app (when `ApiServices.sla` and `clock` are wired and `SLA_SCAN_MINUTES > 0`), scans
  at once and then every `SLA_SCAN_MINUTES` (5) in a worker thread; cancelled on shutdown. One
  uvicorn worker means one scanner.
- Picks `open`/`in_progress` tickets whose `sla_due_at` has passed and that were **never escalated**
  (`escalated_at` null), so each ticket escalates exactly once, even if staff move it back to
  `in_progress`.
- Each: priority one level up (`high` stays `high`), status `escalated`, `escalated_at = now`; Linear
  gets the new priority (no state change); a `ticket_status` notification for the alias
  `office:<office>` with the message "SLA missed (due …): priority raised from X to Y."; an `events`
  row `sla.escalated`. A failed scan or save is logged and retried at the next scan.
- Staff can only read `office:<office>` notifications once the DB allows it (change request filed);
  the escalated ticket itself is visible on the dashboard through `tickets` Realtime.

### Anti-gaming flags (P3.6)

`GamingDetector` runs after the priority is final and only adds flags; it never changes a label.
- `urgency_unsupported`: this request claims urgency ("URGENT", "عاجل") but the priority is not high
  and no high-urgency evidence fired (`deadline_today`, `exam_now`, `safety_risk`, `stranded`,
  `enrollment_blocked`). Staff only.
- `priority_gaming_suspected`: for this alias, after at least `GAMING_MIN_REQUESTS` (5) requests,
  ≥ `GAMING_CLAIM_RATIO` (0.8) of them claim urgency and ≤ `GAMING_HIGH_RATIO_MAX` (0.2) of those
  claims were really high; or 2 injection attempts. Admin only; no penalty.

<a id="use-cases"></a>
## Use cases (application layer)

What the routes (P3.12) call. All return the DTOs in `application/dto.py`; none imports FastAPI.
Wiring for tests: `services/ai/tests/fixtures/containers.py::build_test(**overrides)`.

### `TriageUseCase.run(cmd: TriageRequest, *, debug_members=False) -> TriageResponse` — `use_cases/triage.py`

1. `TriageClassifier.classify(text, picked location)`. Blank text → `InvalidInput` **before any write**.
2. `Repository.save_request` (status `received`, the normalized request).
3. `DecisionFlow.run` (below) with a one-question budget.

`TriageClassifier` (`use_cases/ports.py`) is the `TriageCore.classify` surface (ML P1.15); until it is
merged the tests use `FakeCore`.

### `DecisionFlow.run(...)` — ARCHITECTURE §2.1 [4'], [7]–[14]

| Outcome | Writes | Response |
| --- | --- | --- |
| distress (flag) | prediction (tier `human`), review item `distress`, request status `distress`, event | `status: distress`, message with 911 |
| out of scope | pending clarification `topic`, status, event | topic chips + rephrase message |
| ask | pending clarification, status `needs_clarification`, event | question + provisional labels and sets |
| accept / after LLM | prediction, actions (`ActUseCase.run`), embedding + incident (when wired), status `decided`, event | full contract |
| human review | prediction, review item `needs_review`, provisional actions, status `human_review`, event | `needs_review`, message "A staff member will confirm this…" |

- The LLM tier runs only when `ENABLE_LLM` (and a tier) is on and the request has no `injection_attempt`.
- `policy_path` holds the last rule of each policy evaluation, e.g. `["d_ask", "c_accept"]`,
  `["e_escalate", "f_human"]`, `["a_gibberish", "c_accept"]` (topic chip answered).
- The final priority of a `safety` request is always `high` (re-asserted after the core).
- The explanation: the `Explainer` (ML P3.4) when wired; until then the core's evidence and neighbours
  with no `top_tokens` and no counterfactual.
- Pulse ([12b]/[13]) runs only with `Pulse(vectors, encoder, incidents)` wired: the request embedding is
  upserted into `requests` (meta `building, room, category, priority, created_at`) and an incident id
  goes into `action.incident_id`. Merging member tickets and the broadcast are P4.10.

### `ClarifyUseCase.run(request_id, cmd: ClarifyRequest, *, debug_members=False) -> TriageResponse` — `use_cases/clarify.py`

- The pending question is the last unanswered one. Option answers must be one of its saved options;
  free text is stored as `text:<text>` and appended to the request text (normalization and guards run
  again).
- The core is re-run with the constraints of **every** answer so far (LD-29), then `DecisionFlow`
  continues from [7] with `clarified: true`.
- Budget: one question, two when the first answer is `not_sure`; every answer counts, so afterwards the
  policy never asks again. A topic chip answer drops `gibberish` (the student named the topic).
- `caller_alias` (the route passes the alias of a student caller): it must equal the request's alias.
- Errors: unknown request or option → `NotFound` (404); another student's request → `Unauthorized`
  (403); no pending question (e.g. a third answer) → `ClarificationBudgetExceeded` (409); a
  `question_id` that is not the pending one, or blank free text → `InvalidInput` (422).

### `SyncTicketUseCase` — `use_cases/sync_ticket.py` (P4.9)

`SyncTicketUseCase(sinks, repo, notifier, clock, messages, *, student_inbox)`. See
[Ticket lifecycle](#ticket-lifecycle) for the behaviour.

| Method | Returns | Errors |
| --- | --- | --- |
| `apply_inbound(sink_name, payload, signature)` | `StatusChange` or None (ignored) | `Unauthorized` (bad signature, stale, sink not configured), `InvalidInput`, `StoreError` |
| `change_status(ticket_id, status, actor, note=None)` | `StatusChange` (`changed` false for the same status) | `NotFound`, `Unauthorized` (not staff of that office, not admin), `StoreError` |
| `propagate(change)` | None; never raises | — |
| `run(sink_name, payload, signature)` | `Ticket` or None: apply + propagate | as `apply_inbound` |
| `from_dashboard(ticket_id, status, actor, note=None)` | `Ticket`: change + propagate | as `change_status` |

`StatusChange(ticket, previous, source, note)`; `source` is the sink name or `dashboard`. `actor` is
anything with `role`, `office`, `alias` (`use_cases/ports.Actor`; the route passes its `Principal`).
`STATUS_RANK` holds the forward order.

### `EscalateSlaUseCase.run(now) -> list[str]` — `use_cases/escalate_sla.py` (P4.9)

`EscalateSlaUseCase(sinks, repo, messages)`; returns the ids it escalated. Never raises. Shared sink
pushing for both use cases and `ActUseCase.finalize` is `use_cases/mirror.TicketMirror`.

### `BatchCsvUseCase.run(data, *, use_llm=False) -> bytes` — `use_cases/batch.py` (P4.12)

`BatchCsvUseCase(labeler: BatchLabeler, *, max_rows)` behind `POST /v1/batch` (staff, admin;
multipart `file` + form `use_llm`).
- **Input:** UTF-8 (a BOM is fine), a header with `request_id` and `text` (extra columns ignored),
  values kept exactly as written. At most `BATCH_MAX_ROWS` rows (10,000) and `BATCH_MAX_BYTES`
  (5 MB, checked by the route).
- **Labels:** `BatchLabeler.label(rows, use_llm)` (`use_cases/ports.py`). Composition adapts the ML
  stream's `BatchPredictUseCase` (P1.15) to it, so the labels are `predict.py`'s.
- **Output:** `text/csv`, header `request_id,category,priority`, input order, UTF-8 without BOM, `\n`,
  minimal quoting (`read_batch_csv` / `write_predictions_csv` are public so `predict.py` writes the
  same bytes).
- **Errors:** a bad file (not UTF-8, no header, a missing column, too many rows or bytes) → 422;
  `ArtifactError` → 503; a labeler that loses or reorders rows → 500. Nothing is written to the
  database.

### `MetricsUseCase.run() -> MetricsResponse` — `use_cases/metrics.py` (P4.12)

`MetricsUseCase(reports: ReportsSource, repo, memory, artifact)` behind `GET /v1/metrics` (admin).
- **Offline sections** come from `REPORTS_DIR/model_lab.json` (`adapters/reports/json_reports.py`),
  written by `evaluate.py` (ML) in exactly the offline part of `MetricsResponse`:
  `{generated_at, ask_rate, ask_rate_is_proxy, benchmark[], coverage[], calibration[], fairness[],
  ablations[], confusions[]}` (each row in its DTO shape, see endpoints.md). The file is re-read on
  every call.
- **No report yet:** empty lists, `generated_at`/`ask_rate` null, `ask_rate_is_proxy` true. A section
  that does not validate is logged and returned empty; the others are kept; the page never fails
  because of the report.
- **Live:** `router` from `Repository.router_stats()` plus `cost_per_1k_usd = cost / total × 1000`;
  `memory` from `MemoryStore.stats()`; `artifact` the loaded version and sha (`"none"`/`""` without
  models).
- **`redteam` is `[]`** until the domain `Scorecard` carries `created_at`, `n` and `seed`
  (P4.11; change request filed).
- Errors: `StoreError` from the repository or memory store → 503.

### `CounterfactualUseCase.run(request_id, drop, *, caller_alias=None) -> CounterfactualResponse` — `use_cases/explain.py`

- Loads the request (a student caller only for their own), checks that `drop` occurs in the request
  text (case-insensitive; raw, normalized or model text), reads the decided labels from the latest
  prediction and calls `Explainer.counterfactual(normalized request, drop)` (ML P3.4).
- `flipped` is true when either label changes. Read-only: nothing is written.
- Errors: unknown request or no decision yet → 404; another student's request → 403; a blank token or
  one not in the text → 422; `ArtifactError` → 503.

### `ActUseCase` — `use_cases/act.py`

- `plan_for(pred, provisional) -> ActionPlan`: the routing plan (prediction flags + `safety` + fired
  evidence names).
- `run(pred, request, provisional, understanding=None) -> ActionOut`: see
  [Actions and side effects](#actions-side-effects). A ticket is saved through the repository first,
  then pushed to each sink; the record sink (`supabase`) is not a link.
- `finalize(ticket) -> list[ActionOut]`: after staff confirm a provisional ticket (P3.11 calls it):
  re-plans from the ticket's labels, clears `unconfirmed` and `deferred:*`, mirrors to the sinks
  (`update_status`), and fires what waited (booking; transport alert; a safety alert only if it did not
  fire already). `[]` for a ticket that is not provisional.
- Config: `config/act.yaml` (`faq_top_k`, booking department and office hours), `tau_faq`
  (FrozenConfig), `DEMO_STUDENT_INBOX`, `DEMO_OFFICE_INBOX` (unset → that email is skipped).

<a id="real-app"></a>
## The real app (`frameworks/fastapi_app.py`, P3.12)

`create_app(services=None, settings=None, *, build=None) -> FastAPI`:
- `services` is `composition.api.ApiServices`, a frozen dataclass of the use cases behind the routes
  (`triage`, `clarify`, `counterfactual`, `feedback`, `tickets`, `sla` + `clock` for the SLA scanner,
  `batch`, `metrics`, `identity` for `supabase_jwt`, and `health: HealthInfo` for `/health`). Every
  use-case field is optional: a route whose use case is `None` answers **`501 not_implemented`**
  after the auth checks, with `details.component` naming what is missing.
- `build(settings) -> ApiServices` runs in the startup lifespan when `services` is None.
  `services/ai/api.py` passes `composition.api.build_api`, which today wires only the Supabase
  identity verifier (when `AUTH_MODE=supabase_jwt` and the Supabase URL and service-role key are
  set): `build_online` (P4.3, assigned by the lead) fills the rest of `ApiServices` from the
  `OnlineContainer`. Until then the deployed app answers `/health` with `status: "degraded"` and the
  use-case routes with 501.
- `settings` defaults to `Settings()` from the env (`AI_SERVICE_TOKEN`, `AUTH_MODE`).
- Every contract route is declared with `api_contract.route_kwargs` and the same parameters as the
  mock app, in `ENDPOINTS` order: `create_app().openapi()` is **byte-identical** to the mock's
  export and to `services/ai/openapi.json` (`tests/contracts/test_openapi_real_app.py`). Routes whose
  use case belongs to a later task (`frameworks/routes/pending.py`: incidents, insights, red team,
  admin extras) authenticate and answer 501.

| Route module | Routes | Use case |
| --- | --- | --- |
| `routes/triage.py` | `POST /v1/triage`, `POST /v1/triage/{request_id}/clarify` | `TriageUseCase`, `ClarifyUseCase` |
| `routes/explain.py` | `GET /v1/explain/{request_id}/counterfactual` | `CounterfactualUseCase` |
| `routes/feedback.py` | `POST /v1/feedback` | any `FeedbackHandler` (`use_cases/ports.py`; P3.11 `FeedbackUseCase`) |
| `routes/tickets.py` | `POST /v1/tickets/{ticket_id}/status` | `SyncTicketUseCase.change_status` + `propagate` (background) |
| `routes/integrations.py` | `POST /v1/integrations/linear/webhook` | `SyncTicketUseCase.apply_inbound` + `propagate` (background) |
| `routes/lab.py` | `POST /v1/batch`, `GET /v1/metrics` | `BatchCsvUseCase`, `MetricsUseCase` |
| `routes/health.py` | `GET /health`, `GET /v1/health` | `ApiServices.health` (`status: ok` once triage is wired, else `degraded`) |
| `routes/pending.py` | the routes of later tasks | none yet (501) |
| lifespan (`background.py`) | — | `EscalateSlaUseCase.run` every `SLA_SCAN_MINUTES` |

**Testing over HTTP.**
(`AUTH_MODE` defaults to `supabase_jwt`; the test helper and the local run below set
`trusted_headers` explicitly.) `services/ai/tests/fixtures/api.py`: `api_client(build_test(...), **fields)`
returns a `TestClient` over the real app with `AUTH_MODE=trusted_headers` and a test token, and
`auth(role, alias, office)` builds the headers. Example:

```python
client = api_client(build_test(core=FakeCore().add(text, ambiguous_core)))
r = client.post("/v1/triage", json={"text": text}, headers=auth("student", "demo-17"))
```

**Running it locally** (PowerShell, repo root, venv active):

```powershell
$env:AI_SERVICE_TOKEN = "dev-token"; $env:AUTH_MODE = "trusted_headers"
uvicorn api:app --app-dir services/ai --port 8000
curl.exe -s localhost:8000/health
```

## Optional extras

`POST /v1/admin/simulate` (P5.19) and `POST /v1/admin/reindex` (P4.20) are B-list extras.
- They are in the contract so the UI can be typed against them.
- A deployment that has not built them answers `501 not_implemented`.
- In `openapi.json` they carry `"x-optional": true`.

## The mock app

`frameworks/mock_app.py` serves every route from the fixtures, with the same OpenAPI document as the contract.

For each call it picks a fixture in this order:
1. The header `X-Mock-Fixture: <fixture name>`, a mock-only header (fixture names are listed at `GET /mock/fixtures`).
2. A fixture whose path params, query and body match the call. For `/v1/triage` only `text` is compared, case- and whitespace-insensitively, so typing a fixture's sentence returns that fixture.
3. The endpoint's default fixture.

Auth is mimicked:
- A route that needs the service token answers 401 without a Bearer token. Set `MOCK_SERVICE_TOKEN` to also check its value.
- `X-CP-Role` outside the endpoint's roles answers 403.

Set `MOCK_FIXTURES_DIR` to serve another fixture directory.

Fixture format: one file per example, `{name, description, method, path, path_params, query, headers, request, status_code, response}`. Optional keys:
- `match`: the body keys the mock compares;
- `default`;
- `omit_auth`;
- `alias_paths`.

## Versioning and change process

- **Path version.** `/v1` stays until a breaking change. A breaking change (renaming or removing a key, changing a type, narrowing an enum) means `/v2`.
- **Additive changes** are allowed in `v1` with lead approval (EXECUTION rule 3): a new endpoint, a new response key, a new enum value. Clients must ignore keys they do not know.
- **`info.version`** in `openapi.json` is the `campuspulse_ai` package version.
- **After any DTO or route change:**
  1. `python -m campuspulse_ai.frameworks.export_openapi --out services/ai/openapi.json` (the real
     app; `--mock` exports the mock app, and both must produce the same bytes:
     `tests/contracts/test_openapi_real_app.py`).
  2. `python scripts/gen_api_docs.py`.
  3. `pytest services/ai/tests/contracts/test_dto_contract.py -q`.

  CI fails if `openapi.json` or `endpoints.md` is stale (`python scripts/gen_api_docs.py --check`).
- **Windows note.** In PowerShell 5.1, `>` re-encodes output, so use `--out` for the export.
