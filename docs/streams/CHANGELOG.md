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

### P0.13 — API contract stub  (backend, 2026-10-31, commits a650caa..ad2d418)
- **What now exists:**
  - The frozen `/v1` HTTP contract as Pydantic v2 DTOs.
  - A fixture-backed mock FastAPI app serving every endpoint.
  - The exported `services/ai/openapi.json`: 16 operations, OpenAPI 3.1.
  - 31 EN / Jordanian-Arabic / Arabizi fixtures.
  - Generated per-endpoint docs.
- **Public interfaces added:**
  - `application/dto.py`:
    - request/response models for every SPEC §7 route;
    - the LD-25 additions (`understood_as`, top-level `message`, flag `explanation_failed`, `GET /v1/incidents?open=1`, `POST /v1/tickets/{id}/status`, and the optional `/v1/admin/{simulate,reindex}`);
    - `understanding` (UD-10) and `GET /v1/insights/recurring` (UD-6);
    - `ErrorResponse` / `ErrorCode` / `ERROR_HTTP_STATUS` / `error_code_for(exc)`;
    - `to_student_view()` and `PrincipalHeaders`.
  - `frameworks/api_contract.py`: `ENDPOINTS` and `route_kwargs(op_id)`. Per-route metadata (roles, auth, error codes, side effects) that the real app must reuse so its OpenAPI document matches.
  - `frameworks/mock_app.py` (`app`, `create_mock_app()`).
  - `frameworks/export_openapi.py`.
  - `scripts/gen_api_docs.py [--check]`.
  - Docs: [docs/api/README.md](../api/README.md), [docs/api/endpoints.md](../api/endpoints.md).
- **How to use it:**
  - Run the mock: `uvicorn campuspulse_ai.frameworks.mock_app:app --port 8000`.
  - Call it: `curl.exe -s -X POST localhost:8000/v1/triage -H "Authorization: Bearer x" -H "Content-Type: application/json" --data-binary "@request.json"`.
  - Pick a specific example with `X-Mock-Fixture: triage_distress_ar`, or by sending a fixture's `text`.
  - Regenerate the contract: `python -m campuspulse_ai.frameworks.export_openapi --mock --out services/ai/openapi.json`, then `python scripts/gen_api_docs.py`.
- **Config / env added:** `MOCK_FIXTURES_DIR` (default: `services/ai/tests/fixtures/api`) and `MOCK_SERVICE_TOKEN` (unset = any Bearer token accepted). Both are mock only.
- **Acceptance:**
  - `pytest services/ai/tests/contracts/test_dto_contract.py -q` → `77 passed`.
  - `python -m campuspulse_ai.frameworks.export_openapi --mock > services/ai/openapi.json` → exit 0, with 16 operations (15 `/v1` + `/health`).
  - `python scripts/gen_api_docs.py --check` → `docs/api/endpoints.md is up to date`.
  - `mypy --strict` on `dto.py` and `frameworks/` → no issues.
- **Limitations / TODO / known issues:**
  - `apps/web/src/lib/ai/types.gen.ts` is not generated here: the UI stream generates it from `services/ai/openapi.json`.
  - `dto.py` imports pydantic, which contradicts P3.8's "stdlib dataclasses, no pydantic in application/" line and P0.6's `test_application_domain_numpy_only`. P0.6 must allow `pydantic` in `application/dto.py`, and the P3.8 acceptance line must be dropped (lead to confirm).
  - The `/v1/metrics` sub-shapes (benchmark, coverage, calibration, fairness, ablations, confusions) are a proposal: `evaluate.py` reports (P2.8) must map onto them, or the ML stream files a change request.
  - `HealthResponse` has more keys than P0.7's `{status, artifact, rss_mb}` test expects: P0.7's route should adopt `dto.HealthResponse`.
- **Affects streams:**
  - UI: types, mocks, auth headers and the status/flags tables.
  - Backend: P3.8 and P3.12 implement this contract and reuse `route_kwargs`.
  - Foundation: P0.6 allow-list, P0.7 health shape, CI `gen_api_docs.py --check`.
  - ML: `/v1/metrics` shapes.
  - DB: the incident, ticket and recurring shapes.

### P3.1 — Deterministic DecisionPolicy  (backend, 2026-10-31, commit 9d9df2f)
- **What now exists:** `DefaultDecisionPolicy` in `domain/policy.py`. It is the pure, stdlib-only implementation of the `DecisionPolicy` port: SPEC §5.1 [7] and ARCHITECTURE §2.1 [7] rules a→f, first match wins.
- **Public interfaces added:**
  - `DefaultDecisionPolicy(tau_ood: float)`:
    - `.decide(core, budget, llm_allowed) -> Outcome`;
    - `.decide_with_path(core, budget, llm_allowed, *, after_escalation=False) -> tuple[Outcome, tuple[str, ...]]`;
    - `.tau_ood`.
  - Rule-id constants `RULE_GIBBERISH`…`RULE_HUMAN` and `POLICY_RULES` (`a_gibberish`, `b_ood`, `c_accept`, `d_ask`, `e_escalate`, `f_human`).
- **Rules:**
  - a: flag `gibberish` → OUT_OF_SCOPE.
  - b: `ood_score < tau_ood` and |S_cat| ≥ 3 → OUT_OF_SCOPE.
  - c: both sets are singletons → ACCEPT.
  - d: a set of size 2 and `budget.remaining > 0` → ASK.
  - e: `llm_allowed` and any set of size ≥ 2 → ESCALATE.
  - f: otherwise → HUMAN_REVIEW.
  - With `after_escalation=True`, only c and f are evaluated.
  - The path lists the rules evaluated, and its last id is the one that fired. Use cases append that last id to `explanation.trace.policy_path` at each evaluation, e.g. `["d_ask", "c_accept"]` (see [docs/api/README.md](../api/README.md)).
  - Distress is not handled here (the use case does it first). Unknown flags are ignored.
- **How to use it:**
  ```python
  policy = DefaultDecisionPolicy(tau_ood=config.thresholds.tau_ood)
  outcome = policy.decide(core, ClarificationBudget(max_questions=1, asked=0), llm_allowed)
  ```
- **Config / env added:** none. It reads `thresholds.tau_ood`, passed in by the composition root.
- **Acceptance:**
  - `pytest services/ai/tests/unit/test_policy.py -q` → `14 passed`.
  - `python -c "import campuspulse_ai.domain.policy as p, sys; assert not [m for m in sys.modules if m.startswith(('numpy','sklearn'))]"` → exit 0.
  - `mypy --strict services/ai/campuspulse_ai/domain` → no issues.
- **Limitations / TODO / known issues:**
  - The P3.1 plan text sketches `ClarificationBudget(asked, max, max_if_unsure)` with `left()` and `after_answer()`. The frozen domain type is `ClarificationBudget(max_questions, asked)` with `.remaining`, and the policy uses that.
  - The "not sure → a second question" rule therefore belongs in ClarifyUseCase (P3.10), which builds `ClarificationBudget(max_questions=2, asked=1)`. No domain change is needed.
- **Affects streams:** Backend (P3.9/P3.10 use it); ML (P3 recomputes the true ASK rate with it, LD-24).

### P0.8 — Scaffold the Next.js app (`apps/web`)  (ui, 2026-10-31, commit see git log)
- **What now exists:** strict-TypeScript Next 16.4.2 app (Tailwind 4 CSS-first, ESLint 10 flat config, vitest 4 + Testing Library + jsdom) with a placeholder `/` and a dev-only `/dev/ui` (`notFound()` in production). Every dependency is an exact pin from Appendix A.
- **Public interfaces added or changed:** scripts `dev`, `build`, `typecheck`, `lint`, `test` in `apps/web/package.json`; root `pnpm-workspace.yaml` (so `pnpm --filter web <script>` works); `netlify.toml` (`base = apps/web`, `pnpm run build`, `NODE_VERSION=22`).
- **How to use it:** `pnpm install` (repo root), then `pnpm --filter web dev`.
- **Config / env added:** none.
- **Acceptance:** `pnpm --filter web typecheck` and `lint` exit 0; `build` prints `Compiled successfully` and lists `/dev/ui`; pin check prints `pinned`.
- **Limitations / TODO / known issues:** the plan says npm + `package-lock.json`; the lead's instruction (pnpm 10.17.0, `pnpm-lock.yaml`) was followed, so the Foundation CI job (P0.9) must use pnpm, not `npm ci`. ESLint 10 has unmet-peer warnings from eslint-config-next plugins (lint still passes). Extra devDeps beyond Appendix A: `@types/*`, `@testing-library/{dom,user-event,jest-dom}`, `@vitejs/plugin-react`.
- **Affects streams:** Foundation (CI must use pnpm; Netlify build command).

### P5.1 — Design tokens, Tailwind v4 theme and fonts  (ui, 2026-10-31, commit see git log)
- **What now exists:** `apps/web/src/design/tokens.css` with the `--cp-*` variables (surfaces, text, 6 category and 3 priority colours, semantic colours, spacing, radius, type scale, shadow, motion) in light, `prefers-color-scheme: dark` and forced `[data-theme]` variants, mapped into Tailwind 4 through `@theme inline` (no `tailwind.config.ts`). Inter and IBM Plex Sans Arabic load via `next/font/google`. An ESLint rule bans physical `ml-/mr-/pl-/pr-/left-/right-/text-left/text-right` in `src/components/**` and `src/app/**`, and another bans data-layer imports in components.
- **Public interfaces added or changed:** CSS variables (see [docs/ui/README.md](../ui/README.md#design-tokens)); Tailwind colour utilities `bg-surface-0|1|2`, `text-fg-1|2|3`, `border-line`, `bg-cat-*`, `bg-pri-*`, `text-ok|warn|danger|info`, `bg-accent`.
- **How to use it:** `<div className="bg-surface-1 text-fg-2 ps-4 rounded-md">`.
- **Config / env added:** none.
- **Acceptance:** `vitest run src/design` -> `11 passed` (WCAG contrast for both themes); lint 0 errors; typecheck and build pass.
- **Limitations / TODO / known issues:** dark-mode polish is P5.17 (cut-flagged); category colours were chosen for colour-blind separation but are always paired with a text label.
- **Affects streams:** none outside UI.

### P5.2 — i18n dictionaries, `useT()`, RtlProvider and the language switch  (ui, 2026-10-31, commit see git log)
- **What now exists:** in-repo EN/AR dictionaries (`src/i18n/{en,ar}.ts`; `ar: Dict` makes a missing key a type error), `useT()`, `useLang()`, `labelOf()`, `resolveLang()`, `RtlProvider` (sets `<html lang dir>`, cookie `cp_lang`), `LangScope` (fixed-language subtree for side-by-side demos) and `LanguageSwitch`. The root layout resolves the language server-side (cookie, then `Accept-Language`, then `en`), so the first paint already has the right direction.
- **Public interfaces added or changed:** `useT(): (key: DictKey, vars?) => string`, `labelOf(kind, value, lang)`, `RtlProvider({ lang })`, `LanguageSwitch()`; see [docs/ui/README.md](../ui/README.md#i18n).
- **How to use it:** `const t = useT(); t("common.close")`; `labelOf("category", "IT Support", lang)`.
- **Config / env added:** cookie `cp_lang` (`en` | `ar`).
- **Acceptance:** `vitest run src/i18n src/components` -> `10 passed`; typecheck and lint exit 0.
- **Limitations / TODO / known issues:** the root layout reads cookies and headers, so every page renders dynamically. Chat, staff, pulse and lab strings are added by the tasks that build those pages. vitest is configured with `pool: "threads"` because forked workers timed out on this Windows machine.
- **Affects streams:** none outside UI.

### P5.3 — UI primitives and the `/dev/ui` kitchen sink  (ui, 2026-10-31, commit see git log)
- **What now exists:** `Button, Chip/ChipGroup, Badge, Card, Tabs/TabPanel, Table, ToastProvider/useToast, Dialog, Skeleton, EmptyState, Icon, ThemeSwitch, LanguageSwitch` in `src/components/ui` (exported from `index.ts`), each with a props type and TSDoc, keyboard support (arrows mirrored in RTL) and focus states. `/dev/ui` shows every primitive in English and Arabic side by side with a theme switch. A minimal `playwright.config.ts` and `e2e/devui.spec.ts` exist (P5.13 will extend the config).
- **Public interfaces added or changed:** see the catalog in [docs/ui/README.md](../ui/README.md#component-catalog-srccomponentsui-all-in-indexts). Tones are `cat-*`, `pri-*`, `ok|warn|danger|info|neutral` (`CATEGORY_TONE` / `PRIORITY_TONE` map exact backend labels).
- **How to use it:** `import { Button, Badge, CATEGORY_TONE } from "@/components/ui"`; `<Badge tone={CATEGORY_TONE["IT Support"]}>...</Badge>`.
- **Config / env added:** none.
- **Acceptance:** `vitest run` -> `4 files, 38 tests passed` (`src/components/ui`: 18, `src/i18n`+`src/design`: 20); `playwright test e2e/devui.spec.ts` -> `1 passed` (every Tab stop reachable, no horizontal overflow at 390px, theme forcing); typecheck, lint, build exit 0.
- **Limitations / TODO / known issues:** `ProbBar` and `SetBadge` (named in ARCHITECTURE 1.7) are P5.4. `ThemeSwitch` applies the saved theme after hydration (brief flash possible for a saved dark choice; an inline pre-paint script is a P5.17 polish item). `Dialog` is hand-rolled (not native `<dialog>`) because jsdom lacks `showModal`.
- **Affects streams:** none outside UI.

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

### P0.3 — Wire in the data pipeline, add `config.paths` and the holdout folders  (ML, 2026-10-31)
- **What now exists:** `campuspulse_ai.config.paths` (the one place for data/config/model paths, plus the holdout guard), the holdout READMEs `data/our_test/` and `data/robustness/` ("never trained on"), the augmentation schema in `data/augmented/README.md`, the repo-root `config/` directory (`datasets.yaml`), and pytest coverage of the legacy cleaning pipeline.
- **Public interfaces added:** `REPO_ROOT, DATA_RAW, DATA_CLEAN, DATA_AUGMENTED, OUR_TEST, ROBUSTNESS, CONFIG_DIR, LEXICONS, MODELS_FROZEN, REPORTS, HOLDOUT_MARKERS`, `find_repo_root(start=None) -> Path`, `is_holdout(path) -> bool` ([docs/ml/models.md §1](../ml/models.md#1-paths-campuspulse_aiconfigpaths)).
- **How to use it:** `from campuspulse_ai.config.paths import DATA_CLEAN, is_holdout; assert is_holdout(Path("data/our_test/our_test.csv"))`
- **Config / env added:** env `CAMPUSPULSE_ROOT` (optional root override; Foundation should add it to `.env.example` in P0.5). `config/datasets.yaml` (header only; keys arrive in P0.3d/e).
- **Acceptance:** `pytest services/ai/tests/unit/test_clean_pipeline.py -q` → `2 passed`; `python scripts/test_clean.py` → `ALL TESTS PASSED`; `pytest services/ai/tests/unit/test_paths.py -q` → `9 passed`.
- **Limitations / TODO / known issues:** `is_holdout` is a substring match (strict on purpose). **Parity issue for the lead:** with the pinned `pandas==3.0.6`, `clean_data.py` regenerates `cleaning_report.md` with tied `value_counts` rows in another order (md5 `ee82727f…` vs committed `eb2430a1…`, made with pandas 2.2.3); the 4 CSVs are identical. CI's `git diff --exit-code -- data/clean` will fail on the report until the lead decides (see the ML hand-back). On Windows the regenerated files are CRLF, so `git status` shows them modified although `git diff` is empty for the CSVs.
- **Affects streams:** all (paths); Foundation (CI `git diff` gate on `data/clean`, `CAMPUSPULSE_ROOT` in `.env.example`).

### P0.3a — Freeze a category-stratified `cv_fold` assignment  (ML, 2026-10-31)
- **What now exists:** `data/clean/cv_folds.csv` (`cv_group,cv_fold`, 30 rows, folds 0..4) from `scripts/make_folds.py`: one group per category per fold, all 3 priorities and ≥ 2 Arabic groups in every fold (LD-31, audit F1). It reproduces the audit's assignment exactly (rows/fold 84/84/84/89/91).
- **Public interfaces added:** `scripts/make_folds.py [--k] [--seed] [--include-augmented] [--out]`; `assign_folds(groups, k, seed, *, iterations, min_arabic_groups) -> dict[str, int]`; `append_new_groups(folds, new_groups, k) -> dict[str, int]` ([docs/ml/models.md §2.1](../ml/models.md#21-frozen-folds-cv_foldscsv-p03a-ld-31)).
- **How to use it:** `pd.read_csv("data/clean/train_val_combined.csv").merge(pd.read_csv("data/clean/cv_folds.csv"), on="cv_group")`; hold out `cv_fold == f` for f in 0..4.
- **Config / env added:** `config/train.yaml`: `seed: 42`, `cv.k: 5`, `cv.search_iterations: 20000`, `cv.min_arabic_groups_per_fold: 2`.
- **Acceptance:** `python scripts/make_folds.py` → `wrote data/clean/cv_folds.csv: 30 groups, 5 folds, categories 6/6 and priorities 3/3 in every fold, rows/fold 84/84/84/89/91`; `python -c "...;print(len(d),d.cv_fold.nunique())"` → `30 5`; a second run with `--out .tmp/folds2.csv` is byte-identical (`cmp` silent).
- **Limitations / TODO / known issues:** the search requires exactly k groups per category (true for the official data). New augmentation groups are placed by `--include-augmented` only; they never move an official group.
- **Affects streams:** ML (P1.8 `group_folds`, every OOF computation).

### P0.3b — Add derived columns `lang_script`, `is_arabizi`, `stated_urgency`  (ML, 2026-10-31)
- **What now exists:** `data/clean/train_val_features.csv` (432 rows, `request_id,lang_script,is_arabizi,stated_urgency`) from `scripts/add_derived_columns.py`, plus `data/clean/README.md` stating that `lang` in the CSVs is script-only and that the package `LangIdentifier` owns the Arabizi label (LD-33, audit F2). No existing CSV was rewritten.
- **Public interfaces added:** `python scripts/add_derived_columns.py`; `derive(combined) -> DataFrame` ([docs/ml/models.md §2.2](../ml/models.md#22-derived-features-train_val_featurescsv-p03b-ld-33)).
- **How to use it:** `feats = pd.read_csv("data/clean/train_val_features.csv"); pool = combined.merge(feats, on="request_id")`
- **Config / env added:** none.
- **Acceptance:** `python -c "import pandas as pd; d=pd.read_csv('data/clean/train_val_features.csv'); print(d.is_arabizi.sum(), d.stated_urgency.sum())"` → `0 27`.
- **Limitations / TODO / known issues:** `stated_urgency` here is the case-sensitive `URGENT` marker; the package `WrapperStripper` (P1.1) also flags lowercase/variant forms on new text, and agrees with this column on all 432 rows.
- **Affects streams:** ML (P1.8 pool, P2.8 fairness slices).

### P0.3c — Make `clean_data.py` safe on a cp1252 console  (ML, 2026-10-31)
- **What now exists:** `scripts/clean_data.py` reconfigures stdout to UTF-8 just before its final `print` of the Arabic report (the one permitted edit, LD-35). It no longer crashes with `UnicodeEncodeError` on a cp1252 console; every output file is still written by `run()` before the print.
- **Public interfaces added or changed:** none.
- **How to use it:** `python scripts/clean_data.py > $null; $LASTEXITCODE` → `0` (Windows PowerShell).
- **Config / env added:** none.
- **Acceptance:** before the edit, `$env:PYTHONIOENCODING='cp1252'; python scripts/clean_data.py > $null` → `exit=1` (`UnicodeEncodeError`); after it → `exit=0` (cp1252 and default env). Hash parity (md5, CRLF-normalised) with the edited script under pandas 2.2.3: `train_clean 174582df…, val_clean c3af332d…, train_val_combined d0f17ae8…, scenarios 65074205…, cleaning_report eb2430a1…`, all equal to the committed files. Under the pinned pandas 3.0.6 the four CSVs are equal and `cleaning_report.md` is `ee82727f…` (tie order only; pre-existing, independent of this edit).
- **Limitations / TODO / known issues:** the pandas-version difference in `cleaning_report.md` is escalated to the lead (P0.3 entry). `scripts/test_data_audit.py` (P0.3d) holds the standing parity check.
- **Affects streams:** Foundation (the CI Windows leg can run the script).

### P0.3d — Add `scripts/test_data_audit.py` (the audit's test gaps)  (ML, 2026-10-31)
- **What now exists:** a standing plain-Python data audit with the 11 checks of the data audit (regeneration parity and determinism, labels vs raw, cross-group near-duplicates, group integrity, fold feasibility and reproducibility, `label_flags.csv` validity, script/lang consistency, `normalize` idempotence, unseen-wrapper documentation, cp1252 exit code). It runs in temp copies and never writes to the repo. `test_clean.py` is unchanged.
- **Public interfaces added:** `python scripts/test_data_audit.py`; pytest `test_clean_pipeline.py::test_data_audit_passes` ([docs/ml/models.md §3](../ml/models.md#3-data-scripts)).
- **How to use it:** run it after any change under `data/`, `scripts/clean_data.py` or `scripts/make_folds.py`.
- **Config / env added:** `config/datasets.yaml` `audit.near_dup_cosine: 0.8`.
- **Acceptance:** `python scripts/test_data_audit.py` → `ok 1 … ok 11` then `DATA AUDIT TESTS PASSED` (exit 0); check 4 reports `max 0.375`; check 6 `rows/fold 84/84/84/89/91; byte-identical re-run`. `pytest services/ai/tests/unit/test_clean_pipeline.py -q` → `3 passed`.
- **Limitations / TODO / known issues:** check 1 accepts `cleaning_report.md` when it is equal up to line order, because pandas 3.0.6 orders tied `value_counts` rows differently from the committed (pandas 2.2.3) file; the four CSVs must be byte-equal. The check prints which case applied. Remove the tolerance once the lead regenerates the report with the pinned pandas.
- **Affects streams:** Foundation (add `python scripts/test_data_audit.py` to CI, P0.9), ML.

### P0.3e — Add the leakage gate `scripts/check_leakage.py` (official mode)  (ML, 2026-10-31)
- **What now exists:** the §3.2 leakage gate in char n-gram mode (no encoder): it fails on identical `text_norm` across `cv_group`s and on cross-group char_wb 3–5-gram TF-IDF cosine ≥ 0.8, printing each offending pair. `test_data_audit.py` check 4 now reuses its functions, and a unit test proves it fires on planted leakage.
- **Public interfaces added:** `python scripts/check_leakage.py --official`; `exact_cross_group(df)`, `char_near_pairs(df, threshold) -> list[NearPair]`, `max_cross_group_cosine(df)` ([docs/ml/models.md §3.1](../ml/models.md#31-leakage-gate-scriptscheck_leakagepy-p03e)).
- **How to use it:** `python scripts/check_leakage.py --official` (exit 0 clean, 1 on leakage).
- **Config / env added:** `config/datasets.yaml` `leakage.char_cosine: 0.8`, `leakage.cosine_merge: 0.90` (P2.1).
- **Acceptance:** `python scripts/check_leakage.py --official` → `0 identical text_norm across groups; 0 cross-group pairs >= 0.8 (max 0.375)`, exit 0. `pytest services/ai/tests/unit/test_check_leakage.py -q` → `3 passed`. `python scripts/test_data_audit.py` → `DATA AUDIT TESTS PASSED`.
- **Limitations / TODO / known issues:** official mode only. P2.1 adds augmented rows (text_norm from the package normalizer), holdout overlap and the encoder-cosine merge list. Char n-grams cannot see cross-lingual near-duplicates; the 12 AR↔EN pairs were found by reading.
- **Affects streams:** ML (P2.1, P2.4); Foundation (CI gate).

### P1.1 — Strip wrappers and normalize text with byte-for-byte parity to `clean_data.py`  (ML, 2026-10-31)
- **What now exists:** `adapters/preprocess/wrappers.py` with `WrapperStripper` (the `clean_data` exact loop plus case-insensitive/punctuation variants and an `urgent` regex for unseen wrappers) and literal copies of `collapse_ws`, `script_lang`, `normalize_text`. Parity holds on all 432 official rows for `core`, `prefix`, `suffix`, `text_norm`, `lang` and `stated_urgency` (= `has_urgent_marker`, 23 train + 4 val).
- **Public interfaces added:** `WrapperStripper(prefixes, suffixes, urgency_markers, urgent_regex, *, prefix_variants=False, variant_punctuation=())`, `WrapperStripper.from_yaml(path)`, `.strip(raw) -> StripResult`; `collapse_ws(s)`, `script_lang(text) -> "ar"|"en"`, `normalize_text(core, lang)` ([docs/ml/models.md §4.1](../ml/models.md#41-wrapper-stripping-and-normalization-wrapperspy-p11)).
- **How to use it:** `WrapperStripper.from_yaml(LEXICONS / "wrappers.yaml").strip("urgent: The bus is late")` → `core='The bus is late', stated_urgency=True`.
- **Config / env added:** `config/lexicons/wrappers.yaml`: `prefixes`, `suffixes`, `urgency_markers`, `urgent_regex: (?i)^urgent\b[\s:!.,،-]*`, `prefix_variants: true`, `variant_punctuation`.
- **Acceptance:** `pytest services/ai/tests/unit/test_normalizer_parity.py -q` → `10 passed`. Extra: `test_wrappers.py` → `7 passed` (no over-stripping of `Urgently …` / `Please help me …`, stacked wrappers, Arabic variants).
- **Limitations / TODO / known issues:** deviations from the draft spec, all parity-safe: (1) `urgent_regex` has `\b`, so `Urgently need …` is not cut to `ly need …`; (2) any stripped prefix matching the regex sets `stated_urgency` (the variant `Urgent!` is matched before the regex); (3) wrappers without trailing punctuation also accept an appended mark (`وشكرا.`), and an orphaned leading mark after an exact prefix is dropped (`لو سمحت، …`). `stated_urgency` is never a model feature.
- **Affects streams:** ML (P1.3 normalizer, P1.8 pool); Backend (P3 gaming detector reads `stated_urgency`).

### P1.2 — Add language ID and Arabizi transliteration  (ML, 2026-10-31)
- **What now exists:** `adapters/preprocess/langid.py` (`LangIdentifier`: EN/AR/ARABIZI, conservative, guard veto) and `adapters/preprocess/arabizi.py` (`ArabiziTransliterator`: proclitics → lexicon → digraphs → char map, output normalized like an Arabic `text_norm`), configured by `config/lexicons/arabizi.yaml` (340-entry lexicon) with a 24-pair golden fixture. The package `LangIdentifier` is now the only source of the Arabizi label (LD-33).
- **Public interfaces added:** `LangIdentifier(lexicon, guard_tokens, signal_digits, min_digit_tokens, min_lexicon_hits, *, guard_patterns=(), ignore_patterns=(), min_letters_in_digit_token=1)`, `.from_yaml(path)`, `.identify(text) -> Lang`, `.signals(text)`; `latin_tokens(text)`; `ArabiziTransliterator(lexicon, digraphs, charmap, *, proclitics=None, punctuation=None)`, `.from_yaml(path)`, `.transliterate(text)`, `.model_text(original)`; `MODEL_TEXT_SEPARATOR = " | "` ([docs/ml/models.md §4.2](../ml/models.md#42-language-id-and-arabizi-langidpy-arabizipy-p12-ld-33)).
- **How to use it:** `ArabiziTransliterator.from_yaml(LEXICONS / "arabizi.yaml").model_text("wein el bus")` → `"وين الباص | wein el bus"`.
- **Config / env added:** `config/lexicons/arabizi.yaml`: `lexicon`, `not_signals`, `proclitics`, `digraphs`, `charmap`, `punctuation`, `signal_digits`, `min_digit_tokens: 2`, `min_lexicon_hits: 1`, `min_letters_in_digit_token: 2`, `guard_tokens`, `guard_patterns`, `ignore_patterns`.
- **Acceptance:** `pytest services/ai/tests/unit/test_langid.py services/ai/tests/unit/test_arabizi.py -q` → `7 passed` (0 Arabizi on the 432 official rows; AR/EN equal the clean `lang`; 24/24 golden detected and transliterated exactly; 11 English probes with digits stay EN). Extra: `test_arabizi_rules.py` → `6 passed`. `mypy --strict services/ai/campuspulse_ai/adapters/preprocess/` → `Success: no issues found in 4 source files`.
- **Limitations / TODO / known issues:** **human check needed:** the lexicon and golden pairs were LLM-drafted; the developer should review them (P1.9 slot). Code-switched Arabizi containing an English function word (`... please help`) is labelled EN by design (single guard hit vetoes). The char-map fallback is approximate; the original text is always kept in `model_text`. Spec additions (all config, no thresholds in code): `not_signals`, `guard_patterns`, `ignore_patterns`, `min_letters_in_digit_token`, `proclitics`, `punctuation`.
- **Affects streams:** ML (P1.3 normalizer, P1.9 augmentation, P2.8 fairness slices); Backend/UI (the `arabizi-detected` input mode and the Arabizi hint read `NormalizedRequest.lang`).

### P1.3 — Assemble `DefaultNormalizer` (+ location extraction)  (ML, 2026-10-31)
- **What now exists:** `adapters/preprocess/normalizer.py::DefaultNormalizer` (the `Normalizer` port: wrappers → truncation → `text_norm` → language ID → `model_text` → location) and `adapters/preprocess/location.py::LocationExtractor` with `config/lexicons/gazetteer.yaml`. The location sub-step was **not** deferred.
- **Public interfaces added:** `DefaultNormalizer(wrappers, langid, arabizi, location, max_tokens)`, `DefaultNormalizer.from_lexicons(lexicon_dir, max_tokens, *, with_location=True)`, `.normalize(raw, picked_location=None) -> NormalizedRequest`; `LocationExtractor(buildings, room_regex)`, `.from_yaml(path)`, `.extract(text) -> Location | None` ([docs/ml/models.md §4.3–4.4](../ml/models.md#43-the-normalizer-defaultnormalizer-p13)).
- **How to use it:** `DefaultNormalizer.from_lexicons(LEXICONS, 256).normalize("Hi team, mesh 3arif wein el bus").model_text` → `"مش عارف وين الباص | mesh 3arif wein el bus"`.
- **Config / env added:** `config/train.yaml` `guards.max_tokens: 256` (copied into `config.json` by `train.py`); `config/lexicons/gazetteer.yaml` (`buildings`, `alias_templates`, `room_regex`).
- **Acceptance:** `pytest services/ai/tests/unit/test_normalizer.py -q` → `6 passed`. Extra: `test_location.py` → `12 passed` (5 extractions, 5 no-false-location cases, port conformance, punctuation-only → `InvalidInput`). `mypy --strict services/ai/campuspulse_ai/adapters/preprocess/` → `Success: no issues found in 6 source files`.
- **Limitations / TODO / known issues:** decisions: `text_norm` uses `script_lang(core)` instead of `script_lang(raw)` (identical on all 432 rows, tested; more robust when an English wrapper surrounds Arabic text); `lang` is identified on the core, so an English wrapper cannot veto Arabizi; punctuation-only input raises `InvalidInput` (handled by LD-17 in `BatchPredictUseCase`). The gazetteer has 11 codes (A–M minus I/J); P4.2 says "10 buildings", so the DB stream must reconcile.
- **Affects streams:** ML (P1.8 `load_pool`, P1.15 `TriageCore`); DB (building codes in `01_buildings.sql`); Backend (`NormalizedRequest.location`, `stated_urgency`).

### P1.4 — Add `FrozenConfig`, `config/train.yaml` and the `ArtifactStore` (manifest + sha256)  (ML, 2026-10-31)
- **What now exists:** `config/frozen.py::FrozenConfig` (strict, immutable schema of `config.json`: §1.6 + LD-10 keys, validated distributions, trained thresholds, no `stated_urgency` feature), `adapters/artifacts/io.py::FileArtifactStore` (writes and verifies `MANIFEST.json`, sha256 per file), the full `config/train.yaml` (tuning knobs + the non-learned sections `train.py` copies) and `config/hand_tuned.yaml`.
- **Public interfaces added:** `FrozenConfig.load(path)`, `FrozenConfig.from_dict(data, *, source)`, `.save(path)`, `.to_json()`, section models `EncoderCfg, EnsembleCfg, M1Cfg, M2LrCfg, KnnCfg, HeadCfg, ConformalCfg, ThresholdsCfg, GuardsCfg, LlmCfg, ExplainCfg, PriorsCfg, CvCfg`; `FileArtifactStore(now=...)`, `.write_manifest(model_dir, files) -> Manifest`, `.load_manifest(model_dir) -> Manifest`, `sha256_file(path)`, `MANIFEST_NAME` ([docs/ml/models.md §5–6](../ml/models.md#5-frozenconfig-campuspulse_aiconfigfrozen-p14-the-schema-of-configjson)).
- **How to use it:** `cfg = FrozenConfig.load(model_dir / "config.json"); FileArtifactStore().load_manifest(model_dir)`. A valid test mapping: `from fixtures.frozen_config import valid_config_dict`.
- **Config / env added:** `config/train.yaml`: `artifact_version`, `cv.{group_col,fold_col,folds_file}`, `alpha`, `alpha_priority_fallback`, `ask_rate_max`, `grids`, `tau_ood_percentile`, `tau_margin`, `human_review_min_acc`, `mondrian`, `m3`, plus copied `encoder`, `ensemble.members`, `m1` n-grams, `knn`, `priority_head`, `conformal`, `guards`, `llm`, `explain`. `config/hand_tuned.yaml`: `tau_faq: 0.75`, `tau_inc: 0.80`.
- **Acceptance:** `pytest services/ai/tests/unit/test_frozen_config.py services/ai/tests/unit/test_manifest.py -q` → `7 passed`. Extra: `test_config_and_artifacts_edges.py` → `13 passed`. `mypy --strict services/ai/campuspulse_ai/config/ services/ai/campuspulse_ai/adapters/artifacts/ services/ai/campuspulse_ai/adapters/preprocess/` → `Success: no issues found in 11 source files`.
- **Limitations / TODO / known issues:** no `config.json` exists yet (P1.16). `encoder.runtime` also allows `hashing` for the `tiny_model_dir` fixture (`HashingEncoder`). Thresholds `tau_injection`/`tau_safety` have no upper bound (max similarity + margin may exceed 1, LD-18). The manifest's `artifact_version` falls back to the directory name when there is no `config.json`.
- **Affects streams:** ML (every later component reads `FrozenConfig`; `train.py`/`predict.py` use `FileArtifactStore`); Backend (`/health` reports `Manifest.sha`; `build_test()` fixtures can use `valid_config_dict`); Foundation (`fetch_models.py` verification).

### P0.9 — GitHub Actions CI  (foundation, 2026-10-31, commit see git log)
- **What now exists:** `.github/workflows/ci.yml` with jobs `changes` (path filter), `python` (3.11 and 3.13), `data-gates`, `api-contract`, `web` and `docker` (push to `main` only).
- **Public interfaces added or changed:** none. Check names for branch protection: `python (3.11)`, `python (3.13)`, `data-gates`, `api-contract`, `web`.
- **How to use it:** see [docs/ops/README.md](../ops/README.md#ci) for what each job checks and how to reproduce it locally.
- **Config / env added:** none, no secrets.
- **Acceptance:** every command run locally: ruff `All checks passed!`; `mypy --strict` `Success: no issues found in 58 source files`; pytest `237 passed, 8 skipped, 38 deselected`; `test_clean.py` `ALL TESTS PASSED` with no diff in `data/clean` apart from CRLF (Windows only); `DATA AUDIT TESTS PASSED`; leakage `0 identical text_norm across groups; 0 cross-group pairs >= 0.8 (max 0.375)`; `gen_api_docs.py --check` up to date; fresh mock export identical to `services/ai/openapi.json`; web typecheck, lint, vitest (`38 passed`) and `next build` pass; `docker build` succeeds. YAML parses. The workflow has not run on GitHub yet.
- **Limitations / TODO / known issues:** the generated-types check is skipped until `apps/web` defines `gen:types`. No Windows leg, no Playwright, no `artifacts` job (P1.19). `pnpm test` is run with `--run` because the script is plain `vitest`.
- **Affects streams:** all (keep CI green); UI (add `gen:types` and commit its output); ML (any change to `data/clean` must be a regeneration of `clean_data.py`).
