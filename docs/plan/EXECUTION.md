# Execution model: parallel agent streams

> **Status:** DRAFT — awaiting user approval. User decision [UD-11](../PLAN.md#ud-11).
>
> The phase files say **what** gets built, with task IDs, acceptance tests and exit criteria. This file says **who builds it, in which order, and in parallel with what**. Phase exit criteria still apply. They are checked at the integration gates below instead of strictly phase by phase.

## Roles

| Role | Model | Owns |
| --- | --- | --- |
| **Lead** (main session) | Opus 5.5 | `services/ai/campuspulse_ai/domain/` (the contracts), merges to `main`, integration gates, plan check-offs, the decision log, reviewing every stream's acceptance output, and dispatching agents |
| **ML stream** | Opus | data tasks, training, evaluation, frozen artifacts, `predict.py` |
| **Backend stream** | Opus | use cases, the intelligence layer, the LLM tier and understander, the FastAPI app, integrations, the action engine, Render deploy |
| **DB stream** | Opus | Supabase migrations, RLS, pgvector, RPCs, `SupabaseRepository`, seeds, FAQ retrieval, then the vector-heavy Pulse and Recurring problems |
| **UI stream** | Sonnet | the design system, i18n/RTL, every page, the typed client layer, Playwright |
| **Foundation stream** | Sonnet | package skeleton, settings, Docker/`render.yaml`, CI, deploy plumbing, README |
| **Research** | Haiku | web lookups on demand: versions, API details, limits. Requested by any stream through the lead. It never writes code. |
| **User** | — | accounts, secrets, the human-written data, human checks, approvals, the eligibility email, recording the video |

## Rules for every agent

1. **One task at a time.** Each task is taken from its phase file and ends with that task's **Acceptance** command and its real output pasted into the hand-back. A task without pasted acceptance output is not done.
2. **Each stream works in its own git worktree and branch:** `stream/ml`, `stream/backend`, `stream/db`, `stream/ui` and `stream/foundation`. The lead merges to `main` after review. Streams rebase on `main` at every gate.
3. **File ownership.**
   - Each stream edits only the paths it owns (table below).
   - A change to `domain/` (ports, values, errors), to the API DTOs, or to `requirements*.txt` is a **change request to the lead**. The lead applies it on `main` and every stream rebases.
   - This keeps parallel streams from breaking each other.
4. **Contracts before code.** Streams code against the frozen contracts from gate G0. A stream that needs another stream's work it can't get yet uses the fakes:
   - `build_test()`, `tiny_model_dir`, `HashingEncoder`, `InMemoryRepository`, `FakeSink`, `FakeNotifier`, `ScriptedOracle`
   - mock API fixtures for the UI
5. **Non-negotiables** (CLAUDE.md) apply to every agent:
   - never touch `hidden_test*` or `JUDGE_GUIDE` files;
   - never edit official labels;
   - never contact real people (allow-lists enforced in code);
   - keep secrets server-side and never commit them;
   - `predict.py` stays offline;
   - evaluate only with frozen `cv_fold` CV plus our own test set.
6. **Escalate, don't improvise.** Anything that changes scope, a threshold, a model, a library or a contract goes to the lead, and on to the user if the CLAUDE.md "check with the user" rule applies.
7. **Document as you build ([UD-12](../PLAN.md#ud-12)).** A task is done only when its acceptance output is pasted **and** its stream's docs are updated (see [Documentation](#documentation)).
   - Agents read the other streams' docs, not their code.
   - If a doc is missing or wrong, the reader files a change request to the owning stream instead of reverse-engineering the code.
   - The lead rejects any hand-back without its doc update.

| Path | Owner |
| --- | --- |
| `services/ai/campuspulse_ai/domain/**`, `application/dto.py` | Lead |
| `scripts/**` (data), `data/augmented|our_test|robustness/**`, `adapters/{preprocess,guards,models,uncertainty,training,artifacts,explain}/**`, `config/{frozen.py,train.yaml,lexicons/**}`, `services/ai/{train,predict,evaluate}.py`, `notebooks/**`, `models/**`, `reports/**` | ML |
| `application/{services,use_cases}/**` (except Recurring problems), `adapters/{clarify,llm,understand,memory,integrations,notify,calendar,redteam}/**`, `frameworks/**`, `config/{actions.yaml,integrations.yaml,prompts/**,templates/**}` | Backend |
| `supabase/**`, `adapters/{store,vectors,faq,pulse}/**`, `application/use_cases/{recurring_problems,resolve_incident}.py`, `scripts/{seed_*,simulate_pulse}.py` | DB |
| `apps/web/**` | UI |
| `services/ai/pyproject.toml`, `requirements*.txt` (via lead), `Dockerfile`, `render.yaml`, `netlify.toml`, `.github/**`, `.env.example`, `README.md` | Foundation |

<a id="documentation"></a>
## Documentation (as-built, owned per stream)

[ARCHITECTURE.md](../ARCHITECTURE.md) is the design. The docs below describe **what exists now**: written for another agent or a judge who will not open the code.

| Doc | Owner | Must contain (kept current at every task) |
| --- | --- | --- |
| `docs/api/README.md` + `docs/api/endpoints.md` | Backend | Base URLs (local, Render) and auth (service token; how staff/admin JWT roles are passed). For **every endpoint**: method and path, purpose, the roles allowed, the request schema, a full example request (`curl.exe`), a full example response, the error codes it can return (with the JSON error shape) and side effects (rows written, tickets, emails). Also the `/v1/triage` status values and every `flags` value with its meaning. `endpoints.md` is **generated** from `services/ai/openapi.json` + `tests/fixtures/api/*.json` by `scripts/gen_api_docs.py`; CI fails if it is stale. |
| `docs/db/schema.md` | DB | Every table (columns, types, keys, indexes), every RLS policy in plain words (who can read or write what), the RPC functions with signatures (`match_vectors`, `vector_dim`, …), views, Realtime publications/channels, vector collections (dim, index type, what is embedded), the migration list, and the seed and demo users (aliases only). |
| `docs/ml/models.md` | ML | The frozen artifact layout (`models/frozen/v1/…`) and `MANIFEST.json`. Every `FrozenConfig` key with its value and how it was tuned. How to load and call the core (`build_offline`, `TriageCore.classify`), with an example. The `predict.py` / `train.py` / `evaluate.py` CLI flags. The current metrics table (CV macro-F1, coverage, fairness) with the date and the command that produced it. Known weaknesses. |
| `docs/ui/README.md` | UI | Design tokens (names → meaning), the component catalog (each component: purpose, props type, which DTO it renders, link to `/dev/ui`), routes/pages and the roles allowed, data-layer functions (`src/lib/repos/*`, `src/lib/ai/*`) with signatures, the i18n key conventions, and how to run the dev server and Playwright. |
| `docs/ops/README.md` | Foundation | Every env var (where it's set: local, Render, Netlify, GitHub; secret or not; which service reads it), how to deploy each service, the CI jobs and what they check, the keep-warm step, and the troubleshooting notes collected along the way. |
| `docs/streams/CHANGELOG.md` | every stream (append-only) | One entry per finished task, in the template below. This is the **first thing an agent reads** when it starts a task. |

**Changelog entry template**, appended by the agent at the end of every task:

```markdown
### <task id> — <title>  (<stream>, <date>, commit <sha>)
- **What now exists:** one or two sentences.
- **Public interfaces added or changed:** signatures or endpoint/table names, each linking to its doc section.
- **How to use it:** a minimal example (code, `curl.exe` or SQL).
- **Config / env added:** keys, with their defaults.
- **Acceptance:** the command and its real output (short).
- **Limitations / TODO / known issues:**
- **Affects streams:** which streams should read this, and why.
```

**Code-level docs:**
- Every public class, port implementation, use case and route has a docstring: what it does, its inputs and outputs, the errors it raises, and its side effects.
- Every TypeScript component exports its props type with TSDoc.
- Comments explain *why*, never *what*.

## Stage 0: contracts (sequential, Sat 31 Oct pm to Sun 1 Nov am)

Nothing runs in parallel until gate G0 passes, because every stream depends on these.

| Order | Task | Owner | Note |
| --- | --- | --- | --- |
| 1 | [P0.1](P0_foundations.md#p0-1) verify, `.gitattributes`, push to the **public** GitHub repo, eligibility email | User + Lead | the user creates the repo and sends the email |
| 2 | [P0.2](P0_foundations.md#p0-2) package skeleton + pins | Foundation | |
| 3 | [P0.4](P0_foundations.md#p0-4) domain layer: labels, values, entities, errors, all ports (including `RequestUnderstander`, `ProblemClusterer`) | Lead (Opus) | **the contract**, reviewed line by line |
| 4 | [P0.6](P0_foundations.md#p0-6) architecture test | Foundation | |
| 5 | **P0.13 API contract stub** (new; see below) | Backend | unblocks the UI on day 1 |
| 5 | [P0.10](P0_foundations.md#p0-10) Supabase project + `0001_init.sql` (pgvector) | DB | runs in parallel with P0.13 |
| 5 | [P0.3](P0_foundations.md#p0-3), [P0.3a–e](P0_foundations.md#p0-3a) data pipeline + audit fixes | ML | runs in parallel with P0.13 |
| 5 | [P0.5](P0_foundations.md#p0-5), [P0.7](P0_foundations.md#p0-7), [P0.8](P0_foundations.md#p0-8), [P0.9](P0_foundations.md#p0-9) | Foundation | runs in parallel |
| 6 | [P0.11](P0_foundations.md#p0-11) empty deploys, [P0.12](P0_foundations.md#p0-12) exit gate | Foundation + User | needs the user's accounts |

<a id="p0-13"></a>
### P0.13 — API contract stub (new task, Backend, 1.5 h)

- [ ] Done
- **Goal:** freeze the HTTP contract before the backend exists, so the UI can build against it from day 1.
- **Files:**
  - `services/ai/campuspulse_ai/application/dto.py`: Pydantic models for every `/v1` request and response in SPEC §7, plus the [LD-25](../PLAN.md#ld-25) additions, `understanding` ([UD-10](../PLAN.md#ud-10)) and `/v1/insights/recurring` ([UD-6](../PLAN.md#ud-6)).
  - `frameworks/mock_app.py`: a FastAPI app that returns fixture responses from `services/ai/tests/fixtures/api/*.json`.
  - `services/ai/openapi.json`, exported.
  - `apps/web/src/lib/ai/types.gen.ts`, generated with `openapi-typescript`.
  - `scripts/gen_api_docs.py` → `docs/api/endpoints.md` (every mock endpoint with its example request and response), plus a first `docs/api/README.md`.
- **Acceptance:**
  - `python -m campuspulse_ai.frameworks.export_openapi --mock > services/ai/openapi.json` gives a file with all `/v1` paths.
  - `pnpm --filter web gen:types && pnpm --filter web typecheck` passes with 0 errors.
  - `pytest services/ai/tests/test_dto_contract.py -q` passes: every fixture validates against its DTO.
- **Hands off:** to the UI (mocks + types), and to the Backend's P3.8/P3.12. Those then *implement* this contract rather than define it. Contract changes go through the lead and are re-exported.

**Gate G0, contracts frozen:**
- the P0 exit gate passes;
- `domain/` and `dto.py` are merged on `main`;
- `openapi.json` and the TS types are generated;
- `0001_init.sql` is applied;
- every stream branch is created from this commit.

## Stage 1: parallel streams (Sun 1 to Fri 6 Nov)

```
          Sun 1      Mon 2      Tue 3      Wed 4      Thu 5      Fri 6
ML       P1.1 ─────────────── P1.19 rc1 ─ P2.1 ────────────── P2.13 rc2 ─ P3.4 P3.5 P3.7
Backend  P3.1 P3.2 P3.3 P3.3a P3.6 P3.8 ── P3.9 P3.10 P3.11 P3.12 ─ P4.4 P4.6 P4.7 P4.8 P4.9 P4.11 P4.12
DB       P4.0* P4.1 ─ P4.2 ─ P4.3 ─ P4.5 ─────────── P4.10 ── (P4.21 after G4)
UI       P5.1 P5.2 P5.3 P5.4(mock) P5.5 ─ P5.6(G2) P5.7 P5.8 ─ P5.10 P5.11 P5.12 ─ P5.13(G3)
Found.   CI/deploy upkeep · P4.13 Render memory test as soon as rc1 exists
User     P1.0 own test set (3 h) · P1.9 check (20 m) · P2.5 probes (1.5 h) · P2.4 augmentation check (3.5 h) · accounts
```

\* P4.0 smoke checks run as soon as the user's accounts exist.

| Stream | Tasks, in order | Works against until the real thing lands |
| --- | --- | --- |
| **ML** (Opus) | P1.1–P1.19 → P2.1–P2.10, P2.12, P2.13 (P2.11 not built, [UD-4](../PLAN.md#ud-4)) → P3.4, P3.5, P3.7 | nothing; the critical path for the scored 50 points |
| **Backend** (Opus) | P3.1, P3.2, P3.3, P3.3a, P3.6, P3.8 → P3.9–P3.12 → P4.4, P4.6–P4.9, P4.11, P4.12, P4.14 | `build_test()` + `tiny_model_dir` (built by ML in P1.16; until then a Backend-side fixture with `HashingEncoder`), `InMemoryRepository`, fakes |
| **DB** (Opus) | P4.0 (with the user), P4.1, P4.2, P4.3, P4.5 → P4.10 → (P4.21 after G4) | dim 384 is fixed (both encoder candidates are 384-d) |
| **UI** (Sonnet) | P5.1–P5.5 → P5.6, P5.7 → P5.8, P5.10, P5.11, P5.12 → P5.9 → P5.13 | `mock_app.py` + `types.gen.ts` until G2/G3 |
| **Foundation** (Sonnet) | CI upkeep; [P4.13](P4_product_backend.md#p4-13) Render deploy + memory test, **pulled forward to G1** | |

**Integration gates.** The lead runs each one, merges, and every stream rebases.

| Gate | When | Proof |
| --- | --- | --- |
| **G1 models rc1** | [P1.19](P1_scored_core.md#p1-19) | the P1 exit criteria pass; `predict.py` runs offline on validation and gives a valid CSV; the Render memory test with the real int8 encoder is ≤ 400 MB RSS (an early [P4.13](P4_product_backend.md#p4-13) check) |
| **G2 DB live** | [P4.3](P4_product_backend.md#p4-3) | RLS tests pass; `SupabaseRepository` contract tests pass; the UI swaps the mocks for Supabase reads |
| **G3 API end to end** | [P3.12](P3_intelligence.md#p3-12) + [P4.8](P4_product_backend.md#p4-8) | `/v1/triage` on Render returns the full contract (with `understanding`), creates a Linear issue and sends an allow-listed email; the UI chat runs against the real API |
| **G4 core green** | [P2.13](P2_data_rigor.md#p2-13) + [P4.14](P4_product_backend.md#p4-14) + [P5.13](P5_frontend.md#p5-13) | P2/P3/P4/P5 exit criteria pass; all three video moments pass in Playwright. **This unlocks the extras ([UD-7](../PLAN.md#ud-7)).** |

## Stage 2: extras (after G4, Sat 7 to Sun 8 Nov)

The order is set in [UD-7](../PLAN.md#ud-7). Streams take them in parallel:
- **DB:** P4.21, P4.19, P4.20
- **UI:** P5.20, P5.16, P5.15, P5.19, P5.14, P5.18, P5.17
- **Backend:** P4.18, P3.13

Stage 3 has priority: when it starts, unfinished extras stop.

## Stage 3: ship (Mon 9 to Tue 10 Nov, mostly sequential)

| Order | Task | Owner |
| --- | --- | --- |
| 1 | [P6.1](P6_ship.md#p6-1) final train + reports, [P6.2](P6_ship.md#p6-2) release, [P6.3](P6_ship.md#p6-3) `predictions.csv` | ML |
| 2 (parallel) | [P6.4](P6_ship.md#p6-4) clean-machine reproducibility | ML |
| 2 (parallel) | [P6.5](P6_ship.md#p6-5) final deploy | Foundation + DB |
| 3 | [P6.6](P6_ship.md#p6-6) README + Disclosures | Foundation, reviewed by the Lead |
| 3 | [P6.7](P6_ship.md#p6-7) report draft | Lead, edited by the User |
| 4 | [P6.8](P6_ship.md#p6-8) video | **User** records it; the Lead prepares the script |
| 5 | [P6.9](P6_ship.md#p6-9) checklist + email | User |

## Human work

The user is now the bottleneck. About **10 h of hands-on work**, plus reviews:

| When | Task | Hours |
| --- | --- | --- |
| Sat 31 | public GitHub repo; eligibility email; accounts: Supabase, Render (Starter), Netlify, OpenRouter (credit), Linear demo workspace, Gmail app password; second inbox | 1.5 |
| Sun 1 | [P1.0](P1_scored_core.md#p1-0) write our own test set, **before any model results** (≥ 60 rows; agents may not write it) | 3 |
| Mon 2 | [P1.9](P1_scored_core.md#p1-9) check the Arabizi rows | 0.3 |
| Mon 2 – Tue 3 | [P2.5](P2_data_rigor.md#p2-5) probes (agents draft, the user verifies) | 1.5 |
| Tue 3 – Wed 4 | [P2.4](P2_data_rigor.md#p2-4) check the augmentation drafts | 3.5 |
| Each gate | review and approve the merge | ~0.5 each |
| Tue 10 | record the video, send the email | 2.5 |

## Cost and risk notes

- **Token cost.** Three Opus streams running for about 6 days is the largest cost of the project. The lead dispatches one task batch at a time (never open-ended runs) and stops a stream that is idle or blocked.
- **Merge conflicts.** These are kept low by the ownership table and the contract-first rule. When one happens anyway, the lead resolves it on `main` and the stream rebases.
- **Disclosure.** The rules say "copied code without attribution is prohibited" and judge "team contribution". The README Disclosures ([P6.6](P6_ship.md#p6-6)) states that development used AI coding agents (Claude Code: Opus / Sonnet / Haiku) under the author's direction and review.
- **Shared machine.** All streams run on the user's Windows laptop. Each worktree has its own `.venv`, and only the ML worktree installs `requirements-train.txt` (torch). Training runs (P1.16, P2.7, P6.1) run one at a time.
