# Integrations (as built) — owner: Backend stream

How CampusPulse talks to the outside world: ticket sinks (Supabase, Linear), the signed Linear
webhook, email and in-app notifications, and advisor booking. Design: [ARCHITECTURE §1.4](ARCHITECTURE.md)
(ports) and §3.13 (allow-list); scope: [UD-1, UD-2, UD-3](PLAN.md#user-decisions).

Code: `services/ai/campuspulse_ai/adapters/{integrations,notify,calendar}/`. Config:
[`config/integrations.yaml`](../config/integrations.yaml) (sinks, Linear mapping) and Settings env
vars ([ops env table](ops/README.md#env-vars)). The wiring into `build_online` / `ActUseCase` is P4.8.

**Non-negotiable:** nothing here ever contacts a real person. Every email and every booking
attendee passes `RecipientPolicy(DEMO_EMAIL_ALLOWLIST)` in code; an empty list rejects everything.

## 1. Ticket sinks

### 1.1 The `TicketSink` contract (`domain/ports.py`)

| Method | Does | Idempotent | Errors |
| --- | --- | --- | --- |
| `create(ticket) -> TicketLink` | pushes a new ticket; returns `(ticket_id, sink, external_id, url)` | yes, keyed by `ticket.id` | `SinkError(retryable)` |
| `update_status(ticket)` | mirrors the ticket's status and priority | yes | `SinkError(retryable)` |
| `close(ticket)` | moves the ticket to its closed state | yes | `SinkError(retryable)` |
| `handle_inbound(raw_body, signature) -> InboundEvent \| None` | verifies and parses an inbound status change; None = ignore | — | `Unauthorized`, `InvalidInput` |

- `SinkError.retryable` is True for timeouts, network errors, HTTP 429/5xx and Linear `RATELIMITED`;
  False for anything a retry cannot fix (bad credentials, validation errors, a missing team or link).
- **Order** (`enabled` in `config/integrations.yaml`): `supabase` first (the system of record: the
  `tickets` row must exist before `ticket_links` can point at it), then `linear`.
- **Failures never fail triage.** `ActUseCase` (P4.8) catches `SinkError` per sink, keeps going and
  records the error on a link `TicketLink(ticket_id, sink, external_id="error:<ticket id>", error=<message>)`,
  which the codec writes to `ticket_links.last_error` (D-011). A link with `error` set is a failed push,
  not a mirror: it is left out of `action.external`, and `LinearSink.create` ignores it and tries again.
- `WebhookSink` is future work (UD-3) and is not built; its payload is specified in §5 for later.

### 1.2 `SupabaseSink(repo)` — `adapters/integrations/supabase_sink.py`

`create` upserts the `tickets` row through `Repository.save_ticket` and returns a link whose
`external_id` is the ticket id (no `ticket_links` row is written for it). `update_status` upserts the
ticket as given; `close` upserts it with status `closed`; `handle_inbound` returns None (dashboard
changes go through `POST /v1/tickets/{id}/status`). `NotFound` → `SinkError(retryable=False)`, any
other `StoreError` → `SinkError(retryable=True)`. Callers pass a ticket that already has its UUID.

### 1.3 `RetryingSink(inner, max_attempts, base_backoff_s)` — `adapters/integrations/retrying.py`

Wraps any sink. Retries `create`/`update_status`/`close` on `SinkError(retryable=True)` only, at most
`SINK_RETRY_MAX` (3) attempts, sleeping `SINK_RETRY_BASE_S * 2**(n-1)` (0.5 s, 1 s) between them. A
non-retryable error is raised at once. `handle_inbound` is not retried. `name` is the inner name.

### 1.4 `LinearSink` — `adapters/integrations/linear.py`

```python
mapping = LinearMapping.load(Path("config/integrations.yaml"))
http = httpx.Client(timeout=mapping.timeout_s)
linear = RetryingSink(
    LinearSink(settings.linear_api_key, settings.linear_webhook_secret, mapping, http, clock),
    settings.sink_retry_max, settings.sink_retry_base_s,
)
link = linear.create(ticket)          # TicketLink(ticket.id, "linear", <issue id>, <issue url>)
```

Built only when `ENABLE_SINKS=true` and `LINEAR_API_KEY` is set.

**Workspace (set up 2026-10-31).** Workspace "CampusPulse" (`urlKey` `campus-pulse`). One team for
every office: **CDP** (`8b4300c4-0a05-4581-bd9d-b761e8b6ee70`), states Backlog (`backlog`), Todo
(`unstarted`), In Progress (`started`), Done (`completed`), Canceled (`canceled`), Duplicate
(`duplicate`). New issues land in Backlog. Workspace-level labels: `registration`, `it-support`,
`finance`, `transportation`, `facilities`, `academic-support`. A second team, CAM, exists and is not
used. Smoke issue CDP-1 belongs to the lead; leave it alone.

**Auth.** `POST https://api.linear.app/graphql` with header `Authorization: <LINEAR_API_KEY>` —
a personal API key, **no `Bearer` prefix** (verified). The key is a `SecretStr`, read only for the
header, never logged, and masked in `repr`.

**GraphQL operations.** "Verified" = checked with a real call on the CampusPulse workspace. Run log
(2026-10-31, `scripts/smoke_linear.py`): `viewer` admin=True (the developer can create the webhook
later); team CDP state types backlog, canceled, completed, duplicate, started, unstarted; issue CDP-2
created with the ticket UUID as its id, moved to In Progress and Done, then archived. Still
UNVERIFIED: the inbound webhook payload (no webhook exists until Render is deployed).

| Operation | Document | Status |
| --- | --- | --- |
| `issueCreate` | `mutation CampusPulseIssueCreate($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { id identifier url } } }` with `input {teamId, title, description, priority, dueDate: "YYYY-MM-DD", labelIds}` | **verified** (lead, 2026-10-31: returned CDP-1 and its url) |
| `issueCreate` input `id` | the CampusPulse ticket UUID, so a retried create can never make a second issue | **verified** (`scripts/smoke_linear.py`, 2026-10-31: CDP-2, archived): the returned issue id equals the ticket UUID |
| `teams` | `teams(first: 20) { nodes { id key name states(first: 50) { nodes { id name type position } } } }`, once per process | **verified** (`scripts/smoke_linear.py`, 2026-10-31: CDP-2, archived). The first version (`first: 100` x `first: 100`) was rejected live with **HTTP 400 "Query too complex"**; fixed |
| `issueLabels` | `issueLabels(first: 250) { nodes { id name } }`, once per process | **verified** (`scripts/smoke_linear.py`, 2026-10-31: CDP-2, archived): 6/6 category labels found |
| `issueUpdate` | `issueUpdate(id: $id, input: {stateId?, priority}) { success issue { id identifier url } }` | **verified** (`scripts/smoke_linear.py`, 2026-10-31: CDP-2, archived): in_progress -> `started`, closed -> `completed`, priority kept, each read back |
| `issue` | `issue(id: $id) { id identifier url }`, to recover after a failed or repeated create | **verified** (`scripts/smoke_linear.py`, 2026-10-31: CDP-2, archived): found by the ticket UUID |

**Field mapping (ticket → issue).**

| Linear field | From | Rule |
| --- | --- | --- |
| `id` | `ticket.id` | only when it is a UUID |
| `teamId` | `ticket.office` | `team_by_office[office]` or `default_team` (CDP), resolved by key |
| `title` | `ticket.title` (UD-10 `understanding.ticket_title`) | fallback `"<category> request (<priority>)"`; provisional tickets get `[unconfirmed] ` |
| `description` | `ticket.body` (UD-10 `understanding.ticket_body`) | demo-data banner, the body, then `cp-ticket:<ticket id>` and a trace line `category / priority / office / SLA due` (+ "provisional" note, + `tags: …` when the ticket has tags) |
| `priority` | `ticket.priority`, `ticket.tags` | `priority_map`: high 2, medium 3, low 4; a ticket tagged `safety` gets `safety` = 1 (urgent), on create and on every update (D-011) |
| `dueDate` | `ticket.sla_due_at` | the date in `Asia/Amman`, `YYYY-MM-DD` |
| `labelIds` | `ticket.category` | `label_by_category` name → id (case-insensitive); a missing label is skipped |
| `stateId` (update) | `ticket.status` | `state_type_by_status` → the team's first state (lowest `position`) of that type |

**Outbound status → Linear state type** (`state_type_by_status`): open → `unstarted`, in_progress →
`started`, resolved → `completed`, closed → `completed`, merged → `duplicate`, escalated → *no state
change* (only the bumped priority is sent).

**Idempotent create.** (1) A `linear` link already on `ticket.links`, or created earlier by this
instance, is returned with no HTTP call. (2) The issue id is the ticket UUID. (3) If `issueCreate`
fails retryably (e.g. a timeout that may hide a created issue) or reports a duplicate, the sink looks
the issue up with `issue(id)` and returns it if it exists; otherwise the original error is raised.

## 2. Linear webhook (inbound status sync)

Route: `POST /v1/integrations/linear/webhook` (P4.9, built; no service token — the signature is the auth).
Handler: `LinearSink.handle_inbound(raw_body, request.headers["Linear-Signature"])`.

1. **Signature.** `hex(HMAC_SHA256(LINEAR_WEBHOOK_SECRET, raw_body))` must equal `Linear-Signature`,
   compared with `hmac.compare_digest`. The route must pass the **raw bytes**, never re-serialised
   JSON. An empty secret rejects everything. Failure → `Unauthorized` → 401, nothing written.
2. **Replay window.** `webhookTimestamp` (ms since the epoch) must be within
   `webhook_tolerance_s` (60 s) of the service clock; missing, non-numeric or stale → `Unauthorized`.
3. **Body.** A signed body that is not a JSON object → `InvalidInput` (422).
4. **Filter.** Only `type == "Issue"`, `action == "update"` with `updatedFrom.stateId` present (a real
   state change, not a title edit) produce an event; everything else returns None (ack, no-op).
5. **Inbound state type → ticket status** (`status_by_state_type`): triage/backlog/unstarted → open,
   started → in_progress, completed → resolved, canceled → closed, duplicate → closed. Unlisted types
   → None.
6. **Result.** `InboundEvent(sink="linear", external_id=data.id, status, occurred_at,
   payload={identifier, url, state_name, state_type})`.

**What the service does with it (P4.9, built).** The route is `frameworks/routes/integrations.py`;
the logic is `SyncTicketUseCase` (full behaviour in
[docs/api/README.md › Ticket lifecycle](api/README.md#ticket-lifecycle)):
- `Unauthorized` from the sink → `401 unauthenticated`; nothing is read or written.
- The ticket is found with `Repository.ticket_by_link("linear", external_id)`; an issue we never
  linked (e.g. the lead's smoke issue CDP-1) is acknowledged with `accepted: false`.
- **Only forward moves are applied** (`open < escalated < in_progress < resolved < closed = merged`).
  Our own `update_status`/`close` calls trigger webhooks too: a dashboard `closed` becomes Done in
  Linear, which comes back as `resolved` and is ignored; a dashboard `resolved` comes back as
  `resolved`, equal, ignored. An escalation only changes the issue priority, which has no
  `updatedFrom.stateId`, so it is filtered out by the sink.
- **Ack budget.** Linear expects a 2xx within 5 s and retries 3 times (1 min, 1 h, 6 h). The route
  answers right after the status is saved (one lookup, one write, one audit row); mirroring to other
  sinks, the student notification and the resolution email run as a background task after the
  response. A `503` (database down) makes Linear retry later, which is what we want.
- An applied change is never pushed back to Linear (`skip` the origin sink).

Signing a test body: `campuspulse_ai.adapters.integrations.linear.sign(secret, raw_body)`; the test
helpers are in `services/ai/tests/fixtures/lifecycle.py` (an offline `LinearSink` whose HTTP client
refuses every call).

**Dashboard changes go the other way.** `POST /v1/tickets/{id}/status` saves the ticket and then
calls `update_status` on every sink except the record sink (`supabase`): the Linear issue moves to the
mapped state (`closed` and `resolved` both → `completed`). A failure is kept in
`ticket_links.last_error`.

**Creating the webhook (not done; needs the Render URL).** Linear → Settings → API → Webhooks → URL
`https://<render-service>.onrender.com/v1/integrations/linear/webhook`, resource type **Issues**,
team CDP; copy the signing secret into `LINEAR_WEBHOOK_SECRET` on Render. Then log the first real
delivery into `services/ai/tests/fixtures/linear/webhook_issue_completed.json` (it is still
UNVERIFIED).

Payload shape (from Linear's docs; UNVERIFIED until the first real delivery is logged into
`services/ai/tests/fixtures/linear/webhook_issue_completed.json`):

```json
{"action": "update", "type": "Issue", "webhookTimestamp": 1793858400000,
 "data": {"id": "<issue uuid>", "identifier": "CDP-43", "url": "https://linear.app/campus-pulse/issue/CDP-43/…",
          "state": {"id": "…", "name": "Done", "type": "completed"}},
 "updatedFrom": {"stateId": "<previous state id>"}}
```

## 3. Notifications

Chain built once by the composition root (P4.8):

```python
policy = RecipientPolicy(settings.demo_email_allowlist)
notifier = AllowlistedNotifier(
    ChannelNotifier({
        "email": GmailSmtpNotifier(settings.smtp_host, settings.smtp_port, settings.gmail_smtp_user,
                                   settings.gmail_app_password, policy=policy, clock=clock,
                                   timeout_s=settings.smtp_timeout_s, max_retries=settings.smtp_max_retries,
                                   backoff_s=settings.smtp_backoff_s, daily_cap=settings.smtp_daily_cap),
        "in_app": InAppNotifier(repo),
    }),
    policy, repo,
)
```

| Class | Behaviour |
| --- | --- |
| `AllowlistedNotifier(inner, policy, repo)` | Outermost, and the **only writer of notifier outbox rows**. External kinds (`email`, and `whatsapp` if ever wired) must pass the allow-list, else: outbox `rejected` (reason in `error`), audit event, inner **never called**, `RecipientNotAllowed` raised. Inner `NotificationError` → outbox `failed` (reason in `error`) + event, re-raised. Otherwise the returned message is saved as is (`sent` with `provider_id`, or `deferred` with `error`). `in_app` is not checked (aliases, our own DB) but is recorded. |
| `GmailSmtpNotifier` | stdlib `smtplib` (LD-3). 587: EHLO → STARTTLS (verified default SSL context) → EHLO → LOGIN → send; 465: `SMTP_SSL`. Plain text + HTML with the footer "Demo message from an integration-ready prototype; sent to a developer-owned inbox." `provider_id` = the generated Message-ID. Holds its own `RecipientPolicy` (refuses before connecting). At most `SMTP_DAILY_CAP` sends per Amman day (in-process); above it the message comes back `deferred` (nothing sent). |
| `InAppNotifier(repo)` | `kind="in_app"` only; `to_address` is the alias. Writes one `notifications` row `(alias, kind="message", payload {ref, subject, body, priority, flags})`; `provider_id = "inapp:<ref>"`. Students get updates this way (D-006). |
| `ChannelNotifier({kind: notifier})` | dispatch on `msg.kind`; an unconfigured channel → `NotificationError(retryable=False)`. Leaving `email` out is the SMTP-blocked fallback (OQ-5). |

**SMTP error mapping** (`gmail_smtp.classify`): not retryable — 535 auth, recipients refused, any
5xx reply, STARTTLS unsupported, other protocol errors; retryable — any 4xx reply (e.g. 421),
disconnects, connect errors, timeouts, `OSError` (blocked port). Retryable errors are retried
`SMTP_MAX_RETRIES` (2) times with `SMTP_BACKOFF_S * 2**n` (1 s, 2 s), then raised retryable.

**Where reasons go (D-011).** A rejected or failed send has its reason in `OutboxMessage.error`
(`outbox.error`). The audit event is still written for the admin timeline: actor `notifier`, action
`outbox.rejected` / `outbox.failed`, entity `outbox:<id>`, payload `{to_address, kind, reason, retryable}`.

**Daily cap → `deferred`.** Above `SMTP_DAILY_CAP` the Gmail notifier sends nothing and returns the
message with `status: "deferred"` and `error: "daily email cap of N reached"`; the outbox row is
saved as such. Until the DB allows `deferred` in the `outbox.status` check, `SupabaseRepository`
writes it as `queued` with `error: "deferred: …"` (`codec.for_live_schema`).

## 4. Advisor booking (calendar)

Only Academic Support × high books (UD-1). Google Calendar is future work (UD-3), so the chain is
`FallbackCalendar([SlotsTableCalendar(repo, clock, policy)], policy)`.

| Class | Behaviour |
| --- | --- |
| `SlotsTableCalendar(repo, clock, policy)` — `adapters/calendar/slots_table.py` | `find_slot(advisor_ids, window, office_hours)`: `Repository.free_slots` for those advisors, from `max(window start, now)` to the window end, keeping only slots wholly inside office hours in `office_hours.tz` (seed: Sun–Thu 09:00–15:00 Asia/Amman); the earliest wins (ties by id); None if none. `book(slot, attendees, title)`: every attendee through `RecipientPolicy` **before any write**, then `claim_slot` (`update … where booked_by is null`). Losing the race re-runs the same search once and claims the next slot; otherwise `CalendarUnavailable`. `booked_by` = the first attendee (the port carries no alias). `Booking.provider = "slots_table"`, `external_id` = slot id. `StoreError` → `CalendarUnavailable`. |
| `FallbackCalendar(providers, policy)` — `adapters/calendar/fallback.py` | Checks every attendee first (no provider is called for a non-allow-listed one). `find_slot` asks providers in order (unavailable or empty → next); `CalendarUnavailable` only if all are unavailable. `book` uses the provider that found the slot; if it is unavailable, the search runs on the later providers and their first slot is booked. |

`ActUseCase` (P4.8) passes `window = (now, now + sla_hours)` (24 h for high), the advisors from
`Repository.advisors_for("academic")`, and attendees = the student's demo inbox plus the advisor's
`demo_email`, then saves a `cases` row and emails both through the notifier chain.

## 5. `WebhookSink` payload (future work, UD-3 — specified, not built)

`POST OUTBOUND_WEBHOOK_URL`, `Content-Type: application/json`, headers
`X-CampusPulse-Timestamp: <unix seconds>` and
`X-CampusPulse-Signature: sha256=<hex HMAC_SHA256(OUTBOUND_WEBHOOK_SECRET, "<timestamp>." + raw_body)>`.
Receivers should reject timestamps older than 5 minutes and dedupe on `event_id`.

```json
{
  "event_id": "<uuid>",
  "event": "ticket.created | ticket.status_changed | ticket.closed",
  "sent_at": "2026-11-05T09:05:00+03:00",
  "ticket": {
    "id": "<uuid>", "request_id": "<uuid>", "incident_id": null, "office": "registrar",
    "category": "Registration", "priority": "high", "status": "open", "provisional": false,
    "sla_due_at": "2026-11-06T09:05:00+03:00", "title": "…", "body": "…"
  }
}
```

## 6. Live checks (run by the user; tests never touch the network)

| Check | Command | Expected |
| --- | --- | --- |
| Email, once | `python scripts/smoke_email.py --to <allow-listed inbox> --yes` | `SMTP OK port=587 message_id=<…@gmail.com> outbox=sent`. Refuses (exit 2, nothing sent) without `--yes` or for an address not on `DEMO_EMAIL_ALLOWLIST`. |
| Linear | `python scripts/smoke_linear.py --env-file <path to .env> --yes` (in a worktree set `PYTHONPATH=services/ai`) | `Linear OK team=CDP checks=9/9 archived=1 webhook=not-created`: `viewer` (admin), `teams`, `issueLabels`, `issueCreate` with `id`, `issue`, `issueUpdate` (twice, read back), then `issueArchive` of every issue it created (also after a failure). Refuses (exit 2) without `--yes` or a key. Never creates a webhook. |
