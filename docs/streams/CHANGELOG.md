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
