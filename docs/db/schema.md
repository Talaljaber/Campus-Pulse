# Database schema (as built) — owner: DB stream

Supabase project `efsanbaklpiakhsndhph` (Postgres 17.11, pgvector 0.8.2). Every object below is created by a file in [`supabase/migrations/`](../../supabase/migrations/); nothing is changed by hand. Design: [ARCHITECTURE §3.14](../ARCHITECTURE.md) (RLS) and §3.18 (vectors).

**Access model in one paragraph.** Client roles are read-only. `authenticated` users get `SELECT` policies only, and `anon` gets nothing (all table privileges revoked). Every insert, update and delete comes from the FastAPI service with the **service-role key**, which bypasses RLS and lives only in Render env. Embeddings are never visible to clients, and the vector RPCs are service-role only.

## Migrations

| Version | File | What it does |
| --- | --- | --- |
| 0001 | `0001_init.sql` | `vector` and `pgcrypto` extensions (schema `extensions`); `profiles`, `buildings`, `requests`, `predictions`; RLS on, no policies |
| 0002 | `0002_core_schema.sql` | all other SPEC §8 tables except the vector ones; `requests.simulated`, `requests.conversation_id`; indexes |
| 0003 | `0003_rls.sql` | `cp_*` helper functions, privilege revokes, every SELECT policy, `predictions_student_v` |
| 0004 | `0004_realtime.sql` | adds 6 tables to the `supabase_realtime` publication |
| 0005 | `0005_vectors.sql` | `faq`, `memory_examples`, `request_embeddings` (vector(384), HNSW), `match_vectors`, `vector_dim`, `faq_v`, `memory_examples_v` |
| 0006 | `0006_private_helpers.sql` | moves the `cp_*` helpers into schema `private` so PostgREST does not expose them as `/rpc/cp_*` |
| 0007 | `0007_repository.sql` | `requests.model_text/truncated/location_source`, `predictions.core jsonb`; RPC `bump_student_signals`; trigger that copies a ticket's `office` onto its incident |
| 0008 | `0008_fk_indexes.sql` | one index per foreign key the performance advisor flagged (cases ×4, llm_calls, memory_examples, outbox, requests.building_id, review_queue ×2) |
| 0009 | `0009_ticket_tags_outbox_deferred.sql` | D-011: `tickets.tags text[] not null default '{}'`; `outbox_status_check` re-created with `deferred` added |

**Applying a migration.** Commit the file first. Then apply the same SQL with the Supabase MCP `apply_migration`, or with `supabase db push` on a linked CLI.
- **MCP version repair.** MCP records a timestamp version. Afterwards, set the row in `supabase_migrations.schema_migrations` to the file's version and name (`0001`/`init`, …). This is what `supabase migration repair` does. It keeps the remote history identical to the file names, so a later `db push` does not re-apply anything.
- **Rebuilding from scratch** (P6): `supabase db reset` locally, or `supabase db push` to an empty project.

## TypeScript types

`supabase/types/database.types.ts` holds the generated `Database` type for `@supabase/supabase-js` (tables, views, RPC args/returns). It is DB-owned; the web app imports it from there and never edits it. Embedding columns appear as `string` (pgvector text form), but clients cannot select them anyway.

**Regenerate after every migration**, in the same commit as the migration's docs:
1. Supabase MCP `generate_typescript_types` (what produced the current file), or `npx supabase@2.121.0 gen types typescript --project-id efsanbaklpiakhsndhph > supabase/types/database.types.ts` (needs `supabase login`).
2. Keep the two-line `// GENERATED` header and update the migration number in it.
3. Check it: `npx -p typescript@5.9.3 tsc --noEmit --strict supabase/types/database.types.ts`.

**Advisors:** run MCP `get_advisors` (security and performance) after each migration. As of 0009:
- **Security:** only expected items. `request_embeddings` has RLS with no policy (intentional: service role only), and `public.rls_auto_enable()` is Supabase-managed, left alone by decision. Auth also warns that leaked-password protection is off; that is a dashboard setting (Auth › Passwords), not a migration.
- **Performance:** only `unused_index` INFO notes, expected on a near-empty database.

## Labels and enums (checked by constraints)

- **category:** `Registration`, `IT Support`, `Finance`, `Transportation`, `Facilities`, `Academic Support`
- **priority:** `low`, `medium`, `high`
- **lang:** `en`, `ar`, `arabizi` (`faq.lang` is `en`/`ar` only)
- **tier:** `tier0`, `tier1`, `tier2`, `human`
- **requests.status:** `received`, `needs_clarification`, `clarified`, `decided`, `human_review`, `out_of_scope`, `distress`, `actioned`, `resolved`, `merged`
- **tickets.status:** `open`, `in_progress`, `resolved`, `closed`, `escalated`, `merged`
- **outbox.status:** `queued`, `sent`, `failed`, `rejected`, `simulated`, `deferred` (D-011: held back by the action engine, reason in `error`)
- **tickets.tags** are free text, not checked. In use (D-011): `safety`, `transport-alert`, `exam-in-progress`, `unconfirmed`, `deferred:<kind>`.

These match `domain/labels.py` and `domain/values.py` exactly.

## Tables

All ids are `uuid default gen_random_uuid()` unless stated. Every table has `created_at timestamptz default now()` and RLS enabled.

| Table | Columns (beyond id, created_at) | Keys / indexes |
| --- | --- | --- |
| `profiles` | `id` = `auth.users.id`, `role` (`student`/`staff`/`admin`, default `student`), `office`, `alias` | pk `id` → auth.users (cascade); `alias` unique |
| `buildings` | `id text`, `code`, `name_en`, `name_ar`, `map_x real`, `map_y real` (fictional campus, SVG coords) | pk `id`; `code` unique |
| `requests` | `alias`, `raw_text`, `core`, `text_norm`, `model_text`, `lang`, `is_arabizi`, `input_mode` (`text`/`voice`), `building_id`, `room`, `location_source` (`picked`/`extracted`), `stated_urgency`, `truncated`, `status`, `simulated bool default false`, `conversation_id uuid` | fk `building_id` → buildings; idx `(alias, created_at desc)`, `(created_at desc)` |
| `predictions` | `request_id`, `category`, `priority`, `p_cat jsonb`, `p_pri jsonb`, `set_cat text[]`, `set_pri text[]`, `per_model jsonb`, `tier`, `models_used text[]`, `cost_usd numeric(10,6)`, `latency_ms`, `flags text[] default '{}'`, `explanation jsonb`, `artifact_version`, `core jsonb` (full CoreResult, 0007) | fk `request_id` (cascade); idx `(request_id, created_at desc)` |
| `clarifications` | `request_id`, `question_id`, `options jsonb`, `answer`, `asked_at`, `answered_at` | fk request (cascade); idx `(request_id, asked_at)` |
| `incidents` | `building_id`, `category`, `office` (filled from its first ticket by trigger `tickets_fill_incident_office`), `title`, `priority`, `report_count`, `status` (`open`/`resolved`), `opened_at`, `resolved_at` | fk building; idx `(building_id, status)` |
| `tickets` | `request_id`, `incident_id`, `office`, `category`, `priority`, `status`, `provisional`, `title`, `body`, `sla_due_at`, `escalated_at`, `resolved_at`, `tags text[] not null default '{}'` (D-011) | fk request (cascade), incident (set null); idx `(office, status, sla_due_at)`, `(request_id)`, `(incident_id)` partial |
| `ticket_links` | `ticket_id`, `sink`, `external_id`, `external_url`, `last_synced_at`, `last_error` | pk `(ticket_id, sink)`; unique `(sink, external_id)` (for `ticket_by_link`) |
| `advisors` | `fictional_name`, `department`, `room`, `calendar_id`, `demo_email`, `office_hours jsonb` | — |
| `advisor_slots` | `advisor_id`, `starts_at`, `ends_at`, `booked_by` (alias), `booked_at` | unique `(advisor_id, starts_at)`; check `ends_at > starts_at`; partial idx on free slots |
| `cases` | `request_id`, `ticket_id`, `advisor_id`, `slot_id`, `slot_start`, `outcome_code`, `booking jsonb`, `closed_at` | fks (cascade / set null) |
| `outbox` | `kind` (`email`,`ticket`,`booking`,`alert`,`broadcast`,`in_app`,`whatsapp`), `channel` (`email`/`in_app`/`whatsapp`, default `email`), `alias`, `request_id`, `to_address`, `subject`, `body`, `provider_id`, `status` (`queued`,`sent`,`failed`,`rejected`,`simulated`,`deferred`), `priority`, `flags text[]`, `error` | idx `(created_at desc)`, `(alias, created_at desc)` |
| `notifications` | `alias`, `kind`, `payload jsonb`, `read_at` | idx `(alias, created_at desc)` |
| `review_queue` | `prediction_id`, `reason`, `status` (`open`/`confirmed`/`corrected`), `reviewer_id` → auth.users, `corrected_category`, `corrected_priority`, `note`, `resolved_at` | idx `(status, created_at)` |
| `student_signals` | pk `alias`, `n_requests`, `n_claimed_urgent`, `n_claimed_urgent_not_high`, `n_high`, `n_injection`, `gaming_flag`, `updated_at` | pk `alias` |
| `llm_calls` | `request_id`, `tier`, `model`, `prompt_hash`, `cache_key` (unique, for `SupabaseCache`), `response jsonb`, `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms`, `cached` | `cache_key` unique; idx `(created_at desc)` |
| `redteam_runs` | `config jsonb`, `scorecard jsonb` | — |
| `events` | `id bigint identity`, `actor`, `action`, `entity`, `payload jsonb`, `at` (audit log) | idx `(at desc)` |
| `faq` | `lang` (`en`/`ar`), `question`, `answer`, `source_url`, `is_demo default true`, `embedding vector(384)` (nullable) | HNSW on `embedding` |
| `memory_examples` | `text_norm`, `lang`, `embedding vector(384) not null`, `category`, `priority`, `author_id` → auth.users (set null), `active default true` | HNSW on `embedding`; idx `(active, created_at)` |
| `request_embeddings` | pk `request_id` → requests (cascade), `embedding vector(384) not null`, `lang`, `category`, `priority`, `building_id` → buildings, `room` | HNSW on `embedding`; idx `(building_id, category, created_at)` |

**Notes on differences from SPEC §8:**
- `advisor_slots` uses `starts_at`/`ends_at` (the domain `Slot` names) instead of `start`/`end`.
- `outbox.kind` is the purpose and `outbox.channel` is the transport. The domain `OutboxMessage.kind` (`email`/`in_app`/`whatsapp`) maps to `channel`.
- `incidents.office` and `outbox.alias` are added so RLS needs no join.

## RLS policies, in plain words

Helpers live in schema `private` (not exposed by the API). All are `security definer` and read `profiles` for `auth.uid()`:
- `cp_role()`, `cp_office()`, `cp_alias()`
- `cp_is_staff()` (staff or admin), `cp_is_admin()`
- `cp_owns_request(id)`, `cp_office_has_request(id)` (staff whose office holds a ticket for the request), `cp_can_see_ticket(id)`

| Table / view | Who can SELECT |
| --- | --- |
| `profiles` | your own row; admin all |
| `buildings`, `advisors`, `faq_v` (and `faq` without `embedding`) | any signed-in user |
| `requests` | the student who owns it (alias); staff whose office has a ticket for it; admin |
| `predictions` | staff whose office has a ticket for the request; admin. **Students: no policy.** |
| `predictions_student_v` | a student's own predictions, with `urgency_unsupported` and `priority_gaming_suspected` removed from `flags` (and no `per_model`/cost columns) |
| `clarifications` | the owning student; staff of the ticket's office; admin |
| `tickets` | staff of the ticket's `office`; the student who owns the request; admin |
| `ticket_links` | whoever can see the ticket; admin |
| `incidents` | staff of the incident's `office`; admin |
| `outbox` | the student it was sent for (alias); staff and admin |
| `notifications` | the recipient (alias); admin |
| `review_queue`, `llm_calls`, `redteam_runs`, `events`, `advisor_slots`, `cases`, `memory_examples_v` (and `memory_examples` without `embedding`) | staff and admin |
| `student_signals` | admin only |
| `request_embeddings` | **nobody** (no grant, no policy; service role only) |

**Writes:**
- No client role has any `INSERT`/`UPDATE`/`DELETE` policy or privilege. Write privileges are revoked from `authenticated` on all tables, now and by default for future tables.
- `anon` has no table privileges at all.

**Proof:** [`supabase/tests/rls.sql`](../../supabase/tests/rls.sql) checks 9 cases inside a rolled-back transaction:
- student A ≠ student B
- IT staff ≠ Finance tickets
- authenticated insert fails
- no `request_embeddings`
- no `match_vectors`
- anon sees nothing
- admin sees all
- staff see `review_queue`
- no gaming flags for students

Run it with `python scripts/test_rls.py`: local stack (Docker) via psql, or `--db-url`. Or paste it into the SQL editor or the MCP `execute_sql`.

## Views

| View | Definition | Grant |
| --- | --- | --- |
| `predictions_student_v` | `security_invoker`; selects from `private.cp_student_predictions()` (security definer: rows where the request alias = caller alias, flags stripped) | `authenticated` |
| `faq_v` | `security_invoker`; `id, lang, question, answer, source_url, is_demo` from `faq` | `authenticated` |
| `memory_examples_v` | `security_invoker`; every `memory_examples` column except `embedding` | `authenticated` (rows: staff/admin via policy) |

**Why `predictions_student_v` uses a function.** A plain `security_invoker` view would need a student row policy on `predictions`. With that policy, a student could select `flags` straight from the table.

**Embedding columns:** column-level `GRANT SELECT` excludes `embedding` on `faq` and `memory_examples`. A client that selects `embedding` directly gets `42501 permission denied`.

## RPC functions (service role only; `EXECUTE` revoked from `public`, `anon`, `authenticated`)

```sql
match_vectors(p_collection text, p_query extensions.vector(384), p_k int,
              p_min_sim float8 default 0, p_filters jsonb default '{}')
  returns table(id uuid, text text, lang text, sim float8, meta jsonb, embedding extensions.vector(384))

vector_dim() returns int   -- declared dim of faq.embedding (384); PgVectorStore checks it at startup

bump_student_signals(p_alias text, p_claimed_urgent bool, p_was_high bool, p_injection bool)
  returns student_signals   -- atomic upsert of the counters (0007); gaming_flag is left as stored
```

**`match_vectors` behaviour:**
- **Similarity:** `sim = 1 - cosine distance`. Rows are sorted by `sim desc, id asc`, so ties break deterministically. Only rows with `sim >= p_min_sim` are returned, at most `p_k` of them (clamped to 0..1000).
- **Index use:** the inner query takes an HNSW candidate pool of `max(4k, 40)` rows in index order. The function runs with `hnsw.ef_search = 40` and `hnsw.iterative_scan = relaxed_order`, so filtered searches do not under-return. The outer query re-sorts the pool exactly.
- **`embedding`:** null unless `p_filters->>'with_embedding' = 'true'` (LD-14).
- **Errors:** an unknown collection raises SQLSTATE `22023`.

| Collection | Table | `text` is | `meta` keys | Filters |
| --- | --- | --- | --- | --- |
| `requests` | `request_embeddings` ⨝ `requests` | `requests.text_norm` (or `core`, `raw_text`) | `building_id, room, category, priority, created_at` | `building_id`, `category`, `since` |
| `memory` | `memory_examples` | `text_norm` | `category, priority, author_id, created_at, active` | `active` (**default true**), `lang`, `category`, `since` |
| `faq` | `faq` (rows with an embedding) | `question` | `answer, source_url, is_demo` | `lang` |

## Vector collections

All are `extensions.vector(384)`, from the frozen encoder (e5 with the `query: ` prefix, LD-9). Each has an HNSW index (`vector_cosine_ops`, `m = 16`, `ef_construction = 64`).

| Collection | What is embedded | Written by |
| --- | --- | --- |
| `requests` | every live request's normalised text (UD-6), reusing the classify embedding | `TriageUseCase` via `PgVectorStore.upsert("requests", …)` |
| `memory` | staff-corrected request text | `FeedbackUseCase` via `PgVectorMemoryStore.add` |
| `faq` | each FAQ question | `scripts/seed_faq.py` (P4.5) |

The frozen training index and the injection/safety exemplars are **not** in Postgres. They stay in `LocalNumpyVectorStore` inside the model dir.

## Office codes

`tickets.office`, `incidents.office`, `profiles.office` and `advisors.department` use these codes. The demo staff user is `it`. The routing table (`config/actions.yaml`, Backend) must emit the same strings, or staff RLS will not match:

| Code | Office (SPEC §5.1 routing) |
| --- | --- |
| `registrar` | Registration |
| `it` | IT Support (helpdesk) |
| `finance` | Finance |
| `transport` | Transportation |
| `facilities` | Facilities (maintenance) |
| `academic` | Academic Support (advisors) |

## Python adapters

- **`adapters/vectors/pgvector.py`: `PgVectorStore(client, dim)`** implements `VectorStore`.
  - **Construction:** calls `vector_dim()`; a mismatch raises `ArtifactVersionMismatch`.
  - **`upsert`:** uses the table API with `on_conflict` on the id column.
  - **Ids:** `memory`/`faq` ids must be UUIDs. `requests` items need an existing `requests` row.
  - **`set_active`:** `memory` only; a missing id raises `NotFound`.
  - **Errors:** every SDK error becomes `StoreError`.
- **`adapters/memory/pgvector_memory.py`: `PgVectorMemoryStore(vectors, client)`** implements `MemoryStore`.
  - `author_id=""` is stored as NULL. A non-empty value must be an `auth.users` id.
  - Reads page through PostgREST's 1000-row limit.
- **`adapters/vectors/local_numpy.py`: `LocalNumpyVectorStore(dim, *, read_only=False, collections=())`** implements `VectorStore` offline (P1.7).
  - **Search:** brute-force cosine over float32 matrices, ties broken by id. Inactive items are hidden unless `filters["active"]` is set.
  - **Filters:** `lang`, `since` (meta `created_at`), `with_embedding`, and any other key as equality on `meta`.
  - **Persistence:** `load(index_dir, *, expected_dim, read_only=True)` / `save(index_dir)` use `<coll>/embeddings.npy` + `<coll>/items.jsonl`. A missing file raises `ArtifactMissing`; a dim mismatch raises `ArtifactVersionMismatch`.
  - **Errors:** writes to a read-only store, or searching an unknown collection, raise `StoreError`.
  - **Scope:** it is the only store `build_offline` may construct. `collections=` pre-creates empty collections (tests).
- **Isolation:** the pgvector modules import `supabase` for typing only, and `local_numpy` imports nothing online. `tests/invariants/test_vector_isolation.py` enforces this.

## Memory stores (`adapters/memory/`)

| Class | Where | Behaviour |
| --- | --- | --- |
| `PgVectorMemoryStore(vectors, client)` | online | `memory_examples` via `PgVectorStore("memory")` |
| `InMemoryMemoryStore()` | tests, offline red team | dict-backed; same contract (`tests/contracts/test_memory_store_contract.py`, 7 cases) |
| `NullMemoryStore()` | `build_offline` (§3.11) | always empty; `add` raises `StoreError`, `deactivate` raises `NotFound` |

All three implement the same `MemoryStore` contract:
- `neighbors` are cosine matches over **active** examples, ties broken by id, with `source="memory"`.
- `stats.by_category` counts active examples only.
- `last_added_at` is the newest `created_at`.

## FAQ retrieval

`adapters/faq/retriever.py`: **`VectorFAQRetriever(vectors, encoder, collection="faq")`** implements `FAQRetriever`.
- **Query:** `search(text, lang, k)` embeds the question with the shared encoder (the encoder adds the e5 `query: ` prefix, LD-9).
- **Language:** it searches only the request language. `arabizi` maps to the `ar` entries, because the FAQ has no Arabizi rows.
- **Results:** up to `k` `FAQHit`s, score descending, each with `answer`, `source_url` (`""` when none) and `is_demo`.
- **Errors:** `StoreError` propagates (Act falls back to a ticket).
- **Threshold:** it does **not** apply `tau_faq`; the action engine does. The answer text is always the retrieved text plus its source, with `[demo]` marking placeholders.

**Tuning:** `python scripts/tune_faq.py [--dry-run]` runs `config/faq_tuning.yaml` (15 answerable paraphrases, 15 uncovered questions; EN/AR/Arabizi) through encoder → retriever → pgvector. It sweeps τ over 0.50–0.95 and writes the lowest τ with precision 1.00 to `config/hand_tuned.yaml` `tau_faq` (current default 0.75). It needs the frozen encoder and embedded FAQ rows (`seed_faq.py` first).

## Incident detection (Pulse)

`adapters/pulse/incident_detector.py`: **`WindowedCentroidDetector(repo, vectors, clock, tau_inc, window_min, min_reports=3, bump_at=6)`** implements `IncidentDetector`.

For each located request, `detect(req, pred, embedding)` works like this:
1. **Attach (D-007):** if an incident is open for that building and category, **whatever its age**, the request attaches to the oldest one (`report_count + 1`, `members = [req.id]`). One ongoing outage stays one incident.
2. **Search:** otherwise, `vectors.search("requests", embedding, k=50, filters={building_id, category, since: now − window_min, with_embedding: true})`. The request itself is excluded if it is already stored. The window bounds **opening** only.
3. **Cluster:** centroid = normalised mean of those embeddings plus the new one. Members = rows with cosine to the centroid ≥ `tau_inc`, and the request must be one of them.
4. **Decide:** at least `min_reports` members → `new` (`report_count = members`); fewer → `none`.
5. **Save:** the incident is saved through the repository.
   - Priority = max of the member priorities (on attach, raised to the request's if higher).
   - It is bumped one level, once, when `report_count` first reaches `bump_at` (capped at high).
   - `incidents.office` is filled by the 0007 trigger when the first member ticket is attached.
6. **Return:** `IncidentDecision.members` = the member request ids, with `req` last.

The action engine (P4.8) owns the rest: marking member tickets `merged` with `incident_id`, the single incident ticket through the sinks, the broadcast, and `ResolveIncidentUseCase`.

**Config:**
- `tau_inc`: constructor argument until `config/hand_tuned.yaml` → FrozenConfig exists (LD-11); default 0.80.
- `window_min`: Settings `INCIDENT_WINDOW_MIN` (30).
- `min_reports` and `bump_at`: constructor arguments.

**Simulator:** `python scripts/simulate_pulse.py --scenario config/simulation/wifi_m.yaml [--interval 4] [--reset]` replays 8 fictional reports (EN/AR/Arabizi, building M) as `sim-0N` with `requests.simulated = true`.
- **Direct mode (default):** writes request, prediction and embedding through `SupabaseRepository` + `PgVectorStore`, then calls the detector. It uses the frozen encoder if `models/frozen/v1/encoder` exists, otherwise synthetic topic vectors (it prints which).
- **API mode:** `--mode api` is a TODO for P4.14 (`/v1/triage`).
- **`--reset`:** deletes earlier simulated requests and the open incident from this window.

## Realtime

Publication `supabase_realtime` includes `predictions`, `tickets`, `incidents`, `outbox`, `notifications` and `requests` (`requests` is for the Pulse dots, LD-25). Supabase applies RLS to `postgres_changes`, so each subscriber receives only rows its SELECT policy allows. Students subscribe to `notifications` only.

## Repository mapping (`adapters/store/`)

`SupabaseRepository(client, clock)` and `InMemoryRepository(clock=None)` implement the full `Repository` port, including LD-16. Both store the **same row dicts**, built by `adapters/store/codec.py`. `tests/contracts/test_repository_contract.py` (16 cases) runs every port method against both and passes on the live project.

| Entity | Table(s) | Notes |
| --- | --- | --- |
| `Request` | `requests` | `normalized` ⇄ `core, text_norm, model_text, lang, is_arabizi, stated_urgency, truncated`; `location` ⇄ `building_id, room, location_source`. `normalized` is `None` when `text_norm` or `lang` is null. |
| `Prediction` | `predictions` | The full `CoreResult` is in `core jsonb`, so round trips are lossless. The flat columns (`p_cat`/`p_pri` as label→p, sorted `set_*`, `per_model`, `models_used`, `flags`, `cost_usd`, `latency_ms`) are for the UI and SQL. `latest_prediction` = most recently saved (`created_at desc, id desc`). |
| `Clarification` | `clarifications` | `options` jsonb `[{id, text, constraint}]`; listed by `asked_at, id`. |
| `ReviewItem` | `review_queue` | `resolve_review` sets status, corrections, note and `resolved_at = clock.now()`. |
| `Ticket` | `tickets` + `ticket_links` | `save_ticket` also upserts its links; links are read back ordered by `sink`. `(sink, external_id)` is unique. `tags` ⇄ `tickets.tags`; `TicketLink.error` ⇄ `ticket_links.last_error`. |
| `Incident` | `incidents` | `building` ⇄ `building_id`. `member_ticket_ids` is derived from `tickets.incident_id` (by `created_at, id`); `save_incident` points the listed tickets at the incident. |
| `OutboxMessage` | `outbox` | The domain `kind` (transport) is written to both `kind` and `channel`. `alias`/`request_id` are not in the entity, so they stay null. `status` and `error` map one to one, `deferred` included. |
| `StudentSignals` | `student_signals` | `bump_student_signals` is atomic (RPC). `gaming_suspected` = the stored `gaming_flag`, which stays unused (lead decision): GamingDetector (P3.6) computes suspicion from the returned counters. |
| `Scorecard` | `redteam_runs.scorecard` | `run_id` is kept if it is a UUID, else a new UUID is returned. History is newest first. |
| `Slot`, `Advisor`, `Case` | `advisor_slots`, `advisors`, `cases` | `claim_slot` = `update … where id = ? and booked_by is null`, true only for the winner. `free_slots` = unbooked and inside the window, by `starts_at, id`. |
| events, notifications | `events`, `notifications` | Payloads go through a JSON round trip (datetimes become ISO strings); `at`/`created_at` = `clock.now()`. |

**`router_stats(since)`** counts over `predictions` (tier mix, `cost_usd` sum) and `llm_calls` (`cached` count). `resolved_tier0_pct` is a **percentage 0–100**.

**Errors:**
- `NotFound`: `get_request`, `get_ticket`, `latest_prediction`, `ticket_by_link`, `set_request_status`, `resolve_review`.
- `StoreError`: foreign-key and unique violations, plus every PostgREST or network failure.
- Datetimes are written as ISO-8601 UTC.

**InMemory-only seeding helpers:** `add_advisor`, `add_slot`, `add_llm_call`. Supabase gets these from the seed files or from other writers.

## Seeds and demo users

The seed files are `supabase/seed/*.sql`, loaded by `supabase db reset` (`config.toml` `sql_paths`), or applied to the linked project from the committed files. All four are idempotent upserts with fixed ids.

| File | Rows | Content |
| --- | --- | --- |
| `01_buildings.sql` | 11 | Fictional campus, codes A–M without I/J; EN/AR names; `map_x/map_y` on a 1000×600 grid |
| `02_advisors.sql` | 6 | Fictional advisors (names marked "(fictional)"): 4 `academic`, 2 `registrar`. Each `demo_email` is `campuspulse.support+adv-…@gmail.com`. Office hours Sun–Thu 09:00–15:00 Asia/Amman. |
| `03_advisor_slots.sql` | 720 today | 30-minute slots for the next 14 days, Sun–Thu 09:00–15:00 Amman. Re-running adds new days and never touches booked slots. |
| `04_faq_text.sql` | 28 | 14 topics × EN/AR. 18 rows quote `docs/reference/gju_public_policies.md` with their gju.edu.jo `source_url` and a "check with the office" note; 10 are `is_demo = true` placeholders starting `[demo]`. A changed question clears its embedding. |

**Scripts:**
- `python scripts/check_seed_contacts.py` fails unless every email in the seeds passes `RecipientPolicy(DEMO_EMAIL_ALLOWLIST)`. The allow-list must contain the 6 advisor plus-addresses.
- `python scripts/seed_demo_users.py` (needs `DEMO_USER_PASSWORD`) creates or refreshes these demo logins and upserts their `profiles`. All three share `DEMO_USER_PASSWORD`.

  | Login | Role | Office | Alias |
  | --- | --- | --- | --- |
  | `talal@demo.local` | student | — | `talal` |
  | `it@demo.local` | staff | `it` | `staff-it` |
  | `admin@demo.local` | admin | — | `admin` |

  - **Login names:** chosen by the user on 2026-10-31. They replace `student-demo-17@demo.local` and `staff-it@demo.local`; the script renames users still on those names in place, keeping their ids.
  - **No mail:** nothing is sent to these addresses. The users are created already confirmed.
- `python scripts/seed_faq.py [--model-dir models/frozen/v1] [--all]` embeds FAQ questions with the frozen `OnnxEncoder` and writes them through `PgVectorStore`. It refuses to run when `config.json` `encoder.dim` ≠ `vector_dim()`.

`rls.sql` creates its own fictional users (`rls-*@example.invalid`) and rolls them back. The contract tests tag their rows per run and delete them afterwards.
