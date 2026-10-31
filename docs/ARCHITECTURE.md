# CampusPulse — Architecture (binding)

Author: chief architect · 2026-10-31 · Lead decisions of 2026-10-31 merged in. Companion: [`docs/PLAN.md`](PLAN.md) (index, lead decisions, open questions) and the phase files in [`docs/plan/`](plan/).
Status: **binding**. Decisions below are final unless the user overrides them. The tasks in `docs/plan/` decompose this document; they do not re-decide it.

Project root for every path in this document: the git root `C:/Users/hp/.m2/Ai-Quest` (the repo was flattened on 2026-10-31; it is written as `campuspulse/` below, and every path is relative to it). Source of truth for scope: `docs/SPEC.md` (v2). Where this document and the SPEC differ, this document wins and §6 records why.

Facts to keep in mind (from `data/clean/` and the data audit of 2026-10-31, verdict USE WITH FIXES):
- 432 official rows = **42 unique scenarios** (36 train + 6 val), each repeated 9–11 times with only a wrapper prefix/suffix changed. After wrapper stripping the official data is 42 distinct sentences. Everything that "generalises to unseen scenarios" is therefore driven by augmentation and by pretrained embeddings, not by the 432 rows.
- 12 verified AR↔EN translation pairs → **30 `cv_group`s** (5 per category). Plain GroupKFold(5) leaves some validation folds without every category, so the folds are a **frozen category-stratified assignment** in `data/clean/cv_folds.csv` (one group per category per fold, all 3 priorities in every fold; §3.2). `cv_group` stays the leakage unit.
- **Thin data:** 42 unique texts and 30 groups. The effective n for conformal calibration and slice metrics is ≈ 30, so coverage is approximate and every slice is reported with its counts.
- **Shortcut risk:** all 60 official rows containing "today"/"اليوم" are `high`, and none of the other 372 are. Models will learn "today → high"; P2 probes and a masked-deadline ablation measure it.
- No Arabizi in the official data (0 rows), and `lang` in the CSVs is script-only (`ar`/`en`, also exposed as `lang_script`). The Arabizi slice comes entirely from augmentation plus the package langid. Official priority counts (scenario level): high 14 / low 12 / medium 16.
- `label_flags.csv`: 4 soft-target scenarios (TR-S27, TR-S33 priority low .75/medium .25; TR-S06 medium .75/low .25; TR-S18 category Academic Support .8/IT Support .2), 5 "keep hard" notes.
- Time: 10 calendar days, one developer. Budget allocated in §4.0. Anything not reachable inside that budget is cut per §6.

**Changes from the original brief (lead decisions, 2026-10-31; full list in [PLAN.md › Lead decisions](PLAN.md#lead-decisions)):**
- **Python:** 3.11–3.13 supported; numpy 2.4.6 and scipy 1.17.1 keep cp311 wheels; the reference environment is Linux Python 3.11 (§3.16).
- **Frontend:** Next.js 16, TypeScript 5.9.3, Tailwind 4 with `@theme` (§1.7).
- **Email:** `GmailSmtpNotifier` (stdlib `smtplib`), wrapped by `AllowlistedNotifier`, raising `NotificationError(retryable)`. There is no third-party mail SDK (§1.4, §1.5, §3.13).
- **Render:** `render.yaml` and the Docker build context are both at the repo root (§1.2, §3.15).
- **Model releases:** pre-releases `models-v1-rcN` are GitHub Release assets with a sha256 manifest from P1 on; the final `models-v1` ships in P6 (§3.12).
- **M3:** included only if it gains ≥ 0.01, stays within the 200 MB download and 400 MB RSS budgets and passes the Render memory test; time-boxed to 4 h (§3.6).
- **Reproducibility:** the fresh-clone check compares labels, not bytes (§3.12).
- **ONNX export:** `torch.onnx.export` + `onnxruntime.quantization.quantize_dynamic` (portable int8). No optimum, and no AVX512/VNNI-specific files (§3.6).
- **Config:**
  - e5 `query_prefix = "query: "`.
  - Missing `FrozenConfig` keys are added (§1.6).
  - Hand-tuned values live in `config/hand_tuned.yaml`, which `train.py` copies into `config.json`, so `train.py` stays the only writer.
  - Lexicons are snapshotted into `models/frozen/vN/lexicons/` and covered by the manifest.
- **Domain:**
  - `CoreResult.flags` and `"<member>.<target>"` keys in `per_model`.
  - `VectorHit.embedding`, with `match_vectors` returning a nullable embedding column.
  - `NotificationError`, the extra `Repository` methods, the `empty_input` flag with label priors in the frozen config, and a fixed `tau_injection` sign (+0.02).
  - Offline "danger" is lexicon-only, with a new `tau_safety` key.
  - `faq_seed` exists only in test fixtures.
- **Layout:**
  - Training code lives in `adapters/training/`.
  - The Null/clock stubs and the `tiny_model_dir` test fixture are built in P1.
  - `run_notebooks.py` is built in P2.
  - P2's ASK rate is a proxy, recomputed in P3.
- **Data contract:** additive changes are accepted: the `explanation_failed` flag; `understood_as` and `message` in the `/triage` response; the extra routes; the `llm_calls` cache columns; `requests` in the Realtime publication; optional `OutboxMessage.priority/flags`; Netlify runtime env scope.

---

## 1. Architecture

### 1.0 Guiding constraints (read before the layer map)

1. **Scored core first.** 50 of 100 points are macro-F1 on the hidden test; 20 are reproducibility. `predict.py` must be correct, offline and boring. Every architectural choice below is cheap for the core and only grows for the product layer.
2. **One pipeline, two containers.** The same `TriageCore` application service runs in `predict.py`, `train.py` (for OOF), the FastAPI `/triage`, and the red team. The offline container has zero network adapters; the online container adds them. Nothing in the core knows which container it lives in.
3. **Thin Clean Architecture.** Four layers, dependencies inward, but no DI framework, no repository-per-table explosion, no abstract base class that has only one implementation *and* no test fake. A port exists when (a) the spec names it, (b) it has an offline and an online implementation, or (c) a test needs a fake. Everything else is a plain class.
4. **Thresholds live in `models/frozen/config.json`** (ML) or `Settings` (runtime). No literal threshold in code. Tests load the config.

### 1.1 Layer diagram

```
┌──────────────────────────────── frameworks ─────────────────────────────────┐
│ services/ai/api.py → campuspulse_ai/frameworks/fastapi_app.py (routes only)  │
│   (hosted on Render; Netlify hosts apps/web; Supabase = Postgres + pgvector) │
│ services/ai/predict.py · train.py · evaluate.py → frameworks/cli/*.py        │
│ apps/web (Next.js App Router, TS strict, Tailwind)                           │
└───────────────┬──────────────────────────────────────────────┬───────────────┘
                │ builds containers                            │ HTTP + service token
┌───────────────▼──────────────── composition ──────────────────▼──────────────┐
│ campuspulse_ai/composition/offline.py   build_offline(model_dir, use_llm)     │
│ campuspulse_ai/composition/online.py    build_online(settings)                │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │ wires concretes into
┌───────────────▼──────────────── adapters ────────────────────────────────────┐
│ preprocess/ guards/ models/ uncertainty/ clarify/ explain/ llm/ memory/       │
│ vectors/ store/ integrations/ notify/ calendar/ faq/ pulse/ redteam/ clock.py │
│ (sklearn, numpy, onnxruntime, tokenizers, httpx, supabase, smtplib, …;        │
│  torch only in requirements-train.txt for export/M3)                          │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │ implement ports from
┌───────────────▼──────────────── application ─────────────────────────────────┐
│ services/triage_core.py (steps 2·3·4·5·6·9 shared)                            │
│ use_cases/: triage · clarify · batch_predict · feedback · resolve_incident ·  │
│             sync_ticket · run_redteam · act (action engine) · escalate_sla    │
│ dto.py (request/response dataclasses)                                         │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │ uses only
┌───────────────▼──────────────── domain (pure Python, stdlib only) ───────────┐
│ labels.py (Category, Priority enums) · values.py · entities.py · errors.py    │
│ ports.py (all Protocols/ABCs) · policy.py (DecisionPolicy) ·                  │
│ priority_rules.py (labeller rules as data) · routing.py (action table)        │
└──────────────────────────────────────────────────────────────────────────────┘
Rule: `domain/` imports nothing outside stdlib. `application/` imports domain + numpy only.
`adapters/` import anything. `frameworks/` import composition + application dto.
Enforced by `services/ai/tests/test_architecture.py` (import-graph check, P0).
```

### 1.2 Directory mapping (reconciles SPEC §10 with CLAUDE.md)

SPEC §10 lists flat modules (`preprocess · guards/ · models/ …`). They keep their names but live under `adapters/`, with the pure decision logic lifted into `domain/`. `api.py`, `train.py`, `predict.py`, `evaluate.py`, `Dockerfile`, `tests/` stay exactly where CLAUDE.md and SPEC §10 put them.

```
campuspulse/
├── CLAUDE.md  README.md  .env.example  .gitignore  .gitattributes  pyproject.toml (ruff only, root)
├── render.yaml                    Render blueprint at the repo root (web, Docker, plan: starter, dockerfilePath ./services/ai/Dockerfile, dockerContext ., healthCheckPath /health, autoDeployTrigger: commit)
├── netlify.toml                   base apps/web, NODE_VERSION 22
├── config/
│   ├── integrations.yaml          sinks: [supabase, linear]   (webhook listed, disabled)
│   ├── clarify_questions.yaml     question bank (§5.1[8])
│   ├── actions.yaml               routing table category×priority → action type, SLA hours
│   ├── train.yaml                 training inputs (seed, k, grids, alpha, tuning rules, M3 gates)
│   ├── hand_tuned.yaml            hand-tuned thresholds (tau_faq, tau_inc); read by train.py and copied into config.json
│   ├── datasets.yaml              dataset validation floors, augmentation plan, leakage threshold, probe styles
│   └── lexicons/                  urgency.yaml safety.yaml injection.yaml arabizi.yaml gazetteer.yaml wrappers.yaml
├── apps/web/                      Next.js (see §1.7)
├── services/ai/
│   ├── pyproject.toml             package campuspulse_ai, requires-python ">=3.11,<3.14"
│   ├── requirements.txt           pinned (dependency agent); inference only: numpy, scikit-learn, onnxruntime, tokenizers, pandas, pyyaml, pydantic — NO torch
│   ├── requirements-train.txt     + torch, sentence-transformers, transformers (encoder export via torch.onnx.export + onnxruntime quantize_dynamic, M3) — dev machine only; no optimum
│   ├── requirements-api.txt       requirements.txt + fastapi, uvicorn, httpx, supabase, psutil, python-multipart — what Render installs (email = stdlib smtplib)
│   ├── requirements-dev.txt       + pytest, ruff, mypy, nbformat, nbclient, respx
│   ├── api.py                     `from campuspulse_ai.frameworks.fastapi_app import create_app; app = create_app()`
│   ├── train.py                   thin → frameworks/cli/train.py
│   ├── predict.py                 thin → frameworks/cli/predict.py
│   ├── evaluate.py                thin → frameworks/cli/evaluate.py
│   ├── Dockerfile                 python:3.11-slim, build context = repo root, installs requirements-api.txt, fetches the encoder release at build, listens on $PORT (Render)
│   ├── campuspulse_ai/
│   │   ├── domain/        labels.py values.py entities.py errors.py ports.py policy.py priority_rules.py routing.py
│   │   ├── application/   dto.py services/triage_core.py use_cases/{triage,clarify,batch_predict,feedback,act,resolve_incident,sync_ticket,run_redteam,escalate_sla}.py
│   │   ├── adapters/
│   │   │   ├── preprocess/  normalizer.py wrappers.py langid.py arabizi.py location.py
│   │   │   ├── guards/      injection.py safety.py gibberish.py gaming.py
│   │   │   ├── models/      tfidf_lr.py encoder.py embed_lr.py knn.py transformer_ft.py ensemble.py priority_head.py evidence.py ood.py soft_targets.py
│   │   │   ├── uncertainty/ conformal.py
│   │   │   ├── clarify/     bank.py info_gain.py
│   │   │   ├── explain/     token_attr.py occlusion.py counterfactual.py explainer.py
│   │   │   ├── llm/         openrouter.py set_constrained.py null.py cache_sqlite.py cost.py
│   │   │   ├── vectors/     local_numpy.py (frozen artifacts, offline) pgvector.py (Supabase RPC) — VectorStore port
│   │   │   ├── memory/      null.py inmemory.py pgvector_memory.py (MemoryStore over VectorStore "memory")
│   │   │   ├── store/       inmemory.py supabase_store.py
│   │   │   ├── integrations/ supabase_sink.py linear.py webhook.py (webhook = P4 stretch)
│   │   │   ├── notify/      outbox.py gmail_smtp.py allowlist.py inapp.py
│   │   │   ├── calendar/    slots_table.py google.py (google = stretch)
│   │   │   ├── faq/         retriever.py (FAQRetriever over VectorStore "faq"; same class for local and pgvector)
│   │   │   ├── pulse/       incident_detector.py
│   │   │   ├── redteam/     perturbation.py llm_generator.py scorer.py
│   │   │   ├── artifacts/   io.py (save/load + MANIFEST.json sha256)
│   │   │   ├── training/    pool.py cv.py tuning.py metrics.py (training pool, frozen-cv_fold OOF, stage-B tuning, metrics; used by train.py and evaluate.py)
│   │   │   └── clock.py
│   │   ├── config/        settings.py (pydantic-settings) frozen.py (FrozenConfig schema) paths.py
│   │   ├── composition/   offline.py online.py
│   │   └── frameworks/    fastapi_app.py routes/{triage,feedback,batch,redteam,incidents,integrations,metrics,explain,health}.py auth.py cli/{predict,train,evaluate,export_encoder}.py
│   └── tests/             unit/ contracts/ invariants/ e2e/ fixtures/ conftest.py (tiny_model_dir session fixture) test_architecture.py
├── supabase/              migrations/ seed/ (buildings, advisors, faq, demo profiles)
├── data/                  raw/ clean/ (+ cv_folds.csv, train_val_features.csv from the data audit) augmented/ our_test/ robustness/
├── scripts/               clean_data.py test_clean.py make_folds.py add_derived_columns.py test_data_audit.py validate_dataset.py draft_augmentation.py check_leakage.py fetch_models.py no_network.py validate_predictions.py diff_reports.py run_notebooks.py make_predictions.py make_predictions.sh simulate_pulse.py measure_rss.py keep_warm.ps1 clean_machine_check.{sh,ps1}
├── notebooks/             01_eda 02_benchmark 03_uncertainty_conformal 04_robustness_error_analysis 05_fairness (thin: load reports/*.json, plot)
├── models/frozen/         v1/ {config.json, MANIFEST.json, oof.npz, m1/, m2lr/, head/, conformal/, index/, lexicons/ (snapshot), encoder/ (fetched: ONNX int8 + tokenizer), m3/ (fetched, only if M3 is in)} + CURRENT (text file = "v1")
├── reports/               metrics.json benchmark.md coverage.json fairness.json ablations.json errors.json eda.json confusions/ conformal_scores.npz cv_p1.json cv_p2.json encoder_export.json encoder_choice.json leakage.json predictions_val_check.csv redteam/ (generated by train.py / evaluate.py)
└── docs/                  SPEC.md PLAN.md integrations.md reference/ report/
```

### 1.3 Domain: labels, value objects, entities

`domain/labels.py`
```python
class Category(str, Enum):
    REGISTRATION = "Registration"; IT_SUPPORT = "IT Support"; FINANCE = "Finance"
    TRANSPORTATION = "Transportation"; FACILITIES = "Facilities"; ACADEMIC_SUPPORT = "Academic Support"
class Priority(str, Enum):
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"
    @property
    def rank(self) -> int: ...            # low=0, medium=1, high=2
    def bump(self) -> "Priority": ...     # +1 capped at high
CATEGORY_ORDER: tuple[Category, ...]      # fixed column order for every prob vector
PRIORITY_ORDER: tuple[Priority, ...]
```
The exact spellings above are the **only** place label strings exist. `predict.py` writes `Category.value`/`Priority.value`.

`domain/values.py` (all `@dataclass(frozen=True, slots=True)`)
- `Lang(str, Enum)`: `EN, AR, ARABIZI`
- `ProbVector(values: tuple[float, ...], labels: tuple[str, ...])` with `argmax()`, `top(k)`, `as_dict()`; invariant: sums to 1 ± 1e-6.
- `PredictionSet(labels: frozenset[str])` with `size`, `is_singleton`.
- `Evidence(type: str, span: str, lang: Lang)` — e.g. `("deadline_today", "اليوم", AR)`.
- `EvidenceVector(flags: Mapping[str, bool], spans: tuple[Evidence, ...])` — ordered by `EVIDENCE_FEATURES` tuple in `priority_rules.py`.
- `GuardVerdict(kind: Literal["none","injection","distress","danger","gibberish"], matched_spans: tuple[str, ...], stripped_text: str, score: float)`.
- `NormalizedRequest(raw: str, core: str, text_norm: str, model_text: str, lang: Lang, is_arabizi: bool, stated_urgency: bool, truncated: bool, location: Location | None)` — `model_text` = what models see (transliteration + original for Arabizi, else `text_norm`).
- `Location(building: str, room: str | None, source: Literal["picked","extracted"])`.
- `Tier(str, Enum)`: `TIER0, TIER1, TIER2, HUMAN`.
- `Outcome(str, Enum)`: `ACCEPT, ASK, ESCALATE, HUMAN_REVIEW, OUT_OF_SCOPE, DISTRESS`.
- `ArtifactVersion(name: str, sha256: str)`.
- `ClarificationConstraint(kind: Literal["category","priority","feature"], value: str)`.
- `Money(usd: float)`.

`domain/entities.py` (mutable `@dataclass`, ids are `str` UUIDs)
- `Request(id, alias, raw_text, normalized: NormalizedRequest | None, input_mode, status: RequestStatus, created_at, conversation_id)`
- `CoreResult` (output of `TriageCore.classify`): `p_cat: ProbVector, p_pri: ProbVector, per_model: dict[str, ProbVector] (keys `"<member>.<target>"`, e.g. `"m1.category"`), flags: frozenset[str], set_cat: PredictionSet, set_pri: PredictionSet, ood_score: float, neighbors: tuple[Neighbor, ...], evidence: EvidenceVector, guard: GuardVerdict, safety: bool, floors_applied: tuple[str, ...], tier: Tier, latency_ms: int, artifact: ArtifactVersion`
- `Prediction(id, request_id, category, priority, core: CoreResult, tier, flags: set[str], explanation: Explanation | None, cost: Money, artifact_version)`
- `Clarification(id, request_id, question_id, options, answer, asked_at, answered_at)`
- `Ticket(id, request_id, incident_id, office, category, priority, status: TicketStatus, provisional, sla_due_at, escalated_at, resolved_at, links: list[TicketLink], tags: tuple[str, ...] = ())` (tags: D-011); `TicketLink(ticket_id, sink, external_id, url, error: str | None = None)` (error → `ticket_links.last_error`, D-011)
- `Incident(id, building, category, title, priority, report_count, status, member_ticket_ids, opened_at, resolved_at)`
- `MemoryExample(id, text_norm, lang, embedding, category, priority, author_id, created_at, active)`
- `ReviewItem(id, prediction_id, reason, status, reviewer_id, corrected_category, corrected_priority, note)`
- `OutboxMessage(id, kind, to_address, subject, body, provider_id, status: queued|sent|failed|rejected|deferred, created_at, priority, flags, error: str | None = None)` (deferred + error: D-011)
- `LLMCall(id, request_id, tier, model, prompt_hash, tokens_in, tokens_out, cost, latency_ms, cached)`
- `RedTeamItem(text, style, lang, intended_category, intended_priority, expected_flags)`; `Scorecard(run_id, by_style: dict, by_lang: dict, overall: float, failures: list)`
- `Explanation(top_tokens, urgency_reasons, neighbors, counterfactual, trace)`

Status enums: `RequestStatus` (`received, needs_clarification, clarified, decided, human_review, out_of_scope, distress, actioned, resolved, merged`), `TicketStatus` (`open, in_progress, resolved, closed, escalated, merged`).

`domain/errors.py`
```python
class CampusPulseError(Exception): ...
class InvalidInput(CampusPulseError): ...             # empty text, bad CSV columns
class ArtifactError(CampusPulseError): ...            # base
class ArtifactMissing(ArtifactError): ...             # path absent
class ArtifactChecksumMismatch(ArtifactError): ...
class ArtifactVersionMismatch(ArtifactError): ...     # config.json schema/version
class LLMError(CampusPulseError): ...                 # base
class LLMUnavailable(LLMError): ...                   # no key / network / 5xx after retries
class LLMOutputOutOfSet(LLMError): ...                # label not in allowed set
class RecipientNotAllowed(CampusPulseError): ...      # allow-list violation
class SinkError(CampusPulseError): retryable: bool
class NotificationError(CampusPulseError): retryable: bool   # SMTP/provider failure; 5xx/timeout retryable, auth/4xx not
class CalendarUnavailable(CampusPulseError): ...
class StoreError(CampusPulseError): ...
class NotFound(StoreError): ...
class Unauthorized(CampusPulseError): ...             # role check
class ClarificationBudgetExceeded(CampusPulseError): ...
```
Boundary rule: adapters raise these (never SDK exceptions); use cases catch only what they can degrade (e.g. `SinkError` → log + continue; `LLMUnavailable` → fall back to tier 0); routes map to HTTP codes in one `frameworks/errors.py`.

### 1.4 Ports (`domain/ports.py`) — signatures, errors, concrete implementations

All are `typing.Protocol` (runtime_checkable) unless an ABC is noted for shared behaviour. `Seq = Sequence`, `NDArray = numpy.ndarray` is **not** imported in domain; ports pass `tuple[float, ...]`/`ProbVector`, and adapters convert. (Exception: `SentenceEncoder` returns `list[list[float]]`; adapters wrap to numpy.)

```python
class Normalizer(Protocol):
    def normalize(self, raw: str, picked_location: Location | None = None) -> NormalizedRequest: ...
# impl: adapters/preprocess/normalizer.py::DefaultNormalizer(wrappers, langid, arabizi, location)
# errors: InvalidInput on empty/whitespace raw.

class Guard(Protocol):                                   # one per concern, run in order
    name: str
    def inspect(self, req: NormalizedRequest) -> GuardVerdict: ...
# impls: InjectionGuard(regex bank + ExemplarSimilarity), SafetyGuard (distress + danger), GibberishGuard
# SafetyGuard offline: "danger" comes from the lexicon only; exemplar similarity (thresholds.tau_safety) may only add "distress", which never changes a batch label.
# InjectionGuard has mode: Literal["strip_regex_only","full"]; offline container uses strip_regex_only.
# errors: none (guards never raise; failure → verdict "none" + logged).

class ExemplarSimilarity(Protocol):                      # used by guards; wraps SentenceEncoder
    def max_similarity(self, text: str, bank: str) -> tuple[float, str]: ...   # (score, nearest exemplar)

class SentenceEncoder(Protocol):
    dim: int; model_id: str
    def encode(self, texts: Seq[str]) -> list[list[float]]: ...
# impls: OnnxEncoder (onnxruntime + tokenizers over models/frozen/vN/encoder/{model_int8.onnx,tokenizer.json}; mean pooling + L2 norm; intra_op_num_threads from Settings), HashingEncoder (test fake, deterministic)
#        STEncoder (torch/sentence-transformers) exists ONLY in frameworks/cli/export_encoder.py (train machine) to produce the ONNX file; never loaded at inference.
# errors: ArtifactMissing if local dir absent.

class ProbabilisticClassifier(Protocol):                 # M1, M2-LR, M3 — one per target (category | priority)
    name: str; target: Literal["category","priority"]
    def fit(self, texts: Seq[str], y: Seq[str], sample_weight: Seq[float] | None = None) -> None: ...
    def predict_proba(self, texts: Seq[str]) -> list[ProbVector]: ...
    def save(self, dir: Path) -> None: ...
    @classmethod
    def load(cls, dir: Path) -> "ProbabilisticClassifier": ...
# impls: TfidfLR (M1), EmbedLR (M2-LR, takes SentenceEncoder), TransformerFT (M3, torch), KnnClassifier (M2-kNN via ExampleIndex)
# TfidfLR exposes token_contributions(text) -> list[tuple[str, float]] for the explainer (extra method, not in port).

class VectorStore(Protocol):                             # one port, named collections (see §3.18)
    dim: int
    def upsert(self, collection: str, items: Seq[VectorItem]) -> None: ...
    # VectorItem(id, embedding: Seq[float], text: str, lang: Lang, meta: Mapping[str, str|float|bool|None])
    def search(self, collection: str, query: Seq[float], k: int, min_sim: float = 0.0, filters: Mapping[str, object] | None = None) -> list[VectorHit]: ...
    # VectorHit(id, text, sim, lang, meta, embedding: tuple[float, ...] | None = None)   cosine similarity, descending, deterministic tie-break on id;
    #   embedding is filled only when filters["with_embedding"] is true (incident centroid); both stores honour the flag
    def set_active(self, collection: str, id: str, active: bool) -> None: ...
    def count(self, collection: str, filters: Mapping[str, object] | None = None) -> int: ...
# impls: LocalNumpyVectorStore (brute-force cosine over .npy + items.jsonl per collection; loads from / saves to models/frozen/vN/index/; read-only after load except in tests),
#        PgVectorStore (Supabase RPC: match_vectors(collection, query, k, min_sim, filters jsonb); collections map to tables, §3.18)
# errors: StoreError; ArtifactMissing (local); dim mismatch → ArtifactVersionMismatch at construction (store.dim != encoder.dim).

class ExampleIndex:                                      # concrete class in adapters/models/knn.py, NOT a port
    # frozen training index = VectorStore collection "train" in LocalNumpyVectorStore. Always local, in every container.
    def query(self, embedding: Seq[float], k: int) -> list[Neighbor]: ...   # Neighbor(text, category, priority, sim, source: "train"|"augmented"|"memory", created_at)
    def max_similarity(self, embedding: Seq[float]) -> float: ...           # OOD score (train collection only; memory never changes OOD)

class Ensemble(Protocol):
    members: tuple[str, ...]
    def predict(self, texts: Seq[str], memory: "MemoryStore | None") -> list[EnsembleOutput]: ...
    # EnsembleOutput(p_cat, p_pri_model, per_model, ood_score, neighbors, embedding)
# impl: WeightedEnsemble(classifiers, index, encoder, weights from FrozenConfig). Membership is config-driven.

class EvidenceExtractor(Protocol):
    def extract(self, req: NormalizedRequest) -> EvidenceVector: ...
# impl: LexiconEvidenceExtractor (config/lexicons/urgency.yaml). `stated_urgency` is NOT a feature (asserted by test).

class PriorityHead(Protocol):
    def fit(self, p_pri_oof: Seq[ProbVector], evidence: Seq[EvidenceVector], y: Seq[str], sample_weight: Seq[float] | None) -> None: ...
    def predict(self, p_pri_model: ProbVector, evidence: EvidenceVector, constraints: Seq[ClarificationConstraint] = ()) -> ProbVector: ...
    def save(self, dir: Path) -> None: ...
    @classmethod
    def load(cls, dir: Path) -> "PriorityHead": ...
# impl: LogisticPriorityHead. Floors are NOT inside the head; they are applied by PriorityFinalizer (application) so the head stays a pure model.

class ConformalPredictor(Protocol):
    target: Literal["category","priority"]; alpha: float
    def calibrate(self, probs: Seq[ProbVector], y: Seq[str], groups: Seq[str]) -> None: ...
    def predict_set(self, p: ProbVector) -> PredictionSet: ...
    def save(self, dir: Path) -> None: ...
    @classmethod
    def load(cls, dir: Path) -> "ConformalPredictor": ...
# impl: LACConformal (score = 1 - p_true; q = ceil((n+1)(1-α))/n quantile; empty set → argmax singleton + flag "empty_set").
# optional: MondrianByLang wrapper (only if P2 fairness audit demands it, see §3.5).

class DecisionPolicy(Protocol):                          # pure, in domain/policy.py; class not Protocol
    def decide(self, core: CoreResult, budget: ClarificationBudget, llm_allowed: bool) -> Outcome: ...

class ClarificationStrategy(Protocol):
    def select(self, core: CoreResult, lang: Lang, asked: Seq[str]) -> ClarificationQuestion | None: ...
    def apply(self, core: CoreResult, question_id: str, option_id: str) -> tuple[CoreResult, Seq[ClarificationConstraint]]: ...
# impl: InfoGainStrategy(QuestionBank). Question text rephrasing by LLM is optional via `QuestionRephraser` (NullRephraser offline).

class LabelOracle(Protocol):                             # LLM tiers (SPEC "router")
    tier: Tier; model_id: str
    def choose(self, req: NormalizedRequest, allowed_cat: PredictionSet, allowed_pri: PredictionSet, context: OracleContext) -> OracleAnswer: ...
    # OracleAnswer(category | None, priority | None, rationale: str, call: LLMCall)
# impls: OpenRouterOracle(model_id, cache: ResponseCache, cost: CostLogger, clock), NullOracle (raises LLMUnavailable), ScriptedOracle (tests)
# errors: LLMUnavailable (fallback tier 0), LLMOutputOutOfSet (caller discards answer, logs, falls back).

class ResponseCache(Protocol):
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, value: str) -> None: ...
# impls: SqliteCache (file in model_dir/../cache or /tmp), SupabaseCache (llm_calls table), DictCache (tests)

class CostLogger(Protocol):
    def log(self, call: LLMCall) -> None: ...
    def totals(self) -> dict[str, float]: ...             # {"usd": , "calls": , "cached": }
# impls: InMemoryCostLogger, SupabaseCostLogger

class Explainer(Protocol):
    def explain(self, req: NormalizedRequest, core: CoreResult, decided: tuple[Category, Priority]) -> Explanation: ...
    def counterfactual(self, req: NormalizedRequest, drop_token: str) -> tuple[Category, Priority, ProbVector, ProbVector]: ...
# impl: OcclusionExplainer(core: TriageCore, m1: TfidfLR, max_occlusions from config)

class MemoryStore(Protocol):
    def add(self, ex: MemoryExample) -> MemoryExample: ...
    def active(self, since: datetime | None = None) -> list[MemoryExample]: ...
    def deactivate(self, id: str) -> None: ...
    def stats(self) -> MemoryStats: ...
    def neighbors(self, embedding: Seq[float], k: int, min_sim: float) -> list[Neighbor]: ...   # active items only, source="memory"
# impls: NullMemoryStore (offline: always empty, add() raises StoreError), InMemoryMemoryStore (tests/red team), PgVectorMemoryStore(PgVectorStore, collection="memory")

class ActionPlanner(Protocol):                           # routing table → ActionPlan (domain/routing.py impl is pure)
    def plan(self, category: Category, priority: Priority, flags: frozenset[str], provisional: bool) -> ActionPlan: ...
    # ActionPlan(kind: "faq_answer"|"ticket"|"booking"|"safety_alert", office, sla_hours, tags)

class FAQRetriever(Protocol):
    def search(self, text: str, lang: Lang, k: int) -> list[FAQHit]: ...   # FAQHit(id, question, answer, source_url, is_demo, score)
# impl: VectorFAQRetriever(VectorStore, SentenceEncoder, collection="faq") — one class; local store in tests, PgVectorStore online

class TicketSink(Protocol):
    name: str
    def create(self, ticket: Ticket) -> TicketLink: ...        # idempotent on ticket.id
    def update_status(self, ticket: Ticket) -> None: ...
    def close(self, ticket: Ticket) -> None: ...
    def handle_inbound(self, payload: bytes, signature: str) -> InboundEvent | None: ...
# impls: SupabaseSink (always on), LinearSink (GraphQL via httpx), WebhookSink (HMAC; stretch), FakeSink (tests)
# errors: SinkError(retryable). Retry wrapper: RetryingSink(sink, backoff from Settings).

class Notifier(Protocol):
    def send(self, msg: OutboxMessage) -> OutboxMessage: ...  # returns with provider_id/status
# impls: GmailSmtpNotifier (stdlib smtplib, STARTTLS on SMTP_PORT 587, app password), InAppNotifier (writes notifications row), FakeNotifier
# errors: NotificationError(retryable) — the caller (ActUseCase) records outbox status "failed" and never fails the request
# decorator: AllowlistedNotifier(inner, policy: RecipientPolicy) — raises RecipientNotAllowed, records status="rejected"

class RecipientPolicy:                                   # domain value object, concrete class
    def __init__(self, allowlist: frozenset[str]) -> None: ...
    def check(self, address: str) -> None: ...               # raises RecipientNotAllowed

class CalendarProvider(Protocol):
    def find_slot(self, advisor_ids: Seq[str], window: tuple[datetime, datetime], office_hours: OfficeHours) -> Slot | None: ...
    def book(self, slot: Slot, attendees: Seq[str], title: str) -> Booking: ...   # attendees checked by RecipientPolicy before call
# impls: SlotsTableCalendar (Supabase advisor_slots; default), GoogleCalendarProvider (stretch), FakeCalendar
# errors: CalendarUnavailable → use case falls back to SlotsTableCalendar (composition passes a fallback chain).

class Repository(Protocol):                              # one port, grouped methods; Supabase impl is one class
    # requests
    def save_request(self, r: Request) -> Request: ...
    def get_request(self, id: str) -> Request: ...                # NotFound
    def set_request_status(self, id: str, status: RequestStatus) -> None: ...
    # predictions / clarifications / review
    def save_prediction(self, p: Prediction) -> Prediction: ...
    def latest_prediction(self, request_id: str) -> Prediction: ...
    def save_clarification(self, c: Clarification) -> Clarification: ...
    def clarifications_for(self, request_id: str) -> list[Clarification]: ...
    def enqueue_review(self, item: ReviewItem) -> ReviewItem: ...
    def resolve_review(self, item: ReviewItem) -> None: ...
    # tickets / incidents / outbox / signals / audit
    def save_ticket(self, t: Ticket) -> Ticket: ...
    def get_ticket(self, id: str) -> Ticket: ...
    def overdue_open_tickets(self, now: datetime) -> list[Ticket]: ...
    def save_ticket_link(self, link: TicketLink) -> None: ...
    def save_incident(self, i: Incident) -> Incident: ...
    def open_incidents(self, building: str, category: Category, since: datetime) -> list[Incident]: ...
    # (recent located requests for incident clustering are read from VectorStore collection "requests", not here)
    def save_outbox(self, m: OutboxMessage) -> OutboxMessage: ...
    def bump_student_signals(self, alias: str, claimed_urgent: bool, was_high: bool, injection: bool) -> StudentSignals: ...
    def append_event(self, actor: str, action: str, entity: str, payload: Mapping[str, object]) -> None: ...
    def save_redteam_run(self, scorecard: Scorecard) -> str: ...
    # added (lead decision, from the P4 flows)
    def ticket_by_link(self, sink: str, external_id: str) -> Ticket: ...                 # NotFound
    def incident_members(self, incident_id: str) -> list[tuple[Ticket, Request]]: ...
    def free_slots(self, advisor_ids: Seq[str], window: tuple[datetime, datetime]) -> list[Slot]: ...
    def claim_slot(self, slot: Slot, booked_by: str) -> bool: ...                        # conditional update where booked_by is null
    def save_case(self, c: Case) -> Case: ...                                            # cut B-list ("cases") → no-op when cut
    def save_notification(self, alias: str, kind: str, payload: Mapping[str, object]) -> None: ...
    def advisors_for(self, department: str) -> list[Advisor]: ...
    def router_stats(self, since: datetime | None = None) -> RouterStats: ...
    def redteam_history(self, limit: int = 20) -> list[Scorecard]: ...
# impls: InMemoryRepository (tests + offline red team), SupabaseRepository (service role, bypasses RLS)

class IncidentDetector(Protocol):
    def detect(self, req: Request, pred: Prediction, embedding: Seq[float]) -> IncidentDecision: ...
    # IncidentDecision(kind: "none"|"new"|"attach", incident: Incident | None, members: list[str])
# impl: WindowedCentroidDetector(repo, vectors: VectorStore ("requests" collection, filters building+category+created_at ≥ now−window), FrozenConfig.tau_inc, Settings.incident_window_min, min_reports=3, bump_at=6)

class RedTeamGenerator(Protocol):
    def generate(self, n: int, styles: Seq[str], seed: int) -> list[RedTeamItem]: ...
# impls: PerturbationGenerator (default, offline, over data/our_test), LLMRedTeamGenerator (stretch)

class Clock(Protocol):
    def now(self) -> datetime: ...                               # tz-aware, Asia/Amman
# impls: SystemClock, FrozenClock (tests)

class ArtifactStore(Protocol):
    def load_manifest(self, model_dir: Path) -> Manifest: ...     # ArtifactMissing / ArtifactChecksumMismatch / ArtifactVersionMismatch
    def write_manifest(self, model_dir: Path, files: Seq[Path]) -> Manifest: ...
```

Application-layer concrete services (not ports; one implementation each):
- `application/services/triage_core.py::TriageCore` — holds `Normalizer, Sequence[Guard], Ensemble, EvidenceExtractor, PriorityHead, PriorityFinalizer, ConformalPredictor (cat), ConformalPredictor (pri), MemoryStore, Clock, FrozenConfig`. Method `classify(raw: str, picked_location=None, constraints=(), memory=True) -> tuple[NormalizedRequest, CoreResult]`. **This is the only path that produces labels anywhere in the system.**
- `application/services/priority_finalizer.py::PriorityFinalizer` — applies floors in fixed precedence (§2.1 step 9), returns `(ProbVector, floors_applied)`.
- `application/services/llm_merge.py::LLMMerger` — merges an `OracleAnswer` into `CoreResult` (§3.9).

### 1.5 Composition roots

`composition/offline.py`
```python
@dataclass(frozen=True)
class OfflineContainer:
    core: TriageCore
    oracle: LabelOracle            # NullOracle unless use_llm
    config: FrozenConfig
    manifest: Manifest
    batch: BatchPredictUseCase

def build_offline(model_dir: Path, *, use_llm: bool = False, settings: Settings | None = None,
                  encoder_override: SentenceEncoder | None = None) -> OfflineContainer:
    # 1. ArtifactStore.load_manifest(model_dir)  → verifies sha256 of every artifact file
    # 2. FrozenConfig.load(model_dir / "config.json")
    # 3. encoder = encoder_override or OnnxEncoder(model_dir / "encoder")   (no torch import anywhere on this path)
    # 3b. vectors = LocalNumpyVectorStore.load(model_dir / "index")   collections: exactly "train", "injection_exemplars", "safety_exemplars" ("faq_seed" exists only in test fixtures, never in a model dir)
    # 4. members per config.ensemble.members: TfidfLR.load, EmbedLR.load, KnnClassifier(ExampleIndex(vectors, "train")), TransformerFT.load (only if listed; must be ONNX too)
    # 5. guards = [InjectionGuard(mode="strip_regex_only"), GibberishGuard(), SafetyGuard(exemplars=encoder)]
    # 6. memory = NullMemoryStore()
    # 7. oracle = OpenRouterOracle(...) if use_llm else NullOracle()
    #    use_llm and no OPENROUTER_API_KEY → raise LLMUnavailable at build time with a one-line message (fail fast).
    # 8. core = TriageCore(...); batch = BatchPredictUseCase(core, oracle, config)
```
No Supabase, notifier (`adapters.notify*`), Linear, Google, torch import anywhere in this module graph. `tests/test_architecture.py` asserts `import campuspulse_ai.composition.offline` leaves `sys.modules` free of `supabase`, `httpx`, `torch`, `sentence_transformers` and `campuspulse_ai.adapters.vectors.pgvector` (httpx is only loaded lazily inside `OpenRouterOracle.__init__`).

`composition/online.py`
```python
@dataclass(frozen=True)
class OnlineContainer:
    offline: OfflineContainer                    # reuse, built with use_llm=settings.enable_llm
    repo: Repository; vectors: VectorStore (PgVectorStore); memory: MemoryStore; explainer: Explainer; clarifier: ClarificationStrategy
    policy: DecisionPolicy; planner: ActionPlanner; faq: FAQRetriever
    sinks: tuple[TicketSink, ...]; notifier: Notifier; calendar: CalendarProvider
    incidents: IncidentDetector; gaming: GamingDetector; redteam_gen: RedTeamGenerator
    cost: CostLogger; clock: Clock
    use_cases: UseCases                          # triage, clarify, feedback, act, resolve_incident, sync_ticket, run_redteam, escalate_sla

def build_online(settings: Settings) -> OnlineContainer:
    # vectors = PgVectorStore(supabase_client, dim=config.encoder.dim); asserts RPC vector_dim() == dim at startup (ArtifactVersionMismatch otherwise)
    # memory = PgVectorMemoryStore(vectors) and the offline core is REBUILT with memory=memory (TriageCore is the same class; only the MemoryStore differs;
    #   the frozen "train" collection stays in the in-process LocalNumpyVectorStore — it is never uploaded to Postgres)
    # faq = VectorFAQRetriever(vectors, encoder, "faq"); incidents = WindowedCentroidDetector(repo, vectors, ...)
    # after every classify, TriageUseCase upserts the request embedding into collection "requests" (building, category, created_at in meta)
    # sinks from config/integrations.yaml ∩ keys present: SupabaseSink always; LinearSink if LINEAR_API_KEY; WebhookSink if OUTBOUND_WEBHOOK_URL
    # notifier = AllowlistedNotifier(GmailSmtpNotifier(...) if GMAIL_SMTP_USER and GMAIL_APP_PASSWORD else InAppNotifier(repo), RecipientPolicy(settings.demo_email_allowlist))
    # calendar = FallbackCalendar([GoogleCalendarProvider(...) if GOOGLE_SERVICE_ACCOUNT_JSON else None, SlotsTableCalendar(repo)])
    # oracle tiers: tiers = [OpenRouterOracle(TIER1)] + ([OpenRouterOracle(TIER2)] if settings.openrouter_tier2_model else [])
```
`--use-llm` in `predict.py` = `build_offline(model_dir, use_llm=True)`; in the API = `Settings.enable_llm`. Same adapter class (`OpenRouterOracle`), same cache/cost ports; only the cache impl differs (`SqliteCache` offline vs `SupabaseCache` online).

Test fakes live in `tests/fixtures/fakes.py` and are wired by `build_test(**overrides)` in `tests/conftest.py` (an `OnlineContainer` with `InMemoryRepository`, `HashingEncoder`, `FakeSink`, `FakeNotifier`, `FakeCalendar`, `ScriptedOracle`, `FrozenClock`). This is how P3/P4 "API tests" run without network. The P3/P4 API tests build on the session fixture `tiny_model_dir` (P1: `train.py --fast --encoder hashing` on `tests/fixtures/tiny_train.csv`). `NullMemoryStore`, `NullOracle` and `SystemClock` are created in P1 because `build_offline` needs them.

### 1.6 Frozen config schema (`config/frozen.py::FrozenConfig`, serialized as `models/frozen/v1/config.json`)
```json
{
  "schema_version": 1, "artifact_version": "v1", "trained_at": "...", "seed": 42,
  "encoder": {"model_id": "intfloat/multilingual-e5-small", "revision": "<commit>", "dim": 384, "max_tokens": 256, "query_prefix": "query: ", "runtime": "onnx_int8", "file": "encoder/model_int8.onnx", "pooling": "mean", "normalize": true},
  "ensemble": {"members": ["m1", "m2lr", "m2knn"], "weights_category": {"m1": 0.3, "m2lr": 0.5, "m2knn": 0.2}, "weights_priority": {...}},
  "m1": {"char_ngram": [2, 5], "word_ngram": [1, 2], "C": 1.0},
  "m2lr": {"C": 1.0},
  "knn": {"k": 5, "memory_weight_cap": 0.6, "max_memory_neighbors": 2, "memory_min_sim": 0.80},
  "priority_head": {"features": ["deadline_today", "exam_now", "safety_risk", "stranded", "enrollment_blocked", "transient_glitch", "info_request", "fault_report", "ambient_fixture", "teaching_room"], "C": 1.0},
  "conformal": {"method": "lac", "alpha_category": 0.10, "alpha_priority": 0.10, "q_category": 0.0, "q_priority": 0.0, "n_calib": 0, "mondrian_by_lang": false},
  "thresholds": {"tau_ood": 0.0, "tau_faq": 0.0, "tau_inc": 0.0, "tau_injection": 0.0, "tau_safety": 0.0, "human_review_maxprob": 0.0},
  "guards": {"max_tokens": 256, "gibberish_min_tokens": 2, "gibberish_min_letter_ratio": 0.5, "injection_sentence_strip_ratio": 0.6},
  "llm": {"w_llm": 0.5, "prompt_version": "v1"},
  "explain": {"max_occlusions": 20},
  "priors": {"category": {"Registration": 0.0, "...": 0.0}, "priority": {"low": 0.0, "medium": 0.0, "high": 0.0}},
  "cv": {"k": 5, "group_col": "cv_group", "fold_col": "cv_fold", "folds_file": "data/clean/cv_folds.csv", "oof_macro_f1_category": 0.0, "oof_macro_f1_priority": 0.0}
}
```
- **Single writer:** `train.py` writes `config.json`; nothing else does. `evaluate.py`, `predict.py`, the API and tests read it. `thresholds.*` values of 0.0 fail validation (`FrozenConfig` requires them > 0 after training).
- **Inputs to `train.py`:**
  - `config/train.yaml`: training knobs (seed, k, grids, α, tuning rules, M3 gates)
  - `config/hand_tuned.yaml`: values that cannot be learned from the data (`tau_faq` default 0.75, `tau_inc` default 0.80). `train.py` reads them and copies them into `config.json`, so changing one means a re-freeze (`train.py --retune`, or the P6.1 final train).
- **Priors:** `priors` holds the label frequencies of the training pool. `predict.py` uses their argmax for empty input (flag `empty_input`).
- **Lexicons:** `train.py` snapshots `config/lexicons/*.yaml` into `models/frozen/vN/lexicons/`, and `MANIFEST.json` hashes them. Every container reads lexicons from the model directory, so editing `config/lexicons/` after a freeze cannot change `predict.py` output.

### 1.7 Frontend architecture (`apps/web`)

- Next.js 16 (16.4.2) App Router, TypeScript 5.9.3 with `strict: true`, Tailwind 4 (4.3.3, CSS-first). No component library dependency; a small in-repo design system.
- **Design system first (P5.1):** `src/design/tokens.css` (CSS variables: colour per category (6), per priority (3), semantic surfaces, spacing, radius, font; light + dark via `prefers-color-scheme`), Tailwind 4 `@theme` in `tokens.css` maps the tokens (no `tailwind.config.ts`), `src/components/ui/` = `Button, Card, Badge, Chip, ProbBar, SetBadge, Tabs, Table, Toast, Dialog, Skeleton, EmptyState, RtlProvider`. Feature components under `src/components/{chat,staff,pulse,outbox,lab}/`. Every `ui/` component has a Storybook-free "kitchen sink" page at `/dev/ui` (dev only) as its visual test.
- **Data-access layer:** `src/lib/supabase/{browser.ts, server.ts, types.ts (generated)}`; `src/lib/repos/{requests,tickets,incidents,outbox,metrics}.ts` expose typed `list/get/subscribe` only (reads under RLS, Realtime channels). `src/lib/ai/client.ts` is `import 'server-only'` and is the only module that knows `AI_SERVICE_URL`/`AI_SERVICE_TOKEN`; route handlers in `src/app/api/ai/[...path]/route.ts` forward JSON to FastAPI, attaching the user's role claims from the Supabase session. Components call `fetch('/api/ai/triage')`, never FastAPI directly.
- **Server-only keys:** `SUPABASE_SERVICE_ROLE_KEY` is never in `apps/web` at all (not even server). The web app has `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `AI_SERVICE_URL`, `AI_SERVICE_TOKEN`. A P5 test greps the built `.next/static` for `AI_SERVICE_TOKEN`/`sk-`/`re_` patterns.
- **Env scope (Netlify):** `AI_SERVICE_TOKEN` and `AI_SERVICE_URL` are read at runtime by route handlers, so they are scoped to Functions/Runtime, not only Builds.
- **Auth:** Supabase email/password demo accounts seeded (`talal@demo.local`, `it@demo.local`, `admin@demo.local`), login page with three "Sign in as" buttons. `profiles.role/office` drive RLS and UI routing (`/`, `/staff`, `/pulse`, `/outbox`, `/lab`).
- **i18n:** `src/i18n/{en,ar}.ts` dictionaries + `useT()`; `<html dir>` switches with language; no i18n library.
- **No business logic in components**: a component renders a `TriageResponse` DTO (mirrors SPEC §7 JSON, generated as TS types from the FastAPI OpenAPI schema in P4 via `openapi-typescript`).

---

## 2. End-to-end flows (as sequences through use cases and ports)

Legend: `UC` = use case; `→` call; `[cfg]` = threshold from `FrozenConfig`; `[set]` = runtime `Settings`.

### 2.0 Shared core: `TriageCore.classify(raw, picked_location, constraints, memory)`

```
 1. Normalizer.normalize(raw, picked_location)          → NormalizedRequest (core, text_norm, lang, is_arabizi, stated_urgency, location, truncated at guards.max_tokens [cfg])
 2. for g in guards (order: Gibberish, Injection, Safety):  g.inspect(req) → verdict
      Gibberish: verdict.kind == "gibberish"      → core returns early with flag "gibberish" BUT still carries ensemble output (batch needs a label) — see note.
      Injection: kind "injection" → req.model_text := verdict.stripped_text; flag "injection_attempt"; llm_allowed := False
      Safety:    kind "distress"  → flag "distress" (online halts in UC; batch continues)
                 kind "danger"    → safety := True
 3. Ensemble.predict([req.model_text], memory) → p_cat, p_pri_model, per_model, ood_score, neighbors, embedding
 4. EvidenceExtractor.extract(req)  → evidence (never includes stated_urgency)
 5. PriorityHead.predict(p_pri_model, evidence, constraints) → p_pri_head
 6. PriorityFinalizer.apply(p_pri_head, safety, verdict, constraints) → p_pri_final, floors_applied   (precedence in 2.1 step 9)
 7. ConformalPredictor[cat].predict_set(p_cat) → S_cat ; ConformalPredictor[pri].predict_set(p_pri_final) → S_pri
    constraints of kind "category" override S_cat := {value}; floors override S_pri := {high}
 8. return CoreResult(..., tier=TIER0)
Note: the core NEVER returns without p_cat/p_pri. Gibberish/OOD/distress are flags; the policy (online) decides what to do with them. Batch ignores them for the label.
```

### 2.1 SPEC §5.1 main triage — `TriageUseCase.run(TriageCommand) -> TriageResponse`

```
[1]  repo.save_request(status=received)                                   (Repository)
[2–6] req, core = TriageCore.classify(raw, picked_location)               (2.0)
[4']  if "distress" in core.flags:
        repo.set_request_status(distress); repo.enqueue_review(reason="distress")
        return TriageResponse(status="distress", message=support text + counselling placeholder + 911, action=None)
        — no ticket, no email, no LLM, minimal storage (raw text stored; no explanation computed).
[7]  outcome = DecisionPolicy.decide(core, budget=ClarificationBudget(asked=0, max=1, max_if_unsure=2), llm_allowed=not injection and settings.enable_llm and key present)
       order inside policy (domain/policy.py, deterministic, logged in trace.policy_path):
        a. "gibberish" flag                                  → OUT_OF_SCOPE
        b. ood_score < tau_ood [cfg] and |S_cat| ≥ 3         → OUT_OF_SCOPE
        c. |S_cat| == 1 and |S_pri| == 1                      → ACCEPT
        d. (|S_cat| == 2 or |S_pri| == 2) and budget left     → ASK
        e. llm_allowed and (|S_cat| ≥ 2 or |S_pri| ≥ 2)       → ESCALATE
        f. otherwise                                          → HUMAN_REVIEW  (label = argmax, flag needs_review)
[8]  ASK: q = ClarificationStrategy.select(core, lang, asked)  → repo.save_clarification; status needs_clarification; return response with `clarification`.
     (Resumes in ClarifyUseCase, 2.1b.)
[7e] ESCALATE: for tier in oracles (tier1, then tier2 if configured and still ambiguous):
        answer = oracle.choose(req, S_cat, S_pri, ctx)           cache hit → no network; CostLogger.log(call) always
        LLMUnavailable → break (fall through to policy without llm)
        LLMOutputOutOfSet → discard, log flag "llm_out_of_set", continue to next tier
        core = LLMMerger.merge(core, answer, w_llm [cfg])  → p_cat/p_pri recomputed, sets recomputed, tier := answer.tier
        re-run policy steps c/f only (no ASK after escalation)
[9]  final (category, priority) = argmax of the (possibly merged) core; floors already applied; safety flag → priority high (asserted again here: `assert priority == HIGH if core.safety`).
     precedence for priority, highest first: distress (no label at all, online only) > safety floor (high) > clarification constraint (explicit option) > injection (classified on stripped text; the head never sees stated_urgency) > head output > conformal set.
[9b] GamingDetector.check(req, priority, evidence, alias) → flags "urgency_unsupported" (staff-only note); repo.bump_student_signals(...) → admin flag "priority_gaming_suspected". Never changes the label.
[10] Explainer.explain(req, core, decided) → Explanation (top tokens, urgency reasons, neighbors incl. memory with "learned N s ago", counterfactual, trace)
[11] ActUseCase.run(prediction, provisional = outcome == HUMAN_REVIEW):
        plan = ActionPlanner.plan(category, priority, flags, provisional)
        faq_answer → FAQRetriever.search; score ≥ tau_faq [cfg] → answer + source + "[demo]" ; else open ticket + "I'm not sure…"
        ticket    → Ticket(sla_due_at = now + sla_hours[priority] [actions.yaml]); for sink in sinks: RetryingSink.create (SinkError → ticket_links.last_error)
        booking   → only if not provisional (or safety): CalendarProvider.find_slot/book with attendees checked by RecipientPolicy → Case row (we keep `cases`) + Notifier.send (email to demo inboxes) 
        safety_alert → always fires immediately even if provisional: Notifier.send(kind="alert") + ticket
[12] Notifier (AllowlistedNotifier) → OutboxMessage saved via repo.save_outbox (status sent|rejected|failed)
[12b] vectors.upsert("requests", [VectorItem(request_id, embedding, text_norm, lang, meta={building, room, category, priority, created_at})])   (online only)
[13] IncidentDetector.detect(req, pred, embedding) → vectors.search("requests", embedding, k=50, min_sim=tau_inc, filters={building, category, since}) → centroid + count → new/attach; incident ticket (one), members marked merged; broadcast via Notifier(kind="broadcast") to reporters.
[14] repo.save_prediction, repo.append_event; Supabase Realtime fans out DB inserts (no extra event bus). Explanation failure never fails triage: flag "explanation_failed". The response adds `understood_as` (Arabizi hint) and a top-level `message` (additive to SPEC §7).
```

2.1b `ClarifyUseCase.run(request_id, question_id, option_id | free_text)`:
```
 option: core', constraints = ClarificationStrategy.apply(core, question_id, option_id)   # "category" → S_cat := {label}; "priority" → S_pri := {label}; "feature" → evidence flag set, head re-run
         if option == "not_sure" and asked == 1 → budget.max = 2, ASK again
 free_text: raw' = raw + " " + free_text → TriageCore.classify(raw') (re-run from [2])
 then continue from [7] with budget.asked += 1 (policy step d is now false once budget exhausted).
```

### 2.2 SPEC §5.2 ticket lifecycle

```
open → in_progress → resolved → closed      side: escalated (SLA), merged (incident)
- EscalateSlaUseCase.run(now): repo.overdue_open_tickets(now) → for each: priority = priority.bump(); escalated_at = now; status escalated; sinks.update_status; Notifier (in-app staff). Runs from a FastAPI lifespan asyncio task every Settings.sla_scan_minutes (5). pg_cron NOT used (one fewer moving part).
- SyncTicketUseCase.run(sink_name, payload, signature): sink.handle_inbound → InboundEvent(external_id, new_status) → repo ticket by link → save status → Notifier in-app to student. LinearSink verifies HMAC with LINEAR_WEBHOOK_SECRET; bad signature → Unauthorized (401).
- Dashboard status change → POST /v1/tickets/{id}/status (added to §7 table, see §6) → same use case path (`SyncTicketUseCase.from_dashboard`), then sinks.update_status/close.
```

### 2.3 SPEC §5.3 staff review + live learning

```
FeedbackUseCase.run(FeedbackCommand(prediction_id, reviewer, corrected_category?, corrected_priority?, note)):
 1. auth: reviewer.role in {staff, admin} else Unauthorized (checked in frameworks/auth.py AND re-asserted in the use case)
 2. pred = repo.latest_prediction; final labels = corrected or confirmed
 3. repo.resolve_review; prediction updated (tier := HUMAN, flags += "staff_confirmed"); ticket.provisional = False → ActUseCase.finalize(ticket): booking/alert now fire if the plan says so (safety already fired)
 4. memory.add(MemoryExample(text_norm, lang, embedding (from pred.core — no re-encode), labels, author, now, active=True)) → PgVectorStore.upsert("memory", …)
 5. repo.append_event("feedback")
Immediate effect: Ensemble.predict(..., memory) → KnnClassifier merges ExampleIndex.query (frozen "train", local) with memory.neighbors(embedding, k, min_sim) (pgvector "memory", active only); memory votes weighted by knn.memory_weight_cap [cfg], at most knn.max_memory_neighbors of k. Next similar request's neighbors include source="memory" → explanation says "learned from a staff correction N s ago". OOD score uses the frozen index only.
Consolidation: `train.py --consolidate --memory-export data/augmented/memory_export.csv` (P3 stretch) = retrain with memory rows appended as an augmentation source; writes models/frozen/v2. NOT run before submission; v1 stays CURRENT.
Safety: only staff/admin write; deactivate() reverts; cap on weight; Model lab shows memory stats from memory.stats().
```

### 2.4 SPEC §5.4 red team

```
RunRedTeamUseCase.run(n, styles, seed, use_llm_generator=False):
 1. items = RedTeamGenerator.generate(n, styles, seed)     default PerturbationGenerator over data/our_test/*.csv:
      styles → perturbations: fake_urgency (prepend "URGENT!!" / "عاجل جدا"), calm_emergency (template), typos (char swap p=0.1), arabizi (AR core → rule transliteration reverse map), mixed_language, two_issues (concat two items), very_long (pad with benign filler), injection (wrapper injection phrases from config/lexicons/injection.yaml), off_topic (fixed list), distress_adjacent (fixed list; intended behaviour = distress route)
 2. for item: req, core = TriageCore.classify(item.text) (batch semantics; online memory ON so the demo shows learning), then DecisionPolicy only (no actions, no sinks, no notifier)
 3. RedTeamScorer.score(item, core, outcome): pass rules per style:
      injection → "injection_attempt" in flags and priority ≤ priority of the un-injected base text
      fake_urgency → label equals base label
      off_topic → OUT_OF_SCOPE; distress_adjacent → "distress" flag
      others → category/priority == intended
 4. Scorecard(by_style, by_lang, overall, failures) → repo.save_redteam_run; GET /v1/metrics exposes history
 5. Export: failures → data/robustness/candidates_<run>.csv with needs_human_check=True; promotion to data/robustness/probes.csv is manual.
Offline CLI: `python services/ai/evaluate.py --redteam` runs the same use case with InMemoryRepository and writes reports/redteam/<timestamp>.json (this is the version used in the report).
```

### 2.5 SPEC §5.5 batch / `predict.py`

```
python services/ai/predict.py --input <csv> --output predictions.csv [--use-llm] [--model-dir models/frozen] [--debug] [--batch-size 64]
 1. frameworks/cli/predict.py: parse args; model_dir default = models/frozen/<CURRENT>; set seeds (random, numpy); onnxruntime SessionOptions(intra_op_num_threads=min(4, cpu), execution_mode=SEQUENTIAL); os.environ TOKENIZERS_PARALLELISM=false. No torch, no HF hub.
 2. container = build_offline(model_dir, use_llm)              ArtifactError → exit 2 with message; LLMUnavailable → exit 3
 3. rows = read_csv(input, encoding="utf-8-sig", dtype=str, keep_default_na=False); require columns {request_id, text}; extra columns ignored; InvalidInput → exit 4
 4. BatchPredictUseCase.run(rows):
      for chunk: req, core = TriageCore.classify(text, memory=False)   (NullMemoryStore anyway)
      label_cat = core.p_cat.argmax(); label_pri = core.p_pri.argmax()   ← floors already inside p_pri (safety → high)
      if use_llm and (|S_cat| ≥ 2 or |S_pri| ≥ 2): oracle.choose(...) → LLMMerger.merge → argmax (LLMUnavailable → keep tier 0; out-of-set → keep tier 0)
      empty text → Normalizer raises InvalidInput; BatchPredictUseCase catches it and emits the argmax of FrozenConfig.priors + debug flag "empty_input"
 5. write CSV: columns exactly `request_id,category,priority`, same row order as input, UTF-8 (no BOM), "\n" line endings, no index. --debug adds p_* columns, set sizes, tier, flags, ood_score, artifact_version.
 6. print one summary line: `wrote N rows → predictions.csv (artifact v1 sha=…, tier0=N, llm=0, 12.3 s)`
No clarification, no actions, no repo, no network. The module graph of predict.py must not import `adapters.store`, `adapters.integrations`, `adapters.notify`, `adapters.calendar`, `adapters.memory.pgvector_memory`, `adapters.vectors.pgvector`, `torch` (test_architecture asserts).
```

---

## 3. Sensitive decisions

Each: decision · rationale · rejected · locked in · proof.

### 3.1 Offline/online boundary and the predictions CSV contract
- **Decision:** `predict.py` = `build_offline` + `BatchPredictUseCase` as in §2.5. Output contract: header `request_id,category,priority`; one row per input row in input order; labels exactly from `Category.value`/`Priority.value`; UTF-8 without BOM; LF; no quoting needed. Input read with `utf-8-sig` (official files carry a BOM). Unknown columns ignored, missing `text` → `InvalidInput`.
- **Rationale:** 20 points for functionality/reproducibility hinge on the judges running this on "a common computer". Fail-fast exit codes with messages beat silent wrong output.
- **Rejected:** a separate "lite" model path for batch (two code paths = two bugs); reading `text_norm` from clean data (hidden test is raw).
- **Locked:** P1 (P1.6 predict CLI). Never changes after.
- **Proof:** `tests/e2e/test_predict_cli.py`: run on `data/clean/val_clean.csv` (renamed columns) → asserts header, row count 62, label set ⊆ enum values, order preserved, exit 0, and `socket.socket` monkeypatched to raise (network disabled) during the run. Also `pytest -m offline` runs with `HF_HUB_OFFLINE=1`.

### 3.2 CV protocol and leakage
- **Decision:** Training pool = `train_val_combined.csv` (official train + val) + `data/augmented/*.csv`. Model selection and all OOF artifacts come from **5 frozen folds**: `scripts/make_folds.py` (seed 42) assigns the 30 official `cv_group`s to folds with one group per category per fold and all 3 priorities in every fold, and writes `data/clean/cv_folds.csv` (`cv_group,cv_fold`). The pool joins `cv_fold` by `cv_group`; `cv_group` stays the leakage unit. New augmentation groups (`NEW-Sxx`, `MEM-…`) are appended by `make_folds.py --include-augmented` without moving any official group (each new group goes to the fold with the fewest groups of its category; ties → lowest fold id). Augmented rows inherit `cv_group` from their source scenario (`source_scenario_id` column, required); new scenarios get `cv_group = NEW-Sxx` and `scripts/check_leakage.py` asserts (a) no identical `text_norm` across different groups, (b) prints every cross-group pair with encoder cosine ≥ 0.90 for manual merge (author sets `cv_group` of the new scenario to the existing group). Our own test set (`data/our_test/`) and probes (`data/robustness/`) are never loaded by `train.py` (path guard: `train.py` raises if any input path contains `our_test` or `robustness`; `evaluate.py` is the only reader). Random splits are not implemented anywhere (no `train_test_split` import allowed; ruff `banned-api` rule).
- **Rationale:** the hidden test is scenario-held-out; anything else inflates every number by ~30 points because the 9–11 wrapper variants are near-duplicates.
- **Rejected:** plain GroupKFold(5) (the data audit found validation folds with only 4–5 of 6 categories for every seed tried); StratifiedGroupKFold on the 18 label cells (infeasible with 30 groups; stratifying by category alone is feasible because every category has exactly 5 groups); leave-one-group-out (30 refits × 3 members × 2 targets too slow with the encoder, and the OOF estimates aren't better enough); holding out the official validation set as "the" test (6 scenarios, 5 of them translation-leaked — useless as a holdout, valuable as training).
- **Locked:** P1 (P1.4 `train.py --cv-only`). Own test set authored in P1.0 **before** any model is trained (see §6 flag 2).
- **Proof:** `scripts/test_data_audit.py` (every fold has 6 categories and 3 priorities; no group in two folds); `tests/invariants/test_cv_protocol.py`: folds come from `cv_folds.csv`; for each fold, `set(groups[train]) ∩ set(groups[test]) == ∅`, no `text_norm` overlap between train and test parts, translation pairs always same side; `test_train_refuses_holdout_paths`.

### 3.3 `label_flags.csv` as soft targets
- **Decision:** `adapters/models/soft_targets.py::SoftTargetExpander.expand(df) -> (texts, y, sample_weight)` duplicates a flagged row once per label in its `soft_target` dict with `sample_weight = prob`; non-flagged rows get weight 1. Applies to the flagged scenario and every augmented row whose `source_scenario_id` matches. Used by M1, M2-LR and the priority head via `sample_weight`; M3 uses soft cross-entropy directly; kNN stores the argmax label. Metrics are always computed against the **official hard label**.
- **Rationale:** sklearn LR has no soft-label API; weighted duplication is exactly equivalent for the log-loss. Argmax is preserved by construction (never 50/50), so the official label stays the training answer.
- **Rejected:** editing labels (forbidden); a custom loss (not worth it for 4 scenarios); dropping the flagged scenarios (loses data).
- **Locked:** P1 (P1.3). Ablation "soft vs hard" in P2.
- **Proof:** `tests/unit/test_soft_targets.py`: expanded weights per scenario sum to the original count; argmax of weights per scenario equals the official label; non-flagged rows unchanged.

### 3.4 Threshold tuning on OOF, then frozen
- **Decision:** `train.py` has three stages. **A:** the frozen `cv_fold` folds → OOF `ProbVector`s per member per target, plus OOF embeddings. **B (tune on OOF only):** ensemble weights by grid over the simplex (step 0.1) maximizing OOF macro-F1 (category and priority separately); priority head fitted on OOF `p_pri_model` + evidence with inner folds (the remaining `cv_fold`s) to produce OOF head probs; conformal quantiles from OOF ensemble (cat) and OOF head (pri) scores; `tau_ood` = 5th percentile of OOF max-similarity of in-distribution rows; `tau_injection` = the maximum exemplar similarity over all official + augmented rows **plus** a margin of 0.02 (so there are zero hits; the same rule gives `tau_safety`); `human_review_maxprob` = value at which OOF accuracy of rows below it is < 0.6. **C:** refit every member on 100 % of the pool, build the index, write `models/frozen/vN/` + `config.json` + `MANIFEST.json`. `tau_faq` and `tau_inc` are not learnable from this data: `tau_faq` default 0.75 tuned by hand on the seed FAQ in P4; `tau_inc` default 0.80 verified by the simulator; both still live in `config.json`. They are entered in `config/hand_tuned.yaml`, which `train.py` copies into `config.json`.
- **Rationale:** one command, one artifact set, no hand-edited numbers; the own test set stays an honest check on the OOF-tuned values.
- **Rejected:** nested CV for the ensemble weights (too slow, 30 groups too few); tuning on the own test set (would burn the only honest holdout).
- **Locked:** P1 for A/C and the head; P2 for weights, conformal and `tau_*`.
- **Proof:** `tests/unit/test_frozen_config.py` rejects zero thresholds; `tests/e2e/test_train_determinism.py` runs `train.py --cv-only --fast` twice on a fixture subset and asserts identical `config.json` (modulo `trained_at`).

### 3.5 Conformal method and coverage
- **Decision:** **LAC** score (`1 − p_true`) with a global quantile per target, calibrated on the OOF scores (cross-conformal), α = 0.10 for both targets. Quantile `q = ceil((n+1)(1−α))/n`-th smallest score. Empty set → argmax singleton + flag. `mondrian_by_lang` is a config switch (off by default), turned on in P2 only if AR or Arabizi coverage on the own test set is < 0.85 while EN ≥ 0.90.
- **Rationale:** LAC gives the smallest sets for a confident 6-way classifier, which is what makes the "ask only when genuinely ambiguous" demo crisp; APS inflates sets and needs randomization to be exact. Per-class Mondrian is infeasible (≈5 scenarios per class). Cross-conformal on OOF is the only way to get a calibration set without burning scenarios. Caveat to state in the report: calibration scores are clustered by scenario (wrapper variants), so the effective n is ≈ number of scenarios, and the guarantee is approximate; augmentation raises n.
- **Rejected:** split conformal with a held-out calibration fold (we can't spare 6 scenarios); RAPS (extra hyperparameters, no gain at 6 classes); α = 0.05 (sets of size 2–3 everywhere → every request asks a question).
- **Locked:** P2 (P2.5).
- **Proof:** `tests/unit/test_conformal.py` with synthetic probs: empirical coverage within ±0.03 of 0.90 at n = 2000; monotonic set size in α; empty-set fallback. `evaluate.py` prints coverage and mean set size overall and per language on the own test set (reported, not asserted).

### 3.6 Ensemble (M1/M2/M3) and the M3 cut
- **Decision:** Tier 0 members, config-driven: `m1` = TF-IDF (char_wb 2–5 + word 1–2) → LogisticRegression (`C` grid-searched on OOF, `class_weight="balanced"`), `m2lr` = frozen encoder embedding → LogisticRegression, `m2knn` = cosine kNN over the index (k from config, distance-weighted vote, Laplace-smoothed), `m3` = fine-tuned encoder with a classification head (joint 6+3 heads, soft CE), **listed only if it wins**. Encoder: `intfloat/multilingual-e5-small` is the primary candidate (384-d, strong Arabic, MIT), `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` the fallback; the dependency agent pins ID + revision + size. **The frozen encoder artifact is an ONNX int8 (dynamic quantization) export** produced once by `frameworks/cli/export_encoder.py` (`torch.onnx.export` + `onnxruntime.quantization.quantize_dynamic(QInt8, per_channel=True)` on the dev machine; a portable int8 config; no optimum; never Hugging Face's AVX512/VNNI-specific ONNX files) and used identically by `train.py`, `predict.py` and the Render API (§3.17). Weighted average of calibrated probabilities (M1/M2 LR are already probabilistic; no extra Platt step). Category and priority ensembles have separate weights. **M3 rule:** time-boxed to 4 h in P2; it enters `ensemble.members` only if the OOF macro-F1 (category) of the ensemble with M3 beats without by ≥ 0.01, it is exported to ONNX int8 as well, `predict.py` on 1,000 rows stays < 60 s, the fetched tier stays ≤ 200 MB, and Render RSS stays ≤ 400 MB with `m3` loaded (a local peak-RSS check in P2, then the P4 Render memory test X4.6; failing X4.6 later means the cut). Cutting M3 = removing `"m3"` from `members` in `config.json`; no code change.
- **Rationale:** with 42 + ~600 unique training sentences, a frozen multilingual encoder + LR is the strongest generalizer per hour of work; kNN gives the memory hook for free; M1 gives tokens for explanations and language-independent robustness to typos. M3 is the most expensive and least certain gain.
- **Rejected:** training the kNN on memory with full weight (drift); M3 as a mandatory member; a 768-d encoder (2× slower, bigger download, unclear gain on short texts).
- **Locked:** P1 (m1, m2lr, m2knn), P2 (weights, M3 decision). **Default: M3 is cut (#4)**: fine-tuning on 42 unique texts is low value, so it is included only if OOF shows the gain and every budget gate passes.
- **Proof:** `tests/unit/test_ensemble.py`: removing a member from config still loads and predicts; weights sum to 1; ablation table in `reports/ablations.json` lists "ensemble − M3".

### 3.7 Arabizi and normalization
- **Decision:** `adapters/preprocess/`: `wrappers.py` strips the known prefix/suffix list from `config/lexicons/wrappers.yaml` (same strings as `scripts/clean_data.py`, plus a case-insensitive `^urgent[:!\s]*` regex and case-insensitive matching of the known prefixes with `,`/`!`/`:` variants, so unseen forms such as `urgent: …` and `URGENT …` without a colon are stripped and flagged; the data audit found `clean_data.py`'s exact-match stripper misses them) and sets `stated_urgency` if an urgency wrapper or marker (`URGENT`, `عاجل`, `!!!`) was present. `normalizer.py` reproduces `clean_data.normalize()` **byte-for-byte** (same diacritics regex, same char map, same punctuation strip); `scripts/clean_data.py` is left untouched except for the P0.3c console-encoding guard on its final print (its output files stay byte-identical), and a test asserts equality on all 432 rows. `langid.py`: Arabic-script ratio → `AR`; Latin with Arabizi signals → `ARABIZI`, where signal = ≥ 2 tokens containing an inner digit from {2,3,5,6,7,8,9} **or** ≥ 1 hit in the dialect lexicon (`config/lexicons/arabizi.yaml`, ~300 entries) **and** 0 hits in an English stop-list guard (prevents "2nd", "3rd", "24/7"). `arabizi.py`: lexicon first (whole-token), then the char map; output `model_text = translit + " | " + original` so the embedding sees both. Arabizi training rows come from augmentation: rule-based reverse transliteration of every AR core + LLM-drafted Arabizi paraphrases, all human-checked.
- **Data facts:** `lang` in the CSVs is script-only; `data/clean/train_val_features.csv` adds `lang_script`, `is_arabizi` (False for all 432 rows) and `stated_urgency`. The fairness slice is `lang_script` plus `is_arabizi` from the package `LangIdentifier`.
- **Rationale:** no Arabizi in official data → it's a robustness/fairness point, not a macro-F1 point; the one thing that can hurt macro-F1 is a false positive on English hidden-test rows, so the detector is conservative and tested on all 432 official rows for zero false positives.
- **Rejected:** a learned Arabizi detector (no data); replacing the original with the transliteration (loses signal when transliteration is wrong); refactoring `clean_data.py` to import the package (risk, no points).
- **Locked:** P1 (P1.1).
- **Proof:** `tests/unit/test_normalizer_parity.py` (432/432 equal to `text_norm`), `test_langid.py` (0 Arabizi detections on official EN rows; ≥ 95 % on the Arabizi augmentation), `test_arabizi.py` golden pairs (`mesh 3arif` → `مش عارف`).

### 3.8 Priority head and the safety override precedence
- **Decision:** `LogisticPriorityHead` = LogisticRegression over `[p_pri_model (3) ‖ evidence flags (10)]`, trained on OOF `p_pri_model` with soft-target weights, `class_weight="balanced"`. Evidence flags are the ten in `FrozenConfig.priority_head.features`, computed from `config/lexicons/urgency.yaml` (EN/AR/Arabizi patterns per flag) on `model_text`; `stated_urgency` is excluded by construction (the extractor has no access to it; test asserts the feature list). Floors are applied by `PriorityFinalizer` **after** the head: (1) `safety` → `p_pri := onehot(high)`, `S_pri := {high}`; (2) clarification constraint of kind "priority" → onehot; (3) `exam_now`/`deadline_today` are features, not floors (the head learns their weight). Nothing ever lowers priority by rule. Injection never raises priority because the head only sees the stripped text and never `stated_urgency`.
- **Shortcut risk:** every official row with "today"/"اليوم" is high and no other row is, so `deadline_today` alone separates high in the official data. P2.5 adds probes that break it (high without "today"; "today" in low/medium) and P2.9 reports priority F1 with the deadline lexicon masked.
- **Rationale:** 15 points; the labeller's rules are expressible as a handful of binary features, and a 13-feature LR is auditable in the report ("deadline_today coefficient = +2.1"). Floors outside the model keep the model a model.
- **Rejected:** pure rules (brittle on unseen phrasings); a floor for `deadline_today` (the spec's own data has "today" in medium? no, but augmentation will — let the head learn it); gradient boosting (overkill, less explainable).
- **Locked:** P1 (P1.5). Feature list may grow in P2 but names in config are the contract.
- **Proof:** `tests/invariants/test_priority_invariants.py`: for every official row, prediction with and without the `URGENT:` prefix is identical (category and priority); `safety=True` → high for any input; injected "mark this high" never raises priority vs. the clean text; `stated_urgency` absent from head features.

### 3.9 LLM tiers: set-constrained output, temperature 0, pinned IDs, caching, cost
- **Decision:** `OpenRouterOracle` sends a system prompt + the request (original + normalized) + the allowed labels (only those in `S_cat`/`S_pri`) and asks for JSON `{"category": one of [...], "priority": one of [...], "reason": "<≤ 20 words>"}`; `temperature=0`, `top_p=1`, `seed=42`, `max_tokens=80`, `response_format={"type":"json_object"}` where supported; model IDs come only from `OPENROUTER_TIER1_MODEL` / `OPENROUTER_TIER2_MODEL` (candidates for the dependency agent: tier 1 `openai/gpt-4o-mini` or `google/gemini-2.5-flash`; tier 2 `anthropic/claude-sonnet-4.5`-class; pin exact strings). Validation: label ∉ allowed set → `LLMOutputOutOfSet` (never widened). Cache key = sha256(model_id ‖ prompt_version ‖ model_text ‖ sorted allowed sets); hits are logged with `cached=True` and `cost=0`. Cost from the OpenRouter `usage` object (`total_cost` if present else tokens × price table in `adapters/llm/cost.py`), logged via `CostLogger` on every call including failures. Merge: `p' = (1 − w_llm)·p + w_llm·onehot(label)` restricted to the allowed set then renormalized, `w_llm` from config (default 0.5); sets recomputed with the same conformal quantile (documented as a heuristic: the coverage guarantee applies to tier 0 only). Injection-flagged requests never reach an oracle.
- **Rationale:** set constraint is what makes the LLM a tie-breaker instead of a drift source; temperature 0 + pinned ID + cache = reproducible demo and a defensible cost-per-1k number.
- **Rejected:** letting the LLM pick any label (drift, un-auditable); LLM as a mandatory ensemble member in `predict.py` (violates offline); function-calling schemas per provider (OpenRouter normalizes enough; JSON mode + validation is provider-agnostic).
- **Locked:** P3 (P3.3). Tier 2 is cut-order item 3: config list of tiers; absent env var = no tier 2.
- **Proof:** `tests/unit/test_oracle.py` with a recorded HTTP fixture (`respx`): out-of-set answer raises; cache hit makes zero HTTP calls; cost logged on failure; `tests/unit/test_llm_merge.py`: merged argmax ∈ allowed set always.

### 3.10 Injection guard and anti-gaming placement
- **Decision:** `InjectionGuard` runs as step [3] on every path. Regex bank (`config/lexicons/injection.yaml`, EN/AR/Arabizi) + `ExemplarSimilarity` over ~50 exemplars embedded with the same encoder (`tau_injection` from config). Offline mode `strip_regex_only`: only regex hits strip (zero false positives on official data is asserted), no embedding bank; online mode `full`. On a hit: strip the matched spans (and the sentence that contains them if the span is ≥ 60 % of it), set flag, disable LLM for this request, log an admin-visible event. `GamingDetector` runs at [9b] after finalization, writes flags/signals only, never touches the label. Both guards are plain classes behind the `Guard` port; the policy consumes flags, not guard objects.
- **Rationale:** the guard must see the text before any LLM and before the models (so "mark this high" is not even a token for M1); gaming needs the final priority so it comes last.
- **Rejected:** an LLM-based injection classifier (would itself be injectable, costs money, offline impossible); penalizing flagged students (responsible-AI line in the spec).
- **Locked:** P3 for full mode; the regex strip mode ships in P1 because `predict.py` needs it. P1 seeds ≥ 10 injection exemplars so the `injection_exemplars` collection exists and `tau_injection` is computable; P3 grows them to ~50 and re-freezes.
- **Proof:** `tests/invariants/test_injection.py`: 0 regex hits on 432 official rows + augmentation; the 10 demo injection strings all flag; priority after injection ≤ priority of the base text; `llm_allowed is False` when flagged. `test_gaming.py`: alias with 5 claimed-urgent/0 high → `priority_gaming_suspected`, label unchanged.

### 3.11 Live memory must not affect the frozen evaluation
- **Decision:** `predict.py`, `train.py` and `evaluate.py` only ever construct `build_offline`, which hard-wires `NullMemoryStore` and `LocalNumpyVectorStore`. The online core is a separate instance holding `PgVectorMemoryStore`. The frozen index (`models/frozen/vN/index/`) is built by `train.py` from the training pool only and is never uploaded to Postgres; memory rows live only in pgvector and enter an artifact only via `--consolidate`, which writes a **new** version and never touches `CURRENT` automatically. See also §3.18 for the vector-store isolation test. `/health` and `--debug` report `artifact_version` + sha so the submission's `predictions.csv` is traceable to `v1`.
- **Rationale:** reproducibility (20 pts) and honesty: a judge re-running `predict.py` must get our numbers regardless of what the demo learned.
- **Rejected:** a `memory=False` flag on a shared container (one forgotten flag = leak); snapshotting memory into the frozen index for the demo (the demo shows learning live anyway).
- **Locked:** P1 (offline container), re-asserted in P3.
- **Proof:** `tests/invariants/test_memory_isolation.py`: build online test container, add 50 memory items that would flip a fixture prediction, then run `BatchPredictUseCase` from `build_offline` on the same text → prediction identical to the pre-memory output; `test_architecture.py` import-graph assertion.

### 3.12 How frozen artifacts ship
- **Decision:** Two tiers of artifacts. **(a) Committed in git** (`models/frozen/v1/`): `config.json`, `MANIFEST.json`, M1 (vectorizers + LR, joblib, ≈ 3–8 MB), M2-LR heads (< 1 MB), priority head, conformal quantiles, kNN index (`embeddings.npy` ≈ 1,200 × 384 × float32 ≈ 2 MB + `items.jsonl`), injection exemplar embeddings. Budget ≤ 25 MB committed, each file < 50 MB (no LFS). **(b) Fetched once** (`models/frozen/v1/encoder/` = `model_int8.onnx` + `tokenizer.json` + `config.json`, and `m3/` if it exists): `python scripts/fetch_models.py` downloads `campuspulse-models-v1.tar.gz` from the **GitHub Release** of this repo (our ONNX export is not on the HF Hub, so the release asset is primary; `--source hf` is a mirror we upload to a developer HF model repo as a backup), extracts into the folder and verifies sha256 against `MANIFEST.json`. `predict.py` with the encoder missing → exit 2 with the exact fetch command printed (no silent degraded mode; a degraded M1-only output would be a different model than the one we report). The Render Docker build runs the same fetch at image build time, so the service is offline-capable for inference at runtime. Total download budget ≤ 200 MB (e5-small int8 ≈ 110–130 MB; the dependency agent confirms exact sizes and CPU timings).
- **Rationale:** GitHub blocks > 100 MB files; LFS bandwidth quotas are a judging-day risk; SPEC §5.5 explicitly allows "a one-time documented download step + checksum". Committing the small heads means a clone alone proves the pipeline, and the fetch is a single command in the README (setup ≤ 3 commands: `pip install -r …`, `python scripts/fetch_models.py`, `python services/ai/predict.py …`).
- **Rejected:** git LFS (quota, judge friction); committing the encoder (even int8 it exceeds the 100 MB file limit); downloading at predict time (not offline); shipping fp32 torch weights (470 MB + torch install ≈ 2 GB of wheels for the judges, and it cannot fit Render Starter).
- **Locked:** P1 for the layout and manifest, plus the first pre-release `models-v1-rc1` (GitHub Release asset + `SHA256SUMS`, verified against `MANIFEST.json`) so CI and the P4 Render build can fetch the encoder; `models-v1-rc2` at the P2 exit; the final `models-v1` in P6.
- **Proof:** `tests/unit/test_manifest.py` (tampered file → `ArtifactChecksumMismatch`); P6 clean-machine script `scripts/clean_machine_check.ps1`/`.sh`: fresh clone → 3 commands → `predictions.csv` **label-identical** (row by row) to the committed `reports/predictions_val_check.csv`. Labels are compared, not bytes, because int8/BLAS kernels can flip near-ties across CPUs (§6.2 flags 6 and 15).

### 3.13 Where `DEMO_EMAIL_ALLOWLIST` is enforced
- **Decision:** One `RecipientPolicy` value object built from `Settings.demo_email_allowlist` (comma-separated, lower-cased, exact match; empty list = reject everything). Enforced in exactly two places, both in the AI service: `AllowlistedNotifier` (wraps every `Notifier`, including in-app for symmetry of logging) and `ActUseCase` before `CalendarProvider.book` (attendees). Rejections are persisted as `outbox.status = "rejected"` with the reason, so the Outbox page shows them. Seed advisor `demo_email`s and demo student inboxes are developer-owned addresses in the allow-list. Next.js never sends mail and never holds the list.
- **Rejected:** enforcement inside the SMTP notifier only (Google invites would bypass it); enforcement in the UI (bypassable).
- **Locked:** P4 (P4.4).
- **Proof:** `tests/unit/test_allowlist.py`: `real.person@gju.edu.jo` → `RecipientNotAllowed`, outbox row rejected, provider never called (FakeNotifier call count 0); booking with a non-allow-listed attendee never reaches `FakeCalendar.book`.

### 3.14 Supabase RLS model
- **Decision:** `profiles(id = auth.uid(), role, office, alias)`; SQL helper functions `cp_role()`, `cp_office()`, `cp_alias()` (security definer, read `profiles`). Policies: `requests/predictions/clarifications/tickets/outbox`: student `SELECT` where `alias = cp_alias()`; staff `SELECT` where `office = cp_office()` (tickets/incidents) or via join for predictions; admin `SELECT` all. `review_queue`, `student_signals`, `llm_calls`, `redteam_runs`, `events`, `memory_examples`: staff/admin `SELECT` only (signals admin only). Vector tables (§3.18): `request_embeddings` has **no policy for any client role** (service role only); `memory_examples` staff/admin `SELECT` (embedding column excluded via the view `memory_examples_v`); `faq` `SELECT` for all authenticated (embedding excluded via `faq_v`); the RPC `match_vectors` has `REVOKE EXECUTE FROM anon, authenticated`. **No `INSERT/UPDATE/DELETE` policy for any authenticated role on any table**: all writes come from FastAPI with the service-role key. Realtime: enable publication on `predictions, tickets, incidents, outbox, notifications`; RLS applies to Realtime (Supabase enforces it for `postgres_changes`). `buildings`, `faq`, `advisors` are readable by all authenticated users. Students never see `flags` containing `urgency_unsupported`/`priority_gaming_suspected`: a view `predictions_student_v` strips them and student policies target the view.
- **Rationale:** write-through-FastAPI keeps one place for validation and audit; a read-only RLS surface is small enough to test in a migration test.
- **Rejected:** client-side writes with RLS (double the policy surface); anonymous auth (role mapping still needs profiles; demo accounts are simpler to narrate).
- **Locked:** P4 (P4.1).
- **Proof:** `supabase/tests/rls.sql` (pgTAP-free plain SQL run by `scripts/test_rls.py` against the local Supabase CLI stack): student A cannot select student B's request; staff of IT cannot see Finance tickets; `INSERT` as authenticated fails.

### 3.15 Deployment topology (user decision 2026-10-31: Netlify + Supabase + Render; HF Spaces dropped)
- **Decision:** Netlify (Next.js via the official Netlify Next runtime; env: public Supabase vars + `AI_SERVICE_URL`, `AI_SERVICE_TOKEN`) → **Render Web Service, Docker runtime, plan `starter` (~$7/mo, approved)** defined in the repo-root `render.yaml` (`dockerfilePath: ./services/ai/Dockerfile`, `dockerContext: .`, `healthCheckPath: /health`, `autoDeployTrigger: commit` from `main`, env vars as Render secrets, `PORT` honoured by uvicorn) → Supabase (Postgres + pgvector + Auth + Realtime; migrations via `supabase db push` from local). Models are fetched at Docker build time (`scripts/fetch_models.py` in the Dockerfile) so the running container never needs the network for inference. The SLA scanner runs inside the FastAPI process (one uvicorn worker, `--workers 1`, so the loop runs once). Linear webhook URL = the Render URL. A `scripts/keep_warm.ps1` pings `/health` every 10 min during demo/judging windows (cheap insurance even on Starter). The UI shows a "AI service waking up" banner when `/health` is slow or failing. Nothing else is hosted.
- **Rationale:** HF Docker Spaces reportedly require PRO now; Render Starter removes spin-down and is the cheapest always-on Docker host; one worker keeps memory inside the budget of §3.17.
- **Rejected:** Render free tier (spin-down + 512 MB with no option to pay for warmth); Fly.io (credit card, more config); running the API inside Netlify functions (no Python runtime for onnxruntime at that size); pg_cron (works, but one more thing to debug).
- **Locked:** P0 (skeleton deploy of an empty app and a `/health`-only API on Render), P6 (final).
- **Proof:** P0 exit: `curl https://<render-service>/health` → `{"status":"ok","artifact":null,"rss_mb":<n>}`; Netlify preview renders `/`. P6: the three video moments performed on the hosted URLs; `/health` reports `rss_mb ≤ 400` after 20 triage calls.

### 3.17 Inference memory budget on Render (explicit, with fallback)
- **Facts to verify (Appendix D):** Render Starter is believed to be ~512 MB RAM and 0.5 CPU; the free tier the same plus spin-down. Treat 512 MB as the hard ceiling until confirmed.
- **Decision:** the Render process runs **the full tier-0 pipeline** (normalizer, guards incl. exemplar similarity, M1, M2-LR, M2-kNN over the frozen local index, priority head, conformal, explainer, policy/clarify, pgvector client, LLM client) with these constraints: encoder = ONNX int8 via `onnxruntime` (no torch in `requirements-api.txt`); single uvicorn worker; `intra_op_num_threads=1` on Render (Settings); `max_tokens=256`; explainer occlusions capped at 20 and computed lazily (only when the response is for the UI, never in `/batch`); the frozen index held as float32 numpy (≈ 2 MB); FAQ/memory/request vectors in pgvector, not in process. **Budget: steady-state RSS ≤ 400 MB, measured by `/health` (`psutil`) and by `scripts/measure_rss.py` locally with 100 sequential `/triage` calls; p95 latency ≤ 1.5 s per `/triage` on 0.5 CPU.** Expected: python + fastapi + numpy + sklearn ≈ 120 MB, onnxruntime + int8 e5-small ≈ 150–200 MB, tokenizer + index + heads ≈ 30 MB → ≈ 300–350 MB.
- **Fallbacks, in order, each a config/env change only:** (1) `OnnxEncoder` lazy-loads on first request and `/health` reports `encoder_loaded` (buys startup headroom only); (2) swap the encoder for a smaller int8 model (`paraphrase-multilingual-MiniLM-L12-v2` int8 is the same size class, so the real "smaller" option is `sentence-transformers/distiluse-base-multilingual-cased-v2` or `Alibaba-NLP/gte-multilingual-base`-class — the dependency agent must list one ≤ 80 MB int8 with Arabic support; this changes `encoder.*` in `config.json`, `vector(384)` dimension in the migration, and requires a retrain — do it in P2, not later); (3) Render **Standard** (2 GB, ~$25/mo) — needs user approval, zero code change; (4) last resort: `ENSEMBLE_MEMBERS_OVERRIDE=m1,m2knn` in the API only (no live embedding of new texts: memory/FAQ/incident features disabled; the demo loses moments 2 and 3) — not acceptable for the video, listed only so the plan names it.
- **Note on fallback (2):** research found no Arabic-capable int8 encoder ≤ 80 MB (distiluse is 135 M parameters; `gte-multilingual-base` needs `trust_remote_code`, which is rejected). The practical ladder is therefore (1) lazy load → a lower occlusion cap → (3) Render Standard with user approval.
- **Rejected:** torch fp32 on Render (≈ 900 MB RSS, impossible); Supabase Edge `gte-small` embeddings (English-only, a different vector space from the frozen index, and the kNN/memory/OOD scores must share one encoder); embedding on Netlify functions (same reasons).
- **Locked:** P1 for the ONNX export + `OnnxEncoder` (needed by `predict.py` anyway); P4 for the Render sizing test; fallback (2) only in P2.
- **Proof:** `tests/unit/test_onnx_encoder.py`: cosine(ONNX int8, torch fp32 reference) ≥ 0.98 on 50 fixture sentences (run only where torch is installed, `@pytest.mark.train`); OOF macro-F1 with int8 within 0.01 of fp32 recorded in `reports/encoder_export.json`; `scripts/measure_rss.py` → `rss_mb_p95 ≤ 400` recorded in PLAN.md at P4 exit.

### 3.18 Vector store: pgvector in Supabase (user decision), with offline isolation
- **What is embedded (all with the same frozen encoder, all `vector(384)` = `config.encoder.dim`):**
  | collection | table | row written by | used for |
  | --- | --- | --- | --- |
  | `requests` | `request_embeddings(request_id uuid pk references requests, embedding vector(384), lang text, category text, priority text, building_id text, room text, created_at timestamptz)` | `TriageUseCase` after classify ([12b]) | incident clustering (window + building + category filters), "similar recent requests" on the staff dashboard |
  | `memory` | `memory_examples(id uuid pk, text_norm text, lang text, embedding vector(384), category text, priority text, author_id uuid, created_at timestamptz, active bool default true)` | `FeedbackUseCase` | live learning (kNN neighbours, source="memory"), Model lab memory stats |
  | `faq` | `faq(id uuid pk, lang text, question text, answer text, source_url text, is_demo bool, embedding vector(384))` | `scripts/seed_faq.py` (embeds seed questions on the dev machine with the same ONNX encoder; also re-runnable from Render via `POST /v1/admin/reindex`) | FAQ answer-first retrieval |
  Not stored in Postgres: the frozen training index, injection/safety exemplars (frozen artifacts in `models/frozen/vN/index/`), LLM prompts.
- **Index type:** **HNSW** (`USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)`) on all three tables. Rationale: HNSW needs no training data to build (IVFFlat with `lists` on an empty/tiny table gives poor recall until re-indexed), and at our scale (< 10 k rows) build cost is irrelevant. `SET hnsw.ef_search = 40` inside the RPC.
- **Search path:** one RPC `match_vectors(p_collection text, p_query vector(384), p_k int, p_min_sim float, p_filters jsonb) returns table(id uuid, text text, lang text, sim float, meta jsonb, embedding vector(384))` — `embedding` is null unless `p_filters->>'with_embedding' = 'true'` (`security definer`, `revoke execute from anon, authenticated`), dispatching to the three tables with `1 - (embedding <=> p_query)` as `sim` and filters `building_id`, `category`, `since`, `active`, `lang`. A second RPC `vector_dim() returns int` for the startup check. `PgVectorStore` (`adapters/vectors/pgvector.py`) calls them via `supabase-py` `rpc()`; `upsert` uses the table API with the service-role key. The incident centroid is computed in Python from the ≤ 50 returned rows.
- **Where embedding happens:** on Render, inside the same `OnnxEncoder` instance that feeds M2. The embedding computed during classify is reused for `request_embeddings` and for `memory_examples` (no second forward pass). Supabase's built-in Edge `gte-small` embeddings are **rejected**: English-only, 384-d but a different space, and every consumer (kNN, OOD, memory, incidents, FAQ) must live in the frozen encoder's space.
- **Offline isolation (hard constraint):** `predict.py`, `train.py`, `evaluate.py` and all `pytest -m offline` tests use `LocalNumpyVectorStore` loaded from frozen artifacts; `PgVectorStore` is importable only from `composition/online.py`. The `VectorStore` port is identical for both so `VectorFAQRetriever`, `PgVectorMemoryStore` and `WindowedCentroidDetector` are tested against the local adapter with fixtures, and once (manually, P4) against a real Supabase project. The `memory` collection never exists in the local store except inside tests that create it explicitly.
- **RLS:** as in §3.14 — `request_embeddings` service-only; `memory_examples_v` / `faq_v` views hide embedding columns from clients; RPC execution revoked from client roles.
- **Rejected:** storing embeddings as `jsonb`/`float8[]` relational rows (user wants a vector store; no ANN); a separate vector DB (one more account); per-table RPCs (three functions to keep in sync — one dispatcher is enough).
- **Locked:** P1 (`VectorStore` port + `LocalNumpyVectorStore`), P4 (migration `000N_vectors.sql`, `PgVectorStore`, RPC, seed).
- **Proof:** `tests/contracts/test_vector_store_contract.py` parametrized over `LocalNumpyVectorStore` and (when `SUPABASE_TEST_URL` is set) `PgVectorStore`: upsert → search returns the item with sim ≈ 1.0; filters work; `set_active(False)` hides it; dim mismatch raises. `tests/invariants/test_vector_isolation.py`: (a) `import campuspulse_ai.composition.offline` never imports `supabase` or `adapters.vectors.pgvector`; (b) `build_offline(...).core.vectors` is a `LocalNumpyVectorStore` whose collections are exactly `{"train","injection_exemplars","safety_exemplars"}`; (c) with the online test container, add 50 memory items that flip a fixture prediction, then run `BatchPredictUseCase` from `build_offline` on the same text → prediction identical to the pre-memory output; (d) `predict.py` runs with `SUPABASE_URL` set to an unreachable host and succeeds (no connection attempted; `socket` monkeypatched to raise).

### 3.16 Python version pin
- **Decision:** `requires-python = ">=3.11,<3.14"`. The **reference environment is Linux, Python 3.11** (Dockerfile `python:3.11-slim`, the P6 clean-machine Linux check, the CI `artifacts` job). The developer uses 3.13.1 daily, and the CI matrix runs 3.11 + 3.13 (Linux) and 3.13 (Windows).
  - One exact pin per package, with no environment markers.
  - numpy is pinned to **2.4.6** and scipy to **1.17.1**, the newest lines with cp311, cp312 and cp313 wheels. numpy 2.5.x and scipy 1.18.x need Python ≥ 3.12 and are rejected.
  - The full pin set is in `docs/plan/appendix_A_dependencies.md`.
- **Rationale:** the judges' "common computer" is unknown. 3.11 is the safest floor, and refusing 3.13 would block the developer.
- **Rejected:** raising the floor to 3.12 (judge risk); pinning to 3.13 only; environment-marker pins (two numpy versions = two numerical paths); `uv` as a hard requirement (optional convenience only; the `pip` path is documented).
- **Locked:** P0.
- **Proof:** CI job matrix green on all legs; `scripts/clean_machine_check.sh` uses `python3.11 -m venv`.

---

## 4. Phase contracts

### 4.0 Time budget (binding guidance, 10 days incl. today)
P0 ½ d · P1 2 d · P2 2 d · P3 1½ d · P4 1½ d · P5 1½ d · P6 1 d. Slack: 0. The planned hours against this budget are in [PLAN.md › Phase table](PLAN.md#phase-table). Every task in the plan carries an hour estimate and a `cut` flag; when a phase overruns, cut-flagged tasks go first (§4.8), never the exit criteria.

### 4.1 P0 Foundations
Hands to P1: repo skeleton per §1.2; `pyproject.toml` with `campuspulse_ai` installable (`pip install -e services/ai`); `domain/labels.py`, `values.py`, `errors.py`, `ports.py` (all Protocols from §1.4, bodies `...`); `config/settings.py` + `.env.example` listing every var of SPEC §11 plus `SLA_SCAN_MINUTES`, `ARTIFACT_DIR`; `tests/test_architecture.py` (import-graph rules); CI (`.github/workflows/ci.yml`: ruff, pytest on 3.11 + 3.13, `npm run typecheck`, `npm run build`); `apps/web` scaffold with `/` placeholder and `/dev/ui` route; Supabase project + migration `0001_init.sql` (profiles, buildings, requests, predictions only; `create extension vector` already here); empty FastAPI with `/health` (returns `rss_mb`); Dockerfile + `render.yaml`; Netlify site + Render Starter service deployed. `data/our_test/` and `data/robustness/` folders with README stating "never trained on". Exit (SPEC): CI green; `python scripts/test_clean.py` passes; empty app deploys. **Lead decisions:** `render.yaml` and the Docker build context sit at the repo root; `.env.example` carries `GMAIL_SMTP_USER`, `GMAIL_APP_PASSWORD`, `SMTP_HOST`, `SMTP_PORT` (no mail SDK); CI also runs mypy and eslint; `domain/errors.py` includes `NotificationError`; `CoreResult.flags` and `VectorHit.embedding` exist from P0. **Data audit:** P0.3a–P0.3e add `data/clean/cv_folds.csv` (`scripts/make_folds.py`), `data/clean/train_val_features.csv` (`scripts/add_derived_columns.py`), the cp1252 print guard in `clean_data.py`, `scripts/test_data_audit.py` and `scripts/check_leakage.py --official`.

### 4.2 P1 Scored core
Hands to P2: `adapters/preprocess/*`, `guards/injection.py (strip_regex_only)`, `guards/safety.py` (danger + distress lexicons), `guards/gibberish.py`, `frameworks/cli/export_encoder.py` (torch → ONNX int8, writes `encoder/` + parity report), `adapters/vectors/local_numpy.py` (`VectorStore` port impl), `models/{tfidf_lr,encoder (OnnxEncoder),embed_lr,knn,ensemble,priority_head,evidence,ood,soft_targets}.py`, `uncertainty/conformal.py` (class present; α quantile placeholder tuned in P2), `application/services/{triage_core,priority_finalizer}.py`, `use_cases/batch_predict.py`, `composition/offline.py`, `frameworks/cli/{train,predict}.py`, `artifacts/io.py`, `models/frozen/v1/` (committed small artifacts + fetch script), `scripts/fetch_models.py`, `data/our_test/our_test.csv` (authored first: P1.0, ≥ 60 rows, columns `request_id,text,lang,category,priority,author_method,notes`), `data/augmented/` schema (`request_id,text,lang,source,source_scenario_id,cv_group,needs_human_check,author_method,category,priority`) with the rule-based Arabizi rows only (LLM paraphrases are P2). Exit (SPEC): `predict.py` on validation produces a valid CSV offline; CV macro-F1 reported for category and priority (in `reports/cv_p1.json`); tests pass. Plus the invariants: URGENT-invariance, memory isolation, offline import graph. **Lead decisions:** also `adapters/training/{pool,cv,tuning}.py`, `adapters/memory/null.py`, `adapters/llm/null.py`, `adapters/clock.py`, the `tiny_model_dir` session fixture, `config/hand_tuned.yaml`, the lexicon snapshot in `models/frozen/v1/lexicons/`, and the pre-release `models-v1-rc1` (GitHub Release asset + `SHA256SUMS`).

### 4.3 P2 Data + rigor
Hands to P3: `data/augmented/{paraphrases.csv,new_scenarios.csv,arabizi.csv}` human-checked (`needs_human_check=False` rows only are used by `train.py`); `data/robustness/probes.csv` (≥ 40 rows, styles tagged); `scripts/draft_augmentation.py` (OpenRouter, disclosed) and `scripts/check_leakage.py`; `train.py` stages B/C complete (weights, conformal quantiles, `tau_ood`, `tau_injection`, `human_review_maxprob`); M3 decision recorded in PLAN.md; `evaluate.py` producing `reports/{metrics.json,benchmark.md,coverage.json,fairness.json,ablations.json,confusions/*.json}` from one command; notebooks 01–05 that only read `reports/`. Exit (SPEC): benchmark table, coverage, fairness and ablations generated from one command (`python services/ai/evaluate.py --all`). Benchmark rows: M1, M2-LR, M2-kNN, (M3), ensemble, ensemble+router (`--use-llm`, only if a key is present; otherwise "n/a" row), LLM zero-shot (same `--use-llm` cache; optional). **Lead decisions:** also `scripts/run_notebooks.py` (moved here from P6), `adapters/training/metrics.py`, `reports/predictions_val_check.csv` (same-machine regression snapshot) and `models-v1-rc2`. The ASK rate in `reports/coverage.json` is a **proxy** (share of rows with a size-2 set); P3 recomputes it with the real `DecisionPolicy`.

### 4.4 P3 Intelligence layer
Hands to P4: `domain/policy.py` (DecisionPolicy), `adapters/clarify/{bank,info_gain}.py` + `config/clarify_questions.yaml` (≥ 6 questions from SPEC §5.1[8]), `adapters/llm/*` (OpenRouterOracle, SqliteCache, cost), `application/services/llm_merge.py`, `adapters/explain/*`, `guards/injection.py full mode` + `config/lexicons/injection.yaml` + exemplar embeddings artifact, `guards/gaming.py`, `adapters/memory/{null,inmemory,pgvector_memory}.py` (the pgvector impl lands in P4 with the migration; the port + in-memory impl are P3), `use_cases/{triage,clarify,feedback}.py` runnable against `build_test()`, `frameworks/fastapi_app.py` with `/triage`, `/triage/{id}/clarify`, `/feedback`, `/explain/{id}/counterfactual`, `/health` returning the full SPEC §7 response contract (DTOs in `application/dto.py`; OpenAPI exported to `apps/web/src/lib/ai/openapi.json`). Exit (SPEC): `/triage` returns the full contract; clarification and memory demos pass as API tests (`tests/e2e/test_api_clarify.py`, `test_api_memory.py` using the test container). **Lead decisions:** `adapters/memory/null.py` and `adapters/llm/null.py` already exist (P1); P3 grows the injection exemplars to ~50 and re-freezes; P3 recomputes the true ASK rate.

### 4.5 P4 Product backend
Hands to P5: migrations `0002…000N` (full SPEC §8 schema, RLS, Realtime publication, `notifications` table added, `000N_vectors.sql` with `request_embeddings`, HNSW indexes, `match_vectors`/`vector_dim` RPCs, `memory_examples_v`/`faq_v` views), `supabase/seed/*.sql` (buildings, advisors with `demo_email`s from the allow-list, FAQ with `[demo]` entries from `gju_public_policies.md`, demo profiles, advisor_slots) + `scripts/seed_faq.py` (embeds FAQ with the frozen encoder), `adapters/vectors/pgvector.py`, `adapters/memory/pgvector_memory.py`, `adapters/store/supabase_store.py`, `scripts/measure_rss.py` + Render sizing result (§3.17) recorded in PLAN.md, `adapters/integrations/{supabase_sink,linear}.py` + `RetryingSink`, `adapters/notify/{outbox,gmail_smtp,allowlist,inapp}.py`, `adapters/calendar/slots_table.py` (+ `google.py` stretch), `adapters/faq/retriever.py`, `adapters/pulse/incident_detector.py`, `adapters/redteam/{perturbation,scorer}.py`, `use_cases/{act,resolve_incident,sync_ticket,escalate_sla,run_redteam}.py`, remaining routes (`/batch`, `/redteam/run`, `/incidents/{id}/resolve`, `/integrations/linear/webhook`, `/metrics`, `/tickets/{id}/status`), `frameworks/auth.py` (service token + role claims), `scripts/simulate_pulse.py`, `docs/integrations.md`. Exit (SPEC): request → ticket → Linear issue → status sync → notification works end to end (recorded as `tests/e2e/test_lifecycle.py` with fakes + one manual run against real Linear logged in PLAN.md); the simulator creates an incident.

### 4.6 P5 Frontend
Hands to P6: design system (`tokens.css`, `ui/*`, `/dev/ui`), data layer (§1.7), pages `/login`, `/`, `/staff`, `/pulse`, `/outbox`, `/lab`, Web Speech mic (Chrome only, graceful absence), Arabizi hint, clarification chips, result card with sets/evidence/counterfactual click, review queue with the memory toast, incidents panel, SVG map with dots + pulsing rings + event feed (timeline scrubber = cut-flagged), Model lab reading `reports/*.json` via `/metrics` + sandbox + red-team runner, EN/AR + RTL. Exit (SPEC): all three video moments performed live in the UI (scripted in `docs/report/demo_script.md`).

### 4.7 P6 Ship
Hands to the submission: final `train.py` run → `models/frozen/v1` (CURRENT), GitHub Release asset `campuspulse-models-v1.tar.gz` + checksums (+ HF mirror), `predictions.csv` for the official validation file as a smoke sample (the hidden test is run by the judges or by us on delivery with the same command), `scripts/clean_machine_check.{sh,ps1}` passing on a fresh clone (Linux 3.11 container + Windows 3.13, `pip install -r services/ai/requirements.txt` only — no torch), Render service redeployed from the tagged commit and warmed, README (setup ≤ 3 commands, architecture diagram, Disclosures), `docs/report/report.pdf` (2 pages, SPEC §14), video ≤ 3 min, submission email draft. Exit (SPEC): fresh clone → documented commands → identical predictions; video and report done. **Lead decisions:** the fresh-clone check compares labels, not bytes; the final release is `models-v1` (pre-releases `models-v1-rcN` exist from P1).

### 4.8 Cut order (SPEC §12) and the interface that makes each cut a non-edit
| # | Cut | Mechanism (no code change) |
| --- | --- | --- |
| 0 | WhatsApp urgent channel (Stretch S1, user 2026-10-31) | No `WHATSAPP_*` env → `RoutingNotifier`/`WhatsAppCloudNotifier` are not constructed in `build_online`. |
| 1 | Voice (Whisper upload fallback) | `input_mode="voice"` only via Web Speech in the client; the upload route is never written. Keep Web Speech (see §6 flag 7). |
| 2 | Extra sinks beyond Linear | `config/integrations.yaml` `enabled: [supabase, linear]`; `WebhookSink` class never wired in `build_online`. |
| 3 | Tier 2 | `OPENROUTER_TIER2_MODEL` unset → `tiers = [tier1]`. |
| 4 | M3 | `"m3"` absent from `config.json ensemble.members`; `TransformerFT` never loaded. |
| 5 | Google Calendar | `GOOGLE_SERVICE_ACCOUNT_JSON` unset → `FallbackCalendar([SlotsTableCalendar])`. Default from day one. |
| 6 | Pulse map visuals | `IncidentDetector` + `/incidents` stay; `/pulse` page renders a list instead of the SVG map (component swap). |
| 7 | Red-team LLM generator | `RedTeamGenerator` = `PerturbationGenerator`; `use_llm_generator` flag ignored when `LLMRedTeamGenerator` isn't wired. |
Additional cut-flagged items (mine, in order): timeline scrubber; per-building subscriptions (broadcast to reporters only); `train.py --consolidate`; `cases` table (keep the booking in `outbox` + `tickets` only); dark mode; `/batch` upload UI (keep the API route).

---

## 5. Shared conventions

- **Task ID:** `P<phase>.<n>` (e.g. `P1.3`), sub-steps `P1.3a`. Numbering is by dependency order inside the phase. `P1.0` is reserved for the own-test-set authoring task.
- **Paths:** always relative to `campuspulse/`, forward slashes, exactly as in §1.2. New files must appear in §1.2's tree or the task must add them to a "Files added" line.
- **Interface names:** exactly as in §1.4 (`TicketSink`, `LabelOracle`, `ConformalPredictor`, `VectorStore` …). Concrete class names as given (`LACConformal`, `OpenRouterOracle`, `SlotsTableCalendar`, `OnnxEncoder`, `LocalNumpyVectorStore`, `PgVectorStore` …). Vector collection names exactly: `train, injection_exemplars, safety_exemplars, requests, memory, faq`. Member keys `m1, m2lr, m2knn, m3`. Flag strings exactly: `injection_attempt, urgency_unsupported, safety, needs_review, distress, gibberish, out_of_scope, empty_set, truncated, llm_out_of_set, staff_confirmed, priority_gaming_suspected, explanation_failed` plus the debug-only `empty_input`.
- **Acceptance-test style:** every task ends with ≥ 1 line of the form
  `` `<command run from campuspulse/>` → `<expected stdout substring or file assertion>` ``
  e.g. `` `pytest services/ai/tests/unit/test_conformal.py -q` → `4 passed` ``, `` `python services/ai/predict.py --input data/clean/val_clean.csv --output /tmp/p.csv` → `wrote 62 rows` and file header `request_id,category,priority` ``.
- **Test placement:** `services/ai/tests/{unit,contracts,invariants,e2e}/test_<module>.py`; web: `apps/web/src/**/__tests__/*.test.tsx` (vitest) + `npm run typecheck`.
- **Task template (mandatory fields, this order):**
  ```
  ### P1.3 — <imperative title>
  - Depends on: P1.1, P1.2
  - Est: 3 h · Cut: no | yes (cut-order #4)
  - Files: services/ai/campuspulse_ai/adapters/models/embed_lr.py · services/ai/tests/unit/test_embed_lr.py
  - Interfaces: implements `ProbabilisticClassifier`; uses `SentenceEncoder`
  - Config keys: ensemble.members, encoder.*
  - Steps: 1. … 2. … (≤ 7, each a concrete action)
  - Acceptance: `<command>` → `<expected>` (one per bullet)
  - Hands off: <artifact/interface the next task consumes>
  ```
- **Decisions:** a task may not introduce a threshold, model, or library not named in this brief or the appendices; if it must, it adds a "Needs decision" line and a default, and PLAN.md's decisions log gets a row.

---

## 6. Open questions, contradictions, and blunt flags

> Most items below were resolved by the lead decisions of 2026-10-31 ([PLAN.md › Lead decisions](PLAN.md#lead-decisions)) or are open questions for the user ([PLAN.md › Open questions](PLAN.md#open-questions-for-the-user)). They are kept here for their rationale.

### 6.1 Ambiguities / contradictions in the SPEC (with my default)
1. **M4.** §4 and §14 say "M1–M4"; §5.1 defines M1–M3. Default: M4 = the LLM zero-shot benchmark row (not a tier-0 member). Writers use that name only in the benchmark table.
2. **Own test set "written before any model results" vs. phase order** (P2 after P1 reports CV). Default: author it as `P1.0`, the first task after P0, before `train.py` exists. Hand-written by the developer (not LLM), ≥ 60 rows (SPEC says ~120; see flag 3).
3. **Conformal "APS or LAC".** Default LAC (§3.5).
4. **Policy edge cases.** Empty conformal set → argmax singleton + `empty_set`. `|S_cat| = 2` after the clarification budget with LLM disabled → HUMAN_REVIEW with best guess. Gibberish → OUT_OF_SCOPE before the OOD rule. Batch mode never applies the policy.
5. **Tier merge vs. "must return a label inside the set".** Both: the oracle is constrained to the set, and the answer is merged as a weighted one-hot (§3.9). Coverage guarantee is stated for tier 0 only.
6. **`/tickets/{id}/status` is missing from §7** but §5.2 needs dashboard status changes. Default: add it (P4).
7. **`notifications` table is missing from §8** but in-app notifications are required. Default: add `notifications(id, alias, kind, payload, read_at, created_at)` (P4).
8. **Priority conformal coverage 0.90 with 3 classes** produces size-2 sets for many medium/high rows → the policy would ASK a lot. Default: keep α = 0.10 but let `evaluate.py` report the ASK rate on the own test set; if > 35 %, raise `alpha_priority` to 0.15 in P2 (config only) and record it.
9. **`stated_urgency` and the `URGENT:` wrapper.** The cleaned data strips `URGENT:` as a wrapper, so `stated_urgency` is derived from the wrapper list + markers; it is a gaming signal only (§3.8).
10. **Validation set as holdout?** No. It's 6 scenarios, 5 translation-leaked; it is training data under the frozen group folds. The hidden test is the external holdout; `data/our_test/` is ours.
11. **`cases` entity** is thin; keep the table but only the booking use case writes it (cut-flagged).
12. **`make_predictions.sh`** on a Windows judge machine. Default: `scripts/make_predictions.py` is canonical; the `.sh` is a one-line wrapper kept for the spec.
13. **Whisper fallback** needs a disclosed paid API and an upload route. Default: cut (cut-order #1 is interpreted as this; Web Speech stays).
14. **pg_cron vs. background job.** Background job (§3.15).
15. **Encoder choice** (e5-small vs. MiniLM). Default e5-small pending the dependency agent's int8 size/timing numbers; the `SentenceEncoder` port makes it a config change, but the pgvector dimension is baked into the migration, so the choice must be final by the end of P2.
17. **Render limits are unverified** (512 MB / 0.5 CPU assumed for Starter). Appendix D must confirm from Render's pricing page and record the numbers; §3.17's fallbacks apply if they are worse.
18. **Vector dimension lock-in.** `vector(384)` is tied to the encoder; any encoder swap after P4 means a new migration and re-embedding `faq`/`memory`/`requests`. Acceptable because the data is tiny, but the plan must put the encoder decision before the vectors migration.
16. **Team size.** CHALLENGE_RULES says teams of 2–3 enrolled students; this is a solo entry. §15 says "team-size question resolved with the organizer". Not an engineering question, but it gates everything (flag 1 below).

### 6.2 Blunt flags (what is wrong, risky or overbuilt vs. the §2 rubric and 10 days)
1. **Eligibility risk beats every technical risk.** Solo vs. "2–3 students" must be confirmed with the organizer before the 3 Nov track lock. Send the email today.
2. **The product layer is ~3× the scored core.** Rubric: 50 pts hidden macro-F1, 20 reproducibility, 15 robustness, 10 explanation, 5 originality. P4+P5 as written are 18 tables, 10 endpoints, 5 pages, 4 external services, Realtime, RLS, i18n/RTL, a map, voice — for 20 + 5 points that are also earned by a much smaller app. Budgeted at 3 days total; the plan must mark ≥ 40 % of P4/P5 tasks `cut: yes`.
3. **Augmentation + own test set + probes = ~400 hand-checked sentences in Arabic dialect, English and Arabizi**, by one person, in two days, while building the models. Cut to: ~3 paraphrases per scenario (≈ 130), ~60 new scenarios (balanced over 18 label cells × 3 forms as far as possible), own test ≥ 60, probes ≥ 40. Quality over count; the report says so.
4. **M3 is probably not worth a day.** With < 1,000 unique sentences a frozen e5 + LR usually matches a CPU fine-tune. Keep the time box (§3.6) and expect to cut.
5. **Conformal guarantees are weak with 30 groups.** State it; don't oversell. Report coverage on the own test set with counts; that honesty earns the explanation points more than a false ±0.01 claim.
6. **"Deterministic, identical predictions on a fresh clone"** is not fully achievable across CPUs for encoder float math (1e-6 drifts can flip a near-tie argmax). Mitigation: store OOF/val probabilities with `--debug`, compare labels (not probs) in the clean-machine check, and state the caveat. Also run the judge-facing check on Linux 3.11 *and* Windows 3.13.
7. **SPEC's cut order puts voice first; I disagree.** Web Speech is ~2 h and opens video moment 1. Cut Whisper, keep Web Speech. (Recommendation; the plan follows the spec unless the user agrees.)
8. **Google Calendar** needs a service account with calendar sharing and ≥ 2 h of setup/debug for one screenshot. Default to `advisor_slots` from the start; Google is a P4 stretch only if P4 finishes early.
9. **Clean-architecture tax.** The port list in §1.4 is already the minimum; the writers must not add abstract layers (no `UnitOfWork`, no per-table repositories, no event bus, no DI library). One file per adapter, one fake per port in `tests/fixtures/fakes.py`.
10. **Notebooks 01–05 are required by the checklist but are pure cost.** Make them thin loaders of `reports/*.json` (≤ 30 cells total), executed by `scripts/run_notebooks.py` in P6 so they are never stale.
11. **The LLM tiers cost real money during the red team and augmentation drafting.** Cap: `Settings.llm_daily_budget_usd` (default 5) checked by `CostLogger.totals()` before each call → `LLMUnavailable` when exceeded.
12. **Render memory is the single biggest deployment risk.** The ONNX-int8 decision (§3.17) is what makes a 512 MB box feasible; measure RSS in P1 locally (not P4) so an encoder swap can still happen in P2. If the judges' machine is also small, int8 helps there too. Keep the service warm before recording and judging.
15. **int8 quantization and determinism.** Dynamic-int8 kernels differ across CPU generations (AVX2 vs VNNI), as do fp32 BLAS paths; label flips at near-ties are possible on a different machine. Mitigation as in flag 6: compare labels, store `--debug` probabilities, and state it in the README. Do not chase bit-exactness.
13. **`predict.py` output for empty/gibberish rows** must still be a valid label (the hidden test could contain a weird row). Already in §2.5; writers must not "helpfully" emit `out_of_scope` there.
14. **`DEMO_EMAIL_ALLOWLIST` empty in production = everything rejected** (safe default). Don't invert it.

Recommended cut sequence if behind schedule at the end of P3 (first to go): Google Calendar → Tier 2 → M3 → WebhookSink → LLM red-team generator → consolidation → timeline scrubber/dark mode → SVG map to list → voice → `/outbox` page (keep the API) → `/lab` sandbox (keep the benchmark table + red-team scorecard).
