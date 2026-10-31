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
