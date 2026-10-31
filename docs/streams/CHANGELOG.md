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
