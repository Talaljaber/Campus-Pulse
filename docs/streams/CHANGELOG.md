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

### P3.7 / P1.15 (moved to DB) — InMemoryMemoryStore and NullMemoryStore  (DB, 2026-10-31, commit a27fc43)
- **What now exists:** `adapters/memory/inmemory.py` (dict-backed `MemoryStore` for tests and the offline red team) and `adapters/memory/null.py` (the offline store `build_offline` wires, §3.11).
- **Public interfaces added or changed:** `InMemoryMemoryStore()`, `NullMemoryStore()`. See [schema.md › Memory stores](../db/schema.md#memory-stores-adaptersmemory).
- **How to use it:** `memory = InMemoryMemoryStore(); memory.add(MemoryExample(id="", ...)); memory.neighbors(emb, k=5, min_sim=0.8)`.
- **Config / env added:** none.
- **Acceptance:** `pytest services/ai/tests/contracts/test_memory_store_contract.py services/ai/tests/unit/test_null_memory.py -q` → `15 passed`. The 7 inmemory cases (previously skipped), the 7 live pgvector cases and the null test all pass.
- **Limitations / TODO / known issues:** the memory-aware kNN merge (P3.7) stays with ML/Backend.
- **Affects streams:** ML (`build_offline` uses `NullMemoryStore`), Backend (`build_test()` uses `InMemoryMemoryStore`).

### P4.10 (partial) — WindowedCentroidDetector and the Pulse simulator  (DB, 2026-10-31, commits f3796ec, 1f2cf3e)
- **What now exists:**
  - `adapters/pulse/incident_detector.py`
  - `scripts/simulate_pulse.py` (direct mode)
  - `config/simulation/wifi_m.yaml` (8 fictional EN/AR/Arabizi reports, building M)
  - `tests/unit/test_incident_detector.py`
- **Public interfaces added or changed:** `WindowedCentroidDetector(repo, vectors, clock, tau_inc, window_min, min_reports=3, bump_at=6).detect(req, pred, embedding) -> IncidentDecision`. The detector saves the incident; `members` = member request ids with `req` last. See [schema.md › Incident detection](../db/schema.md#incident-detection-pulse).
- **How to use it:** in `TriageUseCase`, after `vectors.upsert("requests", ...)` ([12b]): `decision = detector.detect(req, pred, embedding)`, then (P4.8) merge member tickets, open the one incident ticket, and broadcast.
- **Config / env added:** `tau_inc` is a constructor argument (default 0.80 in the simulator) until `hand_tuned.yaml` exists (LD-11); `INCIDENT_WINDOW_MIN` (30) comes from Settings.
- **Acceptance:**
  - `pytest services/ai/tests/unit/test_incident_detector.py -q` → `7 passed` local (InMemoryRepository + LocalNumpyVectorStore) and `7 passed` with `-m supabase`. Cases: 2 → none, 3 → new, 4 → attach; priority max, bumped once at 6; other building/category separate; outside the window → none; no location or a dissimilar report → none; thresholds from config.
  - Live simulator, `python scripts/simulate_pulse.py --interval 0 --reset`, with synthetic embeddings: `[3/8] … incident created: 759ea121-… building=M category=IT Support reports=3 priority=medium` → `[6/8] … reports=6 priority=high` + `priority bumped -> high` → `[8/8] … reports=8`. The simulated rows were deleted afterwards.
  - Full suites: default `169 passed, 1 skipped`; `-m supabase` `44 passed, 1 skipped`.
- **Limitations / TODO / known issues:**
  - **Not built (waits for Backend P4.8):** `ResolveIncidentUseCase`, the broadcast, the incidents route, and the simulator's `--mode api` (P4.14).
  - **Attach window:** an incident is only attached to when it was opened inside the window; after 30 minutes a new one opens.
  - **`tau_inc` on the real encoder:** with synthetic embeddings the clustering is trivially tight. Measuring `tau_inc` on the real encoder (X4.3 note) waits for P1.6.
- **Affects streams:** Backend (the detector call in TriageUseCase/Act and the merge/broadcast), UI (Pulse page: `incidents` rows plus Realtime; run the simulator for live data).

### P4.3 follow-up — seed contacts  (DB, 2026-10-31)
- **Acceptance:** `python scripts/check_seed_contacts.py` → `seed contacts OK: 6 addresses in 4 files, all allow-listed`. The user added two personal Gmail inboxes to the local `DEMO_EMAIL_ALLOWLIST`; a GJU address they offered was left out (CLAUDE.md non-negotiable).
- **Pending:** `seed_demo_users.py` waits for `DEMO_USER_PASSWORD` in the worktree `.env`.

### P3.2 — Question bank and expected-information-gain clarifier  (backend, 2026-10-31, commits 4c61049, 5f806a3)
- **What now exists:**
  - `config/clarify_questions.yaml`: 7 EN / Jordanian-Arabic questions (the SPEC §5.1 [8] six plus `cat:Facilities|IT Support`), each with option effects and a `not_sure` chip.
  - The out_of_scope `topic` chip list (LD-36) in the same file.
  - `InfoGainStrategy`, which implements the `ClarificationStrategy` port.
- **Public interfaces added:** see [docs/api/README.md › Clarification](../api/README.md#clarification-llm-understanding).
  - `adapters/clarify/bank.py`:
    - `QuestionBank.load(path, *, features=None)`, `.questions` (7), `.topic`, `.applicable(set_cat, set_pri, *, top_category=None)` and `.get(question_id)` (NotFound);
    - `BankQuestion` (bilingual entry; `.render(lang) -> domain ClarificationQuestion`), `QuestionOption`, `TOPIC_QUESTION_ID = "topic"`.
  - `adapters/clarify/info_gain.py`:
    - `InfoGainStrategy(bank, rephraser=None)` with `.select(core, lang, asked)`, `.apply(core, question_id, option_id)` and `.topic_question(lang)`;
    - `expected_set_size(core, question)`, `QuestionRephraser` (protocol) and `NullRephraser`.
- **How to use it:**
  ```python
  strategy = InfoGainStrategy(QuestionBank.load("config/clarify_questions.yaml", features=config.priority_head.features))
  q = strategy.select(core, req.lang, asked=[c.question_id for c in repo.clarifications_for(request_id)])  # None = no question
  _, constraints = strategy.apply(core, q.id, "registration")   # then TriageCore.classify(raw, loc, constraints) (LD-29)
  chips = strategy.topic_question(req.lang)                     # for status out_of_scope
  ```
- **Config / env added:** none. The bank path is passed in; a `Settings.config_dir` does not exist yet (see the change requests in the hand-back).
- **Acceptance:**
  - `pytest services/ai/tests/unit/test_clarify.py -q` → `19 passed`.
  - `python -c "from campuspulse_ai.adapters.clarify.bank import QuestionBank as B; print(len(B.load('config/clarify_questions.yaml').questions))"` → `7`.
- **Limitations / TODO / known issues:**
  - The plan sketch names the bank entry `ClarificationQuestion`. That name is the frozen domain value (one language), so the bilingual entry is `BankQuestion` and `select` returns the rendered domain value. `expected_info_gain` holds the expected number of labels removed (|S| − E[size]).
  - Scoring: for a split smaller than the set, uncovered mass counts as "the set stays as it is" (a remainder term); for an exact split this is the SPEC formula. Every full split scores 1, so for pairs the category-first rule and the bank order decide.
  - New optional field `when_category` keeps the safety question for Facilities/Transportation and the deadline question for the other categories.
  - `{low, high}` has no question: `select` returns None, and P3.9 must then continue the policy as if the budget were spent.
  - Arabizi requests get the Arabic text. **The Arabic wording is a draft and needs a native-speaker check.**
  - Feature names are checked only when `features=` is passed; P3.9 should pass `FrozenConfig.priority_head.features`.
  - The LLM rephraser is cut (B-list); `NullRephraser` is the default.
  - Test fakes live in `tests/fixtures/backend_fakes.py` (`make_core`, `make_request`, `FakeLAC`, `FrozenClock`, `ScriptedOracle`, `fake_call`), separate from ML's `fakes.py`.
- **Affects streams:**
  - Backend: P3.9 ASK and out_of_scope, P3.10 apply and second question.
  - UI: the question ids and option ids above are the real ones; the fixtures already use `cat:Registration|IT Support` with `registration`/`it`/`not_sure`.
  - ML: feature effects use the evidence names `deadline_today` and `safety_risk`, which the priority head must accept as constraints.

### P3.3 — Tier-1 LLM oracle, caches, cost logging and merge  (backend, 2026-10-31, commits 35603b5, dd2e8e1, bdb827f, 25b4ed9)
- **What now exists:** the set-constrained tier-1 tie-breaker over OpenRouter (plain httpx), its response caches and cost logger, and the `LLMMerger`. Tier 2 is not wired (UD-3).
- **Public interfaces added:** see [docs/api/README.md › LLM tier](../api/README.md#clarification-llm-understanding).
  - `adapters/llm/openrouter.py`:
    - `OpenRouterClient(api_key, *, timeout_s, base_url=..., max_retries=2, retry_backoff_s=0.5, sleep=time.sleep, transport=None)` with `.chat(model_id, messages, *, params, response_format=None) -> ChatResult` (`LLMUnavailable`);
    - `OpenRouterOracle(tier, model_id, http, cache, cost, *, prompt, max_input_tokens, daily_budget_usd)` implements `LabelOracle` (`LLMUnavailable`, `LLMOutputOutOfSet`);
    - `make_call(...)` builds the `LLMCall` records.
  - `adapters/llm/set_constrained.py`: `build_messages`, `answer_schema`, `response_format`, `cache_key`, `parse_answer(raw, allowed_cat, allowed_pri, *, max_reason_words)`, `load_json_object` and `truncate_tokens`.
  - `adapters/llm/prompt.py`: `PromptTemplate.load(path)`, `.render(**values)` and `.limit(name)`; `load_prompt(dir, name, version)`. Prompts are Markdown with YAML front matter (pinned request parameters and output limits) and `# system` / `# user` sections.
  - Ports:
    - `adapters/llm/null.py`: `NullOracle` (`LabelOracle`, always `LLMUnavailable`);
    - `adapters/llm/cache_sqlite.py`: `SqliteCache(path)`;
    - `adapters/llm/cache_dict.py`: `DictCache`;
    - `adapters/llm/cost.py`: `InMemoryCostLogger(clock=None)` (per-day totals when given a clock), `estimate_cost` and `PRICES_PER_MTOK`.
  - `application/services/llm_merge.py`: `LLMMerger.merge(core, answer, w_llm, conf_cat, conf_pri) -> CoreResult` and `merge_vector`.
  - `config/prompts/oracle_v1.md`.
- **How to use it:**
  ```python
  http = OpenRouterClient(settings.openrouter_api_key.get_secret_value(), timeout_s=20)
  oracle = OpenRouterOracle(Tier.TIER1, settings.openrouter_tier1_model, http, SqliteCache(".cache/llm.sqlite"),
                            InMemoryCostLogger(SystemClock()), prompt=load_prompt("config/prompts", "oracle", config.llm.prompt_version),
                            max_input_tokens=config.guards.max_tokens, daily_budget_usd=settings.llm_daily_budget_usd)
  answer = oracle.choose(req, core.set_cat, core.set_pri, OracleContext(req.lang, core.neighbors, "v1"))
  core = LLMMerger().merge(core, answer, config.llm.w_llm, conformal_cat, conformal_pri)
  ```
- **Config / env added:** none new. It reads `OPENROUTER_API_KEY`, `OPENROUTER_TIER1_MODEL` and `LLM_DAILY_BUDGET_USD` (existing Settings). The timeout and cache path are constructor arguments until Settings has `LLM_TIMEOUT_S` / `LLM_CACHE_PATH` (change request). The request parameters (`temperature 0`, `top_p 1`, `seed 42`, `max_tokens 80`) and `max_reason_words 20` are in the prompt front matter.
- **Acceptance:**
  - `pytest services/ai/tests/unit/test_oracle.py services/ai/tests/unit/test_llm_merge.py services/ai/tests/unit/test_cost.py -q` → `26 passed`.
  - `pytest services/ai/tests/test_architecture.py -q` → `5 passed`.
  - `python -c "import sys, campuspulse_ai.adapters.llm.openrouter, campuspulse_ai.adapters.llm.null, campuspulse_ai.adapters.understand.llm_understander; print('httpx' in sys.modules)"` → `False`; the same check is a unit test.
  - The manual run with a key was **not done**: there is no OpenRouter key on this machine.
- **Limitations / TODO / known issues:**
  - Deviations from the plan sketch:
    - `OpenRouterOracle` takes a shared `OpenRouterClient` (as P3.3a's understander does) and a loaded `PromptTemplate` instead of `api_key`/`timeout_s`/`base_url`/`prompt_version`;
    - it takes no `clock`: the daily budget is per Amman day inside `InMemoryCostLogger(clock)`;
    - it takes `max_input_tokens` (`guards.max_tokens`).
  - The response format is a strict JSON schema whose enums are the allowed sets (stronger than `json_object`), and the reply is still validated locally.
  - `require_parameters` is **not** sent, because `seed` is not supported by every provider. Unsupported parameters are ignored and the local validation still applies.
  - The text sent is `req.core` (wrapper-stripped), so a stripped "URGENT:" never reaches the model.
  - Out-of-set and invalid replies are costed but not cached.
  - The `tests/fixtures/openrouter/*.json` replies are hand-written in OpenRouter's response shape. Replace them with real recordings once a key exists.
  - Unknown model ids are costed at the highest pinned price.
  - `NullOracle` lives in `adapters/llm/null.py` (Backend-owned): the P1.15 task must not re-create it.
  - `composition/offline.py` does not exist yet, so the plan's "`import composition.offline` has no httpx" check is covered by the module-level check above.
- **Affects streams:**
  - Backend: P3.9 ESCALATE loop, `build_online` wiring.
  - ML: P1.15 `build_offline(use_llm=True)` builds `OpenRouterOracle` + `SqliteCache`; the P2 "ensemble+router" benchmark row. `LLMMerger` needs the real `LACConformal` predictors.
  - Foundation: Settings change request.

### P3.3a — RequestUnderstander: LLM and rule-based understanding  (backend, 2026-10-31, commits 0fa1dab, 4fed015, f53d031)
- **What now exists:** structured understanding of a request (UD-10): EN and AR summaries, entities, a student reply, and the ticket title and body.
  - It comes from the tier-1 model, schema-validated, at temperature 0, cached and costed.
  - It falls back to rules when there is no key, on an error or a rejected reply, and for injection-flagged requests.
  - It never changes the labels.
- **Public interfaces added:** see [docs/api/README.md › Understanding](../api/README.md#clarification-llm-understanding).
  - `adapters/understand/llm_understander.py`: `LLMUnderstander(http, model_id, prompt, cache, cost, fallback, *, clock, max_input_tokens, daily_budget_usd, tier=TIER1)` implements `RequestUnderstander`. It never raises.
  - `adapters/understand/rule_understander.py`: `RuleBasedUnderstander(templates, clock, limits)`, `ReplyTemplates.load(dir)` and `clip`.
  - `adapters/understand/schema.py`:
    - `UnderstandLimits.from_prompt(prompt)`, `decided_labels(core)` (a singleton set's label, else the argmax);
    - `understanding_schema`, `response_format`, and `parse_understanding(raw, req, category, priority, limits, prompt_version)` (`LLMOutputOutOfSet`).
  - `adapters/understand/entities.py`: `extract_entities(req, today)`, `grounded(value, req)` and text helpers.
  - `application/services/understanding.py`: `understanding_flags(u)` → `{"understanding_fallback"}` when `u.source == "rules"`.
  - Config: `config/prompts/understand_v1.md` and `config/templates/replies.{en,ar}.yaml`.
- **How to use it:**
  ```python
  prompt = load_prompt("config/prompts", "understand", "v1")
  rules = RuleBasedUnderstander(ReplyTemplates.load("config/templates"), clock, UnderstandLimits.from_prompt(prompt))
  understander = LLMUnderstander(http, settings.openrouter_tier1_model, prompt, cache, cost, rules, clock=clock,
                                 max_input_tokens=config.guards.max_tokens, daily_budget_usd=settings.llm_daily_budget_usd) \
      if llm_on else rules
  u = understander.understand(req, decided_core, plan.kind)
  flags |= understanding_flags(u)
  ```
- **Config / env added:** none in Settings. `understand.model_id` is `OPENROUTER_TIER1_MODEL`. `prompt_version` (`v1`) and the limits (`max_title_chars 80`, `max_reply_chars 400`, `max_summary_chars 300`, `max_body_chars 1200`, `max_entity_chars 60`) are in the prompt front matter. The timeout is the shared client's. `understand.enabled` = the composition choosing `LLMUnderstander` or `RuleBasedUnderstander`.
- **Acceptance:** `pytest services/ai/tests/test_understander.py -q` → `7 passed`. The manual `curl.exe` check with a key was **not done** (no key, and no real `/v1/triage` until P3.12).
- **Limitations / TODO / known issues:**
  - Grounding:
    - The model must echo the decided labels (single-value enums), and a different label is rejected.
    - Course codes, rooms and buildings must occur in the request.
    - The reply must be in the request language (Arabic script for `ar`/`arabizi`).
    - Free-text claims inside the reply (e.g. an invented fee) are not machine-checked beyond the prompt rules; the P4.11 red team should cover them.
  - The schema sent to the model carries length limits as descriptions, not `maxLength`, because strict modes reject them. The limits are enforced locally.
  - The cache key adds the model id, action, location and date to the spec's (prompt version, text, labels), so "today" resolves per day.
  - The understander also honours the shared `LLM_DAILY_BUDGET_USD`.
  - The rule-based summaries quote the request text and do not translate it.
  - **The Arabic templates and prompt examples are drafts and need a native-speaker check.**
  - Files added beyond the plan: `entities.py`, `application/services/understanding.py`, and an empty `adapters/understand/__init__.py`.
  - Not wired into `build_online` yet (LD-37: assigned later). P3.9 adds `understanding` to the response.
- **Affects streams:**
  - Backend: P3.9 `understanding` and the fallback flag, P4.8 Linear title/body and the outbox reply, P4.11 red-team reply attacks.
  - DB: P4.21 can use `entities`.
  - UI: `understanding.source` and `understanding_fallback`.

### P3.6 — GamingDetector (anti-gaming signals)  (backend, 2026-10-31, commits 94430f2, a3ba020)
- **What now exists:** `application/services/gaming.py`: after the priority is final it adds `urgency_unsupported` (staff-only) and `priority_gaming_suspected` (admin-only) from the counters `Repository.bump_student_signals` returns (D-006). It never returns or changes a label.
- **Public interfaces added:** `GamingDetector(repo, min_requests, claim_ratio, high_ratio_max, *, injection_strikes=2, high_evidence=HIGH_EVIDENCE_FEATURES)`, `.check(req, priority, evidence, alias, injection) -> GamingResult(flags, signals)`, `.suspected(signals)`, `.has_high_evidence(evidence)`; constants `URGENCY_UNSUPPORTED`, `GAMING_SUSPECTED`. See [docs/api/README.md › Anti-gaming flags](../api/README.md#actions-side-effects).
- **How to use it:** `g = GamingDetector(repo, s.gaming_min_requests, s.gaming_claim_ratio, s.gaming_high_ratio_max)`; `flags |= g.check(req, final_priority, core.evidence, alias, "injection_attempt" in core.flags).flags`.
- **Config / env added:** Settings `GAMING_MIN_REQUESTS` (5), `GAMING_CLAIM_RATIO` (0.8), `GAMING_HIGH_RATIO_MAX` (0.2), in `.env.example` and the ops env table (separate commit `94430f2`, which also adds the P4.4/P4.6 settings).
- **Acceptance:** `pytest services/ai/tests/unit/test_gaming.py -q` → `11 passed` (5 claimed-urgent/0 high → flag; supported claims → no flag; the note needs a claim and no high evidence; 2 injections → flag; label and inputs unchanged; anonymous not counted; per-alias; thresholds validated; `to_student_view` strips both flags).
- **Limitations / TODO / known issues:**
  - **Placement:** `application/services/gaming.py`, not the plan's `adapters/guards/gaming.py` (an ML-owned path). It is pure policy over the `Repository` port, so the application layer is a natural home.
  - **High ratio:** `StudentSignals` carries no plain high count, so "high/n" is measured over the alias's claims: `(claimed_urgent − claimed_urgent_not_high) / claimed_urgent ≤ high_ratio_max`. The exact spec formula needs `StudentSignals.high` (the DB already has `n_high`): optional change request.
  - Empty alias → not counted, never suspected. The injection-strike count (2) is a constructor default, not a Setting.
- **Affects streams:** Backend (P3.9 calls it at [9b]); UI (the flags are already filtered by `to_student_view` and `predictions_student_v`).

### P3.8 (ActionPlanner part) — routing table and TableActionPlanner  (backend, 2026-10-31, commit c806d05)
- **What now exists:** `config/actions.yaml` (the SPEC §5.1 [11] table with UD-1, D-005 office codes, SLA hours, safety and provisional rules) and `TableActionPlanner` in `domain/routing.py` (pure, stdlib-only, validated from the parsed dict).
- **Public interfaces added:** `ActionsConfig.from_dict(data)` (strict: unknown keys, missing cells, unknown offices or kinds → `ValueError`), `.route(category, priority)`; `Route`, `SafetyRule`; `TableActionPlanner(config).plan(category, priority, flags, provisional) -> ActionPlan`; `deferred_kind(plan)`; `SAFETY_FLAG`, `DEFERRED_TAG_PREFIX`. Table: [docs/api/README.md › Routing](../api/README.md#actions-side-effects).
- **How to use it:** `planner = TableActionPlanner(ActionsConfig.from_dict(yaml.safe_load(Path("config/actions.yaml").read_text("utf-8"))))`; `plan = planner.plan(cat, pri, pred_flags | fired_evidence_names, provisional)`.
- **Config / env added:** `config/actions.yaml`: `offices`, `sla_hours {high: 24, medium: 72, low: 336}`, `safety {kind: safety_alert, also_ticket: true, tags: [safety]}`, `provisional {tags: [unconfirmed]}`, `routes[category]{office, low, medium, high}` with `kind`, `tags`, `also_ticket`, `evidence_tags`.
- **Acceptance:** `pytest services/ai/tests/unit/test_routing.py -q` → `37 passed` (18 cells → kind/office; offices = D-005 exactly; SLA hours; only Academic Support × high books; Registration × high = escalation ticket; safety overrides any category even when provisional; provisional → ticket + `deferred:<kind>`; `exam_now` → `exam-in-progress`; 8 invalid configs rejected). `pytest services/ai/tests/test_architecture.py -q` → `5 passed` (routing stays stdlib-only).
- **Limitations / TODO / known issues:**
  - Rules: safety first (fires even when provisional, plus `unconfirmed`), then provisional → ticket only with `deferred:<kind>`, else the cell. Evidence tags apply when the evidence *name* is in `flags`, so ActUseCase passes `pred.flags | {fired evidence names}`.
  - Transportation × high is a `ticket` tagged `transport-alert` (there is no plain `alert` ActionType, and a late bus is not a safety alert); P4.8 sends the office alert for that tag. Finance × high (`escalation`): P4.8 may move `sla_due_at` earlier from `understanding.entities.deadline`.
  - `build_test()` and the DTO work are skipped as instructed (LD-36; waits for the ML `tiny_model_dir`).
- **Affects streams:** Backend (P3.9 act v0, P4.8); UI (`action.type`/`action.tags` values); DB (office codes match D-005).

### P4.4 — Notifications: AllowlistedNotifier, GmailSmtpNotifier, InAppNotifier, outbox  (backend, 2026-10-31, commits 16497b5, 96532f7)
- **What now exists:** `adapters/notify/{allowlist,gmail_smtp,inapp,outbox,channels}.py` and the opt-in `scripts/smoke_email.py`. The allow-list is enforced in code on every email path; no test can send mail.
- **Public interfaces added:** see [docs/integrations.md › Notifications](../integrations.md#3-notifications).
  - `AllowlistedNotifier(inner, policy, repo).send(msg)`: the outermost decorator and the only writer of notifier outbox rows (`rejected` / `failed` / sent).
  - `GmailSmtpNotifier(host, port, user, app_password: SecretStr, *, policy, clock, timeout_s, max_retries, backoff_s, daily_cap, use_ssl=None, sender_name=..., smtp_factory=None, sleep=time.sleep)`; `classify(exc) -> NotificationError`; `default_smtp_factory`.
  - `InAppNotifier(repo, *, notification_kind="message")`; `ChannelNotifier({kind: notifier})`; `OutboxRecorder(repo)`.
  - Test fakes in `tests/fixtures/backend_fakes.py`: `FakeNotifier`, `make_outbox`.
- **How to use it:** the chain in [integrations.md §3](../integrations.md#3-notifications): `AllowlistedNotifier(ChannelNotifier({"email": GmailSmtpNotifier(...), "in_app": InAppNotifier(repo)}), RecipientPolicy(s.demo_email_allowlist), repo)`.
- **Config / env added:** `SMTP_TIMEOUT_S` (10), `SMTP_MAX_RETRIES` (2), `SMTP_BACKOFF_S` (1.0), `SMTP_DAILY_CAP` (100).
- **Acceptance:**
  - X4.7 `pytest services/ai/tests/unit/test_allowlist.py -q` → `15 passed` (`real.person@gju.edu.jo` → `RecipientNotAllowed`, outbox `rejected`, provider called 0 times; an empty list rejects all; exact case-insensitive match with no plus/subdomain wildcards; failures recorded `failed`; the SMTP notifier refuses before connecting).
  - `pytest services/ai/tests/unit/test_gmail_smtp.py -q` → `23 passed` (STARTTLS flow, 465 implicit TLS, 535 not retried, 421 retried twice, 12 error mappings, Message-ID recorded, password masked, daily cap, default factory = stdlib smtplib).
  - `pytest services/ai/tests/unit/test_notifications.py services/ai/tests/unit/test_smoke_email.py -q` → `8 passed`.
  - The `import campuspulse_ai.composition.offline` check was **not run**: `composition/offline.py` does not exist yet (ML P1.15). The notify modules import only stdlib and pydantic `SecretStr`.
  - The live send was **not run** (opt-in, for the user).
- **Limitations / TODO / known issues:**
  - `OutboxMessage` has no `error` field and no `deferred`/`simulated` status, so reasons go to `events` (`outbox.rejected` / `outbox.failed`) and the daily cap raises `NotificationError(retryable=False)` → `failed` (change request filed).
  - The daily cap is counted in-process (it resets on restart); Gmail's own limit is 500/day.
  - `ActUseCase` must not save notifier outbox rows itself (the decorator does); it only catches the errors.
- **Affects streams:** Backend (P4.8/P4.9/P4.10 notifier chain); DB (outbox `error` column unused until the entity has it); UI (outbox statuses `sent`/`failed`/`rejected`).

### P4.6 — Ticket sinks: SupabaseSink, RetryingSink, LinearSink, docs/integrations.md  (backend, 2026-10-31, commits 28d79e2, 0d049e6)
- **What now exists:** `adapters/integrations/{supabase_sink,retrying,linear}.py`, `config/integrations.yaml` with the verified CampusPulse workspace values (team **CDP**, its state types, the six labels), Linear fixtures and [docs/integrations.md](../integrations.md).
- **Public interfaces added:** `SupabaseSink(repo)`; `RetryingSink(inner, max_attempts, base_backoff_s, sleep=time.sleep)`; `LinearSink(api_key: SecretStr, webhook_secret: SecretStr, mapping, http: httpx.Client, clock)` with `create`/`update_status`/`close`/`handle_inbound`; `LinearMapping.load(path)` / `.from_dict(raw)` / `.team_key(office)` / `.priority_for(priority, safety=False)`; `verify_signature(secret, raw, sig)`, `sign(secret, raw)`. Fakes: `FakeSink`, `make_ticket`.
- **How to use it:** [integrations.md §1.4](../integrations.md#14-linearsink--adaptersintegrationslinearpy): `RetryingSink(LinearSink(s.linear_api_key, s.linear_webhook_secret, mapping, httpx.Client(timeout=mapping.timeout_s), clock), s.sink_retry_max, s.sink_retry_base_s)` with `mapping = LinearMapping.load(Path("config/integrations.yaml"))`.
- **Config / env added:** `SINK_RETRY_MAX` (3), `SINK_RETRY_BASE_S` (0.5); `config/integrations.yaml` (`enabled`, `linear.{api_url, timeout_s 10, webhook_tolerance_s 60, timezone, default_team CDP, team_by_office, label_by_category, priority_map {high 2, medium 3, low 4, safety 1}, state_type_by_status, status_by_state_type}`).
- **Acceptance:** `pytest services/ai/tests/unit/test_linear_sink.py services/ai/tests/unit/test_retrying_sink.py -q` → `58 passed` (fields and the no-Bearer header; Amman due date; idempotent create, 2 calls → 1 `issueCreate`; existing link → 0 HTTP; duplicate-id and timed-out creates recovered; 503 retried 3 times then raised; 10 error mappings; state moves incl. merged → Duplicate; bad signature / stale or missing timestamp → `Unauthorized`; 7 state mappings; non-state events ignored; mapping validation). `pytest services/ai/tests/unit/test_supabase_sink.py -q` → `4 passed, 4 skipped` (the skips are `-m supabase`: no keys in the worktree). `python scripts/gen_api_docs.py --check` → `docs/api/endpoints.md is up to date`.
- **Limitations / TODO / known issues:**
  - Verified live by the lead: `issueCreate(input:{teamId,title,description,priority,dueDate,labelIds})` with `Authorization: <key>`. **UNVERIFIED:** the `issueCreate` `id` input, `teams`, `issueLabels`, `issueUpdate`, `issue`, and the webhook payload shape (fixtures are hand-written).
  - Safety tickets cannot get Linear priority 1 yet because `Ticket` has no tags, and `ticket_links.last_error` cannot be written because `TicketLink` has no error field (change requests).
  - Our own updates echo back as webhooks (closed → completed → `resolved`); P4.9 should ignore backwards moves.
  - The API fixture `linear_webhook_status_sync` now includes `updatedFrom.stateId` (the handler ignores updates without it); endpoints.md was regenerated.
  - `WebhookSink` is not built (UD-3); its payload is specified in integrations.md §5.
- **Affects streams:** Backend (P4.8 ActUseCase sinks, P4.9 SyncTicketUseCase + webhook route); UI (`action.external[]` links); DB (`ticket_by_link`).

### P4.7 — Calendar: SlotsTableCalendar and FallbackCalendar  (backend, 2026-10-31, commit b350dd7)
- **What now exists:** `adapters/calendar/{slots_table,fallback}.py`: the earliest free advisor slot within the window and Amman office hours, a race-safe claim, the attendee allow-list before any write, and an ordered fallback chain.
- **Public interfaces added:** `SlotsTableCalendar(repo, clock, policy)` with `find_slot(advisor_ids, window, office_hours)` / `book(slot, attendees, title)`; `in_office_hours(slot, hours)`; `FallbackCalendar(providers, policy)`. Fake: `FakeCalendar`. See [integrations.md §4](../integrations.md#4-advisor-booking-calendar).
- **How to use it:** `cal = FallbackCalendar([SlotsTableCalendar(repo, clock, policy)], policy)`; `slot = cal.find_slot([a.id for a in repo.advisors_for("academic")], (now, now + timedelta(hours=plan.sla_hours)), hours)`; `cal.book(slot, [student_inbox, advisor.email], title)`.
- **Config / env added:** none (the Google Calendar settings stay future work, UD-3).
- **Acceptance:** `pytest services/ai/tests/unit/test_calendar.py -q` → `12 passed, 5 skipped` (earliest slot; office hours, Friday and closing-time slots skipped; window; booking claims; double booking prevented with one retry; non-allow-listed attendee → nothing written; store failure → `CalendarUnavailable`; fallback order, empty provider, finder-then-fall-through, all unavailable, a real attendee never reaches a provider). The 5 skips are the `-m supabase` cases: no keys in the worktree `.env`.
- **Limitations / TODO / known issues:** `booked_by` is the first attendee (the student's demo inbox) because `CalendarProvider.book` carries no alias. Per-advisor `OfficeHours` is not exposed by the repository (`advisors_for` does not read `advisors.office_hours`), so P4.8 passes the seed hours (Sun–Thu 09:00–15:00 Amman).
- **Affects streams:** Backend (P4.8 booking path); DB (`free_slots`/`claim_slot` semantics relied on).
