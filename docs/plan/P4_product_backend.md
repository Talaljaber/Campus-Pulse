# P4 — Product backend

> **Status:** DRAFT — awaiting user approval. **Budget:** 1½ d (ARCHITECTURE §4.0) · **Calendar:** Fri 6 (pm) – Sat 7 Nov · **Planned (not cut-flagged):** 23.25 h · **Cut-flagged:** 5.75 h (P4.15–P4.20).
>
> Conventions: [PLAN.md › Conventions](../PLAN.md#conventions). `§n` refers to [ARCHITECTURE.md](../ARCHITECTURE.md); `LD-n` and `OQ-n` link to the lead decisions and open questions in [PLAN.md](../PLAN.md). Tick `- [ ] Done` under each task as you finish it, and tick this phase's decision log at the bottom.

**Goal.** Make every action real but safe. P4 delivers:
- the Supabase schema with RLS, Realtime and pgvector;
- the action engine (FAQ, ticket, booking, safety alert), with Gmail SMTP behind the allow-list, Linear with inbound sync, and the SLA scanner;
- incident detection with broadcast;
- the red-team runner;
- the full API, deployed on Render Starter inside 512 MB.

**Phase contract (§4.5).** P4 hands these to P5:
- **Migrations `0002…0005`:** the full SPEC §8 schema, RLS, Realtime publication, the `notifications` table, and `0005_vectors.sql` (HNSW, `match_vectors`/`vector_dim`, `memory_examples_v`/`faq_v`).
- **Seeds:** `supabase/seed/*.sql` and `scripts/seed_faq.py`.
- **Adapters:** `vectors/pgvector.py`, `memory/pgvector_memory.py`, `store/supabase_store.py`, `integrations/{supabase_sink,linear}.py` plus `RetryingSink`, `notify/{outbox,gmail_smtp,allowlist,inapp}.py`, `calendar/slots_table.py`, `faq/retriever.py`, `pulse/incident_detector.py`, `redteam/{perturbation,scorer}.py`.
- **Use cases:** `use_cases/{act,resolve_incident,sync_ticket,escalate_sla,run_redteam}.py`.
- **Routes:** `/batch`, `/redteam/run`, `/incidents/{id}/resolve`, `/integrations/linear/webhook`, `/metrics`, `/tickets/{id}/status`.
- **Auth and ops:** `frameworks/auth.py` (service token plus role claims), `scripts/measure_rss.py` with the Render sizing result recorded in PLAN.md, `scripts/simulate_pulse.py`, `docs/integrations.md`.

<a id="exit-criteria"></a>
**Exit criteria (SPEC §12, measurable).**

| # | Check | Command → expected |
| --- | --- | --- |
| X4.1 | Lifecycle with fakes | `pytest services/ai/tests/e2e/test_lifecycle.py -q` → `passed`. Covers request → ticket → FakeSink issue → inbound status → `notifications` row + outbox row. |
| X4.2 | Lifecycle against real services, run once and logged | `python scripts/smoke_integrations.py --api %RENDER_URL% --linear --email` → `linear issue: https://linear.app/...`, `email: sent (provider_id=<Message-ID>)`, then after moving the issue to *Done* in Linear: `ticket <id> status=resolved via linear webhook; notification row created`. The output is pasted into the PLAN.md decisions log with the date. |
| X4.3 | Simulator creates an incident | `python scripts/simulate_pulse.py --api %RENDER_URL% --scenario config/simulation/wifi_m.yaml` → `incident created: <uuid> building=M category=IT Support reports=3`, and after 6 reports `priority bumped → high` |
| X4.4 | RLS holds | `python scripts/test_rls.py` (local `supabase start`) → `RLS: 9/9 checks passed` |
| X4.5 | Vector store contract on real pgvector | `set SUPABASE_TEST_URL=… && pytest services/ai/tests/contracts/test_vector_store_contract.py -q` → `passed` for both `LocalNumpyVectorStore` and `PgVectorStore` |
| X4.6 | Render memory and latency budget (§3.17) | `python scripts/measure_rss.py --remote %RENDER_URL% --n 20` → `rss_mb_max<=400 p95_ms<=1500 OK`. The numbers are recorded in PLAN.md. |
| X4.7 | Allow-list cannot be bypassed | `pytest services/ai/tests/unit/test_allowlist.py -q` → `passed`. `real.person@gju.edu.jo` → rejected; the provider is called 0 times. |
| X4.8 | Scored core still untouched | [X3.5](P3_intelligence.md#exit-criteria) repeated → `no differences encountered` |

---

<a id="p4-0"></a>
## P4.0 — Day-one smoke checks for every external service (P4 morning, before code)

- [ ] Done
- Depends on: the [Appendix D](appendix_D_accounts.md) accounts created on 31 Oct–1 Nov; P0 Render service (Starter) running `/health`
- Est: 0.75 h · Cut: no
- Files:
  - scripts/smoke_smtp.py (Files added)
  - scripts/smoke_linear.py (Files added)
  - docs/PLAN.md decisions log rows
- Interfaces: none (scripts)
- Config keys: `GMAIL_SMTP_USER`, `GMAIL_APP_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`, `DEMO_EMAIL_ALLOWLIST`, `LINEAR_API_KEY`, `OPENROUTER_API_KEY`
- Steps:
  1. **SMTP from Render.** Render blocks ports 25/465/587 on **Free** instances (verified, Render docs, live since 26 Sep 2025). Paid instances are believed to allow 465/587 (UNVERIFIED officially). Run `python scripts/smoke_smtp.py --to <allow-listed address>` **inside the Render service shell** (Render dashboard → Shell, Starter plan). Port 587 STARTTLS first, 465 SSL second. Record which port works.
  2. **Linear.** `python scripts/smoke_linear.py` runs:
     - `viewer { id }`;
     - `teams { nodes { id key name states { nodes { id name type } } } }`;
     - `issueCreate` on the demo team, then archives the issue.
     Record the team ids and state ids in `config/integrations.yaml`. Check that the developer is a **workspace admin**: webhooks can only be created by admins (verified). Check that the free plan allows webhooks (UNVERIFIED) by creating one in Settings → API → Webhooks pointing at `https://<render>/v1/integrations/linear/webhook`.
  3. **OpenRouter.** `curl https://openrouter.ai/api/v1/key -H "Authorization: Bearer %OPENROUTER_API_KEY%"` → `limit_remaining` > 0.
  4. **Supabase.** The project is not paused (dashboard), and `select extversion from pg_extension where extname='vector'` → ≥ 0.7.
- Acceptance:
  - `python scripts/smoke_smtp.py --to campuspulse.support+student17@gmail.com` (run on Render) → `SMTP OK port=587 message_id=<…>`
  - `python scripts/smoke_linear.py` → `Linear OK team=<KEY> states=<n> webhook=<present|missing>`
- Hands off: the working SMTP port into Render env `SMTP_PORT`; Linear IDs into `config/integrations.yaml`.
- Notes:
  - **If SMTP is blocked on Starter too**, keep `GmailSmtpNotifier` as the local/dev path. On Render, wire `InAppNotifier`, which writes an outbox row with `status="simulated"`, and record a "Needs decision" for the user: either the Gmail API over HTTPS (OAuth `gmail.send`, refresh token; the consent screen must be "In production" or tokens expire after 7 days) or record moment 1 with the API running locally. No other provider is added without approval.
  - If Linear webhooks are unavailable on Free: inbound sync is demonstrated through `/v1/tickets/{id}/status` from the dashboard (same use case), and the gap is stated in the README.

<a id="p4-1"></a>
## P4.1 — Write the core schema, RLS, Realtime migrations and RLS test

- [x] Done
- Depends on: P0 (`0001_init.sql`), P4.0
- Est: 2 h · Cut: no
- Files:
  - supabase/migrations/0002_core_schema.sql
  - supabase/migrations/0003_rls.sql
  - supabase/migrations/0004_realtime.sql
  - supabase/tests/rls.sql
  - scripts/test_rls.py
- Interfaces: SQL only. The tables are SPEC §8 plus:
  - `notifications(id, alias, kind, payload jsonb, read_at, created_at)` (§6.1 #7);
  - `ticket_links.last_error`;
  - `llm_calls.cache_key text unique` and `llm_calls.response jsonb`, needed by `SupabaseCache` ([LD-25](../PLAN.md#ld-25));
  - `outbox.channel text default 'email'` and `outbox.error text`;
  - `requests.simulated bool default false`.
- Config keys: none
- Steps:
  1. **`0002`:** every SPEC §8 table except `faq`/`memory_examples`, which go to 0005. Enum checks are `check (category in (...))` with the exact label spellings. Add `created_at timestamptz default now()` everywhere and indexes on `tickets(office,status,sla_due_at)`, `requests(alias,created_at)` and `incidents(building_id,status)`.
  2. **`0003`:** helpers `cp_role()`, `cp_office()`, `cp_alias()` (`security definer`, `set search_path = public`, stable). Policies exactly §3.14. `enable row level security` on every table. No insert/update/delete policies. Views `predictions_student_v` (flags minus `urgency_unsupported`/`priority_gaming_suspected`) with `security_invoker = true`.
  3. **`0004`:** `alter publication supabase_realtime add table predictions, tickets, incidents, outbox, notifications, requests;`. `requests` is added for Pulse dots ([LD-25](../PLAN.md#ld-25)).
  4. **`rls.sql`** runs as `set local role authenticated; set local request.jwt.claims = '{"sub":"<uuid>"}'`. It checks:
     - student A ≠ student B requests;
     - IT staff ≠ Finance tickets;
     - an authenticated insert fails;
     - a student cannot select `request_embeddings`;
     - a student cannot execute `match_vectors` (0005);
     - anon sees nothing;
     - admin sees all;
     - staff see `review_queue`;
     - a student sees no gaming flags.
  5. **`scripts/test_rls.py`** runs `supabase db reset` on the local stack (needs Docker Desktop) and then runs `rls.sql` via `psql`. It prints a pass count.
- Acceptance:
  - `supabase db reset` → `Finished supabase db reset`
  - `python scripts/test_rls.py` → `RLS: 9/9 checks passed`
- Hands off: the schema to P4.2/P4.3; RLS to the P5 read layer.
- Notes: the service role bypasses RLS and lives only in Render env (§1.7). The web app never holds it.

<a id="p4-2"></a>
## P4.2 — Add pgvector: the vectors migration, PgVectorStore, PgVectorMemoryStore and contract tests

- [x] Done (X4.5 live pgvector contract pending SUPABASE_TEST_* keys)
- Depends on: P4.1; P2 final encoder decision (dim 384 locked, §6.1 #18)
- Est: 2 h · Cut: no
- Files:
  - supabase/migrations/0005_vectors.sql
  - services/ai/campuspulse_ai/adapters/vectors/pgvector.py
  - services/ai/campuspulse_ai/adapters/memory/pgvector_memory.py
  - services/ai/tests/contracts/test_vector_store_contract.py (parametrised with Local)
  - services/ai/tests/contracts/test_memory_store_contract.py
- Interfaces: implements `VectorStore` (`PgVectorStore`) and `MemoryStore` (`PgVectorMemoryStore`).
  ```python
  class PgVectorStore:  # VectorStore
      def __init__(self, client: "supabase.Client", dim: int) -> None: ...   # calls rpc vector_dim(); != dim → ArtifactVersionMismatch
      def upsert(self, collection: str, items: Sequence[VectorItem]) -> None: ...     # table API, service role; StoreError on PostgREST error
      def search(self, collection: str, query: Sequence[float], k: int, min_sim: float = 0.0, filters: Mapping[str, object] | None = None) -> list[VectorHit]: ...
      def set_active(self, collection: str, id: str, active: bool) -> None: ...      # memory only; else StoreError
      def count(self, collection: str, filters: Mapping[str, object] | None = None) -> int: ...
  class PgVectorMemoryStore:  # MemoryStore
      def __init__(self, vectors: PgVectorStore, client: "supabase.Client", clock: Clock) -> None: ...
  ```
  ```sql
  -- 0005_vectors.sql (vector type lives in schema "extensions" on Supabase)
  create table faq (id uuid primary key default gen_random_uuid(), lang text not null check (lang in ('en','ar')), question text not null, answer text not null,
                    source_url text, is_demo bool not null default true, embedding extensions.vector(384));
  create table memory_examples (id uuid primary key default gen_random_uuid(), text_norm text not null, lang text not null, embedding extensions.vector(384) not null,
                    category text not null, priority text not null, author_id uuid references auth.users, created_at timestamptz default now(), active bool default true);
  create table request_embeddings (request_id uuid primary key references requests(id) on delete cascade, embedding extensions.vector(384) not null, lang text,
                    category text, priority text, building_id text, room text, created_at timestamptz default now());
  create index on faq using hnsw (embedding extensions.vector_cosine_ops) with (m = 16, ef_construction = 64);   -- same for memory_examples, request_embeddings
  create function match_vectors(p_collection text, p_query extensions.vector(384), p_k int, p_min_sim float8, p_filters jsonb default '{}')
    returns table(id uuid, text text, lang text, sim float8, meta jsonb, embedding extensions.vector(384))   -- embedding only when p_filters->>'with_embedding'='true' (LD-14)
    language plpgsql security definer set search_path = public, extensions as $$ ... $$;   -- set_config('hnsw.ef_search','40',true); order by distance, id
  create function vector_dim() returns int language sql stable security definer set search_path = public, extensions
    as $$ select atttypmod from pg_attribute where attrelid = 'public.faq'::regclass and attname = 'embedding' $$;
  revoke execute on function match_vectors, vector_dim from anon, authenticated, public;
  alter table request_embeddings enable row level security;   -- no policies → service role only
  create view memory_examples_v with (security_invoker = true) as select id, text_norm, lang, category, priority, author_id, created_at, active from memory_examples;
  create view faq_v with (security_invoker = true) as select id, lang, question, answer, source_url, is_demo from faq;
  ```
- Config keys: Settings `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (AI only); `SUPABASE_TEST_URL`/`SUPABASE_TEST_SERVICE_ROLE_KEY` gate the contract test.
- Steps:
  1. The dispatcher supports collections `requests` (filters `building_id`, `category`, `since`), `memory` (`active`) and `faq` (`lang`). An unknown collection → exception → `StoreError`.
  2. Filtered HNSW search can under-return. At fewer than 10 k rows, set `hnsw.iterative_scan = relaxed_order` if pgvector ≥ 0.8, otherwise accept it. Record the version.
  3. `VectorHit` gains an optional `embedding: tuple[float, ...] | None = None`, so `IncidentDetector` can compute the centroid ([LD-14](../PLAN.md#ld-14)). `LocalNumpyVectorStore` fills it under the same filter flag.
  4. Contract tests run unchanged against both stores:
     - upsert → search gives sim ≈ 1.0 for the item;
     - filters;
     - `set_active(False)` hides the item;
     - deterministic tie-break;
     - dim mismatch → `ArtifactVersionMismatch`.
  5. Memory contract: the [P3.7](P3_intelligence.md#p3-7) tests are parametrised over `InMemoryMemoryStore` and `PgVectorMemoryStore`.
- Acceptance:
  - `supabase db push` (linked project) → `Applying migration 0005_vectors.sql... Finished`
  - X4.5 → `passed`
  - `pytest services/ai/tests/invariants/test_vector_isolation.py -q` → `passed` (offline never imports `adapters.vectors.pgvector`)
- Hands off: `PgVectorStore` to P4.3 (composition), P4.5 (FAQ) and P4.10 (incidents).

<a id="p4-3"></a>
## P4.3 — Write SupabaseRepository, seeds, demo users, seed_faq and wire build_online

- [ ] Done — partial: SupabaseRepository, InMemoryRepository, migration 0007, seeds 01–04 applied. Still to do: `seed_demo_users.py` run (needs DEMO_USER_PASSWORD), `seed_faq.py` run (needs P1.6 encoder), `build_online` (lead assigns later).
- Depends on: P4.2
- Est: 2 h · Cut: no
- Files:
  - services/ai/campuspulse_ai/adapters/store/supabase_store.py
  - services/ai/campuspulse_ai/composition/online.py
  - supabase/seed/{01_buildings.sql, 02_advisors.sql, 03_advisor_slots.sql, 04_faq_text.sql}
  - scripts/seed_demo_users.py (Files added)
  - scripts/seed_faq.py
  - services/ai/tests/contracts/test_repository_contract.py (InMemory always; Supabase when `SUPABASE_TEST_URL`)
- Interfaces: implements `Repository` (`SupabaseRepository(client, clock)`), including the **additions** of [LD-16](../PLAN.md#ld-16):
  ```python
  def ticket_by_link(self, sink: str, external_id: str) -> Ticket: ...                 # NotFound
  def incident_members(self, incident_id: str) -> list[tuple[Ticket, Request]]: ...
  def free_slots(self, advisor_ids: Sequence[str], window: tuple[datetime, datetime]) -> list[Slot]: ...
  def claim_slot(self, slot: Slot, booked_by: str) -> bool: ...                        # conditional update where booked_by is null
  def save_case(self, c: Case) -> Case: ...                                            # cut B-list ("cases") → no-op when cut
  def save_notification(self, alias: str, kind: str, payload: Mapping[str, object]) -> None: ...
  def advisors_for(self, department: str) -> list[Advisor]: ...
  def router_stats(self, since: datetime | None = None) -> RouterStats: ...            # tier mix, cost per 1k, p50/p95 latency from predictions/llm_calls
  def redteam_history(self, limit: int = 20) -> list[Scorecard]: ...
  ```
  `build_online(settings) -> OnlineContainer` is exactly §1.5, with these changes:
  - the notifier line becomes `AllowlistedNotifier(GmailSmtpNotifier(...) if GMAIL_APP_PASSWORD else InAppNotifier(repo), RecipientPolicy(settings.demo_email_allowlist))`;
  - the S1 hook is inactive unless `WHATSAPP_*` is set.
- Config keys: Settings `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DEMO_EMAIL_ALLOWLIST`, `ENABLE_SINKS`
- Steps:
  1. **Seeds are fictional only:**
     - 10 buildings, `A`–`M` minus `I`/`J`, with `map_x/map_y` on a 1000×600 grid and AR/EN names;
     - 6 advisors with fictional names, each `demo_email` an allow-listed plus-address (`campuspulse.support+adv-reg@gmail.com` …), office hours Sun–Thu 09:00–15:00 Asia/Amman;
     - slots for the next 14 days generated with `generate_series`;
     - FAQ text: every non-`[demo]` entry quotes `docs/reference/gju_public_policies.md` with its source URL, and every other entry is `is_demo = true`, at least 24 entries EN+AR.
  2. **`seed_demo_users.py`** uses the service key on the dev machine only. It calls `auth.admin.create_user` for `student-demo-17@demo.local`, `staff-it@demo.local` and `admin@demo.local` (§1.7), with passwords from `DEMO_USER_PASSWORD`, and inserts their `profiles`.
  3. **`seed_faq.py`** embeds FAQ questions with the frozen `OnnxEncoder` and upserts them with `PgVectorStore`. It refuses to run if `config.json.encoder.dim != vector_dim()`.
  4. **Repository** maps PostgREST errors to `StoreError`/`NotFound`, uses no SDK exceptions outside the adapter, and stores datetimes as ISO UTC.
- Acceptance:
  - `supabase db push && psql "%SUPABASE_DB_URL%" -f supabase/seed/01_buildings.sql …` → no errors
  - `python scripts/seed_demo_users.py` → `3 users ready`
  - `python scripts/seed_faq.py` → `embedded 24 faq rows (dim=384)`
  - `pytest services/ai/tests/contracts/test_repository_contract.py -q` → `passed`
- Hands off: a working online container to every later P4 task.
- Notes: no real GJU staff names and no real addresses. The seed lint `python scripts/check_seed_contacts.py` (Files added) asserts that every email in `supabase/seed/` is in `DEMO_EMAIL_ALLOWLIST`.

<a id="p4-4"></a>
## P4.4 — Notifications: RecipientPolicy, AllowlistedNotifier, GmailSmtpNotifier, InAppNotifier and outbox

- [ ] Done
- Depends on: P4.3
- Est: 1.5 h · Cut: no
- Files:
  - services/ai/campuspulse_ai/domain/values.py (`RecipientPolicy`)
  - services/ai/campuspulse_ai/adapters/notify/{allowlist.py, gmail_smtp.py, inapp.py, outbox.py}
  - services/ai/tests/unit/{test_allowlist.py, test_gmail_smtp.py}
- Interfaces: implements `Notifier`.
  ```python
  class RecipientPolicy:
      def __init__(self, allowlist: frozenset[str]) -> None: ...      # lower-cased, exact match; empty → reject all
      def check(self, address: str) -> None: ...                       # RecipientNotAllowed
  class AllowlistedNotifier:  # Notifier (decorator)
      def __init__(self, inner: Notifier, policy: RecipientPolicy, repo: Repository) -> None: ...
      def send(self, msg: OutboxMessage) -> OutboxMessage: ...         # reject → repo.save_outbox(status="rejected", error=reason); raise RecipientNotAllowed
  class GmailSmtpNotifier:  # Notifier
      def __init__(self, host: str, port: int, user: str, app_password: str, *, sender_name: str = "CampusPulse (demo)",
                   use_ssl: bool, timeout_s: float, max_retries: int, backoff_s: float,
                   smtp_factory: Callable[..., smtplib.SMTP] | None = None) -> None: ...
      def send(self, msg: OutboxMessage) -> OutboxMessage: ...         # status="sent", provider_id=Message-ID
  class InAppNotifier:  # Notifier
      def __init__(self, repo: Repository) -> None: ...                # writes notifications row; status="sent", provider_id="inapp:<id>"
  ```
- Config keys: Settings:
  - `GMAIL_SMTP_USER` (= `campuspulse.support@gmail.com`), `GMAIL_APP_PASSWORD`;
  - `SMTP_HOST` (default `smtp.gmail.com`), `SMTP_PORT` (default 587; 465 ⇒ SSL);
  - `SMTP_TIMEOUT_S` (10), `SMTP_MAX_RETRIES` (2), `SMTP_BACKOFF_S` (1.0);
  - `DEMO_EMAIL_ALLOWLIST`.
- Steps:
  1. **The SMTP flow:**
     - port 587: `smtplib.SMTP(host, port, timeout)` → `ehlo` → `starttls(context=ssl.create_default_context())` → `login`;
     - port 465: `SMTP_SSL`;
     - then `send_message(EmailMessage)` with plain-text and HTML bodies;
     - a footer "Demo message from an integration-ready prototype; sent to a developer-owned inbox."
  2. **Error mapping** to the new `NotificationError(retryable: bool)` ([LD-15](../PLAN.md#ld-15)):
     - `SMTPAuthenticationError` (535) → not retryable;
     - `SMTPRecipientsRefused` or a 5xx response → not retryable;
     - `SMTPServerDisconnected`, `SMTPConnectError`, `socket.timeout`, `OSError` (port blocked) or a 4xx response → retryable, with exponential backoff up to `max_retries`, then raise.
  3. **`ActUseCase` catches `NotificationError`** → outbox `status="failed"` plus `error`. Triage never fails because of email.
  4. **Gmail consumer limits:** 500 recipients/day (verified). Sends are counted per day in `outbox`. Above `SMTP_DAILY_CAP` (default 100, so the demo can never hit Google's cap), status is `"deferred"`.
  5. **Tests:**
     - `real.person@gju.edu.jo` → `RecipientNotAllowed`, outbox rejected, inner call count 0;
     - an empty allow-list rejects everything;
     - case-insensitive exact match, with no subdomain or plus-address wildcards;
     - the SMTP fake raising 535 → non-retryable;
     - 421 → retried twice;
     - the Message-ID is recorded.
  6. **`ActUseCase` checks booking attendees** with the same `RecipientPolicy` before `CalendarProvider.book` (§3.13). That test lives in P4.8.
- Acceptance:
  - X4.7 → `passed`
  - `pytest services/ai/tests/unit/test_gmail_smtp.py -q` → `≥ 6 passed`
  - `python -c "import campuspulse_ai.composition.offline, sys; assert not any(m.startswith('campuspulse_ai.adapters.notify') for m in sys.modules)"` → exit 0 (the same assertion is added to `tests/test_architecture.py`)
- Hands off: the notifier chain to P4.8, P4.9 and P4.10.
- Notes:
  - Secrets come only from env (Render secret), never logged. `repr(GmailSmtpNotifier)` masks the password, and a test asserts it.
  - Gmail SMTP sent to the **same** account may land only in *Sent* (UNVERIFIED). The demo student inbox should be a second developer-owned Gmail address, which is in the allow-list.

<a id="p4-5"></a>
## P4.5 — Write VectorFAQRetriever and hand-tune `tau_faq`

- [ ] Done — partial: VectorFAQRetriever and tune_faq.py are merged. Still to do: seed_faq + the real tau_faq tuning once the P1.6 encoder is merged.
- Depends on: P4.2, P4.3
- Est: 1 h · Cut: no
- Files:
  - services/ai/campuspulse_ai/adapters/faq/retriever.py
  - config/hand_tuned.yaml (Files added: `tau_faq`, `tau_inc`; read by `train.py` stage C, [LD-11](../PLAN.md#ld-11))
  - services/ai/tests/unit/test_faq.py
  - scripts/tune_faq.py (Files added)
- Interfaces: implements `FAQRetriever`.
  ```python
  class VectorFAQRetriever:  # FAQRetriever
      def __init__(self, vectors: VectorStore, encoder: SentenceEncoder, collection: str = "faq") -> None: ...
      def search(self, text: str, lang: Lang, k: int) -> list[FAQHit]: ...   # Arabizi → search "ar"; StoreError propagates (Act degrades to ticket)
  ```
- Config keys: `thresholds.tau_faq` (FrozenConfig, written from `config/hand_tuned.yaml`, default 0.75)
- Steps:
  1. Embed the query with the same `query_prefix` as everything else ([LD-9](../PLAN.md#ld-9)).
  2. `scripts/tune_faq.py` runs 30 hand-written questions (15 answerable, 15 not) against the seed FAQ and prints precision and recall per threshold. Pick the lowest τ with precision 1.0 and record it in `hand_tuned.yaml`.
  3. Tests (LocalNumpyVectorStore + HashingEncoder): language filter, k, ordering, empty store → `[]`.
- Acceptance:
  - `pytest services/ai/tests/unit/test_faq.py -q` → `passed`
  - `python scripts/tune_faq.py` → `chosen tau_faq=0.7x precision=1.00 recall≥0.6`
- Hands off: FAQ answer-first to P4.8.
- Notes: never generate policy text. The answer is the retrieved text plus its source, with `[demo]` when `is_demo`.

<a id="p4-6"></a>
## P4.6 — Ticket sinks: SupabaseSink, RetryingSink, LinearSink and docs/integrations.md

- [ ] Done
- Depends on: P4.0 (Linear IDs), P4.3
- Est: 2.5 h · Cut: no
- Files:
  - services/ai/campuspulse_ai/adapters/integrations/{supabase_sink.py, linear.py, retrying.py (Files added)}
  - config/integrations.yaml
  - docs/integrations.md
  - services/ai/tests/unit/{test_linear_sink.py, test_retrying_sink.py}
  - services/ai/tests/fixtures/linear/*.json
- Interfaces: implements `TicketSink`.
  ```python
  class LinearSink:  # TicketSink
      name = "linear"
      def __init__(self, api_key: str, webhook_secret: str, mapping: LinearMapping, http: "httpx.Client", clock: Clock, *, tolerance_s: int = 60) -> None: ...
      def create(self, ticket: Ticket) -> TicketLink: ...        # idempotent: existing link → return it; else issueCreate
      def update_status(self, ticket: Ticket) -> None: ...       # issueUpdate(stateId) + priority
      def close(self, ticket: Ticket) -> None: ...               # → completed state
      def handle_inbound(self, payload: bytes, signature: str) -> InboundEvent | None: ...   # Unauthorized on bad HMAC / stale timestamp
  class RetryingSink:  # TicketSink (decorator)
      def __init__(self, inner: TicketSink, max_attempts: int, base_backoff_s: float, sleep: Callable[[float], None] = time.sleep) -> None: ...
  ```
- Config keys: Settings `LINEAR_API_KEY`, `LINEAR_WEBHOOK_SECRET`, `SINK_RETRY_MAX` (3), `SINK_RETRY_BASE_S` (0.5), `ENABLE_SINKS`. In `config/integrations.yaml`: `enabled: [supabase, linear]`, `linear.team_by_office`, `linear.state_by_status`, `linear.priority_map {high: 2, medium: 3, low: 4, safety: 1}` and `linear.label_by_category`.
- Steps:
  1. **GraphQL** goes to `https://api.linear.app/graphql` with header `Authorization: <LINEAR_API_KEY>`. Personal keys take no `Bearer` (verified).
  2. `issueCreate(input:{teamId,title,description,priority,dueDate,labelIds})`:
     - the description contains `cp-ticket:<id>`, the decision trace summary and the "demo data" banner;
     - `dueDate` = the `sla_due_at` date in Asia/Amman as `YYYY-MM-DD`;
     - the field names are verified once via `smoke_linear.py` introspection (UNVERIFIED in docs).
  3. **Inbound:**
     - `hmac.compare_digest(hex(hmac_sha256(secret, raw_body)), Linear-Signature)`;
     - reject if `|now − webhookTimestamp| > 60 s`;
     - handle only `type=="Issue"`, `action=="update"` with `updatedFrom.stateId`;
     - map `data.state.type`: `unstarted`/`backlog` → open, `started` → in_progress, `completed` → resolved, `canceled` → closed (payload shape UNVERIFIED; log the first real payload into `tests/fixtures/linear/`).
  4. **Retry:**
     - httpx timeouts, 5xx and 429 → `SinkError(retryable=True)`;
     - GraphQL `errors` or 4xx → `SinkError(retryable=False)`;
     - the last error is written to `ticket_links.last_error` by `ActUseCase`.
  5. **`docs/integrations.md`** covers the `TicketSink` contract, the Linear field mapping, the webhook verification and the outbound `WebhookSink` payload schema (documented even though cut #2).
  6. **Tests** (`respx`):
     - idempotent create (2 calls → 1 HTTP);
     - 503 → retried then raised;
     - bad signature → `Unauthorized`;
     - stale timestamp → `Unauthorized`;
     - state mapping.
- Acceptance: `pytest services/ai/tests/unit/test_linear_sink.py services/ai/tests/unit/test_retrying_sink.py -q` → `≥ 8 passed`
- Hands off: sinks to P4.8 and P4.9.
- Notes:
  - Linear webhooks retry 3 times (1 min, 1 h, 6 h) and need a 200 within 5 s (verified), so the webhook route acks after verification and processes inline only if under 1 s, otherwise via `BackgroundTasks`.
  - The free plan is believed to cap at 250 issues (UNVERIFIED). `simulate_pulse.py` creates one incident issue, not N.

<a id="p4-7"></a>
## P4.7 — Calendar: SlotsTableCalendar and FallbackCalendar

- [ ] Done
- Depends on: P4.3
- Est: 1 h · Cut: no. GoogleCalendarProvider is P4.16, cut #5.
- Files:
  - services/ai/campuspulse_ai/adapters/calendar/{slots_table.py, fallback.py (Files added)}
  - services/ai/tests/unit/test_calendar.py
- Interfaces: implements `CalendarProvider`.
  ```python
  class SlotsTableCalendar:  # CalendarProvider
      def __init__(self, repo: Repository, clock: Clock) -> None: ...
      def find_slot(self, advisor_ids: Sequence[str], window: tuple[datetime, datetime], office_hours: OfficeHours) -> Slot | None: ...
      def book(self, slot: Slot, attendees: Sequence[str], title: str) -> Booking: ...   # claim_slot false → retry next slot once → CalendarUnavailable
  class FallbackCalendar:  # CalendarProvider
      def __init__(self, providers: Sequence[CalendarProvider]) -> None: ...           # CalendarUnavailable → next
  ```
- Config keys: Settings `GOOGLE_SERVICE_ACCOUNT_JSON` and `DEMO_CALENDAR_IDS` (both unset ⇒ slots only)
- Steps:
  1. The earliest free slot within `[now, now + sla_hours]` and office hours (Asia/Amman).
  2. A race-safe claim.
  3. Tests: earliest slot, outside office hours skipped, double booking prevented, fallback order.
- Acceptance: `pytest services/ai/tests/unit/test_calendar.py -q` → `≥ 5 passed`
- Hands off: the calendar to P4.8.

<a id="p4-8"></a>
## P4.8 — Action engine: the full ActUseCase (FAQ, ticket, booking, safety alert, provisional and finalize)

- [ ] Done
- Depends on: P4.4–P4.7, [P3.9](P3_intelligence.md#p3-9) (act v0)
- Est: 2 h · Cut: no. `cases` writes are B-list cut.
- **UD-10:** tickets (Supabase and Linear) use `understanding.ticket_title` and `ticket_body`. The student notification uses `understanding.student_reply`, and the FAQ answer stays retrieved-and-cited, never generated. Entities fill the `building`/`room` fields when the student did not pick a location.
- Files:
  - services/ai/campuspulse_ai/application/use_cases/act.py
  - services/ai/tests/unit/test_act_usecase.py
- Interfaces:
  ```python
  class ActUseCase:
      def __init__(self, planner: ActionPlanner, faq: FAQRetriever, sinks: Sequence[TicketSink], calendar: CalendarProvider, notifier: Notifier,
                   recipients: RecipientPolicy, repo: Repository, clock: Clock, config: FrozenConfig, actions: ActionsConfig) -> None: ...
      def run(self, pred: Prediction, req: Request, provisional: bool) -> ActionOut: ...
      def finalize(self, ticket: Ticket) -> list[ActionOut]: ...   # deferred booking/alert after staff confirm
  ```
- Config keys: `config/actions.yaml` ([P3.8](P3_intelligence.md#p3-8)), `thresholds.tau_faq`
- Steps:
  1. **`faq_answer`:** if top hit ≥ τ → message = answer + source + `[demo]`. Otherwise a ticket and "I'm not sure. I've opened a ticket so a person can answer."
  2. **`ticket`:**
     - `sla_due_at = now + sla_hours`;
     - `SupabaseSink` first, then the others via `RetryingSink`;
     - `SinkError` → link `last_error` and continue;
     - tags include `exam-in-progress` if the `exam_now` evidence fires (SPEC table).
  3. **`booking`:**
     - only if `not provisional`;
     - `RecipientPolicy.check` on each attendee **before** `calendar.book`;
     - then email the student and advisor demo inboxes;
     - plus a ticket (`also_ticket`).
  4. **`safety_alert`:** always, even when provisional. Send `kind="alert"` with the text "call campus security now (demo)" plus a ticket at Linear priority 1.
  5. **Notifications:** every `Notifier.send` → `repo.save_outbox`. `RecipientNotAllowed`/`NotificationError` → outbox rejected/failed, and the response `message` still succeeds.
  6. **Tests:**
     - each kind;
     - provisional defers booking but not the alert;
     - `finalize` fires the deferred booking;
     - a non-allow-listed attendee never reaches `FakeCalendar.book`;
     - a sink failure is recorded and does not raise.
- Acceptance: `pytest services/ai/tests/unit/test_act_usecase.py -q` → `≥ 8 passed`
- Hands off: the full action engine to the triage and feedback paths and to P4.14.

<a id="p4-9"></a>
## P4.9 — Ticket lifecycle: SyncTicketUseCase, webhook route, `/tickets/{id}/status` and SLA scanner

- [ ] Done
- Depends on: P4.6, P4.8
- Est: 1.5 h · Cut: no
- Files:
  - services/ai/campuspulse_ai/application/use_cases/{sync_ticket.py, escalate_sla.py}
  - services/ai/campuspulse_ai/frameworks/routes/integrations.py
  - services/ai/campuspulse_ai/frameworks/routes/tickets.py (Files added)
  - services/ai/campuspulse_ai/frameworks/fastapi_app.py (lifespan task)
  - services/ai/tests/unit/{test_sync_ticket.py, test_escalate_sla.py}
- Interfaces:
  ```python
  class SyncTicketUseCase:
      def run(self, sink_name: str, payload: bytes, signature: str) -> Ticket | None: ...
      def from_dashboard(self, ticket_id: str, new_status: TicketStatus, actor: Principal) -> Ticket: ...   # staff of that office | admin
  class EscalateSlaUseCase:
      def run(self, now: datetime) -> list[str]: ...   # escalated ticket ids
  # POST /v1/integrations/linear/webhook (raw body; no service token — HMAC is the auth) · POST /v1/tickets/{id}/status {status} (service token + staff/admin)
  ```
- Config keys: Settings `SLA_SCAN_MINUTES` (5)
- Steps:
  1. The lifespan starts an `asyncio` task: every N minutes run `EscalateSlaUseCase.run(clock.now())` in a thread. There is one uvicorn worker (§3.15).
  2. Escalation does `priority.bump()`, `status=escalated`, `escalated_at`, `sinks.update_status` and an in-app staff notification.
  3. A status change sends an in-app notification to the student. Resolved also sends an email if the student inbox is allow-listed.
  4. Tests:
     - an overdue ticket escalates exactly once;
     - high stays high;
     - a webhook with a bad signature → 401 and no DB write;
     - a dashboard change by other-office staff → 403.
- Acceptance: `pytest services/ai/tests/unit/test_sync_ticket.py services/ai/tests/unit/test_escalate_sla.py -q` → `≥ 6 passed`
- Hands off: the lifecycle to P4.14 and the P5 staff dashboard.

<a id="p4-10"></a>
## P4.10 — Pulse: WindowedCentroidDetector, ResolveIncidentUseCase, broadcast and simulate_pulse.py

- [ ] Done
- Depends on: P4.2, P4.8
- Est: 2 h · Cut: no. Per-building subscriptions are P4.19 (cut).
- Files:
  - services/ai/campuspulse_ai/adapters/pulse/incident_detector.py
  - services/ai/campuspulse_ai/application/use_cases/resolve_incident.py
  - services/ai/campuspulse_ai/frameworks/routes/incidents.py
  - scripts/simulate_pulse.py
  - config/simulation/wifi_m.yaml (Files added: 8 reports EN/AR/Arabizi, building M)
  - services/ai/tests/unit/test_incident_detector.py
- Interfaces: implements `IncidentDetector`.
  ```python
  class WindowedCentroidDetector:  # IncidentDetector
      def __init__(self, repo: Repository, vectors: VectorStore, clock: Clock, tau_inc: float, window_min: int, min_reports: int = 3, bump_at: int = 6) -> None: ...
      def detect(self, req: Request, pred: Prediction, embedding: Sequence[float]) -> IncidentDecision: ...
  class ResolveIncidentUseCase:
      def run(self, incident_id: str, actor: Principal) -> Incident: ...   # close merged tickets + external issue; notify all reporters
  # POST /v1/incidents/{id}/resolve (staff of office | admin)
  ```
- Config keys: `thresholds.tau_inc` (`config/hand_tuned.yaml`, default 0.80), Settings `INCIDENT_WINDOW_MIN` (30)
- Steps:
  1. **Detection** needs a location. It runs `vectors.search("requests", e, k=50, min_sim=0, filters={building_id, category, since, with_embedding: true})`. The centroid is the normalised mean of the returned embeddings plus `e`. Members are rows with cos(centroid) ≥ τ_inc. If members ≥ 3 → new, or attach to the open incident from `repo.open_incidents`.
  2. **The incident** has priority = max(member priorities), bumped once at ≥ 6, capped at high. Exactly **one** incident ticket goes through sinks. Member tickets get `status=merged` and `incident_id`.
  3. **Broadcast:** one `kind="broadcast"` notifier message per reporter, through the allow-list. Reporters without an allow-listed inbox get in-app only.
  4. **The simulator** posts each YAML line to `/v1/triage` with `student_alias=sim-0N`, `simulated=true` and `location.building=M`, at `--interval` seconds (default 4). It prints incident status after each post via `GET /v1/incidents?open=1` (Files added: read route) and is labelled "SIMULATED TRAFFIC" in the output and in `requests.simulated`.
  5. **Tests** (FrozenClock, LocalNumpy):
     - 2 reports → none, 3 → new, 4 → attach;
     - 6 → bump;
     - a different building → separate;
     - outside the window → none;
     - resolve closes members and notifies reporters exactly once each.
- Acceptance:
  - `pytest services/ai/tests/unit/test_incident_detector.py -q` → `≥ 7 passed`
  - X4.3 against local uvicorn → `incident created … reports=3`
- Hands off: incidents and Realtime rows to the P5 Pulse page; the simulator to the video (moment 2).
- Notes: `tau_inc` is checked on the **real** encoder in X4.3. If the 8 Wi-Fi paraphrases don't cluster at 0.80, lower it in `hand_tuned.yaml` with the measured similarities recorded. No code change.

<a id="p4-11"></a>
## P4.11 — Red team: PerturbationGenerator, RedTeamScorer, RunRedTeamUseCase, route and offline CLI

- [ ] Done
- Depends on: [P3.9](P3_intelligence.md#p3-9); P2 (`data/our_test/`, `evaluate.py`)
- Est: 1.5 h · Cut: no. The LLM generator is P4.17 (cut #7).
- Files:
  - services/ai/campuspulse_ai/adapters/redteam/{perturbation.py, scorer.py}
  - services/ai/campuspulse_ai/application/use_cases/run_redteam.py
  - services/ai/campuspulse_ai/frameworks/routes/redteam.py
  - services/ai/campuspulse_ai/frameworks/cli/evaluate.py (`--redteam` flag)
  - services/ai/tests/unit/test_redteam.py
- Interfaces: implements `RedTeamGenerator` (`PerturbationGenerator(rows: Sequence[OurTestRow], lexicons: Path)`).
  ```python
  class RedTeamScorer:
      def score(self, item: RedTeamItem, core: CoreResult, outcome: Outcome, base: CoreResult | None) -> tuple[bool, str]: ...
  class RunRedTeamUseCase:
      def run(self, n: int, styles: Sequence[str], seed: int, use_llm_generator: bool = False) -> Scorecard: ...
  # POST /v1/redteam/run {n ≤ 200, styles, seed} (admin) → Scorecard
  ```
- Config keys: Settings `REDTEAM_MAX_N` (200)
- Steps:
  1. The 10 styles and pass rules follow §2.4.
  2. Online, it runs with memory ON. The offline CLI uses `InMemoryRepository` and writes `reports/redteam/<ts>.json`.
  3. Failures → `data/robustness/candidates_<run>.csv` with `needs_human_check=True`.
  4. Tests:
     - deterministic generation by seed;
     - an injection item passes only with the flag and no priority raise;
     - off_topic → OUT_OF_SCOPE;
     - distress_adjacent → distress.
- Acceptance:
  - `pytest services/ai/tests/unit/test_redteam.py -q` → `passed`
  - `python services/ai/evaluate.py --redteam --n 200 --seed 42` → `scorecard overall=0.xx written reports/redteam/`
- Hands off: the scorecard to the P5 Model lab and the report §4.

<a id="p4-12"></a>
## P4.12 — Remaining routes and auth hardening: `/batch`, `/metrics`, Supabase JWT role verification

- [ ] Done
- Depends on: P4.3, P4.11
- Est: 1 h · Cut: no
- Files:
  - services/ai/campuspulse_ai/frameworks/routes/{batch.py, metrics.py}
  - services/ai/campuspulse_ai/frameworks/auth.py
  - services/ai/tests/contracts/test_routes_auth.py
- Interfaces:
  ```python
  # POST /v1/batch (multipart file=csv, use_llm=false) → text/csv request_id,category,priority (BatchPredictUseCase from container.offline; same bytes as predict.py)
  # GET  /v1/metrics → {benchmark, coverage, fairness, ablations, confusions, router: RouterStats, memory: MemoryStats, redteam: [Scorecard], artifact}
  def principal(...) -> Principal: ...   # AUTH_MODE=supabase_jwt: client.auth.get_user(jwt) → profiles row (cached 60 s by sub) → role/office/alias
  ```
- Config keys: Settings `AUTH_MODE=supabase_jwt` (production default), `REPORTS_DIR` (default `reports/`, copied into the image)
- Steps:
  1. `/batch` streams rows through `BatchPredictUseCase`. A test asserts byte-identity with `predict.py` on `data/raw/validation.csv`.
  2. `/metrics` reads `reports/*.json` and adds live router, memory and redteam stats.
  3. JWT verification: the role comes **only** from `profiles`, never from client headers, in `supabase_jwt` mode.
  4. Tests:
     - a student calling `/feedback` → 403;
     - staff calling `/redteam/run` → 403;
     - a missing service token → 401 on every route except the webhook and `/health`.
- Acceptance:
  - `pytest services/ai/tests/contracts/test_routes_auth.py -q` → `passed`
  - `curl -s -H "Authorization: Bearer %AI_SERVICE_TOKEN%" -F file=@data/raw/validation.csv localhost:8000/v1/batch > %TEMP%\b.csv && fc /b %TEMP%\b.csv reports\predictions_val_check.csv` → `no differences encountered`
- Hands off: the complete SPEC §7 surface. `openapi.json` is regenerated (`python scripts/export_openapi.py`).

<a id="p4-13"></a>
## P4.13 — Deploy to Render: Docker image, memory and latency budget, SMTP from Render, keep-warm

- [ ] Done
- Depends on: P4.12; the encoder pre-release `models-v1-rcN` on GitHub Releases, published from [P1.19](P1_scored_core.md#p1-19) on ([LD-5](../PLAN.md#ld-5))
- Est: 1.5 h · Cut: no
- Files:
  - services/ai/Dockerfile
  - render.yaml (repo root, [LD-4](../PLAN.md#ld-4))
  - scripts/measure_rss.py
  - scripts/keep_warm.ps1
  - scripts/keep_warm.sh (Files added)
  - reports/render_rss.json
- Interfaces: `/health` reports `rss_mb`, `encoder_loaded`, `artifact`, `sha`, `sinks`, `llm_tiers` and `vector_store`.
- Config keys:
  - Render env (secrets, `sync: false`): `AI_SERVICE_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_*`, `ENABLE_LLM`, `GMAIL_SMTP_USER`, `GMAIL_APP_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`, `DEMO_EMAIL_ALLOWLIST`, `LINEAR_API_KEY`, `LINEAR_WEBHOOK_SECRET`, `ENABLE_SINKS`;
  - `ORT_INTRA_OP_THREADS=1`, `AUTH_MODE=supabase_jwt`, `TZ=Asia/Amman`.
- Steps:
  1. **The Dockerfile** builds from the repo-root context:
     - base `python:3.11-slim`;
     - `pip install --no-cache-dir -r services/ai/requirements-api.txt`;
     - `COPY` `services/ai`, `config`, `models/frozen` (committed parts), `reports` and `scripts/fetch_models.py`;
     - `RUN python scripts/fetch_models.py --verify` (release asset, sha256 against MANIFEST);
     - a non-root user;
     - `CMD uvicorn api:app --app-dir services/ai --host 0.0.0.0 --port ${PORT:-10000} --workers 1`.
  2. **`render.yaml`:** `type: web`, `runtime: docker`, `plan: starter`, `dockerfilePath: ./services/ai/Dockerfile`, `dockerContext: .`, `healthCheckPath: /health`, `autoDeployTrigger: commit` (the brief's `autoDeploy: true` is deprecated, verified), and `envVars` with `sync: false`.
  3. **Local simulation of Render** (do this first):
     - `docker build -f services/ai/Dockerfile -t cp-ai .`
     - `docker run --rm -m 512m --cpus 0.5 -p 8000:10000 --env-file .env cp-ai`
     - `python scripts/measure_rss.py --remote http://localhost:8000 --n 100`
  4. **`measure_rss.py`:**
     - sends 100 sequential `/v1/triage` calls (a mix of EN/AR/Arabizi from `data/our_test`);
     - polls `/health` `rss_mb`;
     - prints `rss_mb_max`, `p50_ms`, `p95_ms` and an OK/FAIL against 400 MB / 1500 ms;
     - writes `reports/render_rss.json`.
  5. **Deploy to Render.** Then run X4.6, and run `python scripts/smoke_smtp.py` in the Render shell again with the real `GmailSmtpNotifier`.
  6. **`keep_warm.ps1`** loops `Invoke-WebRequest $env:RENDER_URL/health` every 10 min for `-Hours N`. It also runs `select 1` against Supabase through `/health?deep=1` so the free project never hits 7 days idle.
  7. **If the budget fails**, apply §3.17 in order:
     - (a) lazy encoder load;
     - (b) `EXPLAIN_MAX_OCCLUSIONS=12` for latency;
     - (c) **Render Standard (2 GB, about $25/mo), which needs user approval**;
     - (d) never the M1-only override for the video.
- Acceptance:
  - `docker run … -m 512m --cpus 0.5` + `python scripts/measure_rss.py --remote http://localhost:8000 --n 100` → `rss_mb_max<=400 p95_ms<=1500 OK`
  - `curl -s %RENDER_URL%/health` → `"status":"ok"`, `"artifact":"v1"`, `"encoder_loaded":true`
  - X4.6 → `OK`; numbers recorded in the PLAN.md decisions log
- Hands off: `AI_SERVICE_URL` for Netlify ([P5.6](P5_frontend.md#p5-6), [P6.5](P6_ship.md#p6-5)); the keep-warm procedure for P6.

<a id="p4-14"></a>
## P4.14 — Test the lifecycle end to end (fakes) and run it once against real Linear and Gmail

- [ ] Done
- Depends on: P4.8–P4.13
- Est: 1 h · Cut: no
- Files:
  - services/ai/tests/e2e/test_lifecycle.py
  - scripts/smoke_integrations.py (Files added)
- Interfaces: none new
- Steps:
  1. The fake e2e runs triage → `ticket` → FakeSink link → `SyncTicketUseCase.run("linear", signed payload)` → resolved → `notifications` row + outbox email row. It runs the same with an incident: 3 located reports → one incident ticket → resolve → 3 notifications.
  2. The real run uses `smoke_integrations.py`, which prints each hop. The developer moves the Linear issue to Done; the script polls `tickets.status` for 60 s.
  3. Paste the output into the decisions log (X4.2).
- Acceptance: X4.1 → `passed`; X4.2 → `ticket <id> status=resolved via linear webhook; notification row created`
- Hands off: P4 exit.

## Cut-flagged P4 tasks (built only if P4 finishes early, in this order)

> **User decisions:**
> - P4.15, P4.16 and P4.17 are **future work** ([UD-3](../PLAN.md#ud-3)).
> - P4.18, P4.19, P4.20 and the new P4.21 are **in scope after the core is green** ([UD-7](../PLAN.md#ud-7)), in the order set there.

| Task | Cut | What it is | Not wired when cut |
| --- | --- | --- | --- |
| P4.15 `WebhookSink` (HMAC-SHA256 header `X-CampusPulse-Signature`, `adapters/integrations/webhook.py`, 1 h) | #2 | outbound JSON to `OUTBOUND_WEBHOOK_URL` | absent from `config/integrations.yaml enabled`; never constructed in `build_online` |
| P4.16 `GoogleCalendarProvider` (`adapters/calendar/google.py`, `google-api-python-client` in `requirements-google.txt`, 2 h) | #5 | creates events **on shared demo calendars only, with no attendees** (service accounts cannot invite without domain-wide delegation); the invite email goes through the allow-listed notifier | `GOOGLE_SERVICE_ACCOUNT_JSON` unset → `FallbackCalendar([SlotsTableCalendar])` |
| P4.17 `LLMRedTeamGenerator` (`adapters/redteam/llm_generator.py`, 1 h) | #7 | per-style generation through `OpenRouterOracle`'s HTTP client, labels marked `needs_human_check` | `use_llm_generator` ignored; `PerturbationGenerator` only |
| P4.18 `cases` table writes (0.5 h) | B-list | `repo.save_case` on booking | the booking stays in `tickets` plus `outbox` |
| P4.19 Per-building subscriptions (0.75 h) | B-list | `building_subscriptions(alias, building_id)` + broadcast fan-out | broadcast to reporters only |
| P4.20 `POST /v1/admin/reindex` (0.5 h) | B-list | re-embed FAQ from Render | use `scripts/seed_faq.py` from the dev machine |

<a id="p4-21"></a>
## P4.21 — Recurring problems: cluster stored request embeddings ([UD-6](../PLAN.md#ud-6))

- [ ] Done
- **Goal:** rank the problems students report again and again (by meaning, building and category, across all time or a window), so staff can fix root causes before they recur.
- **Depends on:** P4.10 (`requests` vectors in pgvector, the centroid logic of `WindowedCentroidDetector`), P4.12 (route auth).
- **Est / Cut:** 1.5 h · after core green ([UD-7](../PLAN.md#ud-7)).
- **Files:**
  - `domain/values.py` (+ `ProblemCluster`)
  - `domain/ports.py` (+ `ProblemClusterer`)
  - `adapters/pulse/recurring.py`
  - `application/use_cases/recurring_problems.py`
  - `frameworks/fastapi_app.py` (route)
  - `tests/test_recurring_problems.py`
- **Interfaces:**
  ```python
  @dataclass(frozen=True)
  class ProblemCluster:
      cluster_id: str
      category: Category
      building_id: str | None
      size: int
      first_seen: datetime
      last_seen: datetime
      representative_text: str      # medoid request text (alias-only, no PII)
      sample_request_ids: tuple[str, ...]

  class ProblemClusterer(Protocol):
      def cluster(self, items: Sequence[VectorHit], tau: float, min_size: int) -> list[ProblemCluster]: ...

  class GreedyCentroidClusterer:      # adapters/pulse/recurring.py; same cosine/centroid maths as WindowedCentroidDetector
      def cluster(self, items: Sequence[VectorHit], tau: float, min_size: int) -> list[ProblemCluster]: ...

  class RecurringProblemsUseCase:
      def __init__(self, repo: Repository, vectors: VectorStore, clusterer: ProblemClusterer, settings: Settings, clock: Clock) -> None: ...
      def run(self, window_days: int | None, category: Category | None, building_id: str | None, top_k: int) -> list[ProblemCluster]: ...
  ```
  Route: `GET /v1/insights/recurring?window_days=&category=&building=&top_k=` (staff and admin roles only).
- **Config keys:**
  - `insights.tau_cluster` (default = `FrozenConfig.thresholds.tau_inc`)
  - `insights.min_size` (3)
  - `insights.top_k` (10)
  - `insights.default_window_days` (null = all time)

  Hand-tuned values go in `config/hand_tuned.yaml` ([LD-11](../PLAN.md#ld-11)).
- **Steps:** port → `ProblemCluster` → errors (`StoreError` propagates as 503) → tests with `InMemoryRepository` + `LocalNumpyVectorStore` + `HashingEncoder` → adapter → use case → route.
- **Acceptance:**
  - `pytest services/ai/tests/test_recurring_problems.py -q` → `4 passed`:
    1. three near-identical "projector broken in building H" requests over 3 weeks plus two unrelated ones → the top cluster has `size == 3`;
    2. a clique below `min_size` is not returned;
    3. the category filter works;
    4. the route returns 403 for the student role.
  - Against Supabase (marker `supabase`): after `scripts/simulate_pulse.py`, `curl.exe -H "Authorization: Bearer $STAFF_JWT" "$AI_URL/v1/insights/recurring?top_k=5"` → JSON array; the first item's `size` ≥ the simulated burst.
- **Hands off:** the `/v1/insights/recurring` DTO to [P5.20](P5_frontend.md#p5-20).
- **Notes:** offline containers never construct it, because it reads only pgvector `requests`. Returns aliases, never student identities.

## P4 risks and fallbacks

| Risk | Fallback |
| --- | --- |
| **SMTP blocked from Render** (free tier verified blocked; Starter believed to be open) | P4.0 detects it on day one. Fall back to `InAppNotifier`, with outbox `status="simulated"` and in-app notifications, plus a user decision on the Gmail API over HTTPS or local recording. |
| **RSS > 400 MB or p95 > 1.5 s on Starter** | Brief §3.17 ladder: (1) lazy load → (2) fewer occlusions → (3) Render Standard with user approval. Never M1-only for the video. |
| **Linear free plan lacks webhooks or the issue cap is hit** | Inbound sync shown via `/v1/tickets/{id}/status`. Archive demo issues after each rehearsal (`smoke_linear.py --archive-demo`). |
| `tau_inc` does not cluster the 8 Wi-Fi reports | Measure and set it in `hand_tuned.yaml`. **Cut #6 does not apply**: detection is core, only map visuals are cuttable. |
| P4 overruns | Cut P4.15–P4.20 and S1 first (they are already cut-flagged). Then, per the brief's sequence, the `/batch` upload UI (P5), with the route kept. Never X4.1–X4.8. |

## P4 decisions logged during this phase
- [ ] Day-one smoke results (P4.0): SMTP port from Render (465/587/blocked), Linear webhooks on Free, issue cap
- [ ] Gmail sender `campuspulse.support@gmail.com` + allow-listed demo inboxes ([OQ-6](../PLAN.md#oq-6))
- [ ] `tau_faq` value in `config/hand_tuned.yaml` (with precision/recall from `tune_faq.py`)
- [ ] `tau_inc` value in `config/hand_tuned.yaml` (with measured Wi-Fi similarities)
- [ ] RLS check result (X4.4) and pgvector contract result (X4.5)
- [ ] Render memory/latency result (X4.6): rss_mb_max, p95_ms; Starter kept or Standard requested ([OQ-8](../PLAN.md#oq-8))
- [ ] Real-services lifecycle run (X4.2) date and output
- [ ] Cut-flagged P4.15–P4.20 built or cut
