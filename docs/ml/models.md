# ML stream: as-built reference (`docs/ml/models.md`)

Owner: ML stream. This file describes **what exists now** (ARCHITECTURE.md is the design). It is updated at
every ML task, so another agent or a judge can use the ML pieces without opening the code.

Status: P0.3 to P1.4 (data pipeline, preprocessing, config and artifact plumbing). There is no trained model,
`models/frozen/v1/`, metrics table or `predict.py` yet (P1.5+).

## 1. Paths (`campuspulse_ai.config.paths`)

```python
from campuspulse_ai.config.paths import REPO_ROOT, DATA_CLEAN, LEXICONS, is_holdout
```

| constant | path |
| --- | --- |
| `REPO_ROOT` | the repo root: env `CAMPUSPULSE_ROOT`, else the first ancestor of the package (then of the cwd) holding both `data/` and `config/`; `RuntimeError` if none |
| `DATA_RAW`, `DATA_CLEAN`, `DATA_AUGMENTED` | `data/raw`, `data/clean`, `data/augmented` |
| `OUR_TEST`, `ROBUSTNESS` | `data/our_test`, `data/robustness` (holdouts, never trained on) |
| `CONFIG_DIR`, `LEXICONS` | `config`, `config/lexicons` |
| `MODELS_FROZEN`, `REPORTS` | `models/frozen`, `reports` |

`is_holdout(path)` is true when the path contains `our_test` or `robustness` anywhere (a case-insensitive
substring match, deliberately strict). `load_pool` (P1.8) and `train.py` refuse such paths.

## 2. Data files

All under `data/clean/`, UTF-8 without BOM. `data/raw/*.csv` are the official files (UTF-8 **with** BOM: read
with `utf-8-sig`) and are never edited.

| file | produced by | rows | columns |
| --- | --- | --- | --- |
| `train_clean.csv`, `val_clean.csv` | `scripts/clean_data.py` | 370, 62 | `request_id,split,text,lang,prefix,suffix,core,text_norm,scenario_id,category,priority,has_urgent_marker,n_chars` |
| `train_val_combined.csv` | `scripts/clean_data.py` | 432 | the columns above + `cv_group` |
| `scenarios.csv` | `scripts/clean_data.py` | 42 | `scenario_id,split,lang,core,category,priority,n_variants,translation_of` |
| `label_flags.csv` | hand-written (label debate) | 9 | `scenario_id,core,field,official_label,decision,soft_target,rationale,app_behaviour` |
| `cv_folds.csv` | `scripts/make_folds.py` (P0.3a) | 30 | `cv_group,cv_fold` |
| `train_val_features.csv` | `scripts/add_derived_columns.py` (P0.3b) | 432 | `request_id,lang_script,is_arabizi,stated_urgency` |

Column meanings (`train_val_combined.csv`):
- `text`: the raw official text. `prefix`/`suffix`: the stripped wrapper strings (empty when none).
- `core`: `text` without wrappers. `text_norm`: `core` normalised (see §4).
- `lang`: **script only** (`ar` if Arabic letters outnumber Latin letters, else `en`). The CSVs have no Arabizi
  label; the package `LangIdentifier` (P1.2) owns it (LD-33).
- `scenario_id`: one id per distinct (`lang`, `text_norm`); the 432 rows are 42 scenarios × 9–11 wrapper variants.
- `cv_group`: the **leakage unit**. A scenario and its verified AR↔EN translation share one group (30 groups,
  5 per category). The group id is the lexically smaller scenario id, so a `TR-*` group can contain val rows
  (cosmetic; use `split` for provenance).
- `has_urgent_marker`: `"URGENT" in text` (case-sensitive); 27 rows (23 train + 4 val), no label signal.

### 2.1 Frozen folds: `cv_folds.csv` (P0.3a, LD-31)

- Five folds, ids `0..4`. Every validation fold has exactly **one group per category** (so all 6 categories),
  all **3 priorities**, and at least 2 groups with Arabic rows.
- Official result (seed 42): rows per fold `84/84/84/89/91`; priority groups per fold (high/low/medium)
  `2/1/3, 3/2/1, 1/2/3, 1/2/3, 2/1/3`; Arabic groups per fold `2, 2, 2, 5, 4`.
- Join it to any row table on `cv_group`. **Never** split randomly (ruff bans the sklearn splitters).
- Re-running `python scripts/make_folds.py` reproduces the file byte for byte (LF line endings).
- `--include-augmented` adds groups that exist only in `data/augmented/*.csv` (`NEW-Sxx`, `MEM-…`) without moving
  an official group: each goes to the fold with the fewest groups of its category (ties → lowest fold id).
  Augmented rows that inherit an official `cv_group` inherit its fold through the join.

```bash
python scripts/make_folds.py                 # -> wrote data/clean/cv_folds.csv: 30 groups, 5 folds, ...
python scripts/make_folds.py --out .tmp/f.csv  # write elsewhere (used by the audit's determinism check)
```

Knobs (`config/train.yaml`): `seed: 42`, `cv.k: 5`, `cv.search_iterations: 20000`,
`cv.min_arabic_groups_per_fold: 2`.

### 2.2 Derived features: `train_val_features.csv` (P0.3b, LD-33)

Join on `request_id`. `lang_script` = the CSV `lang` (script-only `ar`/`en`); `is_arabizi` = `False` for all
432 rows (the script asserts no Latin letter touches a digit 2/3/5/6/7/8/9); `stated_urgency` =
`has_urgent_marker` (27 `True`). The fairness slice key is `lang_script` + `is_arabizi`; for new text both come
from the package `LangIdentifier` (§4.2). `stated_urgency` is a gaming signal only, never a model feature.

```bash
python scripts/add_derived_columns.py   # -> wrote data/clean/train_val_features.csv: 432 rows, is_arabizi=0, stated_urgency=27
```

### 2.3 Holdout and augmentation folders

- `data/our_test/` (P1.0, hand-written by the developer) and `data/robustness/` (P2.5) are **never trained on**;
  only `evaluate.py` reads them. Their READMEs state the schema.
- `data/augmented/README.md` holds the augmentation schema (ARCHITECTURE §4.2):
  `request_id,text,lang,source,source_scenario_id,cv_group,needs_human_check,author_method,category,priority`.
  Only `needs_human_check == False` rows are trained on.

## 3. Data scripts

| command | does |
| --- | --- |
| `python scripts/clean_data.py` | regenerates `data/clean/{train_clean,val_clean,train_val_combined,scenarios}.csv` and `cleaning_report.md` from `data/raw` |
| `python scripts/test_clean.py` | regenerates, then asserts structure; last line `ALL TESTS PASSED` |
| `python scripts/make_folds.py` | writes `data/clean/cv_folds.csv` (§2.1) |
| `python scripts/add_derived_columns.py` | writes `data/clean/train_val_features.csv` (§2.2) |
| `python scripts/test_data_audit.py` | the standing data audit (checks 1–11 below); last line `DATA AUDIT TESTS PASSED` |

`scripts/test_data_audit.py` (P0.3d) regenerates in two temporary copies (copying only `data/raw/train.csv` and
`data/raw/validation.csv`, by name) and never touches the repo. Checks:

| # | check |
| --- | --- |
| 1 | committed `data/clean` == regenerated (md5 after CRLF→LF) for the 4 CSVs; `cleaning_report.md` byte-equal, or equal up to line order (pandas tie order, see the known issue below) |
| 2 | two regenerations hash equal |
| 3 | `request_id`, `text`, `category`, `priority` in `train_val_combined.csv` equal raw for all 432 ids |
| 4 | no cross-`cv_group` char_wb 3–5-gram TF-IDF cosine ≥ `audit.near_dup_cosine` (0.8; max today 0.375) |
| 5 | each `cv_group` is a union of whole scenarios; the 12 translation pairs share a group; one category and priority per group |
| 6 | `cv_folds.csv` covers all 30 groups once, folds `0..k-1`, 6 categories and 3 priorities per fold, `make_folds.py` re-run byte-identical |
| 7 | `label_flags.csv`: ids exist, `official_label` and `core` equal the data, soft targets sum to 1 with the official label as the unique argmax |
| 8 | no Latin letters in `ar` rows, no Arabic letters in `en` rows |
| 9 | `clean_data.normalize` idempotent; no diacritics, tatweel or unmapped أ/إ/آ/ى/ة/ؤ/ئ in `text_norm` |
| 10 | documents that `clean_data.py` does **not** strip `urgent: …` / `URGENT …` (the package stripper does, §4.1) |
| 11 | `clean_data.py` exits 0 with `PYTHONIOENCODING=cp1252` |

It also runs under pytest: `pytest services/ai/tests/unit/test_clean_pipeline.py` (3 tests).

`pytest services/ai/tests/unit/test_clean_pipeline.py` runs `test_clean.py` in a subprocess and checks the
combined file's shape (432 rows, 30 groups).

**Known issue (escalated to the lead):** under the pinned `pandas==3.0.6`, `clean_data.py` writes
`cleaning_report.md` with tied `value_counts` rows in a different order than the committed file (made with
pandas 2.2.3). The four CSVs are byte-identical (modulo CRLF) under both versions. On Windows, pandas also
writes CRLF, so `git status` lists the files as modified even though `git diff` is empty for the CSVs. Restore
with `git checkout -- data/clean` after running the script locally.
