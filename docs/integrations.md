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
  records the error for the dashboard. *Known gap:* `TicketLink` has no error field and the codec does
  not write `ticket_links.last_error`, so recording the error needs a small contract change (filed).
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

**GraphQL operations.** "Verified" = checked with a real call on the CampusPulse workspace.

| Operation | Document | Status |
| --- | --- | --- |
| `issueCreate` | `mutation CampusPulseIssueCreate($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { id identifier url } } }` with `input {teamId, title, description, priority, dueDate: "YYYY-MM-DD", labelIds}` | **verified** (lead, 2026-10-31: returned CDP-1 and its url) |
| `issueCreate` input `id` | the CampusPulse ticket UUID, so a retried create can never make a second issue | UNVERIFIED |
| `teams` | `teams(first: 100) { nodes { id key name states(first: 100) { nodes { id name type position } } } }`, once per process | UNVERIFIED (same query as the P4.0 smoke) |
| `issueLabels` | `issueLabels(first: 250) { nodes { id name } }`, once per process | UNVERIFIED |
| `issueUpdate` | `issueUpdate(id: $id, input: {stateId?, priority}) { success issue { id identifier url } }` | UNVERIFIED |
| `issue` | `issue(id: $id) { id identifier url }`, to recover after a failed or repeated create | UNVERIFIED |

**Field mapping (ticket → issue).**

| Linear field | From | Rule |
| --- | --- | --- |
| `id` | `ticket.id` | only when it is a UUID |
| `teamId` | `ticket.office` | `team_by_office[office]` or `default_team` (CDP), resolved by key |
| `title` | `ticket.title` (UD-10 `understanding.ticket_title`) | fallback `"<category> request (<priority>)"`; provisional tickets get `[unconfirmed] ` |
| `description` | `ticket.body` (UD-10 `understanding.ticket_body`) | demo-data banner, the body, then `cp-ticket:<ticket id>` and a trace line `category / priority / office / SLA due` (+ "provisional" note) |
| `priority` | `ticket.priority` | `priority_map`: high 2, medium 3, low 4; `safety` 1 is reserved for safety alerts (needs `Ticket.tags`, filed) |
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

Route: `POST /v1/integrations/linear/webhook` (P4.9; no service token — the signature is the auth).
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
   payload={identifier, url, state_name, state_type})`; `SyncTicketUseCase` (P4.9) finds the ticket
   with `Repository.ticket_by_link("linear", external_id)`, saves the status and notifies the student.

Notes for P4.9: Linear expects a 200 within 5 s and retries 3 times (1 min, 1 h, 6 h). Our own
`update_status`/`close` calls also trigger webhooks: closing sets `completed`, which comes back as
`resolved`, so the use case should ignore an inbound status that would move a ticket backwards.
Signing a test body: `campuspulse_ai.adapters.integrations.linear.sign(secret, raw_body)`.

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
| `AllowlistedNotifier(inner, policy, repo)` | Outermost, and the **only writer of notifier outbox rows**. External kinds (`email`, and `whatsapp` if ever wired) must pass the allow-list, else: outbox `rejected`, audit event, inner **never called**, `RecipientNotAllowed` raised. Inner `NotificationError` → outbox `failed` + event, re-raised. Success → the sent message is saved (`sent`, `provider_id`). `in_app` is not checked (aliases, our own DB) but is recorded. |
| `GmailSmtpNotifier` | stdlib `smtplib` (LD-3). 587: EHLO → STARTTLS (verified default SSL context) → EHLO → LOGIN → send; 465: `SMTP_SSL`. Plain text + HTML with the footer "Demo message from an integration-ready prototype; sent to a developer-owned inbox." `provider_id` = the generated Message-ID. Holds its own `RecipientPolicy` (refuses before connecting). At most `SMTP_DAILY_CAP` sends per Amman day (in-process). |
| `InAppNotifier(repo)` | `kind="in_app"` only; `to_address` is the alias. Writes one `notifications` row `(alias, kind="message", payload {ref, subject, body, priority, flags})`; `provider_id = "inapp:<ref>"`. Students get updates this way (D-006). |
| `ChannelNotifier({kind: notifier})` | dispatch on `msg.kind`; an unconfigured channel → `NotificationError(retryable=False)`. Leaving `email` out is the SMTP-blocked fallback (OQ-5). |

**SMTP error mapping** (`gmail_smtp.classify`): not retryable — 535 auth, recipients refused, any
5xx reply, STARTTLS unsupported, other protocol errors; retryable — any 4xx reply (e.g. 421),
disconnects, connect errors, timeouts, `OSError` (blocked port). Retryable errors are retried
`SMTP_MAX_RETRIES` (2) times with `SMTP_BACKOFF_S * 2**n` (1 s, 2 s), then raised retryable.

**Why reasons go to `events`.** `OutboxMessage` has no `error` field (frozen contract), so the reason
of a rejected/failed send is an audit event: actor `notifier`, action `outbox.rejected` /
`outbox.failed`, entity `outbox:<id>`, payload `{to_address, kind, reason, retryable}`.

## 4. Advisor booking (calendar)

See §4 below once P4.7 lands. Google Calendar is future work (UD-3).

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
| Linear | `scripts/smoke_linear.py` (P4.0, not written yet) | should exercise `teams`, `issueLabels`, `issueCreate` with `id`, `issueUpdate` and `issue`, then archive its demo-labelled issue |
