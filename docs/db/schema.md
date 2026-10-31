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

**Applying a migration.** Commit the file first. Then apply the same SQL with the Supabase MCP `apply_migration`, or with `supabase db push` on a linked CLI.
- **MCP version repair.** MCP records a timestamp version. Afterwards, set the row in `supabase_migrations.schema_migrations` to the file's version and name (`0001`/`init`, …). This is what `supabase migration repair` does. It keeps the remote history identical to the file names, so a later `db push` does not re-apply anything.
- **Rebuilding from scratch** (P6): `supabase db reset` locally, or `supabase db push` to an empty project.

## Labels and enums (checked by constraints)

- **category:** `Registration`, `IT Support`, `Finance`, `Transportation`, `Facilities`, `Academic Support`
- **priority:** `low`, `medium`, `high`
- **lang:** `en`, `ar`, `arabizi` (`faq.lang` is `en`/`ar` only)
- **tier:** `tier0`, `tier1`, `tier2`, `human`
- **requests.status:** `received`, `needs_clarification`, `clarified`, `decided`, `human_review`, `out_of_scope`, `distress`, `actioned`, `resolved`, `merged`
- **tickets.status:** `open`, `in_progress`, `resolved`, `closed`, `escalated`, `merged`

These match `domain/labels.py` and `domain/values.py` exactly.

## Tables

All ids are `uuid default gen_random_uuid()` unless stated. Every table has `created_at timestamptz default now()` and RLS enabled.

| Table | Columns (beyond id, created_at) | Keys / indexes |
| --- | --- | --- |
| `profiles` | `id` = `auth.users.id`, `role` (`student`/`staff`/`admin`, default `student`), `office`, `alias` | pk `id` → auth.users (cascade); `alias` unique |
| `buildings` | `id text`, `code`, `name_en`, `name_ar`, `map_x real`, `map_y real` (fictional campus, SVG coords) | pk `id`; `code` unique |
| `requests` | `alias`, `raw_text`, `core`, `text_norm`, `lang`, `is_arabizi`, `input_mode` (`text`/`voice`), `building_id`, `room`, `stated_urgency`, `status`, `simulated bool default false`, `conversation_id uuid` | fk `building_id` → buildings; idx `(alias, created_at desc)`, `(created_at desc)` |
| `predictions` | `request_id`, `category`, `priority`, `p_cat jsonb`, `p_pri jsonb`, `set_cat text[]`, `set_pri text[]`, `per_model jsonb`, `tier`, `models_used text[]`, `cost_usd numeric(10,6)`, `latency_ms`, `flags text[] default '{}'`, `explanation jsonb`, `artifact_version` | fk `request_id` (cascade); idx `(request_id, created_at desc)` |
| `clarifications` | `request_id`, `question_id`, `options jsonb`, `answer`, `asked_at`, `answered_at` | fk request (cascade); idx `(request_id, asked_at)` |
| `incidents` | `building_id`, `category`, `office`, `title`, `priority`, `report_count`, `status` (`open`/`resolved`), `opened_at`, `resolved_at` | fk building; idx `(building_id, status)` |
| `tickets` | `request_id`, `incident_id`, `office`, `category`, `priority`, `status`, `provisional`, `title`, `body`, `sla_due_at`, `escalated_at`, `resolved_at` | fk request (cascade), incident (set null); idx `(office, status, sla_due_at)`, `(request_id)`, `(incident_id)` partial |
| `ticket_links` | `ticket_id`, `sink`, `external_id`, `external_url`, `last_synced_at`, `last_error` | pk `(ticket_id, sink)`; unique `(sink, external_id)` (for `ticket_by_link`) |
| `advisors` | `fictional_name`, `department`, `room`, `calendar_id`, `demo_email`, `office_hours jsonb` | — |
| `advisor_slots` | `advisor_id`, `starts_at`, `ends_at`, `booked_by` (alias), `booked_at` | unique `(advisor_id, starts_at)`; check `ends_at > starts_at`; partial idx on free slots |
| `cases` | `request_id`, `ticket_id`, `advisor_id`, `slot_id`, `slot_start`, `outcome_code`, `booking jsonb`, `closed_at` | fks (cascade / set null) |
| `outbox` | `kind` (`email`,`ticket`,`booking`,`alert`,`broadcast`,`in_app`,`whatsapp`), `channel` (`email`/`in_app`/`whatsapp`, default `email`), `alias`, `request_id`, `to_address`, `subject`, `body`, `provider_id`, `status` (`queued`,`sent`,`failed`,`rejected`,`simulated`), `priority`, `flags text[]`, `error` | idx `(created_at desc)`, `(alias, created_at desc)` |
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
- **Isolation:** both modules import `supabase` for typing only. `tests/invariants/test_vector_isolation.py` enforces this.

## Realtime

Publication `supabase_realtime` includes `predictions`, `tickets`, `incidents`, `outbox`, `notifications` and `requests` (`requests` is for the Pulse dots, LD-25). Supabase applies RLS to `postgres_changes`, so each subscriber receives only rows its SELECT policy allows. Students subscribe to `notifications` only.

## Seed and demo users

None yet. Seeds go in `supabase/seed/*.sql` (P4.3+), and all names and addresses are fictional aliases. `rls.sql` creates its own fictional users (`rls-*@example.invalid`) and rolls them back.
