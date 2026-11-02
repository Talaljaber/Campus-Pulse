# P9 discovery: backend inventory (read-only, facts only)

Paths relative to repo root. "not verified" = not checked. Migrations are in `supabase/migrations/`; Python in `services/ai/campuspulse_ai/` (abbrev. `ai/`).

## 1. Supabase (migrations 0001-0012; no newer file exists)

Roles: `profiles.role` in `student|staff|admin` (0001). Staff carry `profiles.office` (codes: registrar, it, finance, transport, facilities, academic). Students carry `profiles.alias`. 0012 adds `profiles.advisor_id`. Helper fns (moved to schema `private` in 0006): `cp_role, cp_office, cp_alias, cp_is_staff, cp_is_admin, cp_owns_request, cp_office_has_request, cp_can_see_ticket, cp_student_predictions, cp_category_office, cp_fill_incident_office, cp_fill_review_office`.

Grants (0003): `revoke all on all tables from anon`; authenticated has SELECT only (insert/update/delete/etc revoked, default privileges too). All writes go through the AI service with the service role. RLS is enabled on every table; every policy is `for select to authenticated`. No write policies exist anywhere.

| Table | Columns (key ones) | Read policy |
|---|---|---|
| profiles | id (fk auth.users), role, office, alias unique, advisor_id | own row or admin |
| buildings | id, code, name_en, name_ar, map_x, map_y | all authenticated |
| requests | id, alias, raw_text, core, text_norm, lang, is_arabizi, input_mode(text/voice), building_id, room, stated_urgency, status (received, needs_clarification, clarified, decided, human_review, out_of_scope, distress, actioned, resolved, merged), simulated, conversation_id, model_text, truncated, location_source, created_at | owner alias, staff of an office with a ticket on it, admin |
| predictions | id, request_id, category(6), priority(low/medium/high), p_cat, p_pri, set_cat, set_pri, per_model, tier(tier0/1/2/human), models_used, cost_usd, latency_ms, flags, explanation, artifact_version, core | office staff or admin; students via view `predictions_student_v` (hides two flags) |
| clarifications | id, request_id, question_id, options, answer, asked_at, answered_at | owner, office staff, admin |
| incidents | id, building_id, category, office, title, priority, report_count, status(open/resolved), opened_at, resolved_at | staff of own office, admin |
| tickets | id, request_id, incident_id, office, category, priority, status (open, in_progress, resolved, closed, escalated, merged), provisional, title, body, sla_due_at (not null), escalated_at, resolved_at, tags text[] (0009), created_at | staff of own office, request owner, admin |
| ticket_links | ticket_id, sink, external_id, external_url, last_synced_at, last_error; pk (ticket_id, sink) | can-see-ticket or admin |
| advisors | id, fictional_name, department, room, calendar_id, demo_email, office_hours jsonb, profile_id unique (0012) | all authenticated |
| advisor_slots | id, advisor_id, starts_at, ends_at, booked_by, booked_at | staff |
| cases | id, request_id, ticket_id, advisor_id, slot_id, slot_start, outcome_code, booking jsonb, closed_at | staff |
| outbox | id, kind(email/ticket/booking/alert/broadcast/in_app/whatsapp), channel, alias, request_id, to_address, subject, body, provider_id, status(queued/sent/failed/rejected/simulated/deferred), priority, flags, error | own alias or any staff/admin |
| notifications | id, alias, kind, payload jsonb, read_at | own alias, staff for alias `office:<office>` (0010), admin |
| review_queue | id, prediction_id, reason, status(open/confirmed/corrected), reviewer_id, corrected_category, corrected_priority, note, assignee, office (0012), resolved_at | admin; staff of own office, reason<>'distress', unassigned or assigned to self (0011, 0012) |
| student_signals | alias pk, n_requests, n_claimed_urgent, n_claimed_urgent_not_high, n_high, n_injection, gaming_flag | admin |
| llm_calls | id, request_id, tier, model, prompt_hash, cache_key, response, tokens, cost_usd, latency_ms, cached | staff |
| redteam_runs | id, config, scorecard | staff |
| events | id bigint, actor, action, entity, payload, at | staff |
| faq | id, lang, question, answer, source_url, is_demo, embedding vector(384) | column grant + policy; view `faq_v` |
| memory_examples | id, text_norm, lang, embedding vector(384), category, priority, author_id, active, created_at | column grant + `memory_examples_v` (no embedding) |
| request_embeddings | request_id, embedding, lang, category, priority, building_id, room | no client grant or policy (service role only) |

Other DB objects: extensions `vector`, `pgcrypto` (0001); fn `match_vectors(text, vector, int, float8, jsonb)` and `vector_dim()` (0005, service_role); `bump_student_signals(...)` (0007, service_role only); triggers `tickets_fill_incident_office`, `review_queue_fill_office`; realtime publication on predictions, tickets, incidents, outbox, notifications, requests (0004), review_queue, ticket_links (0010).

Facts for the target features:
- Storage buckets: none. No `storage` objects in any migration; `supabase/config.toml` has only commented bucket examples (L115-153).
- Comments / internal notes table: none. Attachments table: none. Announcements table: none. Departments table: none (offices are text codes; `private.cp_category_office` maps category to office code, 0012; also `config/actions.yaml` L14).
- Staff corrections: `review_queue` (corrected_category/priority/note) plus `memory_examples` (live memory, section 5). No separate "hints" table.
- SLA/deadline: `tickets.sla_due_at`, `escalated_at`, `resolved_at`. No reminder-sent column, no overdue column (overdue is computed by the scanner query).
- Ticket statuses today: open, in_progress, resolved, closed, escalated, merged. No `new` or `solved`, no "forward" status.
- Tests: `supabase/tests/rls.sql`, `scripts/test_rls.py`. Generated types: `supabase/types/database.types.ts`.

## 2. Tickets today

- Creation: inside `POST /v1/triage` (`ai/frameworks/routes/triage.py:36`), by `ActUseCase._open_ticket` (`ai/application/use_cases/act.py:350`), then `open_ticket` (L368) saves the row (record sink = Supabase) and creates it in each sink in order. Incident tickets: `application/use_cases/incidents.py` (L117, L179). Feedback path also creates tickets (`feedback.py:229`). The browser never writes tickets (no write grants).
- SLA: `sla_due_at = now + sla_hours` from `config/actions.yaml` L17-20: high 24, medium 72, low 336 hours.
- Linear sink (`ai/adapters/integrations/linear.py`, config `config/integrations.yaml`): GraphQL `issueCreate(id, teamId, title, description, priority, dueDate, labelIds)`; `issueUpdate(stateId, priority, title, description, labelIds)`; default team `CDP`, `team_by_office` all empty strings; label per category; priority map high 2, medium 3, low 4, safety 1; status map open->unstarted, in_progress->started, resolved/closed->completed, merged->duplicate, escalated->null. Inbound: `POST /v1/integrations/linear/webhook` (signature, timestamp tolerance 60 s), applied only if it raises status rank (`sync_ticket.py:131`). Failures stored in `ticket_links.last_error`. Env `ENABLE_SINKS`, `LINEAR_API_KEY`, `LINEAR_WEBHOOK_SECRET`.
- Status changes: `POST /v1/tickets/{id}/status` (staff of the ticket's office, or admin; `sync_ticket.py` `change_status`), or the Linear webhook. Rank: open < escalated < in_progress < resolved < closed = merged (`domain/values.py:84-106`). Dashboard reopen clears `resolved_at`.
- Assignment: no assignee column on tickets. Only `review_queue.assignee` exists (0012, advisor routing of review items).
- Forwarding: `POST /v1/tickets/{id}/forward` (`application/use_cases/forward.py`): changes `office` and category, adds tag `forwarded`, keeps status, priority and SLA (the clock is NOT restarted; see `api_contract.py` ~L206-225), updates Linear, in-app notification to `office:<new>`. No email. Also `POST /v1/reviews/{id}/forward` for review items (this one teaches the model).
- SLA scanner: section 4 (escalates once, bumps priority, status `escalated`).

## 3. Email today

- Sender: `ai/adapters/notify/gmail_smtp.py` (`GmailSmtpNotifier`, stdlib smtplib, 587 STARTTLS or 465 SSL, retries on 4xx, daily cap `SMTP_DAILY_CAP` default 100 per Amman day counted in-process; over cap -> outbox status `deferred`). HTML body = escaped plain body with `<br>` (L187); From = sender name + `GMAIL_SMTP_USER` (L182). Subject/body only; no attachments, no reply-to (not verified beyond grep).
- Allow-list: `ai/domain/policy.py:134-147` (`RecipientPolicy`, lowercase compare, empty list rejects all); enforced in `ai/adapters/notify/allowlist.py` (`AllowlistedNotifier`, outermost decorator, checks every non-`in_app` kind before the inner send, writes exactly one outbox row `sent|rejected|failed|deferred`). Chain built in `composition/api.py` with `ChannelNotifier` (`adapters/notify/channels.py`) dispatching on `kind` (email, in_app). Env `DEMO_EMAIL_ALLOWLIST`.
- Templates: `config/templates/messages.yaml` (subjects: update, booking, safety, transport, resolved, review), `replies.en.yaml`, `replies.ar.yaml`; loader `application/use_cases/messages.py`. Plain text, no HTML templates.
- Events that email today:
  - advisor booking confirmation to `DEMO_STUDENT_INBOX` (`act.py:432`);
  - safety and transport alerts to `DEMO_OFFICE_INBOX` (`act.py:497`);
  - ticket resolved -> student demo inbox (`sync_ticket.py:201-221`);
  - review assigned -> advisor's `demo_email` if `REVIEW_EMAIL_ADVISOR` (`reviews.py:187`);
  - incident alerts (`incidents.py:215, 342`; recipients not verified).
  Ticket created, other status changes, forward, escalation: in-app notification only (no email). No comments exist.
- Recipients: every student resolves to the single `DEMO_STUDENT_INBOX`; offices to `DEMO_OFFICE_INBOX`; advisors to `advisors.demo_email` plus-addresses. `profiles` has no email column.
- Scheduler for email/reminders: none.

## 4. Scheduled and background jobs

- In-process only: `ai/frameworks/background.py` `sla_loop`, started in the FastAPI lifespan (`frameworks/fastapi_app.py` ~L90) every `SLA_SCAN_MINUTES` (default 5), one uvicorn worker. Runs `EscalateSlaUseCase` (`application/use_cases/escalate_sla.py`; repo query `overdue_open_tickets(now)` at `adapters/store/supabase_store.py:150`: status open/in_progress, `sla_due_at < now`, never escalated). Writes in-app `office:<office>` notification and event `sla.escalated`; no email, no reminders.
- pg_cron: not used (stated in `escalate_sla.py` docstring). Supabase edge functions: none (no `supabase/functions`). Render cron: none.
- `render.yaml`: one web service `campuspulse-ai` (docker, starter, frankfurt, health `/health`, autodeploy on commit); env keys in section 7.
- `netlify.toml`: base `apps/web`, build `pnpm run build`, NODE_VERSION 22. Nothing else.
- `.github/workflows/ci.yml`: python ruff/mypy/pytest, artifact tests, data checks, api docs/openapi check, TS types check (not fully verified). `keepalive.yml`: cron `17 */6 * * *`, pings API /health, web, and signs in as the demo student to touch Supabase.

## 5. Python AI service API

Entry `services/ai/api.py` (11 lines) -> `ai/frameworks/fastapi_app.py`; contract `ai/frameworks/api_contract.py` (`ENDPOINTS`, `route_kwargs`); schemas `ai/application/dto.py`; routes `ai/frameworks/routes/`; export `services/ai/openapi.json`; mock `frameworks/mock_app.py`.

Auth (`frameworks/auth.py`): every route except `/health`, `/v1/health`, Linear webhook needs `Authorization: Bearer AI_SERVICE_TOKEN` (constant-time compare). Caller identity: `AUTH_MODE=supabase_jwt` (default) verifies `X-CP-User-JWT` with Supabase and loads role/office/alias from `profiles`; no user JWT = `service`; `trusted_headers` mode uses `X-CP-Role/Alias/Office`. Per-endpoint role gate.

| op_id | Method path | Roles | Response model |
|---|---|---|---|
| triage | POST /v1/triage | student, staff, admin, service | not verified |
| clarify | POST /v1/triage/{request_id}/clarify | student, service | not verified |
| explain_counterfactual | GET /v1/explain/{request_id}/counterfactual | student, staff, admin | CounterfactualResponse |
| feedback | POST /v1/feedback | staff, admin | FeedbackResponse |
| ticket_status | POST /v1/tickets/{ticket_id}/status | staff, admin | TicketOut |
| ticket_forward | POST /v1/tickets/{ticket_id}/forward | staff, admin | TicketOut |
| list_reviews | GET /v1/reviews | staff, admin | not verified |
| review_forward | POST /v1/reviews/{review_id}/forward | staff, admin | not verified |
| list_incidents | GET /v1/incidents | staff, admin, service | not verified |
| resolve_incident | POST /v1/incidents/{incident_id}/resolve | staff, admin | not verified |
| insights_recurring | GET /v1/insights/recurring | staff, admin | not verified |
| linear_webhook | POST /v1/integrations/linear/webhook | public (signature) | not verified |
| batch | POST /v1/batch | staff, admin | CSV |
| redteam_run | POST /v1/redteam/run | admin | not verified |
| metrics | GET /v1/metrics | admin | not verified |
| health, health_root | GET /v1/health, /health | public | not verified |
| admin_simulate | POST /v1/admin/simulate | admin | not verified |
| admin_reindex | POST /v1/admin/reindex | admin | not verified |

Web proxy to the service: `apps/web/src/app/api/ai/[...path]/route.ts` (server side).

Corrections: `POST /v1/feedback` -> `ai/application/use_cases/feedback.py` `FeedbackUseCase`: confirm or correct a prediction; prediction becomes tier `human`, `review_queue` row resolved, ticket `provisional` -> false, `events` row, and the example is added via `MemoryStore.add` into `memory_examples` (active, 384-d embedding) immediately. At inference the kNN neighbours include the memory (`source="memory"`, weight capped by `knn.memory_weight_cap`); adapters `ai/adapters/memory/pgvector_memory.py` (+ `cached.py`, `inmemory.py`, `null.py`), vectors in `ai/adapters/vectors/`. The frozen model and `predict.py` never see corrections. Corrections are (category, priority) label examples only; there are no free-text hints, and whether the chat LLM path (`composition/llm_frontend.py`, `config/llm_frontend.yaml`) could read them is not verified.

## 6. Seed data

| What | Where | Run |
|---|---|---|
| 4 demo logins: `talal@demo.local` (student, alias talal), `it@demo.local` (staff, office it), `advisor@demo.local` (staff, office academic, linked to advisor a...0001), `admin@demo.local` (admin) | `scripts/seed_demo_users.py` (password `DEMO_USER_PASSWORD`; idempotent) | `python scripts/seed_demo_users.py` (needs SUPABASE_URL + service key) |
| Buildings | `supabase/seed/01_buildings.sql` | SQL (how applied: not verified) |
| 6 fictional advisors (4 academic, 2 registrar; demo_email plus-addresses of campuspulse.support@gmail.com) | `supabase/seed/02_advisors.sql`; check `scripts/check_seed_contacts.py` | SQL |
| Advisor slots | `supabase/seed/03_advisor_slots.sql` | SQL |
| FAQ text | `supabase/seed/04_faq_text.sql`; embeddings `scripts/seed_faq.py` | SQL then script |
| Pulse simulation | `scripts/simulate_pulse.py`, `config/simulation/`, `POST /v1/admin/simulate` | script or API |

No staff accounts exist for finance, registrar, transport, facilities. Login is Supabase email/password at `apps/web/src/app/login/page.tsx`; no simulated university login.

Web pages today (`apps/web/src/app`): `(student)/page.tsx`, `login`, `staff`, `staff/reviews`, `pulse`, `outbox`, `lab`, `dev/ui`.

## 7. Env var names

AI service (`.env.example`, `config/settings.py`, `render.yaml`): AI_SERVICE_TOKEN, AUTH_MODE, AUTH_CACHE_S, AUTH_TIMEOUT_S, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, STORE_TIMEOUT_S, OPENROUTER_API_KEY, OPENROUTER_TIER1_MODEL (render.yaml only), ENABLE_LLM, LLM_DAILY_BUDGET_USD, LLM_TIMEOUT_S, LLM_MAX_RETRIES, LLM_RETRY_BACKOFF_S, LLM_CACHE_PATH, LLM_MODEL, LLM_PROVIDER_ORDER, LLM_PROVIDER_ALLOW_FALLBACKS, LLM_PROVIDER_DATA_COLLECTION, LLM_REASONING_OFF, LLM_ARABIZI_TRANSLATE, LLM_ARABIZI_MODEL, LLM_ARABIZI_TIMEOUT_S, LLM_ARABIZI_CACHE_PATH, LLM_FRONTEND, LLM_FRONTEND_CONFIG, LLM_FRONTEND_MODEL, LLM_FRONTEND_CACHE_PATH, GMAIL_SMTP_USER, GMAIL_APP_PASSWORD, SMTP_HOST, SMTP_PORT, SMTP_TIMEOUT_S, SMTP_MAX_RETRIES, SMTP_BACKOFF_S, SMTP_DAILY_CAP, DEMO_EMAIL_ALLOWLIST, DEMO_STUDENT_INBOX, DEMO_OFFICE_INBOX, LINEAR_API_KEY, LINEAR_WEBHOOK_SECRET, OUTBOUND_WEBHOOK_URL, OUTBOUND_WEBHOOK_SECRET, ENABLE_SINKS, SINK_RETRY_MAX, SINK_RETRY_BASE_S, GAMING_MIN_REQUESTS, GAMING_CLAIM_RATIO, GAMING_HIGH_RATIO_MAX, REVIEW_FALLBACK_OFFICE, REVIEW_LIST_LIMIT, REVIEW_EMAIL_ADVISOR, SLA_SCAN_MINUTES, INCIDENT_WINDOW_MIN, ARTIFACT_DIR, ORT_INTRA_OP_THREADS, ORT_LOW_MEMORY, MEMORY_QUERY_CACHE_S, CAMPUSPULSE_ROOT, REPORTS_DIR, BATCH_MAX_ROWS, BATCH_MAX_BYTES, REDTEAM_MAX_N, REDTEAM_SEED_CSV, PORT. render.yaml also lists GITHUB_TOKEN.

Web (`apps/web/src`): NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_DEMO_LOGIN_HINT, AI_SERVICE_URL, AI_SERVICE_TOKEN.

Scripts/CI only: DEMO_USER_PASSWORD, SUPABASE_PROJECT_REF, SUPABASE_DB_PASSWORD, SUPABASE_TEST_URL, SUPABASE_ANON_KEY, DEMO_STUDENT_EMAIL, DEMO_STUDENT_PASSWORD, API_URL, WEB_URL.
