# CampusPulse — Plan

**Status: DRAFT — awaiting user approval.** Nothing in this plan has been started.

CampusPulse is a solo Track C entry for GJU AI Quest 2026.
- **Track lock:** Tue 3 Nov.
- **Submission:** Tue 10 Nov 2026, 23:59 Asia/Amman.
- **Scope:** `docs/SPEC.md`.
- **Binding architecture:** [ARCHITECTURE.md](ARCHITECTURE.md).
- **Plan:** this file is the index; the work is in the phase files under [`plan/`](plan/).

<a id="user-decisions"></a>
## User decisions (2026-10-31)

These override any lead decision or default below that conflicts with them.

- <a id="ud-1"></a>**UD-1 Routing: tickets for staff teams.** The SPEC §5.1 routing table applies as written. Requests for an office or tech team open a ticket in Linear; Registration × high is a same-day escalation ticket with no advisor booking. Only Academic Support × high books a fictional advisor, from `SlotsTableCalendar`. Video moment 1 shows "Linear issue created + email", not a booking. Resolves [OQ-4](#oq-4), replacing its default.
- <a id="ud-2"></a>**UD-2 Linear is required.** `LinearSink` and inbound status sync are core P4 work.
- <a id="ud-3"></a>**UD-3 Future work (out of scope for this submission).** These go in the README "Future work" list:
  - WhatsApp urgent channel ([S1](plan/S1_whatsapp.md))
  - Tier 2 LLM ([P3.3](plan/P3_intelligence.md#p3-3), tier-2 wiring)
  - `WebhookSink` (P4.15)
  - Google Calendar (P4.16)
  - red-team LLM generator (P4.17)
- <a id="ud-4"></a>**UD-4 No fine-tuning.** M3 is not built ([P2.11](plan/P2_data_rigor.md#p2-11)). With 42 unique texts the gain is not worth it.
- <a id="ud-5"></a>**UD-5 Our model labels first.**
  - Both `predict.py` and the live app use the trained ensemble (M1 TF-IDF, M2 embeddings + LR, M2 kNN) as the primary labeller.
  - Tier-1 Haiku is consulted only when the conformal set is ambiguous, and only inside that set.
  - `predict.py` stays offline, with `--use-llm` optional.
- <a id="ud-6"></a>**UD-6 Every message is embedded and analysed.**
  - Every request embedding is stored in pgvector (`requests`).
  - A new **Recurring problems** view clusters requests across all time by meaning, building and category, and ranks them by frequency, so staff can fix root causes early.
  - Tasks [P4.21](plan/P4_product_backend.md#p4-21) and [P5.20](plan/P5_frontend.md#p5-20) do this, after the core is green.
- <a id="ud-7"></a>**UD-7 Extras are in scope, after the core is green.** Covers the B-list (P3.13, P4.18–P4.20, P5.14–P5.19) and UD-6.
  - "Core green" means [P5.13](plan/P5_frontend.md#p5-13) passes: the three video moments work.
  - In P6, the report, video and `predict.py` checks come first.
  - Default order: P4.21 + P5.20 (Recurring problems) → P5.16 (Model-lab sandbox: shows each trained model's vote) → P5.15 → P5.19 → P4.18 → P4.19 → P5.14 → P5.18 → P4.20 → P3.13 → P5.17. These add about 11.5 h.
- <a id="ud-8"></a>**UD-8 Repo: `Talaljaber/Ai-Quest`, private until submission.**
  - The user makes it public at P6, before the email.
  - Until then, Render deploys through its GitHub app, and `scripts/fetch_models.py` reads `GITHUB_TOKEN` when it is set, to download the private Release assets.
  - After the switch to public, it works with no token ([LD-5](#ld-5)). The [P6.4](plan/P6_ship.md#p6-4) clean-clone check runs **after** the switch.
  - Resolves [OQ-7](#oq-7). This changed the earlier "public now" on 2026-10-31.
- <a id="ud-10"></a>**UD-10 Structured NLP understanding (core).** A `RequestUnderstander` turns each live request into schema-validated JSON:
  - a summary in EN and AR
  - entities: building, room, course, deadline, system
  - a natural student reply
  - a Linear ticket title and body

  Haiku writes it with a versioned prompt, at temperature 0, cached and costed. A rule-based fallback is used when there is no key, on errors, or when injection is flagged. It never changes the trained model's labels, and `predict.py` never calls it ([P3.3a](plan/P3_intelligence.md#p3-3a), +3 h).
- <a id="ud-11"></a>**UD-11 Parallel agent streams.**
  - Opus agents own ML/training, the backend and the DB.
  - Sonnet agents own the UI pages and the foundation/config work.
  - Haiku does web research.
  - The lead owns the contracts and integration.

  Streams work in separate git worktrees against contracts frozen at gate G0, and merge at gates G1–G4. See [EXECUTION.md](plan/EXECUTION.md), which adds task [P0.13 API contract stub](plan/EXECUTION.md#p0-13).
- <a id="ud-12"></a>**UD-12 Every agent documents its work.** A task is done only when its acceptance output is pasted and its stream's as-built docs are updated:
  - `docs/api/` (endpoints, examples, errors, generated from OpenAPI)
  - `docs/db/schema.md`
  - `docs/ml/models.md`
  - `docs/ui/README.md`
  - `docs/ops/README.md`
  - a `docs/streams/CHANGELOG.md` entry

  Agents read the docs, not each other's code ([EXECUTION.md › Documentation](plan/EXECUTION.md#documentation)).
- <a id="ud-9"></a>**UD-9 Render plan.** Starter ($7) is approved. Standard (2 GB) only after asking the user, if the memory test fails ([OQ-8](#oq-8)).

## How to use these files

- **Work phase by phase.** Follow P0 → P6 in order (CLAUDE.md). A phase starts only when the previous phase's exit criteria pass. S1 is a stretch, started only after [P6.7](plan/P6_ship.md#p6-7) is green.
- **Tick tasks.** Every task in a phase file has a `- [ ] Done` box under its title. Tick it when the task's **Acceptance** lines give the stated output, not before.
- **Log decisions.** Each phase file ends with "decisions logged during this phase"; tick each box and write the value next to it. Anything that changes scope, a threshold, a model or a library also gets a row in the [global decision log](#decision-log) below.
- **Cut, don't slip.** When a phase overruns, cut-flagged tasks go first, in the [cut order](#cut-order), and exit criteria are never cut. Check with the user before cutting anything not listed in [OQ-2](#oq-2).
- **References.**
  - `§n` means a section of [ARCHITECTURE.md](ARCHITECTURE.md).
  - `LD-n` is a [lead decision](#lead-decisions).
  - `OQ-n` is an [open question](#open-questions-for-the-user).
  - `Xn.m` is exit criterion m of phase n (in the phase file).

## Conventions

- **Working directory.** Every command runs from the repo root (the git root `C:/Users/hp/.m2/Ai-Quest`, flattened on 2026-10-31) inside the venv `.venv`. All paths are project-relative with forward slashes.
- **Scratch outputs.** They go to `.tmp/` (gitignored). On Windows PowerShell 5.1 use `curl.exe`, not `curl`.
- **pytest markers** (declared in `services/ai/pyproject.toml`):

  | Marker | Needs |
  | --- | --- |
  | `train` | torch (`requirements-train.txt`) |
  | `artifacts` | complete `models/frozen/v1` including the fetched encoder |
  | `supabase` | `SUPABASE_TEST_URL` |
  | `slow` | > 30 s |
  | `offline` | sockets disabled |

  Default CI selection: `-m "not train and not artifacts and not supabase"`. A separate CI job runs `-m artifacts`.
- **Task template** (ARCHITECTURE §5), with fields in this order:
  - Goal
  - Depends on
  - Est / Cut
  - Files
  - Interfaces (Python signatures for every new class)
  - Config keys (no magic numbers)
  - Steps, component-first: interface → I/O → errors → tests → implementation
  - Acceptance: `command` → expected output
  - Hands off
  - Notes (where a non-negotiable applies)
- **Files added.** A task that creates a file not in the ARCHITECTURE §1.2 tree says so in "Files added".
- **Hours.** Estimates are focused hours. The [phase table](#phase-table) compares them with the 10-day budget.

## Architecture overview

The full, binding detail is in [ARCHITECTURE.md](ARCHITECTURE.md). In one paragraph:
- **One pipeline, two containers.** One `TriageCore` (normalize → guards → ensemble → evidence → priority head → floors → conformal sets) is the only code path that produces labels.
- **Offline container.** `build_offline(model_dir)` wires it with local adapters only (`LocalNumpyVectorStore`, `NullMemoryStore`, `NullOracle`, no network). `predict.py`, `train.py`, `evaluate.py` and the red-team CLI use it.
- **Online container.** `build_online(settings)` reuses the same core with pgvector memory, Supabase, SMTP, Linear and the LLM tiers. The FastAPI service on Render uses it.
- **Frontend.** The Next.js app on Netlify reads Supabase under RLS and sends every command through a server-only proxy to FastAPI.

### Layer diagram

```
┌──────────────────────────────── frameworks ─────────────────────────────────┐
│ services/ai/api.py → campuspulse_ai/frameworks/fastapi_app.py (routes only)  │
│   (hosted on Render; Netlify hosts apps/web; Supabase = Postgres + pgvector) │
│ services/ai/predict.py · train.py · evaluate.py → frameworks/cli/*.py        │
│ apps/web (Next.js 16 App Router, TS 5.9 strict, Tailwind 4 @theme)           │
└───────────────┬──────────────────────────────────────────────┬───────────────┘
                │ builds containers                            │ HTTP + service token
┌───────────────▼──────────────── composition ──────────────────▼──────────────┐
│ campuspulse_ai/composition/offline.py   build_offline(model_dir, use_llm)     │
│ campuspulse_ai/composition/online.py    build_online(settings)                │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │ wires concretes into
┌───────────────▼──────────────── adapters ────────────────────────────────────┐
│ preprocess/ guards/ models/ uncertainty/ clarify/ explain/ llm/ memory/       │
│ vectors/ store/ integrations/ notify/ calendar/ faq/ pulse/ redteam/          │
│ training/ artifacts/ clock.py                                                 │
│ (sklearn, numpy, onnxruntime, tokenizers, httpx, supabase, smtplib, …;        │
│  torch only in requirements-train.txt for export/M3)                          │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │ implement ports from
┌───────────────▼──────────────── application ─────────────────────────────────┐
│ services/triage_core.py · priority_finalizer.py · llm_merge.py                │
│ use_cases/: triage · clarify · batch_predict · feedback · resolve_incident ·  │
│             sync_ticket · run_redteam · act · escalate_sla                    │
│ dto.py                                                                        │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │ uses only
┌───────────────▼──────────────── domain (pure Python, stdlib only) ───────────┐
│ labels.py · values.py · entities.py · errors.py · ports.py · policy.py ·      │
│ priority_rules.py · routing.py                                                │
└──────────────────────────────────────────────────────────────────────────────┘
domain/ imports nothing outside stdlib; application/ imports domain + numpy only.
Enforced by services/ai/tests/test_architecture.py (P0.6, extended in P1.18).
```

### Ports

All ports are in `domain/ports.py` (`typing.Protocol`, runtime-checkable). Full signatures are in ARCHITECTURE §1.4. Adapters raise only `domain/errors.py` exceptions.

| Port | Signature summary | Concrete implementations | Errors |
| --- | --- | --- | --- |
| `Normalizer` | `normalize(raw, picked_location=None) -> NormalizedRequest` | `DefaultNormalizer` | `InvalidInput` (empty text) |
| `Guard` | `inspect(req) -> GuardVerdict` (run in order Gibberish, Injection, Safety) | `GibberishGuard`, `InjectionGuard` (`strip_regex_only` offline / `full` online), `SafetyGuard` (offline danger = lexicon only) | never raises |
| `ExemplarSimilarity` | `max_similarity(text, bank) -> (score, exemplar)` | `StoreExemplarSimilarity` | — |
| `SentenceEncoder` | `encode(texts) -> list[list[float]]`; `dim`, `model_id` | `OnnxEncoder` (ONNX int8, `query: ` prefix), `CachingEncoder`, `HashingEncoder` (tests) | `ArtifactMissing` |
| `ProbabilisticClassifier` | `fit(texts, y, sample_weight)`, `predict_proba(texts)`, `save`/`load` | `TfidfLR` (m1), `EmbedLR` (m2lr), `KnnClassifier` (m2knn), `TransformerFT` (m3, ONNX at inference) | `ArtifactMissing` |
| `VectorStore` | `upsert`, `search(collection, query, k, min_sim, filters) -> list[VectorHit]` (with optional `embedding`), `set_active`, `count` | `LocalNumpyVectorStore` (offline, frozen), `PgVectorStore` (Supabase `match_vectors`) | `StoreError`, `ArtifactMissing`, `ArtifactVersionMismatch` |
| `Ensemble` | `predict(texts, memory) -> list[EnsembleOutput]` | `WeightedEnsemble` (members from config) | `ArtifactVersionMismatch` |
| `EvidenceExtractor` | `extract(req) -> EvidenceVector` (10 features, never `stated_urgency`) | `LexiconEvidenceExtractor` | — |
| `PriorityHead` | `fit(...)`, `predict(p_pri_model, evidence, constraints) -> ProbVector` | `LogisticPriorityHead` | — |
| `ConformalPredictor` | `calibrate(probs, y, groups)`, `predict_set(p) -> PredictionSet` | `LACConformal`, `MondrianByLang` (only if triggered) | `ValueError` (n too small) |
| `DecisionPolicy` | `decide(core, budget, llm_allowed) -> Outcome` | `domain/policy.py` (pure) | — |
| `ClarificationStrategy` | `select(core, lang, asked)`, `apply(core, question_id, option_id)` | `InfoGainStrategy(QuestionBank)` | `ClarificationBudgetExceeded` |
| `LabelOracle` | `choose(req, allowed_cat, allowed_pri, ctx) -> OracleAnswer` | `OpenRouterOracle`, `NullOracle`, `ScriptedOracle` (tests) | `LLMUnavailable`, `LLMOutputOutOfSet` |
| `ResponseCache` | `get(key)`, `put(key, value)` | `SqliteCache`, `SupabaseCache`, `DictCache` | — |
| `CostLogger` | `log(call)`, `totals()` | `InMemoryCostLogger`, `SupabaseCostLogger` | — |
| `Explainer` | `explain(req, core, decided)`, `counterfactual(req, drop_token)` | `OcclusionExplainer` | sets flag `explanation_failed` (never fails triage) |
| `MemoryStore` | `add`, `active`, `deactivate`, `stats`, `neighbors(embedding, k, min_sim)` | `NullMemoryStore`, `InMemoryMemoryStore`, `PgVectorMemoryStore` | `StoreError` |
| `ActionPlanner` | `plan(category, priority, flags, provisional) -> ActionPlan` | `domain/routing.py` over `config/actions.yaml` | — |
| `FAQRetriever` | `search(text, lang, k) -> list[FAQHit]` | `VectorFAQRetriever` (VectorStore `faq`) | `StoreError` |
| `TicketSink` | `create`, `update_status`, `close`, `handle_inbound` | `SupabaseSink`, `LinearSink`, `WebhookSink` (cut #2), `FakeSink`; wrapper `RetryingSink` | `SinkError(retryable)` |
| `Notifier` | `send(msg) -> OutboxMessage` | `GmailSmtpNotifier` (stdlib smtplib), `InAppNotifier`, `FakeNotifier`; decorator `AllowlistedNotifier`; S1: `RoutingNotifier`, `WhatsAppCloudNotifier` | `NotificationError(retryable)`, `RecipientNotAllowed` |
| `CalendarProvider` | `find_slot(...)`, `book(slot, attendees, title)` | `SlotsTableCalendar`, `GoogleCalendarProvider` (cut #5), `FakeCalendar`; `FallbackCalendar` chain | `CalendarUnavailable` |
| `Repository` | requests, predictions, clarifications, review, tickets, incidents, outbox, signals, audit, red-team runs, plus `ticket_by_link`, `incident_members`, `free_slots`, `claim_slot`, `save_case`, `save_notification`, `advisors_for`, `router_stats`, `redteam_history` | `InMemoryRepository`, `SupabaseRepository` (service role) | `StoreError`, `NotFound` |
| `IncidentDetector` | `detect(req, pred, embedding) -> IncidentDecision` | `WindowedCentroidDetector` | `StoreError` |
| `RedTeamGenerator` | `generate(n, styles, seed) -> list[RedTeamItem]` | `PerturbationGenerator`, `LLMRedTeamGenerator` (cut #7) | — |
| `Clock` | `now()` (Asia/Amman) | `SystemClock`, `FrozenClock` | — |
| `ArtifactStore` | `load_manifest(model_dir)`, `write_manifest(model_dir, files)` | `FileArtifactStore` | `ArtifactMissing`, `ArtifactChecksumMismatch`, `ArtifactVersionMismatch` |

**Composition roots.**
- `build_offline(model_dir, use_llm=False)`:
  1. verifies `MANIFEST.json`
  2. loads `FrozenConfig`, `OnnxEncoder` and `LocalNumpyVectorStore` (collections exactly `train`, `injection_exemplars`, `safety_exemplars`)
  3. adds the configured members, the guards, `NullMemoryStore` and `NullOracle` (or `OpenRouterOracle` with `--use-llm`)
  4. returns `TriageCore` + `BatchPredictUseCase`

  `predict.py` and `evaluate.py` call it. `train.py` uses the same component classes through `adapters/training/`.
- `build_online(settings)` reuses the offline container and rebuilds the core with `PgVectorMemoryStore`. It adds the repository, sinks, notifier chain, calendar, FAQ, incidents, red team and the use cases. FastAPI routes call only use cases. Tests use `build_test()` over the `tiny_model_dir` fixture.

**Frontend design system.**
- `src/design/tokens.css`: CSS variables per category (6), per priority (3), surfaces, spacing, radius and font; light and dark. It is mapped by Tailwind 4 `@theme`.
- `src/components/ui/`: Button, Card, Badge, Chip, ProbBar, SetBadge, Tabs, Table, Toast, Dialog, Skeleton, EmptyState, RtlProvider. They are shown at `/dev/ui` (dev only).
- Feature components render DTOs only.
- Data goes through `src/lib/repos/*` (RLS reads, Realtime) and the server-only `src/lib/ai/client.ts` proxy.
- i18n uses in-repo EN/AR dictionaries with RTL.

## Phase table

The budget comes from ARCHITECTURE §4.0: 10 days including Sat 31 Oct, slack 0. **Planned** = tasks not cut-flagged (it includes voice, cut #1, and map visuals, cut #6, which are not pre-approved cuts). **Cut-flagged** = tasks that start only if time remains.

| Phase | File | Budget | Calendar (Asia/Amman) | Planned h | Cut-flagged h | Capacity @ 9 h/d | Capacity @ 12 h/d |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P0 Foundations | [P0_foundations.md](plan/P0_foundations.md) | ½ d | Sat 31 Oct (pm) | 10 | 0 | 4.5 | 6 |
| P1 Scored core | [P1_scored_core.md](plan/P1_scored_core.md) | 2 d | Sun 1 – Mon 2 Nov | 21 | 0.25 | 18 | 24 |
| P2 Data + rigor | [P2_data_rigor.md](plan/P2_data_rigor.md) | 2 d | Tue 3 – Wed 4 Nov | 19 | 4 (M3, default cut) | 18 | 24 |
| P3 Intelligence layer | [P3_intelligence.md](plan/P3_intelligence.md) | 1½ d | Thu 5 – Fri 6 (am) | 22.5 (incl. P3.3a, UD-10) | 2 | 13.5 | 18 |
| P4 Product backend | [P4_product_backend.md](plan/P4_product_backend.md) | 1½ d | Fri 6 (pm) – Sat 7 | 23.25 | 5.75 | 13.5 | 18 |
| P5 Frontend | [P5_frontend.md](plan/P5_frontend.md) | 1½ d | Sun 8 – Mon 9 (am) | 23 | 5.75 | 13.5 | 18 |
| P6 Ship | [P6_ship.md](plan/P6_ship.md) | 1 d | Mon 9 (pm) – Tue 10 (am); Tue 10 pm = submission buffer | 11.75 | 0 | 9 | 12 |
| S1 WhatsApp | [S1_whatsapp.md](plan/S1_whatsapp.md) | — | **future, out of scope ([UD-3](#ud-3))** | 0 | 0 | — | — |
| **Total** | | **10 d** | | **130.5** | **≈ 20** | **90** | **120** |

**After the user decisions:**
- The future items in [UD-3](#ud-3) and M3 ([UD-4](#ud-4)) leave the "Cut-flagged" column: about 10.5 h.
- The extras plus Recurring problems ([UD-7](#ud-7)) are about 11.5 h of after-core work.
- Planned core work rises to **130.5 h** with P3.3a ([UD-10](#ud-10)), **10.5 h over** a 12-hour day. The figures below were written before UD-10, so add 3 h to each.

**Honest reading:**
- **Planned work:** 127.5 h. That is **7.5 h over** a 12-hour-a-day sprint (120 h) and **37.5 h over** a 9-hour day (90 h). It needs about 13 focused hours a day for 10 days with zero slack.
- **If nothing is cut:** 147.5 h, which is 27.5 h over at 12 h/d.
- **Already partly spent:** today is already half gone, and P0 ran over its ½ d because the data audit added P0.3a–P0.3e (2.5 h).
- **Recommendation:**
  - pre-approve the cuts in [OQ-2](#oq-2) now, so those tasks never start;
  - accept 12–13 h days through P5;
  - decide on #6 (map → list) and #1 (voice) by the end of P4.

**Appendices:** [A Dependencies](plan/appendix_A_dependencies.md) · [B Models and LLM tiers](plan/appendix_B_models.md) · [C Artifact shipping](plan/appendix_C_artifacts.md) · [D External accounts](plan/appendix_D_accounts.md)

<a id="cut-order"></a>
### Cut order (SPEC §12 + S1 + ARCHITECTURE §4.8). Each cut is a non-edit: the code is simply not wired.

| # | Cut | Tasks that never start | What is not wired |
| --- | --- | --- | --- |
| **0** | WhatsApp urgent channel | [S1.1](plan/S1_whatsapp.md#s1-1)–[S1.3](plan/S1_whatsapp.md#s1-3) | No `WHATSAPP_*` env → `RoutingNotifier`/`WhatsAppCloudNotifier` are not constructed; the notifier is `AllowlistedNotifier(GmailSmtpNotifier)` |
| 1 | Voice | [P5.9](plan/P5_frontend.md#p5-9) | `MicButton` not passed as `micSlot`; `input_mode` always `text`; no Whisper route |
| 2 | Extra sinks beyond Linear | P4.15 | `WebhookSink` not in `config/integrations.yaml enabled`; never constructed |
| 3 | Tier 2 | (config only, inside [P3.3](plan/P3_intelligence.md#p3-3)) | `OPENROUTER_TIER2_MODEL` unset → `oracles = [tier1]` |
| 4 | M3 (**default: cut**, [LD-32](#ld-32)) | [P2.11](plan/P2_data_rigor.md#p2-11) | `"m3"` absent from `config.json ensemble.members`; no `m3/` in the release asset |
| 5 | Google Calendar | P4.16 | `GOOGLE_SERVICE_ACCOUNT_JSON` unset → `FallbackCalendar([SlotsTableCalendar])` (default from day one) |
| 6 | Pulse map visuals | [P5.5](plan/P5_frontend.md#p5-5), P5.14 | `/pulse` renders `IncidentList` + `EventFeed`; `IncidentDetector` unchanged |
| 7 | Red-team LLM generator | P4.17 | `RedTeamGenerator = PerturbationGenerator` |
| B | Brief extras: timeline scrubber, per-building subscriptions, `--consolidate`, `cases`, dark mode, `/batch` UI, `/outbox` page, lab sandbox, admin simulate/reindex | P5.14, P4.19, [P3.13](plan/P3_intelligence.md#p3-13), P4.18, P5.17, P5.18, P5.15, P5.16, P5.19, P4.20 | listed in each phase file |

## Lead decisions

Decided by the lead on 2026-10-31 and applied throughout the phase files and [ARCHITECTURE.md](ARCHITECTURE.md). Each line names its sources: "A-n" is an issue from the P0–P2 writer, "L-n" one from the P3–P6 writer, and "audit" is the data audit.

- <a id="ld-1"></a>**LD-1 Python.** Support 3.11–3.13 by pinning numpy 2.4.6 and scipy 1.17.1. The reference environment is Linux Python 3.11, and the floor is not raised to 3.12. (A-1, L-24)
- <a id="ld-2"></a>**LD-2 Frontend versions.** Next 16.4.2, Tailwind 4.3.3 with `@theme` in `tokens.css` (no `tailwind.config.ts`), TypeScript 5.9.3 (not 7). (A-2, L-17)
- <a id="ld-3"></a>**LD-3 Email.** `GmailSmtpNotifier` (stdlib `smtplib`, `campuspulse.support@gmail.com`, app password, `SMTP_HOST`/`SMTP_PORT`), wrapped by `AllowlistedNotifier`. There is no mail SDK anywhere. (A-3, L-25)
- <a id="ld-4"></a>**LD-4 Render.** `render.yaml` and the Docker build context are at the repo root (`dockerfilePath: ./services/ai/Dockerfile`, `dockerContext: .`, `autoDeployTrigger: commit`). (A-4, L-15)
- <a id="ld-5"></a>**LD-5 Model releases.** From P1, encoder/model pre-releases are published as GitHub Release assets tagged `models-v1-rcN` with a `SHA256SUMS` manifest verified against `MANIFEST.json` (rc1 at P1.19, rc2 at P2.13). The final `models-v1` ships in P6.2. (A-16, L-14)
- <a id="ld-6"></a>**LD-6 M3 gates.** M3 is included only if ΔOOF category macro-F1 ≥ 0.01, `predict.py` on 1,000 rows < 60 s, the fetched tier ≤ 200 MB, RSS ≤ 400 MB with `m3` loaded, and it passes the Render memory test (X4.6). Time box: 4 h. (A-17, L-21)
- <a id="ld-7"></a>**LD-7 Reproducibility.** The fresh-clone check compares labels (category and priority per row), not bytes. (A-19)
- <a id="ld-8"></a>**LD-8 ONNX export.** `torch.onnx.export` + `onnxruntime.quantization.quantize_dynamic` with a portable int8 config. No optimum, and no AVX512/VNNI-specific files. (A-20, A-21, L-23)
- <a id="ld-9"></a>**LD-9 e5 prefix.** `encoder.query_prefix = "query: "` for every e5 use (one symmetric prefix). (A-13, L-13)
- <a id="ld-10"></a>**LD-10 FrozenConfig keys.** Added:
  - `guards.gibberish_min_tokens`, `guards.gibberish_min_letter_ratio`, `guards.injection_sentence_strip_ratio`
  - `thresholds.tau_safety`
  - `m1.{char_ngram, word_ngram, C}`, `m2lr.C`
  - `priors.{category, priority}`
  - `llm.w_llm` (0.5), `llm.prompt_version` ("v1")
  - `explain.max_occlusions` (20)
  - `knn.memory_min_sim` (0.80)
  - `cv.fold_col`/`cv.folds_file`

  (A-13, L-3)
- <a id="ld-11"></a>**LD-11 Hand-tuned values.** `tau_faq` and `tau_inc` (and any similar value) live in `config/hand_tuned.yaml`. `train.py` reads that file and writes the values into `config.json`, so `train.py` stays the only writer of `config.json`. (L-12)
- <a id="ld-12"></a>**LD-12 Lexicon snapshot.** `train.py` copies `config/lexicons/*.yaml` into `models/frozen/vN/lexicons/`, the manifest hashes them, and containers read lexicons from the model dir. (A-5)
- <a id="ld-13"></a>**LD-13 CoreResult.** `CoreResult.flags: frozenset[str]`, and `per_model` keys are `"<member>.<target>"`. (A-6, A-7, L-20)
- <a id="ld-14"></a>**LD-14 VectorHit.embedding.** An optional `embedding`, filled only when `filters["with_embedding"]` is true. `match_vectors` returns a nullable `embedding` column (used for the incident centroid). (L-1)
- <a id="ld-15"></a>**LD-15 NotificationError.** `NotificationError(CampusPulseError)` with `retryable: bool` in `domain/errors.py`. `ActUseCase` records outbox `failed` and never fails triage. (L-2)
- <a id="ld-16"></a>**LD-16 Repository methods.** `ticket_by_link`, `incident_members`, `free_slots`, `claim_slot`, `save_case`, `save_notification`, `advisors_for`, `router_stats`, `redteam_history` are added to the single `Repository` port. (L-4)
- <a id="ld-17"></a>**LD-17 Empty input.** `BatchPredictUseCase` catches `InvalidInput` and emits the argmax of `FrozenConfig.priors`, with the debug-only flag `empty_input`. (A-8)
- <a id="ld-18"></a>**LD-18 tau_injection sign.** It is the max similarity over official + augmented rows **plus** 0.02 (zero hits), and the same rule gives `tau_safety`. (A-9)
- <a id="ld-19"></a>**LD-19 Offline safety.** Offline "danger" comes from the lexicon only. Exemplar similarity (`thresholds.tau_safety`) may only add `distress`, which never changes a batch label. (A-10)
- <a id="ld-20"></a>**LD-20 faq_seed.** It exists only in test fixtures, never in a model dir. The offline collections are exactly `train`, `injection_exemplars`, `safety_exemplars`. (A-12)
- <a id="ld-21"></a>**LD-21 Training code.** It lives in `adapters/training/{pool,cv,tuning,metrics}.py`. (A-14)
- <a id="ld-22"></a>**LD-22 P1 stubs and fixture.** `adapters/memory/null.py`, `adapters/llm/null.py`, `adapters/clock.py` and the session fixture `tiny_model_dir` (on `tests/fixtures/tiny_train.csv`) are built in P1 ([P1.15](plan/P1_scored_core.md#p1-15), [P1.16](plan/P1_scored_core.md#p1-16)). (A-15, L-9)
- <a id="ld-23"></a>**LD-23 run_notebooks.py.** Moved into P2 ([P2.12](plan/P2_data_rigor.md#p2-12)); P6 reuses it. (A-23)
- <a id="ld-24"></a>**LD-24 ASK rate.** The P2 ASK rate is labelled a proxy (`ask_proxy_rate`); P3 recomputes the true rate with `DecisionPolicy`. (A-24)
- <a id="ld-25"></a>**LD-25 Additive data-contract changes.** Accepted:
  - the flag `explanation_failed` (L-7)
  - `understood_as` and a top-level `message` in the `/triage` response (L-8)
  - routes `GET /v1/incidents?open=1`, `/v1/admin/simulate` (cut), `/v1/admin/reindex` (cut) and `/v1/tickets/{id}/status` (L-33)
  - `llm_calls.cache_key` + `response` (L-10)
  - `requests` in the Realtime publication, with students subscribing to `notifications` only (L-11)
  - optional `OutboxMessage.priority/flags` (L-16)
  - Netlify `AI_SERVICE_*` vars scoped to Functions/Runtime (L-18)
- <a id="ld-26"></a>**LD-26 P0.1.** There is no flatten-leftovers check (the cleanup handles it); the eligibility email stays. (A-0)
- <a id="ld-27"></a>**LD-27 Injection exemplars.** P1 seeds ≥ 10 so the collection exists and `tau_injection` is computable. P3.5 grows them to ~50 and re-freezes. (A-11; writer resolution kept)
- <a id="ld-28"></a>**LD-28 Missing pins.** Merged into [Appendix A](plan/appendix_A_dependencies.md): `pyyaml 6.0.3`, `psutil 7.2.2`, `respx 0.23.1`, `nbformat 5.11.1`, `nbclient 0.11.0` (already there), plus `mypy 2.4.0`, `types-PyYAML 6.0.12.20260906`, `ipykernel 7.4.0` and Supabase CLI `2.121.0`. `optimum` was removed. (A-25)
- <a id="ld-29"></a>**LD-29 Clarify re-runs the core.** `ClarificationStrategy.apply` returns constraints, and `ClarifyUseCase` re-runs `TriageCore.classify(..., constraints)`. (L-6; writer resolution kept)
- <a id="ld-30"></a>**LD-30 Render memory ladder.** No Arabic-capable int8 encoder ≤ 80 MB exists, so the ARCHITECTURE §3.17 ladder is lazy load → lower occlusion cap → Render Standard ([OQ-8](#oq-8)). (L-22; writer resolution kept)
- <a id="ld-31"></a>**LD-31 Frozen category-stratified folds.**
  - Plain GroupKFold(5) leaves validation folds missing categories for every seed tried.
  - `scripts/make_folds.py` (seed 42) writes `data/clean/cv_folds.csv`: one group per category per fold, and all 3 priorities in every fold.
  - All OOF work uses the frozen `cv_fold` column, and `cv_group` stays the leakage unit.
  - New augmentation groups are appended without moving official groups.
  - See [P0.3a](plan/P0_foundations.md#p0-3a), ARCHITECTURE §3.2. (audit F1)
- <a id="ld-32"></a>**LD-32 Thin data.** 42 unique texts and 30 groups, so the effective n for conformal and slices is ≈ 30. Coverage is reported as approximate, every fairness slice carries its counts (rows and groups), and **M3 is cut by default** (#4) unless OOF shows the gain and every LD-6 gate passes. (audit F3)
- <a id="ld-33"></a>**LD-33 Arabizi.** The official data has 0 Arabizi rows, and `lang` is script-only. The Arabizi slice comes entirely from augmentation plus the package `LangIdentifier`. The fairness slice is `lang_script` + `is_arabizi` ([P0.3b](plan/P0_foundations.md#p0-3b), [P1.2](plan/P1_scored_core.md#p1-2), [P2.8](plan/P2_data_rigor.md#p2-8)). (audit F2)
- <a id="ld-34"></a>**LD-34 "today" shortcut.**
  - All 60 rows containing "today"/"اليوم" are high, and none of the other 372 are.
  - P2.5 adds `deadline_shortcut` probes: high without "today", and "today" in low/medium.
  - P2.9 adds a masked-deadline ablation.
  - The report states the risk ([P6.7](plan/P6_ship.md#p6-7)). (audit F3)
- <a id="ld-35"></a>**LD-35 Wrapper stripping.** `clean_data.py` strips exact matches only. The package stripper ([P1.1](plan/P1_scored_core.md#p1-1)) also strips `urgent:` (lowercase), `URGENT` without a colon and case/punctuation variants of known prefixes, with tests. The P0.3c print guard is the only edit to `clean_data.py`, and its outputs stay byte-identical. (audit F4, F6)

## Open questions for the user

Each has a recommended default. The plan proceeds on the default unless the user says otherwise.

- <a id="oq-1"></a>**OQ-1 Solo eligibility.** The rules say teams of 2–3 students. **Default:** email the organizer today, before the Tue 3 Nov lock. This blocks everything ([P0.1](plan/P0_foundations.md#p0-1)).
- <a id="oq-2"></a>**OQ-2 Pre-approve cuts so those tasks never start.** **Resolved → [UD-3](#ud-3), [UD-4](#ud-4), [UD-7](#ud-7).**
  - **Recommended pre-approved cuts** (≈ 20 h saved):

    | Cut | Saves |
    | --- | --- |
    | #0 WhatsApp | 2.5 h |
    | #2 extra sinks | 1 h |
    | #3 Tier 2 | ≈ 0.5 h |
    | #5 Google Calendar | 2 h |
    | #7 red-team LLM generator | 1 h |
    | #4 M3 (default cut per [LD-32](#ld-32)) | 4 h |
    | B-list (P3.13 1.5, P4.18–P4.20 1.75, P5.14–P5.19 5.75) | 9 h |

  - **Optional:** #6 map visuals → list saves 1.5 h; #1 voice saves 1 h.
  - **Remaining overrun:** with the recommended cuts, the planned work is 127.5 h, which is 7.5 h over 120 h (12 h/d). Adding #6 and #1 brings it to 125 h, 5 h over. With **nothing** cut it is 147.5 h, 27.5 h over at 12 h/d.
- <a id="oq-3"></a>**OQ-3 Data volumes below SPEC.** SPEC asks for ~120 own-test rows, ~100 probes and ~5 paraphrases per scenario. **Default:** the brief's floors: ≥ 60 own-test rows, ≥ 40 probes, ~3 paraphrases per scenario, ~60 new scenarios. (A-22)
- <a id="oq-4"></a>**OQ-4 Registration × high.** **Resolved → [UD-1](#ud-1): ticket, no booking (the default below is superseded).**
  - The conflict: SPEC's routing table says to open a ticket, but the storyboard books an advisor. (L-5, L-32)
  - **Default:** follow the storyboard: `config/actions.yaml` sets Registration×high and Academic Support×high to `booking` with `also_ticket: true`.
  - Also add a deadline word to the moment-1 sentence ("…واليوم آخر يوم") so high is reachable and the counterfactual means something.
- <a id="oq-5"></a>**OQ-5 SMTP from Render.** If Render blocks SMTP even on Starter (L-26), **default fallback:** the Gmail API over HTTPS (OAuth refresh token), with `InAppNotifier` meanwhile.
- <a id="oq-6"></a>**OQ-6 Student inbox.** Gmail may not show self-sent mail in the inbox (L-27). **Default:** the user supplies a second inbox they own, which appears in the allow-list and in the video as the "student inbox".
- <a id="oq-7"></a>**OQ-7 Public repo.** The repo must be public before the P0 deploys, for the Render build, the release fetch and judge clones. (L-19) **Resolved → [UD-8](#ud-8): private until submission.**
- <a id="oq-8"></a>**OQ-8 Render Standard.** **Default:** escalate to Render Standard (2 GB, ~$25/mo) only if the X4.6 memory test fails on Starter after the [LD-30](#ld-30) ladder. **Resolved → [UD-9](#ud-9): ask before upgrading.**

## Decision log

Global log for decisions that change scope, a threshold, a model, a library or a contract. Each phase file also has its own checklist. Add rows at the bottom and never edit old rows; supersede them with a new row.

| ID | Date | Phase / task | Decision | Why / evidence (command output, link) | Supersedes |
| --- | --- | --- | --- | --- | --- |
| D-001 | | | | | |
