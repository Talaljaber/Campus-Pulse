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
