# P0 — Foundations

> **Status:** DRAFT — awaiting user approval. **Budget:** ½ d (ARCHITECTURE §4.0) · **Calendar:** Sat 31 Oct (pm) · **Planned (not cut-flagged):** 10 h (incl. 2.5 h of data-audit tasks P0.3a–P0.3e) · **Cut-flagged:** 0 h.
>
> Conventions: [PLAN.md › Conventions](../PLAN.md#conventions). `§n` refers to [ARCHITECTURE.md](../ARCHITECTURE.md); `LD-n` and `OQ-n` link to the lead decisions and open questions in [PLAN.md](../PLAN.md). Tick `- [ ] Done` under each task as you finish it, and tick this phase's decision log at the bottom.

**Goal:** a repo where every later task has a home and a test harness, CI is green, and an empty web app and an empty AI service are live on Netlify and Render. Supabase already has the `vector` extension.

**Phase contract (§4.1):**
- **Inputs:** the flattened project tree (formerly `data/campuspulse/`, now the git root) (`data/raw`, `data/clean`, `scripts/clean_data.py`, `scripts/test_clean.py`, `docs/`).
- **Hands to P1:**
  - repo skeleton per §1.2, with `campuspulse_ai` installable via `pip install -e services/ai`
  - `domain/{labels,values,errors,ports,entities}.py`
  - `config/settings.py` + `.env.example`
  - `tests/test_architecture.py`
  - CI: ruff, mypy, pytest on 3.11 + 3.13, and web typecheck, lint and build
  - `apps/web` with `/` and `/dev/ui`
  - Supabase migration `0001_init.sql` with `vector`
  - FastAPI `/health`, a Dockerfile and `render.yaml`
  - the Netlify site and the Render Starter service, both deployed
  - `data/our_test/` and `data/robustness/` READMEs that say "never trained on"
  - **from the data audit:** `data/clean/cv_folds.csv` (frozen category-stratified folds), `data/clean/train_val_features.csv` (`lang_script`, `is_arabizi`, `stated_urgency`), a cp1252-safe `clean_data.py`, `scripts/test_data_audit.py` and `scripts/check_leakage.py --official`

<a id="exit-criteria"></a>
**Exit criteria (SPEC §12, as checks):**
1. **CI green:** `gh run list --workflow ci.yml --branch main --limit 1 --json conclusion -q ".[0].conclusion"` → `success`.
2. **Data pipeline:** `python scripts/test_clean.py` → last line `ALL TESTS PASSED`, then `git status --porcelain -- data/clean` → empty output (regeneration is deterministic). Also `python scripts/test_data_audit.py` → `DATA AUDIT TESTS PASSED` and `python scripts/check_leakage.py --official` → exit 0.
3. **Empty app deploys:**
   - `curl.exe -s https://<render-service>.onrender.com/health` → JSON with keys exactly `status, artifact, rss_mb` and `"status":"ok"`, `"artifact":null`.
   - `curl.exe -s -o NUL -w "%{http_code}" https://<site>.netlify.app/` → `200`.

<a id="p0-1"></a>
## P0.1 — Verify the flattened repo, add `.gitattributes`, push, and send the eligibility email

- [x] Done
- **Goal:** start from one clean git root and a GitHub remote, and get the solo-entry question to the organizer before the track lock.
  - **Decided 2026-10-31:** the repo is flattened, so the git root `C:/Users/hp/.m2/Ai-Quest` is the project root. A separate cleanup already handles the leftover files, so this task does not check for them ([LD-26](../PLAN.md#ld-26)).
- **Depends on:** the flatten and cleanup (done by the user/lead). **Blocks** every commit in P0.2–P0.12; P0.2–P0.8 may be drafted before it.
- **Est / Cut:** 0.5 h · Cut: no
- **Files:**
  - `.gitattributes` (new: `* text=auto eol=lf`)
  - `.gitignore`, extended with `.tmp/`, `.cache/`, `dist/`, `models/frozen/*/encoder/`, `models/frozen/*/m3/`, `*.tar.gz`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `apps/web/.netlify/`
- **Interfaces / Config keys:** none.
- **Steps:**
  1. Add `.gitattributes` and run `git add --renormalize .`.
  2. Extend `.gitignore` as listed. Keep the existing `*hidden_test*` and `JUDGE_GUIDE.md` lines.
  3. Commit and push to the existing **private** repo `Talaljaber/Ai-Quest` ([UD-8](../PLAN.md#ud-8)). It goes public at submission.
  4. **User action, today:** email the organizer about the solo entry vs. "teams of 2–3" ([OQ-1](../PLAN.md#oq-1)). It must go before the Tue 3 Nov track lock.
- **Acceptance:**
  - `git rev-parse --show-toplevel` → `C:/Users/hp/.m2/Ai-Quest`
  - `git ls-files CLAUDE.md docs/SPEC.md scripts/clean_data.py data/raw/train.csv` → exactly those 4 paths
  - `git check-ignore -v data/raw/hidden_test.csv` → `.gitignore:<n>:*hidden_test*	data/raw/hidden_test.csv`. This tests the rule only; nothing is listed or opened.
  - `git ls-files --eol docs/SPEC.md` → starts with `i/lf`
  - `python scripts/test_clean.py` → `ALL TESTS PASSED`, then `git status --porcelain -- data/clean` → empty
  - `git remote -v` → `origin  https://github.com/Talaljaber/Ai-Quest.git (push)`
- **Hands off:** a git root that is the project root, with a public remote.
- **Notes:**
  - Non-negotiable: never `ls` or glob for `hidden_test*` or `JUDGE_GUIDE*`; rely on the ignore rule.
  - `scripts/clean_data.py` stays untouched except for the P0.3c print guard (§3.7).

<a id="p0-2"></a>
## P0.2 — Create the Python package skeleton with exact pins

- [x] Done
- **Goal:** `campuspulse_ai` installs in editable mode. Four requirement sets with exact pins separate inference (no torch) from API, dev and train.
- **Depends on:** P0.1
- **Est / Cut:** 0.75 h · Cut: no
- **Files:**
  - `pyproject.toml` (root: ruff config only)
  - `services/ai/pyproject.toml`: package `campuspulse_ai`, `requires-python = ">=3.11,<3.14"`, version `0.1.0`, pytest markers and mypy config
  - `services/ai/requirements.txt`, `services/ai/requirements-api.txt`, `services/ai/requirements-dev.txt`, `services/ai/requirements-train.txt`
  - `services/ai/campuspulse_ai/__init__.py` (`__version__ = "0.1.0"`)
  - an empty `__init__.py` in every package directory of the §1.2 tree (`domain/`, `application/{services,use_cases}/`, `adapters/*/`, `config/`, `composition/`, `frameworks/{routes,cli}/`)
  - `services/ai/tests/{unit,contracts,invariants,e2e,fixtures}/__init__.py`
  - `services/ai/tests/unit/test_requirements_pinned.py`
- **Interfaces:** none.
- **Config keys:** none.
- **Pins:** copy the four requirement files from [Appendix A](appendix_A_dependencies.md) › "Ready-to-paste Python files" exactly. Key points:
  - `requirements.txt` is inference only (used by `predict.py`): `numpy==2.4.6`, `scipy==1.17.1` (both have cp311–cp313 wheels; [LD-1](../PLAN.md#ld-1)), `scikit-learn==1.9.1`, `joblib==1.6.0`, `pandas==3.0.6`, `onnxruntime==1.31.0`, `tokenizers==0.23.3`, `pyyaml==6.0.3`, `pydantic==2.14.1`, `pydantic-settings==2.16.0`. **No torch, transformers, sentence-transformers, optimum or mail SDK.**
  - `requirements-api.txt` adds `fastapi`, `uvicorn`, `httpx`, `supabase`, `psutil`, `python-multipart`. Email uses stdlib `smtplib` ([LD-3](../PLAN.md#ld-3)).
  - `requirements-dev.txt` adds `pytest`, `pytest-asyncio`, `respx`, `ruff`, `nbformat`, `nbclient`, `mypy==2.4.0` and `types-PyYAML==6.0.12.20260906`.
  - `requirements-train.txt` adds `torch==2.14.1+cpu` (CPU index), `sentence-transformers`, `transformers`, `safetensors`, `huggingface-hub`, `matplotlib`, `mapie`, `ipykernel==7.4.0`. No optimum ([LD-8](../PLAN.md#ld-8)).
  - One exact pin per package; no environment markers.
- **Steps:**
  1. Interface: the package layout per §1.2.
  2. Inputs/outputs: requirement files.
  3. Errors: `pip check` must be clean.
  4. Tests: `test_requirements_pinned.py` asserts that every non-comment, non-`-r`, non-`--` line matches `^[A-Za-z0-9_.\[\]-]+==[0-9][^;\s]*(\s*;.*)?$`.
  5. Implementation:
     - Root ruff config: `target-version = "py311"`, `line-length = 110`, rules `E,F,I,B,UP,SIM,TID`.
     - `[tool.ruff.lint.flake8-tidy-imports.banned-api]` bans `sklearn.model_selection.train_test_split`, `sklearn.model_selection.KFold`, `sklearn.model_selection.StratifiedKFold`, `sklearn.model_selection.ShuffleSplit` and `sklearn.model_selection.StratifiedShuffleSplit`, each with the message `"random splits are forbidden (SPEC §3); use adapters.training.cv"` (§3.2).
- **Acceptance:**
  - `python -m pip install -r services/ai/requirements-dev.txt -e services/ai` → exit 0
  - `python -m pip check` → `No broken requirements found.`
  - `python -c "import campuspulse_ai; print(campuspulse_ai.__version__)"` → `0.1.0`
  - `pytest services/ai/tests/unit/test_requirements_pinned.py -q` → `1 passed`
  - `python -c "import re,pathlib;t=pathlib.Path('services/ai/requirements.txt').read_text();assert not re.search(r'(?im)^(torch|transformers|sentence-transformers|optimum)\b',t);print('inference set clean')"` → `inference set clean`
  - `ruff check .` → `All checks passed!`
- **Hands off:** an installable package and the four requirement sets.
- **Notes:**
  - Non-negotiable: `predict.py` must run from `pip install -r requirements.txt`, so torch never enters that file (§3.17).
  - **Files added:** root `pyproject.toml` already exists in §1.2. `test_requirements_pinned.py` is new.

<a id="p0-3"></a>
## P0.3 — Wire in the existing data pipeline and create the holdout folders

- [ ] Done
- **Goal:** the cleaning pipeline runs under pytest and CI. The package has one place for data paths. The holdout folders exist and say they are never trained on.
- **Depends on:** P0.2
- **Est / Cut:** 0.5 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/config/paths.py`
  - `data/our_test/README.md`, `data/robustness/README.md`
  - `data/augmented/README.md` (schema of §4.2)
  - `services/ai/tests/unit/test_clean_pipeline.py`
- **Interfaces:**
  ```python
  # config/paths.py
  REPO_ROOT: Path            # walk up from __file__ until a dir containing both "data/" and "config/" (or env CAMPUSPULSE_ROOT)
  DATA_RAW: Path; DATA_CLEAN: Path; DATA_AUGMENTED: Path; OUR_TEST: Path; ROBUSTNESS: Path
  CONFIG_DIR: Path; LEXICONS: Path; MODELS_FROZEN: Path; REPORTS: Path
  HOLDOUT_MARKERS: tuple[str, ...] = ("our_test", "robustness")
  def is_holdout(path: Path) -> bool: ...
  ```
- **Config keys:** env `CAMPUSPULSE_ROOT` (optional override, also documented in `.env.example` in P0.5).
- **Steps:**
  1. Interface: the constants above.
  2. Inputs/outputs: paths only. No file is read at import time.
  3. Errors: `RuntimeError` if the root cannot be found.
  4. Tests:
     - `test_clean_script_passes`: subprocess `python scripts/test_clean.py`, the last stdout line is `ALL TESTS PASSED`
     - `test_combined_shape`: `train_val_combined.csv` has 432 rows and 30 unique `cv_group`s, with columns ⊇ `request_id,text,lang,core,text_norm,scenario_id,category,priority,cv_group`
  5. Implementation: write the paths module and the READMEs. Each holdout README states "never read by `train.py`; only `evaluate.py` reads this folder (§3.2)".
- **Acceptance:**
  - `pytest services/ai/tests/unit/test_clean_pipeline.py -q` → `2 passed`
  - `python scripts/test_clean.py` → `ALL TESTS PASSED`
- **Hands off:** `config.paths` for every later task.
- **Notes:** labels in `data/raw` and `data/clean` are never edited. `test_clean.py` regenerates `data/clean`, and CI asserts with `git diff --exit-code` that nothing changed.

<a id="p0-3a"></a>
## P0.3a — Freeze a category-stratified `cv_fold` assignment

- [ ] Done
- **Goal:** five folds in which every validation part contains all 6 categories and all 3 priorities. Plain GroupKFold(5) on the 30 `cv_group`s leaves validation folds with only 4–5 categories for every seed tried, which makes per-fold macro-F1 and calibration undefined or biased (data audit F1; [LD-31](../PLAN.md#ld-31)).
- **Depends on:** P0.3
- **Est / Cut:** 0.75 h · Cut: no
- **Files:**
  - `scripts/make_folds.py` (new)
  - `data/clean/cv_folds.csv` (new; columns `cv_group,cv_fold`)
  - No existing CSV is edited. The pool joins `cv_fold` by `cv_group`.
- **Interfaces:**
  ```python
  # python scripts/make_folds.py [--k 5] [--seed 42] [--include-augmented]
  def assign_folds(groups: pd.DataFrame, k: int, seed: int) -> dict[str, int]: ...
      # groups: one row per cv_group with category, priority, has_ar; exactly one group per category per fold,
      # all 3 priorities per fold, ≥ 2 groups with Arabic per fold; deterministic search seeded by `seed`
  def append_new_groups(folds: dict[str, int], new_groups: pd.DataFrame, k: int) -> dict[str, int]: ...
      # --include-augmented: official assignments never move; each NEW-S/MEM group goes to the fold with the
      # fewest groups of its category (ties → lowest fold id)
  ```
- **Config keys:** `config/train.yaml` `cv.k: 5`, `seed: 42`; `FrozenConfig.cv.{fold_col: "cv_fold", folds_file: "data/clean/cv_folds.csv"}`.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: `data/clean/train_val_combined.csv` → `cv_folds.csv` (30 rows for the official data).
  3. Errors: exit 1 if no assignment satisfies the constraints within the search budget. The audit found one, with fold rows 84/84/84/89/91.
  4. Tests: in `scripts/test_data_audit.py` (P0.3d): every fold has 6 categories and 3 priorities, no group appears in two folds, and the file is reproduced byte-identically by a second run.
  5. Implementation: a seeded randomized search with a fixed iteration cap.
- **Acceptance:**
  - `python scripts/make_folds.py` → `wrote data/clean/cv_folds.csv: 30 groups, 5 folds, categories 6/6 and priorities 3/3 in every fold, rows/fold <n>/<n>/<n>/<n>/<n>`
  - `python -c "import pandas as pd;d=pd.read_csv('data/clean/cv_folds.csv');print(len(d),d.cv_fold.nunique())"` → `30 5`
- **Hands off:** the frozen folds for [P1.8](P1_scored_core.md#p1-8) and every OOF computation in P1/P2.
- **Notes:** `cv_group` stays the leakage unit. Folds only decide which whole groups are held out together. Never a random split.

<a id="p0-3b"></a>
## P0.3b — Add derived columns: `lang_script`, `is_arabizi`, `stated_urgency`

- [ ] Done
- **Goal:** the columns the plan assumes but the cleaned data does not provide, in a separate file so the existing CSVs keep their parity hashes (data audit F2; [LD-33](../PLAN.md#ld-33)).
- **Depends on:** P0.3
- **Est / Cut:** 0.25 h · Cut: no
- **Files:**
  - `scripts/add_derived_columns.py` (new)
  - `data/clean/train_val_features.csv` (new: `request_id,lang_script,is_arabizi,stated_urgency`)
- **Interfaces:** `python scripts/add_derived_columns.py`. It computes `lang_script = lang` (`ar`/`en`, script-only), `is_arabizi = False` for all 432 rows (asserted with a digit-inside-word regex) and `stated_urgency = has_urgent_marker`.
- **Config keys:** none.
- **Steps:**
  1. Read `train_val_combined.csv` with `utf-8`.
  2. Assert that no row has Latin letters adjacent to the digits 2/3/5/6/7/8/9.
  3. Write the file.
  4. Document in `data/clean/README` and in [P1.2](P1_scored_core.md#p1-2) that `lang` in the CSVs is script-only. The package `LangIdentifier` owns the Arabizi label.
- **Acceptance:** `python -c "import pandas as pd; d=pd.read_csv('data/clean/train_val_features.csv'); print(d.is_arabizi.sum(), d.stated_urgency.sum())"` → `0 27`
- **Hands off:** the fairness slice keys `lang_script` + `is_arabizi` for [P2.8](P2_data_rigor.md#p2-8).

<a id="p0-3c"></a>
## P0.3c — Make `clean_data.py` safe on a cp1252 console (outputs byte-identical)

- [ ] Done
- **Goal:** `python scripts/clean_data.py` exits 0 on a Windows cp1252 console. Today it crashes with `UnicodeEncodeError` in its final `print` of the Arabic report, after all files are written (data audit F4).
- **Depends on:** P0.3
- **Est / Cut:** 0.1 h · Cut: no
- **Files:** `scripts/clean_data.py`. Only the final `print` changes. This is the one permitted edit ([LD-35](../PLAN.md#ld-35)).
- **Interfaces / Config keys:** none.
- **Steps:**
  1. Record the md5 (CRLF-normalised) of the five outputs: `train_clean.csv` `174582df…`, `val_clean.csv` `c3af332d…`, `train_val_combined.csv` `d0f17ae8…`, `scenarios.csv` `65074205…`, `cleaning_report.md` `eb2430a1…`.
  2. Guard the final print with `sys.stdout.reconfigure(encoding="utf-8")`.
  3. Re-run and compare the hashes.
- **Acceptance:**
  - On Windows PowerShell: `python scripts/clean_data.py > $null; $LASTEXITCODE` → `0`
  - `python scripts/test_data_audit.py` → `DATA AUDIT TESTS PASSED` (P0.3d includes the hash-parity check)
  - `git status --porcelain -- data/clean` → empty
- **Hands off:** a script that CI can run on the Windows leg.
- **Notes:** labels and outputs must not change. If any hash differs, revert.

<a id="p0-3d"></a>
## P0.3d — Add `scripts/test_data_audit.py` (the audit's test gaps)

- [ ] Done
- **Goal:** turn the data audit's findings into a standing test, without editing `test_clean.py` (data audit F5).
- **Depends on:** P0.3a, P0.3b, P0.3c
- **Est / Cut:** 1 h · Cut: no
- **Files:** `scripts/test_data_audit.py` (new, plain Python like `test_clean.py`, also run under pytest by `services/ai/tests/unit/test_clean_pipeline.py`)
- **Interfaces:** `python scripts/test_data_audit.py` → `DATA AUDIT TESTS PASSED`, exit 0, or an `AssertionError` naming the check.
- **Config keys:** `config/datasets.yaml` `audit.{near_dup_cosine: 0.8}`.
- **Steps (checks 1–11 of the audit):**
  1. The committed `data/clean/*` equals what `clean_data.py` produces. Regenerate in a temp copy and compare md5 after CRLF normalisation.
  2. Determinism: two regenerations hash equal.
  3. Labels and text in `train_val_combined.csv` equal raw for all 432 ids.
  4. No cross-group char 3–5-gram TF-IDF cosine ≥ 0.8. The maximum today is 0.375.
  5. Every `cv_group` is a union of whole scenarios; translation pairs are never split; one category and one priority per group.
  6. Fold feasibility: `cv_folds.csv` covers all 30 groups once, with 6 categories and 3 priorities per fold.
  7. `label_flags.csv`: ids exist, `official_label` equals the data, soft targets sum to 1, and argmax equals the official label.
  8. No Latin script in `ar` rows and no Arabic script in `en` rows.
  9. `normalize` is idempotent; no diacritics or tatweel in `text_norm`.
  10. Unseen wrappers (lowercase `urgent:`, `URGENT ` without a colon) are **documented** as not stripped by `clean_data.py`. Expected `False` here; the package stripper covers them ([P1.1](P1_scored_core.md#p1-1)).
  11. The `clean_data.py` exit code is 0 with `PYTHONIOENCODING=cp1252`.
- **Acceptance:** `python scripts/test_data_audit.py` → `DATA AUDIT TESTS PASSED`
- **Hands off:** a CI gate (P0.9) and the regression guard for every later data change.

<a id="p0-3e"></a>
## P0.3e — Add the leakage gate `scripts/check_leakage.py` (official mode)

- [ ] Done
- **Goal:** the leakage check that §3.2 names, available from P0. [P2.1](P2_data_rigor.md#p2-1) extends it to augmented rows and holdouts.
- **Depends on:** P0.3
- **Est / Cut:** 0.5 h · Cut: no
- **Files:** `scripts/check_leakage.py` (new)
- **Interfaces:**
  ```python
  # python scripts/check_leakage.py --official            (char n-gram mode, no encoder needed)
  def exact_cross_group(df: pd.DataFrame) -> list[tuple[str, str, str]]: ...      # (text_norm, group_a, group_b)
  def char_near_pairs(df: pd.DataFrame, threshold: float) -> list[NearPair]: ...    # char_wb 3–5 TF-IDF cosine across groups
  ```
- **Config keys:** `config/datasets.yaml` `leakage.char_cosine: 0.8`, `leakage.cosine_merge: 0.90` (encoder mode, [P2.1](P2_data_rigor.md#p2-1)).
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: `train_val_combined.csv` → a printed report.
  3. Errors: exit 1 on any identical `text_norm` across groups or any char pair at or above the threshold.
  4. Tests: covered by `test_data_audit.py` check 4 and by [P2.1](P2_data_rigor.md#p2-1)'s unit tests.
  5. Implementation.
- **Acceptance:** `python scripts/check_leakage.py --official` → `0 identical text_norm across groups; 0 cross-group pairs >= 0.8 (max 0.375)`, exit 0
- **Hands off:** the gate reused in [P2.1](P2_data_rigor.md#p2-1) and [P2.4](P2_data_rigor.md#p2-4).

<a id="p0-4"></a>
## P0.4 — Write the domain layer (labels, values, entities, errors, ports)

- [x] Done
- **Goal:** every type and port of §1.3–§1.4 exists with real signatures and `...` bodies for the ports. This is the vocabulary that every later task imports.
- **Depends on:** P0.2
- **Est / Cut:** 1 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/domain/{labels,values,entities,errors,ports}.py`
  - `domain/{policy,priority_rules,routing}.py` as module docstrings only (filled in [P1.12](P1_scored_core.md#p1-12) and P3)
  - `services/ai/tests/unit/test_domain_values.py`
- **Interfaces:** exactly §1.3 and §1.4. The brief names these supporting value types but leaves their fields implicit, so P0.4 fixes them in `values.py`. All are `@dataclass(frozen=True, slots=True)`:
  ```python
  class VectorItem:   id: str; embedding: tuple[float, ...]; text: str; lang: Lang; meta: Mapping[str, str | float | bool | None]
  class VectorHit:    id: str; text: str; sim: float; lang: Lang; meta: Mapping[str, str | float | bool | None]; embedding: tuple[float, ...] | None = None
  class Neighbor:     text: str; category: Category; priority: Priority; sim: float; source: Literal["train","augmented","memory"]; created_at: datetime | None
  class EnsembleOutput: p_cat: ProbVector; p_pri_model: ProbVector; per_model: Mapping[str, ProbVector]; ood_score: float; neighbors: tuple[Neighbor, ...]; embedding: tuple[float, ...]
  class Manifest:     artifact_version: str; files: Mapping[str, str]; created_at: str   # relpath -> sha256
                      @property
                      def sha(self) -> str: ...      # sha256 over sorted "relpath:sha" lines; reported by /health and predict.py
  class StripResult:  prefix: str; suffix: str; core: str; stated_urgency: bool
  ```
  - `per_model` keys are `"<member>.category"` and `"<member>.priority"`, for example `"m1.category"` ([LD-13](../PLAN.md#ld-13)).
  - `CoreResult` gets `flags: frozenset[str]` ([LD-13](../PLAN.md#ld-13)).
  - `VectorHit.embedding` is filled only when `filters["with_embedding"]` is true (incident centroid; [LD-14](../PLAN.md#ld-14)).
  - `domain/errors.py` adds `NotificationError(CampusPulseError)` with `retryable: bool` ([LD-15](../PLAN.md#ld-15)).
  - The `Repository` port carries the extra methods of [LD-16](../PLAN.md#ld-16) (`ticket_by_link`, `incident_members`, `free_slots`, `claim_slot`, `save_case`, `save_notification`, `advisors_for`, `router_stats`, `redteam_history`), with `...` bodies.
  - The flag-string constants of §5.1 go into `domain/values.py` as `FLAGS: frozenset[str]`, plus `explanation_failed` ([LD-25](../PLAN.md#ld-25)) and the debug-only `empty_input` ([LD-17](../PLAN.md#ld-17)).
- **Config keys:** none.
- **Steps:**
  1. Interface: transcribe §1.3 and §1.4.
  2. Inputs/outputs: `ProbVector` is validated in `__post_init__`.
  3. Errors: `errors.py` exactly as §1.3. A `ProbVector` that does not sum to 1 ± 1e-6 raises `ValueError` (a programming error, not `InvalidInput`).
  4. Tests:
     - `test_category_values_match_official_labels`: the set of `Category.value` equals the unique `category` values in `data/clean/scenarios.csv`, and the same for `Priority`
     - `test_priority_rank_and_bump_caps_at_high`
     - `test_probvector_rejects_non_normalized`
     - `test_probvector_argmax_tiebreak_follows_label_order`
     - `test_predictionset_size_and_singleton`
     - `test_ports_are_runtime_checkable_protocols`
  5. Implementation: stdlib only.
- **Acceptance:**
  - `pytest services/ai/tests/unit/test_domain_values.py -q` → `6 passed`
  - `mypy --strict services/ai/campuspulse_ai/domain` → `Success: no issues found in 9 source files`
- **Hands off:** the domain vocabulary and every port name.
- **Notes:** label strings exist only in `labels.py` (§1.3). `domain/` imports nothing outside stdlib (§1.1).

<a id="p0-5"></a>
## P0.5 — Add `Settings` and `.env.example` (Gmail SMTP)

- [x] Done
- **Goal:** one typed runtime-settings object. `.env.example` lists every variable, and a test keeps the two in sync.
- **Depends on:** P0.3
- **Est / Cut:** 0.5 h · Cut: no
- **Files:** `services/ai/campuspulse_ai/config/settings.py`, `.env.example`, `services/ai/tests/unit/test_env_example.py`
- **Interfaces:**
  ```python
  class Settings(BaseSettings):     # pydantic-settings, env_prefix "", case-insensitive, .env optional
      openrouter_api_key: SecretStr | None = None
      openrouter_tier1_model: str | None = None
      openrouter_tier2_model: str | None = None
      enable_llm: bool = False
      llm_daily_budget_usd: float = 5.0             # §6.2 flag 11
      supabase_url: str | None = None
      supabase_service_role_key: SecretStr | None = None
      ai_service_token: SecretStr | None = None
      gmail_smtp_user: str | None = None             # campuspulse.support@gmail.com
      gmail_app_password: SecretStr | None = None
      smtp_host: str = "smtp.gmail.com"
      smtp_port: int = 587
      demo_email_allowlist: frozenset[str] = frozenset()   # comma-separated, lower-cased; empty = reject all (§3.13, §6.2 flag 14)
      google_service_account_json: SecretStr | None = None
      demo_calendar_ids: tuple[str, ...] = ()
      linear_api_key: SecretStr | None = None
      linear_webhook_secret: SecretStr | None = None
      outbound_webhook_url: str | None = None
      outbound_webhook_secret: SecretStr | None = None
      enable_sinks: bool = True
      sla_scan_minutes: int = 5
      incident_window_min: int = 30
      artifact_dir: Path = Path("models/frozen")    # resolved against REPO_ROOT; CURRENT picks the version
      ort_intra_op_threads: int = 4                 # Render sets 1 (§3.17)
      campuspulse_root: Path | None = None
  ```
- **`.env.example` layout:** one section per scope, and every line carries a `# scope: ai|web|cli` comment.

  | Scope | Variables |
  | --- | --- |
  | `ai` | every field above, upper-cased |
  | `web` | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (this is SPEC §11's `SUPABASE_ANON_KEY`, renamed for Next.js and noted in a comment), `AI_SERVICE_URL`, `AI_SERVICE_TOKEN` |
  | `cli` | `SUPABASE_PROJECT_REF`, `SUPABASE_DB_PASSWORD`, `SUPABASE_TEST_URL`, `PORT` (Render) |

  - The email variables are `GMAIL_SMTP_USER`, `GMAIL_APP_PASSWORD`, `SMTP_HOST=smtp.gmail.com` and `SMTP_PORT=587`.
  - `DEMO_EMAIL_ALLOWLIST` is kept.
- **Config keys:** the env vars above. Later tasks (P3, P4, S1) add their fields through the same test.
- **Steps:**
  1. Interface: `Settings`.
  2. Inputs/outputs: env and an optional `.env` file.
  3. Errors: `pydantic.ValidationError` on a bad type, surfaced once at startup.
  4. Tests:
     - `test_every_settings_field_documented`
     - `test_every_ai_scoped_var_is_a_field`
     - `test_defaults_build_with_empty_env` (`enable_llm is False`, allowlist empty)
     - `test_example_contains_no_secret_values`: every `*_KEY|*_SECRET|*_PASSWORD|*_TOKEN` line is empty, and no `sk-`, `eyJ` or `re_` prefix appears
  5. Implementation.
- **Acceptance:**
  - `pytest services/ai/tests/unit/test_env_example.py -q` → `4 passed`
  - `python -c "from campuspulse_ai.config.settings import Settings;print(Settings().smtp_host)"` → `smtp.gmail.com`
- **Hands off:** `Settings` for `build_offline`/`build_online` and P4's SMTP notifier.
- **Notes:**
  - Non-negotiables: secrets are server-side only (no `SUPABASE_SERVICE_ROLE_KEY` in a `web` line, §1.7), and `.env.example` stays current.
  - Email is Gmail SMTP through stdlib `smtplib` ([LD-3](../PLAN.md#ld-3)).

<a id="p0-6"></a>
## P0.6 — Write the architecture test (import-graph rules)

- [x] Done
- **Goal:** the layer rules of §1.1 are enforced from the first commit. [P1.18](P1_scored_core.md#p1-18) extends the test with the offline-graph assertions.
- **Depends on:** P0.4
- **Est / Cut:** 0.5 h · Cut: no
- **Files:** `services/ai/tests/test_architecture.py`
- **Interfaces:**
  ```python
  def imported_modules(py_file: Path) -> set[str]: ...          # ast walk: Import / ImportFrom (absolute + resolved relative)
  def violations(layer_dir: Path, allowed: Callable[[str], bool]) -> list[tuple[Path, str]]: ...
  ```
- **Config keys:** none.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: a package directory, returning a list of violations.
  3. Errors: none. The test fails and lists the violations.
  4. Tests:
     - `test_domain_stdlib_only` (allowed: `sys.stdlib_module_names` ∪ `campuspulse_ai.domain`)
     - `test_application_domain_numpy_only`
     - `test_adapters_do_not_import_frameworks_or_composition`
     - `test_frameworks_import_only_composition_and_dto` (plus `fastapi`, `uvicorn`, `argparse`)
     - `test_checker_flags_forbidden_import`: a self-test on a temp module that does `import requests` inside a fake `domain/`
  5. Implementation.
- **Acceptance:** `pytest services/ai/tests/test_architecture.py -q` → `5 passed`
- **Hands off:** the import-graph guard. [P1.18](P1_scored_core.md#p1-18) adds the `sys.modules` checks of §1.5 and §3.18.
- **Notes:** this is the "no clean-architecture tax" guard (§6.2 flag 9). No DI library, no extra layers.

<a id="p0-7"></a>
## P0.7 — Build the FastAPI `/health`, Dockerfile and `render.yaml`

- [x] Done
- **Goal:** an AI service that boots on Render Starter with a single worker and reports its RSS. It has no models yet.
- **Depends on:** P0.5
- **Est / Cut:** 0.75 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/frameworks/fastapi_app.py`
  - `services/ai/campuspulse_ai/frameworks/routes/health.py`
  - `services/ai/api.py`
  - `services/ai/Dockerfile`
  - `render.yaml` (repo root; [LD-4](../PLAN.md#ld-4))
  - `.dockerignore`
  - `services/ai/tests/e2e/test_health.py`
- **Interfaces:**
  ```python
  def create_app(settings: Settings | None = None) -> FastAPI: ...        # mounts routers under /v1 and /health at root (+ /v1/health alias)
  # routes/health.py
  class HealthResponse(BaseModel): status: Literal["ok"]; artifact: str | None; rss_mb: float
  @router.get("/health") def health() -> HealthResponse: ...             # artifact = Manifest.sha once a container exists (P3/P4), None in P0
  ```
- **Config keys:** `Settings.ort_intra_op_threads`, env `PORT`.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: GET returns JSON.
  3. Errors: none. psutil failure → `rss_mb = -1.0` and a log line.
  4. Tests:
     - `test_health_contract`: 200, keys exactly `{status, artifact, rss_mb}`, `rss_mb > 0`
     - `test_app_import_has_no_torch`: subprocess `import api`, then `'torch' not in sys.modules`
  5. Implementation:
     - **Dockerfile:**
       - `FROM python:3.11-slim` (§3.16; [LD-1](../PLAN.md#ld-1))
       - build context = repo root
       - `COPY services/ai/requirements*.txt` → `pip install --no-cache-dir -r requirements-api.txt`
       - `COPY services/ai config scripts models/frozen`
       - `ARG FETCH_MODELS=0`, then `RUN if [ "$FETCH_MODELS" = "1" ]; then python scripts/fetch_models.py --tag "$MODELS_TAG"; fi`. This stays 0 until P4.
       - `pip install --no-deps -e services/ai`
       - a non-root user
       - `CMD uvicorn api:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1` (shell form, so the variable expands)
     - **`render.yaml`:**
       - `services: - type: web, runtime: docker, plan: starter, region: frankfurt, dockerfilePath: ./services/ai/Dockerfile, dockerContext: ., healthCheckPath: /health, autoDeployTrigger: commit, branch: main`
       - `envVars`: `ORT_INTRA_OP_THREADS=1`, plus every secret as `sync: false`
- **Acceptance:**
  - `pytest services/ai/tests/e2e/test_health.py -q` → `2 passed`
  - Optional, only if Docker Desktop is installed: `docker build -f services/ai/Dockerfile -t campuspulse-ai .`, then `docker run --rm -e PORT=8000 -p 8000:8000 campuspulse-ai` and `curl.exe -s localhost:8000/health` → `{"status":"ok","artifact":null,"rss_mb":…}`. The binding check is the Render deploy in P0.11.
- **Hands off:** `create_app`, the Docker image recipe and the Render blueprint.
- **Notes:** a single uvicorn worker is mandatory: the SLA loop (§3.15) and the memory budget (§3.17) depend on it.

<a id="p0-8"></a>
## P0.8 — Scaffold the Next.js app (`apps/web`)

- [ ] Done
- **Goal:** a strict-TypeScript Next.js app with Tailwind and ESLint, a placeholder `/` and a dev-only `/dev/ui`, all pinned exactly.
- **Depends on:** P0.1
- **Est / Cut:** 0.75 h · Cut: no
- **Files:**
  - `apps/web/{package.json,package-lock.json,tsconfig.json,next.config.ts,eslint.config.mjs,postcss.config.mjs,.nvmrc}`
  - `apps/web/src/app/{layout.tsx,page.tsx,globals.css}`
  - `apps/web/src/app/dev/ui/page.tsx`
  - `netlify.toml` (repo root)
- **Interfaces:** `/dev/ui` calls `notFound()` when `process.env.NODE_ENV === "production"` (§1.7).
- **Config keys:**
  - `netlify.toml`: `[build] base = "apps/web"`, `command = "npm run build"`, `[build.environment] NODE_VERSION = "22"`
  - `.nvmrc` = `22` (`@supabase/supabase-js` 2.118 needs Node ≥ 22)
- **Steps:**
  1. Run `npx create-next-app@16.4.2 apps/web --ts --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm`. Then pin `typescript` to `5.9.3` and keep Tailwind 4 CSS-first with `@theme`; there is no `tailwind.config.ts` ([LD-2](../PLAN.md#ld-2); versions in [Appendix A](appendix_A_dependencies.md)).
  2. Strip `^` and `~` from every dependency.
  3. Add scripts: `"typecheck": "tsc --noEmit"`, `"lint": "eslint ."`, `"build": "next build"`.
  4. Set `strict: true` in `tsconfig.json`.
  5. Write placeholder pages with no business logic.
- **Acceptance:**
  - `npm --prefix apps/web ci` → exit 0
  - `npm --prefix apps/web run typecheck` → exit 0
  - `npm --prefix apps/web run lint` → exit 0
  - `npm --prefix apps/web run build` → output contains `Compiled successfully` and lists `/dev/ui`
  - `node -e "const p=require('./apps/web/package.json');const a={...p.dependencies,...p.devDependencies};const b=Object.entries(a).filter(([k,v])=>/^[\^~]/.test(v));if(b.length){console.log(b);process.exit(1)}console.log('pinned')"` → `pinned`
- **Hands off:** the web scaffold that the [P5.1](P5_frontend.md#p5-1) design system builds on.
- **Notes:** no `SUPABASE_SERVICE_ROLE_KEY` anywhere under `apps/web` (§1.7).

<a id="p0-9"></a>
## P0.9 — Set up CI (ruff, mypy, pytest on 3.11 and 3.13, tsc, eslint, build)

- [ ] Done
- **Goal:** every push is checked on both supported Pythons and on Windows (the developer's OS and a likely judge OS).
- **Depends on:** P0.3, P0.3d, P0.3e, P0.6, P0.7, P0.8
- **Est / Cut:** 0.5 h · Cut: no
- **Files:** `.github/workflows/ci.yml`
- **Interfaces:** none.
- **Config keys:** none.
- **Steps:**
  1. **Job `python`:**
     - matrix `{os: ubuntu-latest, py: "3.11"}`, `{os: ubuntu-latest, py: "3.13"}`, `{os: windows-latest, py: "3.13"}`
     - `actions/setup-python` with pip cache
     - `pip install -r services/ai/requirements-dev.txt -e services/ai`
     - `ruff check .` and `ruff format --check .`
     - `mypy --strict services/ai/campuspulse_ai/domain services/ai/campuspulse_ai/application services/ai/campuspulse_ai/config`
     - `python scripts/test_clean.py`, then `git diff --exit-code -- data/clean`
     - `python scripts/test_data_audit.py` and `python scripts/check_leakage.py --official`
     - `pytest services/ai/tests -m "not train and not artifacts and not supabase" -q`
  2. **Job `web`:** Node 22, `npm ci`, `run typecheck`, `run lint`, `run build`, all in `apps/web`.
  3. [P1.19](P1_scored_core.md#p1-19) adds an `artifacts` job.
- **Acceptance:**
  - `gh workflow run ci.yml --ref main`, then `gh run watch --exit-status` → exit 0
  - `gh run list --workflow ci.yml --limit 1` → status `completed`, conclusion `success`
- **Hands off:** the green CI that every later task must keep green.
- **Notes:**
  - The Windows leg catches CRLF, `utf-8-sig` and path bugs that a judge on Windows would hit.
  - On the Windows leg, run the regeneration check as `git diff --ignore-cr-at-eol --exit-code -- data/clean` (pandas writes CRLF on Windows). `clean_data.py` is never edited.

<a id="p0-10"></a>
## P0.10 — Create the Supabase project and the first migration (pgvector enabled)

- [ ] Done
- **Goal:** the system-of-record project exists, linked to the repo, with `vector` enabled and four tables under RLS (deny-all until P4).
- **Depends on:** P0.1
- **Est / Cut:** 0.75 h · Cut: no
- **Files:** `supabase/config.toml` (from `supabase init`), `supabase/migrations/0001_init.sql`, `supabase/seed/.gitkeep`
- **Interfaces:** the SQL schema. Columns per SPEC §8:
  - `profiles(id uuid pk references auth.users on delete cascade, role text check (role in ('student','staff','admin')), office text, alias text unique)`
  - `buildings(id text pk, code text unique, name_en text, name_ar text, map_x real, map_y real)`
  - `requests(id uuid pk default gen_random_uuid(), alias text, raw_text text not null, core text, text_norm text, lang text, is_arabizi bool, input_mode text, building_id text references buildings, room text, stated_urgency bool, status text not null, created_at timestamptz default now())`
  - `predictions(id uuid pk default gen_random_uuid(), request_id uuid references requests on delete cascade, category text, priority text, p_cat jsonb, p_pri jsonb, set_cat text[], set_pri text[], per_model jsonb, tier text, models_used text[], cost_usd numeric(10,6), latency_ms int, flags text[], explanation jsonb, artifact_version text, created_at timestamptz default now())`
- **Config keys:** env `SUPABASE_PROJECT_REF`, `SUPABASE_DB_PASSWORD` (cli scope).
- **Steps:**
  1. Create the project on supabase.com, in the Frankfurt region (closest to Render's Frankfurt region).
  2. Run `npx supabase@2.121.0 init`, then `npx supabase link --project-ref $SUPABASE_PROJECT_REF`.
  3. Write `0001_init.sql`. It starts with `create extension if not exists vector with schema extensions;` and ends with `alter table … enable row level security;` for all four tables, with no policies (policies are P4, §3.14).
  4. Run `npx supabase db push`.
- **Acceptance:**
  - `npx supabase migration list --linked` → a row with `0001` in both the Local and Remote columns
  - Manual SQL-editor check, with the output pasted into the decisions log: `select extversion from pg_extension where extname='vector';` → 1 row
  - `select relname, relrowsecurity from pg_class where relname in ('profiles','buildings','requests','predictions');` → 4 rows, all `t`
- **Hands off:** a linked project. P4 adds `0002…000N` (vectors in `000N_vectors.sql`, `extensions.vector(384)`).
- **Notes:**
  - Both encoder candidates are 384-d, so the [P2.6](P2_data_rigor.md#p2-6) encoder decision does not change the P4 vector dimension unless §3.17 fallback (2) is used (§6.1 #18).
  - The service-role key never leaves the AI service.

<a id="p0-11"></a>
## P0.11 — Deploy the empty apps: Netlify site and Render Starter service

- [ ] Done
- **Goal:** both hosts build from `main` on push, so later phases only redeploy.
- **Depends on:** P0.7, P0.8, P0.9 (green), P0.10 (URL and anon key)
- **Est / Cut:** 1 h · Cut: no
- **Files:** `docs/PLAN.md` "Deployments" line (URLs). README stub with the URLs.
- **Interfaces:** the public URLs.
- **Config keys:**
  - Render secrets: `AI_SERVICE_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ORT_INTRA_OP_THREADS=1`. The rest stay empty until P3/P4.
  - Netlify env: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `AI_SERVICE_URL`, `AI_SERVICE_TOKEN` (server-only, never `NEXT_PUBLIC_`).
- **Steps:**
  1. **Render:** New → Blueprint → select the repo → `render.yaml`. Confirm `plan: starter` (user-approved ~$7/mo) and enter the secrets.
  2. **Netlify:** Import from GitHub. `netlify.toml` sets base and Node. Add the env vars with the Builds + Functions + Runtime scopes.
  3. Push a no-op commit to prove auto-deploy.
- **Acceptance:**
  - `curl.exe -s https://<render-service>.onrender.com/health` → starts with `{"status":"ok","artifact":null,"rss_mb":`
  - `curl.exe -s -o NUL -w "%{http_code}" https://<site>.netlify.app/` → `200`
  - `curl.exe -s -o NUL -w "%{http_code}" https://<site>.netlify.app/dev/ui` → `404` (dev-only route hidden in production)
- **Hands off:** live URLs (P3–P6 redeploy). `AI_SERVICE_URL` known.
- **Notes:**
  - If Render reports less than 512 MB or any blocker, record it now. [Appendix D](appendix_D_accounts.md) confirms the limits.
  - §3.17 fallbacks are a P2 concern ([P1.6](P1_scored_core.md#p1-6) measures RSS locally).

<a id="p0-12"></a>
## P0.12 — Run the P0 exit gate

- [ ] Done
- **Goal:** prove the three SPEC exit criteria and tick the decisions log.
- **Depends on:** P0.1–P0.11
- **Est / Cut:** 0.25 h · Cut: no
- **Files:** `docs/PLAN.md` (tick boxes, record URLs and RLS check output).
- **Interfaces / Config keys:** none.
- **Steps:** run the three exit checks at the top of P0, then paste the outputs into the decisions log.
- **Acceptance:** the three exit-criteria commands give the stated outputs.
- **Hands off:** P1 may start.

## P0 risks and fallbacks

P0 is not on the SPEC §12 cut list, and its exit criteria are prerequisites for everything. Fallbacks therefore simplify the work and never remove an exit criterion.

| Risk | Likelihood / impact | Fallback (simplification, not a cut) |
| --- | --- | --- |
| P0.3c changes an output byte of `clean_data.py` | L / parity break | The hash check in P0.3c/P0.3d catches it; revert the edit and drop the print instead. |
| Flatten/cleanup not finished when P0 starts | M / blocks commits | Draft P0.2–P0.8 before it. Every path is project-relative, so nothing changes. |
| A pinned wheel is missing on one CI leg | L / CI leg red | numpy 2.4.6 and scipy 1.17.1 were chosen for their cp311–cp313 wheels ([LD-1](../PLAN.md#ld-1)). Re-check the failing package (VERIFY@P0) and log any pin change. |
| Render blueprint path or Docker context mis-set | L / no deploy | Root `render.yaml` with `dockerContext: .` ([LD-4](../PLAN.md#ld-4)). If the blueprint import fails, create the service manually in the dashboard with the same fields. |
| Next 16 tooling breaks `next build` or `tsc` | L / web job red | TypeScript is already pinned to 5.9.3 (not 7). If Next 16 itself breaks, fall back to the latest Next 15.x only with a logged decision ([LD-2](../PLAN.md#ld-2)). |
| Supabase CLI on Windows needs Docker for some commands | M / slower | Only `init`, `link`, `db push` and `migration list` are used in P0 (no Docker). Local `supabase start` is P4's problem. |
| P0 overruns ½ d (planned 7.5 h) | H / pushes P1 | P0.11 (deploys) may finish in the first hour of Sun 1 Nov. [P1.0](P1_scored_core.md#p1-0) (own test set, a human-writing task) can run in parallel because it touches no code. |

## P0 decisions logged during this phase
- [ ] Git root = `C:/Users/hp/.m2/Ai-Quest` verified · repo public
- [ ] Eligibility email sent to the organizer (date)
- [ ] Pins install on Linux 3.11, Linux 3.13 and Windows 3.13 (numpy 2.4.6 / scipy 1.17.1) · Docker base image `python:3.11-slim` digest
- [ ] Next 16.4.2 / TypeScript 5.9.3 / Tailwind 4.3.3 installed (or a logged fallback)
- [ ] Render plan, region and service URL · Netlify site URL · Supabase project ref and region
- [ ] `0001_init.sql` applied (pgvector version from the SQL check)
- [ ] `render.yaml` and Docker build context at the repo root confirmed on Render
- [ ] Frozen folds written (`cv_folds.csv` rows per fold); data-audit tests green
