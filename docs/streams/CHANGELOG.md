# Stream changelog: append-only, one entry per finished task, newest last; never edit earlier entries.

### P0.2 — Python package skeleton with exact pins  (foundation, 2026-10-31, commit pending)
- **What now exists:** the installable `campuspulse_ai` package (`services/ai/`, version `0.1.0`) with an empty `__init__.py` in every directory of the ARCHITECTURE §1.2 tree, the four exact-pinned requirement sets, the root ruff config (with the random-split ban) and `tests/{unit,contracts,invariants,e2e,fixtures}/` packages.
- **Public interfaces added or changed:** `campuspulse_ai.__version__`; `services/ai/requirements{,-api,-dev,-train}.txt` (see [docs/ops/README.md](../ops/README.md#local-python-setup)); pytest markers `slow`, `network`, `e2e`.
- **How to use it:** `python -m venv .venv && .venv/Scripts/python -m pip install -r services/ai/requirements-dev.txt -e services/ai`
- **Config / env added:** none.
- **Acceptance:** pip install exit 0; `pip check` -> `No broken requirements found.`; version -> `0.1.0`; `pytest ...test_requirements_pinned.py -q` -> `1 passed`; `inference set clean`. `ruff check .` -> `All checks passed!` after the lead review.
- **Limitations / TODO / known issues:** Lead review: the legacy data scripts are excluded from ruff (`extend-exclude`), and the pytest markers were set to the plan conventions (`train`, `artifacts`, `supabase`, `slow`, `offline`, with `--strict-markers`). `requirements-train.txt` was not installed here (ML stream does that).
- **Affects streams:** all (dev install and lint/test commands); ML (train set, ruff findings in `scripts/`).

### P0.4 — Domain layer: labels, values, entities, errors, ports  (Lead, 2026-10-31)
- **What now exists:** `services/ai/campuspulse_ai/domain/` — the frozen contract every stream codes against. Stdlib only, `mypy --strict` clean.
- **Public interfaces added:** see `domain/ports.py` (`ALL_PORTS` lists all 29 ports: the ARCHITECTURE §1.4 set plus `RequestUnderstander` (UD-10) and `ProblemClusterer` (UD-6)). Labels: `Category`, `Priority` (StrEnum; `str(x) == x.value`), `CATEGORY_ORDER`/`PRIORITY_ORDER` (fixed prob-vector column order), `CATEGORY_LABELS`/`PRIORITY_LABELS`.
- **Types the brief only named, now fixed (values.py unless noted):** `ProbabilityTarget`, `MetaValue`, `ActionType` (faq_answer, ticket, booking, safety_alert, incident_merge), `RequestStatus`/`TicketStatus` (moved to values.py; entities import them), `ClarificationBudget(max_questions, asked).remaining`, `ClarificationOption(id, text, constraint)`, `ClarificationQuestion(id, target, text, lang, options, expected_info_gain)`, `MemoryStats`, `ActionPlan(kind, office, sla_hours, tags, also_ticket)`, `FAQHit`, `TicketLink(ticket_id, sink, external_id, url)`, `InboundEvent(sink, external_id, status, occurred_at, payload)`, `OfficeHours(tz, weekdays, start, end)`, `Slot`, `Booking`, `Advisor`, `RouterStats`, `StudentSignals`, `Counterfactual(drop, category, priority)`, `Entities`, `Understanding` (UD-10), `ProblemCluster` (UD-6). In entities.py: `IncidentDecision`, `OracleAnswer`, `OracleContext(lang, neighbors, prompt_version)`, `Case`, `Explanation`; `Ticket` gained `title`/`body` (filled from `Understanding`); `OutboxMessage` gained optional `priority`/`flags` (LD-25) and `kind` includes `"whatsapp"` (future).
- **Flags:** `values.FLAGS` = ARCHITECTURE §5 list + `understanding_fallback` (UD-10) + debug-only `empty_input`.
- **Implemented now:** `ProbVector` (validated; `argmax` ties → label order; `top`, `as_dict`, `prob`), `PredictionSet`, `Manifest.sha`, `Priority.rank/bump`, `policy.RecipientPolicy` (empty allow-list rejects all; case/space-insensitive).
- **How to use:** `from campuspulse_ai.domain.ports import TicketSink` — implement the Protocol structurally; no inheritance needed. Raise only `domain/errors.py` exceptions (`SinkError(msg, retryable=...)`).
- **Acceptance:** `pytest services/ai/tests/unit/test_domain_values.py -q` → `7 passed`; `mypy --strict services/ai/campuspulse_ai/domain` → `Success: no issues found in 9 source files`; `ruff check .` → `All checks passed!`.
- **Limitations:** `policy.DefaultDecisionPolicy` (P3.1), `priority_rules.EVIDENCE_FEATURES` (P1.12), `routing` planner (P3.8/P4.8) are docstring placeholders. **Domain changes go through the lead only** (EXECUTION rule 3).
- **Affects streams:** all.

### P0.5 — Settings and .env.example (Gmail SMTP)  (foundation, 2026-10-31, commit b32ee6d)
- **What now exists:** `campuspulse_ai.config.settings.Settings` (pydantic-settings) and a scoped `.env.example` (ai/web/cli), kept in sync by `tests/unit/test_env_example.py`.
- **Public interfaces added or changed:** `Settings()`; fields listed in the [ops env table](../ops/README.md#env-vars).
- **How to use it:** `from campuspulse_ai.config.settings import Settings; s = Settings()`; `s.demo_email_allowlist` is a lower-cased frozenset, empty rejects all.
- **Config / env added:** all variables in `.env.example`; defaults `enable_llm=False`, `smtp_host=smtp.gmail.com`, `smtp_port=587`, `ort_intra_op_threads=4`.
- **Acceptance:** `pytest services/ai/tests/unit/test_env_example.py -q` -> `4 passed`; `Settings().smtp_host` -> `smtp.gmail.com`.
- **Limitations / TODO / known issues:** the Google Calendar fields in the P0.5 spec (`google_service_account_json`, `demo_calendar_ids`) are NOT fields; they are commented-out future work. Empty env values count as unset (`env_ignore_empty`). `AUTH_MODE`, `TZ`, `REPORTS_DIR` are added by P3/P4.
- **Affects streams:** Backend (SMTP notifier, auth), all (add new vars to `.env.example` and `Settings` together or the test fails).

### P0.6 — Architecture import-graph test  (foundation, 2026-10-31, commit ed66055)
- **What now exists:** `services/ai/tests/test_architecture.py`, an AST walk enforcing ARCHITECTURE 1.1.
- **Public interfaces added or changed:** test helpers `imported_modules(py_file)`, `violations(layer_dir, allowed)`.
- **How to use it:** `pytest services/ai/tests/test_architecture.py -q`; a failure lists (file, module) pairs.
- **Config / env added:** none.
- **Acceptance:** `pytest services/ai/tests/test_architecture.py -q` -> `5 passed`.
- **Limitations / TODO / known issues:** frameworks may import stdlib, fastapi, starlette, uvicorn, argparse, pydantic(+settings), psutil, and `campuspulse_ai.{frameworks,composition,application.dto,config,domain}`. Adapters are checked for no frameworks/composition/web-framework imports (third-party libs otherwise free). The "only entry points import frameworks" rule is checked inside the adapters test for all in-package layers. P1.18 adds runtime checks.
- **Affects streams:** all (a new cross-layer import fails CI).

### P0.7 — FastAPI /health, Dockerfile, render.yaml  (foundation, 2026-10-31, commit e678839)
- **What now exists:** `create_app()`, `GET /health` and `/v1/health`, `services/ai/api.py` (`uvicorn api:app`), `services/ai/Dockerfile`, root `.dockerignore` and `render.yaml`.
- **Public interfaces added or changed:** `frameworks.fastapi_app.create_app(settings=None) -> FastAPI` (settings on `app.state.settings`); `HealthResponse{status, artifact, rss_mb}`.
- **How to use it:** `docker build -f services/ai/Dockerfile -t campuspulse-ai .` then `docker run --rm -e PORT=8000 -p 8000:8000 campuspulse-ai`; see [ops Deploy](../ops/README.md#deploy). New routers: `app.include_router(...)` in `create_app` under the `/v1` router.
- **Config / env added:** `PORT`, `ORT_INTRA_OP_THREADS=1` (Dockerfile and render.yaml), `GITHUB_TOKEN` (build secret, future).
- **Acceptance:** `pytest services/ai/tests/e2e/test_health.py -q` -> `2 passed`; Docker build succeeded; `curl.exe -s localhost:8000/health` -> `{"status":"ok","artifact":null,"rss_mb":52.15234375}`.
- **Limitations / TODO / known issues:** the encoder fetch and the `config/`, `scripts/`, `models/frozen` COPY lines are TODOs (those paths do not exist yet; `COPY` of a missing path fails the build). Image is about 880 MB on disk. The Render deploy itself (P0.11) is unverified. The Backend stream's mock app is separate.
- **Affects streams:** Backend (mount routers in `create_app`, entry point is `api.py`), Foundation P0.11 (deploy), ML/P4 (fetch step).

### P0.10 — Supabase config and first migration (pgvector)  (DB, 2026-10-31, commit 22aff77)
- **What now exists:** `supabase/config.toml` (CLI project `campuspulse`, seeds from `supabase/seed/*.sql`) and `0001_init.sql`, applied to project `efsanbaklpiakhsndhph`: extensions `vector` 0.8.2 and `pgcrypto` in schema `extensions`; tables `profiles`, `buildings`, `requests`, `predictions` with label checks, RLS on and no policies.
- **Public interfaces added or changed:** the four tables; see [docs/db/schema.md › Tables](../db/schema.md#tables).
- **How to use it:** `select extversion from pg_extension where extname='vector';` → `0.8.2`.
- **Config / env added:** none (the project already existed; applied through the Supabase MCP, not `supabase link`).
- **Acceptance:** MCP `list_migrations` → `0001 init`; `select extversion ... 'vector'` → `0.8.2`; `select relname, relrowsecurity ...` → `buildings true, predictions true, profiles true, requests true`.
- **Limitations / TODO / known issues:** MCP `apply_migration` records a timestamp version; the history row was repaired to `0001`/`init` so it matches the file name (same as `supabase migration repair`). See [Migrations](../db/schema.md#migrations).
- **Affects streams:** all (gate G0: `0001_init.sql` is applied).

### P4.1 — Core schema, RLS, Realtime and RLS test  (DB, 2026-10-31, commits c824cc4, f3c23fb)
- **What now exists:** migrations `0002_core_schema` (every remaining SPEC §8 table plus `notifications`, `ticket_links.last_error`, `llm_calls.cache_key/response`, `outbox.channel/error`, `requests.simulated`), `0003_rls` (read-only client surface per §3.14, `predictions_student_v`), `0004_realtime` (6 tables published) and `0006_private_helpers` (RLS helpers moved out of the exposed `public` schema). All applied. `supabase/tests/rls.sql` + `scripts/test_rls.py`.
- **Public interfaces added or changed:** tables and policies in [schema.md › RLS policies](../db/schema.md#rls-policies-in-plain-words); view `predictions_student_v`; Realtime tables in [schema.md › Realtime](../db/schema.md#realtime).
- **How to use it:** UI (anon key + user JWT): `supabase.from('tickets').select('*')` returns only the caller's office's tickets; students read predictions from `predictions_student_v`. All writes go through FastAPI with the service role.
- **Config / env added:** none.
- **Acceptance:** `supabase/tests/rls.sql` run on the linked project through MCP `execute_sql` (rolled back) → 9 rows `ok=true` + `RLS: 9/9 checks passed`, re-run after 0006 → `RLS: 9/9 checks passed`. Security advisors after 0006: only the intended INFO `request_embeddings has RLS enabled, no policies` and a pre-existing `public.rls_auto_enable()` not created by our migrations.
- **Limitations / TODO / known issues:** `python scripts/test_rls.py` (local `supabase db reset` + psql) not run: Docker Desktop is not running and psql is not installed. `predictions_student_v` is a `security_invoker` view over a security-definer function (a plain invoker view would let students read raw `flags`). Spec deviations: `advisor_slots.starts_at/ends_at`; `outbox.kind` = purpose, `outbox.channel` = transport; added `incidents.office`, `outbox.alias`, `outbox.request_id`, `requests.conversation_id`. `outbox` is readable by all staff (spec lists only student + admin).
- **Affects streams:** UI (RLS read surface, Realtime, `predictions_student_v`), Backend (write columns, `llm_calls.cache_key`, outbox `channel`/`status='simulated'`), DB P4.3 (`SupabaseRepository`).

### P4.2 — pgvector: vectors migration, PgVectorStore, PgVectorMemoryStore  (DB, 2026-10-31, commits f3b932c, 96fa9f7)
- **What now exists:** `0005_vectors` (applied): `faq`, `memory_examples`, `request_embeddings` as `vector(384)` with HNSW cosine indexes; RPCs `match_vectors` and `vector_dim` (service role only); views `faq_v`, `memory_examples_v`; embedding columns hidden from clients by column grants. Adapters `PgVectorStore` and `PgVectorMemoryStore` with contract, unit and isolation tests.
- **Public interfaces added or changed:** `match_vectors(p_collection, p_query, p_k, p_min_sim, p_filters) -> (id, text, lang, sim, meta, embedding)` and `vector_dim() -> int` ([schema.md › RPC functions](../db/schema.md#rpc-functions-service-role-only-execute-revoked-from-public-anon-authenticated)); `PgVectorStore(client, dim)`; `PgVectorMemoryStore(vectors, client)`.
- **How to use it:** `store = PgVectorStore(service_client, dim=384)`; `store.search("requests", emb, k=50, min_sim=0.8, filters={"building_id": "M", "since": t, "with_embedding": True})`; `PgVectorMemoryStore(store, service_client).neighbors(emb, k=5, min_sim=0.8)`.
- **Config / env added:** tests read `SUPABASE_TEST_URL` and `SUPABASE_TEST_SERVICE_ROLE_KEY` (unset → `-m supabase` cases skip).
- **Acceptance:** migration applied (MCP `list_migrations` → `0005 vectors`). SQL check of the RPC on the linked project (rolled back): `vector_dim` → `384`; building filter + `with_embedding` → 1 hit, sim 1.000, embedding returned; memory ties → ordered by id, inactive hidden; unknown collection → `22023`; client `select embedding` → `42501`. `pytest services/ai/tests/unit/test_pgvector_adapter.py services/ai/tests/invariants/test_vector_isolation.py services/ai/tests/contracts -q` → `10 passed, 43 skipped`; default selection `-m "not train and not artifacts and not supabase"` → `18 passed, 22 skipped`; `mypy --strict` on both adapters → `Success`; `ruff check .` → `All checks passed!`.
- **Limitations / TODO / known issues:** **X4.5 not yet run**: the PgVectorStore contract cases need `SUPABASE_TEST_URL` + `SUPABASE_TEST_SERVICE_ROLE_KEY`. LocalNumpyVectorStore (ML P1) and InMemoryMemoryStore (Backend P3.7) params skip until those exist; add the Local harness in `test_vector_store_contract.py`. `PgVectorMemoryStore` drops the plan's `clock` constructor argument (unused). `memory` search and count default to `active=true`. `requests` items need an existing `requests` row (FK), and their text comes from `requests.text_norm`. `vector_dim()` reads `faq.embedding` only. Isolation invariant covers part (a); parts (b)–(d) need `build_offline`.
- **Affects streams:** Backend (`PgVectorMemoryStore` for `build_online`, the `requests` upsert in `TriageUseCase`), ML (Local store must satisfy the same contract), DB P4.5/P4.10 (FAQ, incidents).

### P1.7 — LocalNumpyVectorStore  (DB, 2026-10-31, commit 3cdd0d1)
- **What now exists:** `adapters/vectors/local_numpy.py`, the offline `VectorStore` (numpy only). The vector contract test runs every case against it without keys; the §3.18 isolation invariant covers it.
- **Public interfaces added or changed:** `LocalNumpyVectorStore(dim, *, read_only=False, collections=())`, `.load(index_dir, *, expected_dim, read_only=True)`, `.save(index_dir) -> list[Path]`, `.collections()`, plus the port methods. On disk: `<index>/<collection>/{embeddings.npy, items.jsonl}`. See [schema.md › Python adapters](../db/schema.md#python-adapters).
- **How to use it:** `s = LocalNumpyVectorStore(384, collections=("train",)); s.upsert("train", items); s.save(model_dir / "index")`, then `LocalNumpyVectorStore.load(model_dir / "index", expected_dim=384).search("train", q, k=5)`.
- **Config / env added:** none.
- **Acceptance:** `pytest services/ai/tests/contracts/test_vector_store_contract.py -q` → `16 passed, 15 skipped` without keys (all 15 cases for local_numpy + 1 local-only read-only/missing-file test; the skips are pgvector). `pytest services/ai/tests/invariants -q` → `4 passed, 1 skipped` (build_offline not built). `mypy --strict` → `Success`.
- **Limitations / TODO / known issues:**
  - Added to the plan interface: `collections=` (pre-create empty collections) and `read_only=` on `load` (default True).
  - Filters: `lang`, `since` and `active` have fixed meanings; any other key is meta equality.
  - Searching an unknown collection raises `StoreError` (a typo'd frozen collection must not return `[]`).
  - Isolation parts (b) to (d) wait for `build_offline`.
- **Affects streams:** ML (build the frozen `train`/`injection_exemplars`/`safety_exemplars` collections with `save`; `build_offline` loads with `load`), Backend (tests can use it for FAQ/incidents).

### P4.2 follow-up — X4.5 on real pgvector  (DB, 2026-10-31)
- **Acceptance:** with the service-role key in `.env`, `pytest services/ai/tests/contracts/test_vector_store_contract.py services/ai/tests/contracts/test_memory_store_contract.py -q -m supabase` → `21 passed, 1 skipped` (the skip is the local-only save/load case). Tables were empty afterwards.
- **Change:** the Supabase test helper reads the repo `.env`. It reuses `SUPABASE_SERVICE_ROLE_KEY` when the test URL is the main project, and falls back to `NEXT_PUBLIC_SUPABASE_URL`.

### P3.8 (moved to DB) — InMemoryRepository  (DB, 2026-10-31, commit 0c3d8cf)
- **What now exists:** `adapters/store/inmemory.py` (the reference `Repository` for tests and the offline red team) and `adapters/store/codec.py` (the entity ⇄ row mapping shared with Supabase), plus `tests/contracts/test_repository_contract.py`.
- **Public interfaces added or changed:** `InMemoryRepository(clock: Clock | None = None)` with the full port, including LD-16. Seeding helpers outside the port: `add_advisor(name, department, email="")`, `add_slot(advisor_id, starts_at, ends_at)`, `add_llm_call(tier, cost_usd, cached)`. Behaviour: [schema.md › Repository mapping](../db/schema.md#repository-mapping-adaptersstore).
- **How to use it:** `repo = InMemoryRepository(FrozenClock(...)); req = repo.save_request(Request(id="", ...))`. An empty id gets a UUID, and the saved entity is returned.
- **Config / env added:** none.
- **Acceptance:** `pytest services/ai/tests/contracts/test_repository_contract.py -q -k inmemory` → `16 passed`.
- **Limitations / TODO / known issues:**
  - Behaves like Supabase: foreign keys, unique ticket links, NotFound, conditional `claim_slot`, orderings, and JSON-normalised payloads.
  - Building FKs are not checked in memory.
  - `latest_prediction` means the most recently saved one.
- **Affects streams:** Backend (`build_test()` should use it; P3.6 GamingDetector calls `bump_student_signals`).

### P4.3 (partial) — SupabaseRepository, seeds, seed scripts  (DB, 2026-10-31, commits 775d800, a6e0a0a, b0f371a)
- **What now exists:**
  - migration `0007_repository` (applied): lossless request/prediction columns, the atomic `bump_student_signals` RPC, and the incident-office trigger
  - `adapters/store/supabase_store.py`
  - seeds 01–04, applied to the linked project
  - `scripts/check_seed_contacts.py`, `scripts/seed_demo_users.py`, `scripts/seed_faq.py`
- **Public interfaces added or changed:** `SupabaseRepository(client, clock)`, the full port; RPC `bump_student_signals(...)`; columns `requests.model_text/truncated/location_source` and `predictions.core`; office codes (`registrar`, `it`, `finance`, `transport`, `facilities`, `academic`). See [schema.md › Seeds and demo users](../db/schema.md#seeds-and-demo-users).
- **How to use it:** `SupabaseRepository(create_client(url, service_key), SystemClock())`. Seeds: `supabase db reset` locally (it runs `supabase/seed/*.sql`), or execute the files on the linked project.
- **Config / env added:** scripts read `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DEMO_EMAIL_ALLOWLIST` and `DEMO_USER_PASSWORD` (env or repo `.env`).
- **Acceptance:**
  - Seeds applied via MCP `execute_sql` from the committed files: buildings `11`, advisors `6`, slots `720` (Sun–Thu, 09:00–15:00 Amman, 1–12 Nov), faq `28` (EN 14 / AR 14, all `[demo]` rows marked, all public rows sourced). A re-run left the counts unchanged.
  - `pytest services/ai/tests/contracts/test_repository_contract.py -q -k supabase` → `16 passed`.
  - All contracts live: `pytest services/ai/tests/contracts -q` → `69 passed, 8 skipped`; tables clean afterwards, seeds intact.
  - Default selection → `63 passed, 8 skipped`. `mypy --strict` on the store adapters → `Success`.
  - Security advisors: unchanged (only `request_embeddings` INFO and the Supabase-managed `rls_auto_enable`).
- **Limitations / TODO / known issues:**
  - **Pending:** `check_seed_contacts.py` fails until `DEMO_EMAIL_ALLOWLIST` lists the 6 advisor plus-addresses (it prints them).
  - **Pending:** `seed_demo_users.py` waits for `DEMO_USER_PASSWORD`.
  - **Pending:** `seed_faq.py` waits for `OnnxEncoder` (P1.6) and `models/frozen/v1/config.json`; it exits cleanly with a message today.
  - **Deferred:** `composition/online.py` / `build_online` (lead assigns later).
  - **Plan says 10 buildings:** "A–M minus I/J" is 11 codes, and the seed follows the codes.
  - **Outbox:** `alias`/`request_id` stay null (not in the entity), so students see no outbox rows until the entity carries them.
  - **`resolved_tier0_pct`** is a percentage 0–100.
- **Affects streams:**
  - Backend: must use these office codes in `config/actions.yaml`; `build_online` wiring.
  - UI: buildings and FAQ for the map and FAQ pages; demo logins once seeded.
  - ML: `seed_faq.py` needs the encoder.
