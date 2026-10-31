# P2 — Data + rigor

> **Status:** DRAFT — awaiting user approval. **Budget:** 2 d (ARCHITECTURE §4.0) · **Calendar:** Tue 3 – Wed 4 Nov · **Planned (not cut-flagged):** 19 h · **Cut-flagged:** 4 h (M3 box, default cut) + small sub-steps.
>
> Conventions: [PLAN.md › Conventions](../PLAN.md#conventions). `§n` refers to [ARCHITECTURE.md](../ARCHITECTURE.md); `LD-n` and `OQ-n` link to the lead decisions and open questions in [PLAN.md](../PLAN.md). Tick `- [ ] Done` under each task as you finish it, and tick this phase's decision log at the bottom.

**Goal:**
- Turn 42 scenarios into a defensible training pool: human-checked augmentation, leakage-checked.
- Finish the OOF-tuned stage B: weights, conformal, thresholds.
- Decide the encoder and M3.
- Produce every number the report and the Model lab need from **one** command, measured on scenario-held-out OOF, our own test set and the probes.

**Phase contract (§4.3):**
- **Inputs:** P1's frozen `v1-rc1`, `run_cv`/`PipelineToggles`, the validators and our own test set.
- **Hands to P3:**
  - `data/augmented/{paraphrases.csv,new_scenarios.csv,arabizi.csv}`, human-checked (only `needs_human_check=False` rows train)
  - `data/robustness/probes.csv` (≥ 40 rows, style-tagged)
  - `scripts/draft_augmentation.py` (OpenRouter, disclosed) and `scripts/check_leakage.py`
  - `train.py` stages B and C complete (weights, conformal quantiles, `tau_ood`, `tau_injection`, `human_review_maxprob`)
  - the M3 decision recorded in PLAN.md
  - `evaluate.py` producing `reports/{metrics.json,benchmark.md,coverage.json,fairness.json,ablations.json,confusions/*.json}` from one command
  - notebooks 01–05 that only read `reports/`

<a id="exit-criteria"></a>
**Exit criteria (SPEC §12, as checks):**
1. **One command:** `python services/ai/evaluate.py --all` → exit 0, and the last line is `wrote reports/{metrics.json,benchmark.md,coverage.json,fairness.json,ablations.json,errors.json,eda.json,confusions/} (artifact v1 sha=<12 hex>)`.
2. **Report schemas:** `pytest services/ai/tests/e2e/test_reports_schema.py -q` → `8 passed`. This asserts:
   - **benchmark rows:** `M1`, `M2-LR`, `M2-kNN`, `M3` (or `cut`), `Ensemble (tier 0)`, `Ensemble + router` (`n/a` until P3), `LLM zero-shot (M4)` (`n/a` until P3)
   - **coverage:** overall and per language, for both targets
   - **fairness:** EN/AR/Arabizi with counts
   - **ablations:** the five SPEC §6.2 ablations plus each member removed
3. **Determinism:** running `evaluate.py --all` twice → `git diff --stat reports/` shows only `generated_at` lines (`python scripts/diff_reports.py` → `identical modulo generated_at`).
4. **Notebooks:** `python scripts/run_notebooks.py` → `5/5 executed` (01–05, reading only `reports/`).

**P2-evaluation can never be cut (SPEC §12).** Cut-flagged items here are §4.8 #4 (M3), the conditional `MondrianByLang` wrapper and the optional Arabizi-transliteration ablation arm.

<a id="p2-1"></a>
## P2.1 — Extend `check_leakage.py` to augmentation and holdouts

- [x] Done (ML batch 4): `pytest services/ai/tests/unit/test_check_leakage.py -q` → `5 passed` (2 new + 3 P0.3e); `python scripts/check_leakage.py` → `exact cross-group duplicates: 0; near pairs >=0.90: 1793 (listed); holdout near-duplicates: 136 (listed; augmented 0 failing + 444 encoder-only for review, official 48)`, exit 0. Encoder-only holdout hits are listed, not failed (`leakage.holdout_fail_on: [exact, char]`; e5 0.90 = shared topic). See models.md §18.
- **Goal:** guarantee that augmentation cannot leak across CV groups, and that our holdouts are not near-duplicates of training text (§3.2).
- **Depends on:** [P0.3e](P0_foundations.md#p0-3e) (official mode exists), [P1.8](P1_scored_core.md#p1-8), [P1.6](P1_scored_core.md#p1-6)
- **Est / Cut:** 0.75 h · Cut: no
- **Files:**
  - `scripts/check_leakage.py`
  - `services/ai/tests/unit/test_check_leakage.py`
- **Interfaces:**
  ```python
  # python scripts/check_leakage.py [--encoder {onnx,hashing}] [--threshold <from config>] [--out reports/leakage.json]
  def exact_cross_group(pool: Pool) -> list[tuple[str, str, str]]: ...                 # (text_norm, group_a, group_b)
  def near_pairs(pool: Pool, emb: np.ndarray, threshold: float) -> list[NearPair]: ...    # cross-group pairs with cos ≥ threshold
  def holdout_near(pool_emb: np.ndarray, holdout: Sequence[str], threshold: float) -> list[NearPair]: ...
  ```
- **Config keys:** `config/datasets.yaml` `leakage.cosine_merge: 0.90` (§3.2).
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: pool (official + all augmented, reviewed or not) + `our_test` + `probes` → a report and exit code.
  3. Errors: exit 1 on any exact cross-group duplicate. Near pairs are printed for **manual** merge (the author sets the new scenario's `cv_group` to the existing group) and never auto-fixed.
  4. Tests: `test_exact_duplicate_across_groups_detected`, `test_near_pairs_listed_with_hashing_encoder`.
  5. Implementation. This is the only tool that reads holdouts for comparison. It never writes to `train.py` inputs.
- **Acceptance:**
  - `pytest services/ai/tests/unit/test_check_leakage.py -q` → `2 passed`
  - `python scripts/check_leakage.py` → `exact cross-group duplicates: 0; near pairs ≥0.90: <n> (listed); holdout near-duplicates: <m> (listed)`, exit 0
- **Hands off:** the leakage gate used in P2.4 and P2.13.
- **Notes:** a holdout near-duplicate is fixed by editing the **augmented** row or the holdout row. The holdout never moves into training.

<a id="p2-2"></a>
## P2.2 — Add the LLM drafting modes to `draft_augmentation.py` (paraphrases, new scenarios, Arabizi)

- [x] Done (ML batch 4): `pytest services/ai/tests/unit/test_draft_augmentation.py -q` → `6 passed`. Pinned drafter `anthropic/claude-sonnet-5.5`, checker `anthropic/claude-haiku-5.5` (D-014 pre-check), plus `translate` (D-014), `precheck`, `prune`, `apply-review`. models.md §19.
- **Goal:** LLM-drafted candidates, each with `needs_human_check=True`. The model ID is pinned, temperature is 0, responses are cached, and cost is logged (CLAUDE.md).
- **Depends on:** [P1.9](P1_scored_core.md#p1-9); an OpenRouter account and key ([Appendix D](appendix_D_accounts.md))
- **Est / Cut:** 1.25 h · Cut: no
- **Files:**
  - `scripts/draft_augmentation.py` (subcommands `paraphrase`, `new-scenarios`)
  - `scripts/prompts/{paraphrase,new_scenarios}.md`
  - `services/ai/tests/unit/test_draft_augmentation.py`
  - `.cache/llm_drafts.sqlite` (gitignored)
  - `data/augmented/draft_log.jsonl`
- **Interfaces:**
  ```python
  # python scripts/draft_augmentation.py paraphrase --model <pinned id> --per-scenario 3 --out data/augmented/paraphrases.csv
  # python scripts/draft_augmentation.py new-scenarios --model <pinned id> --plan config/datasets.yaml --out data/augmented/new_scenarios.csv
  def call_openrouter(model: str, system: str, user: str, *, cache: Path, budget_usd: float) -> DraftResponse: ...
  # temperature=0, top_p=1, seed=42, response_format json; cache key sha256(model‖prompt_version‖user); cost from usage
  ```
- **Config keys:**
  - `config/datasets.yaml`:
    - `augmented.paraphrase.per_scenario: 3`, with forms `[same_lang, other_lang, arabizi]`
    - `augmented.new_scenarios.target: 60`
    - `augmented.new_scenarios.per_cell_min: 3`
    - `augmented.new_scenarios.forms: [en, ar]`, with `arabizi` for 1 in 3 scenarios
  - env `OPENROUTER_API_KEY`, `LLM_DAILY_BUDGET_USD`
- **Steps:**
  1. Interface above.
  2. Inputs/outputs:
     - **Prompts** carry the category definitions (CHALLENGE_RULES), the labeller rules (LABEL_DECISIONS) and the source core.
     - **Rows** use the §4.2 schema:
       - paraphrases inherit `source_scenario_id` and `cv_group` (cross-language paraphrases too, because translations share a group)
       - new scenarios get `cv_group=NEW-Sxx`, shared by their EN/AR/Arabizi forms
       - `author_method=llm:<model_id>`, `needs_human_check=True`
     - **LLM-proposed labels** for new scenarios are suggestions that the human must confirm in P2.4.
  3. Errors:
     - schema-invalid JSON → retry once, then skip and log
     - over budget → stop with a message
     - missing key → exit 3
  4. Tests (respx, no network): `test_schema_invalid_output_rejected`, `test_cache_hit_makes_no_http_call`, `test_rows_marked_needs_human_check`.
  5. Implementation.
- **Acceptance:** `pytest services/ai/tests/unit/test_draft_augmentation.py -q` → `3 passed`
- **Hands off:** the drafting tool (disclosed in the README: model, date, purpose).
- **Notes:**
  - Non-negotiables: pinned model ID, temperature 0, cached.
  - The default drafting model is `OPENROUTER_TIER2_MODEL`'s pin from [Appendix A](appendix_A_dependencies.md), for dialect quality. It is passed explicitly as `--model` and recorded per row.
  - Disclose LLM-generated training data (SPEC §3).
  - **Files added:** `scripts/prompts/*.md`, `data/augmented/draft_log.jsonl`.

<a id="p2-3"></a>
## P2.3 — Run the drafts

- [x] Done (ML batch 4), paraphrases and translations only (new scenarios came from a separate writer, `new_scenarios.csv`): `OK augmented: 64 rows; 0 reviewed; … cells covered 18/18`; translations `17 rows; 0 reviewed; … 12/18`; 93 of 174 drafts pruned as holdout neighbours. Spend: `0.3467` USD in `draft_log.jsonl` (drafts 0.266, pre-check 0.081).
- **Goal:** candidate rows exist in all three augmented files.
- **Depends on:** P2.2
- **Est / Cut:** 0.5 h (wall time is mostly API latency) · Cut: no
- **Files:** `data/augmented/{paraphrases.csv,new_scenarios.csv}`. [P1.9](P1_scored_core.md#p1-9)'s `arabizi.csv` is unchanged.
- **Interfaces / Config keys:** as in P2.2.
- **Steps:**
  1. Run `paraphrase` (42 × 3 ≈ 126 rows).
  2. Run `new-scenarios` (≈ 60 scenarios ≈ 130 rows). The plan in `config/datasets.yaml` targets the cells that are empty in the official data first: AR Academic Support low, AR Finance low, AR IT Support medium, EN Transportation high (data audit F3). Every Arabizi row in the pool comes from augmentation ([LD-33](../PLAN.md#ld-33)).
  3. Run `python scripts/validate_dataset.py --kind augmented` on both.
  4. Commit the drafts **unreviewed**. They cannot train, because `load_pool` drops `needs_human_check=True`.
- **Acceptance:**
  - `python scripts/validate_dataset.py --kind augmented data/augmented/paraphrases.csv` → `OK augmented: <≈126> rows; 0 reviewed; …`
  - `python scripts/validate_dataset.py --kind augmented data/augmented/new_scenarios.csv` → `OK augmented: <≈130> rows; 0 reviewed; cells covered <≥16>/18`
  - `python -c "import json;print(sum(json.loads(l)['cost_usd'] for l in open('data/augmented/draft_log.jsonl')))"` → a number ≤ `LLM_DAILY_BUDGET_USD`
- **Hands off:** candidates for P2.4.
- **Notes:** the cost is recorded for the report's cost section.

<a id="p2-4"></a>
## P2.4 — Human-check the augmentation and resolve leakage

- [ ] Done — **human task, prepared**: `data/augmented/REVIEW.md` (≈ 75–90 min; 187 rows to read in full of 501, review sheet `data/augmented/review/review_sheet.csv`).
- **Goal:** every row that trains has been read, corrected and labelled by the developer. That covers Arabic dialect naturalness, Arabizi spelling and labels per the labeller rules. Leakage is resolved.
- **Depends on:** P2.1, P2.3
- **Est / Cut:** 3.5 h (human) · Cut: no. The volume may shrink to the §6.2 flag-3 minimums: ≥ 2 paraphrases per scenario, ≥ 40 new scenarios.
- **Files:** `data/augmented/*.csv` (edited), `reports/leakage.json`
- **Interfaces:** none.
- **Config keys:** `leakage.cosine_merge`.
- **Steps:**
  1. Review in VS Code with a CSV extension: fix the text, confirm or fix the labels, delete bad rows, and set `needs_human_check=False`.
  2. Run `python scripts/check_leakage.py`. Merge near-pair groups by hand by editing `cv_group`.
  2b. Run `python scripts/make_folds.py --include-augmented` to append `cv_fold` for the new groups. Official groups never move, and `test_data_audit.py` re-checks this.
  3. Re-run the guard and Arabizi gates on the reviewed augmentation:
     - zero injection regex hits
     - zero danger hits on non-high rows
     - ≥ 95 % Arabizi detection
  4. Commit.
- **Acceptance:**
  - `python scripts/validate_dataset.py --kind augmented data/augmented/paraphrases.csv` → `OK augmented: <n> rows; <n> reviewed; …`, and likewise for `new_scenarios.csv` and `arabizi.csv`
  - `python scripts/check_leakage.py` → `exact cross-group duplicates: 0`
  - `python scripts/make_folds.py --include-augmented` → `appended <n> groups; official assignment unchanged`, then `python scripts/test_data_audit.py` → `DATA AUDIT TESTS PASSED`
  - `pytest services/ai/tests/invariants/test_injection.py services/ai/tests/unit/test_safety.py services/ai/tests/unit/test_langid.py -q` → `0 failed`. Those tests extend their "zero hits" assertions to the reviewed augmentation through a `pool_rows` fixture.
- **Hands off:** the final training pool.
- **Notes:**
  - Quality beats count (§6.2 flag 3). The report states the counts and the review method.
  - Labels are never taken from the LLM without review.

<a id="p2-5"></a>
## P2.5 — Author the robustness probes

- [ ] Done — **human task, prepared**: instructions and column list in `data/augmented/REVIEW.md` part 2.
- **Goal:** ≥ 40 human-verified probes across the red-team styles. They are never trained on, and P2.8 scores them. They also seed P4's red-team scorer.
- **Depends on:** [P1.0](P1_scored_core.md#p1-0)
- **Est / Cut:** 1.5 h (human) · Cut: no
- **Files:** `data/robustness/probes.csv`, columns `request_id,text,lang,style,base_request_id,intended_category,intended_priority,expected_flags,author_method,notes`
- **Interfaces:** `scripts/validate_dataset.py --kind probes`.
- **Config keys:** `config/datasets.yaml`:
  - `probes.min_rows: 40`
  - `probes.styles: [fake_urgency, calm_emergency, typos, arabizi, mixed_language, two_issues, very_long, injection, off_topic, distress_adjacent, deadline_shortcut]` (the §2.4 styles)
  - `probes.min_per_style: 3`
- **Steps:**
  1. Write most probes as perturbations of `our_test` rows (`base_request_id` set), by hand or with a small helper (typos, `URGENT!!`/`عاجل جدا` prefixes, injection phrases from `injection.yaml`).
  2. Hand-write `off_topic` and `distress_adjacent`.
  2b. Hand-write ≥ 6 `deadline_shortcut` probes that break the "today → high" shortcut ([LD-34](../PLAN.md#ld-34)): ≥ 3 **high without** "today"/"اليوم" (exam happening now, students stranded, a definitive enrolment loss) and ≥ 3 **low/medium with** "today" ("Where is today's bus timetable?", "الضو بالممر خربان اليوم").
  3. Set `expected_flags` per §2.4 (`injection_attempt`, `distress`, …).
  4. Use `author_method ∈ {hand, perturb}`.
  5. Validate and commit.
- **Acceptance:** `python scripts/validate_dataset.py --kind probes data/robustness/probes.csv` → `OK probes: <N≥40> rows; styles 11/11 (min ≥3); langs en=… ar=… arabizi=…`
- **Hands off:** `probes.csv` for P2.8, P4's `RedTeamScorer` and P5's Model lab.
- **Notes:**
  - Non-negotiable: never trained on (`load_pool` refuses `robustness/`).
  - SPEC says ~100 probes; the brief's floor is 40 (§6.2 flag 3).

<a id="p2-6"></a>
## P2.6 — Decide the encoder (e5-small vs MiniLM) and check int8-vs-fp32 OOF parity

- [x] Done (ML batch 4, D-016 bake-off): `encoder_choice.json` → `intfloat/multilingual-e5-small 0.7768`; the parity check prints **False** (int8 0.777 vs fp32 0.746 category: |Δ| 0.031 > 0.01, in int8's favour, within the noise of 30 groups). MiniLM out (int8 parity ≤ 0.969 in every variant; 0/3 heads pass the rule). No §3.17 fallback; dimension stays 384.
- **Goal:** the final encoder for v1, chosen **on OOF only**. The ONNX int8 export is confirmed not to cost more than 0.01 OOF macro-F1 (§3.17 proof). §3.17 fallback (2) is triggered here if RSS demands it, which must happen before P4's vector migration (§6.1 #18).
- **Depends on:** P2.4, [P1.6](P1_scored_core.md#p1-6)
- **Est / Cut:** 1.25 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/frameworks/cli/export_encoder.py` (adds `--oof-parity`)
  - `reports/encoder_export.json` (extended)
  - `reports/encoder_choice.json`
- **Interfaces:**
  ```python
  # python -m campuspulse_ai.frameworks.cli.export_encoder --oof-parity --model <id> --revision <sha> --int8-dir <dir>
  #   runs run_cv twice (STEncoder fp32 — torch, train machine only — vs OnnxEncoder int8) → oof_macro_f1_{fp32,int8} per target
  # python services/ai/train.py --cv-only --encoder-dir <dir> --report .tmp/cv_<name>.json
  ```
- **Config keys:** `encoder.*` (`model_id`, `revision`, `query_prefix`: `"query: "` for e5, `""` for MiniLM); `config/train.yaml` gains `encoder_selection.metric: category_macro_f1_oof_official`.
- **Steps:**
  1. Run CV-only for both encoders on the final pool.
  2. Pick the higher OOF category macro-F1 on official rows. Ties within 0.005 → e5 (the primary, per the user decision).
  3. Run `--oof-parity` for the winner.
  4. Compare the winner's `rss_mb_after_load` with the §3.17 budget. If the projected RSS is above 400 MB, apply fallback (2) now.
  5. Write `reports/encoder_choice.json` and log the decision.
- **Acceptance:**
  - `python -c "import json;d=json.load(open('reports/encoder_choice.json'));print(d['chosen'],d['oof_cat_official'])"` → `<model id> <float>`
  - `python -c "import json;d=json.load(open('reports/encoder_export.json'));print(abs(d['oof_macro_f1_fp32']['category']-d['oof_macro_f1_int8']['category'])<=0.01)"` → `True`
- **Hands off:** the final encoder pin. The `vector(384)` dimension for P4 is confirmed, or changed with a decision-log row if fallback (2) is used.
- **Notes:**
  - Model selection never looks at `our_test` (§3.4).
  - `STEncoder` stays inside `export_encoder.py` (§1.4).

<a id="p2-7"></a>
## P2.7 — Complete `train.py` stage B (weights, C grids, conformal, thresholds) + `--retune`

- [x] Done (ML batch 4) in the D-016 form (fixed pre-declared weights; the tuned search is a reported variant): `pytest services/ai/tests/unit/test_tuning.py -q` → `17 passed` (incl. the 5 named); `python services/ai/train.py --out models/frozen/v1 --report reports/cv_p2.json` → `froze v1: members=m1,m2lr,m2knn,m2proto weights_cat={m1:0.0,m2lr:0.5,m2knn:0.0,m2proto:0.5} cat_macroF1_oof_official=0.806 pri_macroF1_oof_official=0.904 nested_cat=0.806 nested_pri=0.904 q_cat=0.78 q_pri=0.57 sha=809f6c8a913e` (then `--retune` for P2.10 → sha 9a379d97c0cd).
- **Goal:** every tunable value is learned from OOF, then frozen (§3.4). `--retune` re-runs stage B from the cached `oof.npz` so the config-only decisions of P2.10 need no full retrain.
- **Depends on:** [P1.16](P1_scored_core.md#p1-16); final run after P2.6
- **Est / Cut:** 2 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/adapters/training/tuning.py` (extended)
  - `services/ai/campuspulse_ai/frameworks/cli/train.py`
  - `services/ai/tests/unit/test_tuning.py`
- **Interfaces:**
  ```python
  def simplex_weights(probs: Mapping[str, np.ndarray], y: np.ndarray, step: float, labels: Sequence[str]) -> dict[str, float]: ...
      # grid over the simplex; maximize OOF macro-F1; tie-break: smallest L1 distance to uniform, then lexicographic member order
  def select_C(pool: Pool, encoder: SentenceEncoder, member: str, grid: Sequence[float], cfg: TrainCfg) -> float: ...
  def calibrate_conformal(p_cat_oof: np.ndarray, p_pri_head_oof: np.ndarray, pool: Pool, alpha: Mapping[str, float]) -> tuple[LACConformal, LACConformal]: ...
  ```
- **Config keys:** `config/train.yaml` `grids.*`, `alpha.*`, `tau_*` rules. Writes `ensemble.weights_*`, `m1.C`, `m2lr.C`, `conformal.*`, `thresholds.*` and `cv.oof_macro_f1_*`.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs:
     - stage A per `C` candidate (embeddings cached)
     - weights per target
     - head inner folds (the remaining `cv_fold`s) → OOF head probabilities
     - conformal on the OOF ensemble (category) and the OOF head (priority)
     - `tau_ood` (5th percentile)
     - `tau_injection` and `tau_safety` via `tau_from_zero_hits` ([LD-18](../PLAN.md#ld-18))
     - `human_review_maxprob` per §3.4
  3. Errors: `ArtifactVersionMismatch` if `--retune` finds an `oof.npz` from another pool hash.
  4. Tests:
     - `test_simplex_weights_sum_to_one_and_beat_uniform_on_synthetic`
     - `test_tau_ood_percentile`
     - `test_tau_from_zero_hits_has_no_hits`
     - `test_human_review_maxprob_rule`
     - `test_retune_reuses_oof_and_changes_only_stage_b_keys`
  5. Implementation.
- **Acceptance:**
  - `pytest services/ai/tests/unit/test_tuning.py -q` → `5 passed`
  - `python services/ai/train.py --out models/frozen/v1 --report reports/cv_p2.json` → last line `froze v1: members=m1,m2lr,m2knn weights_cat={…} cat_macroF1_oof_official=<x.xxx> pri_macroF1_oof_official=<x.xxx> q_cat=<x.xx> q_pri=<x.xx> sha=<12 hex>`
- **Hands off:** a fully tuned `config.json`, and `--retune`.
- **Notes:**
  - No tuning on `our_test` (§3.4).
  - **Files added:** `reports/cv_p2.json`.

<a id="p2-8"></a>
## P2.8 — Build `evaluate.py`: benchmark, coverage/calibration, fairness, confusions, robustness, errors, EDA

- [x] Done (ML batch 4): `python services/ai/evaluate.py --all` → `wrote reports/{metrics.json,benchmark.md,coverage.json,fairness.json,ablations.json,errors.json,eda.json,confusions/} (artifact v1 sha=9a379d97c0cd)`; `pytest services/ai/tests/e2e/test_reports_schema.py -q` → `9 passed` (the 8 + model_lab).
- **Goal:** one offline command that produces every number of SPEC §6.2 under one protocol. The protocol is OOF over the frozen `cv_fold` folds (from `oof.npz`) plus frozen-model predictions on `our_test` and `probes`.
- **Depends on:** P2.7, P2.5, [P1.0](P1_scored_core.md#p1-0)
- **Est / Cut:** 3 h · Cut: no (P2-evaluation is never cut)
- **Files:**
  - `services/ai/campuspulse_ai/frameworks/cli/evaluate.py`
  - `services/ai/evaluate.py`
  - `services/ai/campuspulse_ai/adapters/training/metrics.py`
  - `services/ai/tests/e2e/test_reports_schema.py`
  - `scripts/diff_reports.py`
  - outputs: `reports/{metrics.json, benchmark.md, coverage.json, fairness.json, errors.json, eda.json, conformal_scores.npz, confusions/<model>_<target>_<set>.json}`
- **Interfaces:**
  ```python
  # python services/ai/evaluate.py [--all] [--benchmark] [--coverage] [--fairness] [--ablations] [--robustness] [--errors] [--eda]
  #                                [--use-llm] [--model-dir models/frozen] [--reports reports]
  def macro_f1(y: Sequence[str], yhat: Sequence[str], labels: Sequence[str]) -> float: ...
  def ece(p: np.ndarray, y: np.ndarray, bins: int) -> tuple[float, list[ReliabilityBin]]: ...
  def coverage(sets: Sequence[PredictionSet], y: Sequence[str]) -> CoverageStats: ...    # coverage, mean size, singleton rate, n
  ```
- **Config keys:** `config/train.yaml` `eval.{ece_bins: 10, langs: [en, ar, arabizi]}`. Read only from `config.json`.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs:
     - **Benchmark rows** (category and priority macro-F1 and accuracy, on OOF-official, OOF-all, `our_test` and probes):
       - `M1`, `M2-LR`, `M2-kNN` (member argmax)
       - `M3` if present, else `cut`
       - `Ensemble (tier 0)`, where priority means head + finalizer
       - `Ensemble + router` and `LLM zero-shot (M4)`: `n/a` until P3's `OpenRouterOracle` exists and `--use-llm` is passed
     - **Coverage:** empirical coverage and mean set size per target, overall and per language, on `our_test`, plus OOF, with `n_rows` and `n_groups` beside each number and the note that coverage is approximate (effective n ≈ 30); ECE and reliability bins; and the **ASK-proxy rate** (share with |S_cat| = 2 or |S_pri| = 2) for P2.10. It is stored as `ask_proxy_rate` and labelled a proxy because `DecisionPolicy` arrives in P3, which recomputes the true rate ([LD-24](../PLAN.md#ld-24)).
     - **Fairness:** slices EN and AR (`lang_script`, non-Arabizi rows) and Arabizi (`is_arabizi` from the package `LangIdentifier`; the official data has none). Macro-F1 per slice on OOF-official, `our_test` and probes, **each with row and group counts**, plus the max gap. No significance claims: the effective n is ≈ 30 groups ([LD-32](../PLAN.md#ld-32), [LD-33](../PLAN.md#ld-33)). "Before vs after mitigation" comes from the P2.9 arms.
     - **Robustness:** per-style label accuracy on probes, plus flag checks the offline core can make (`injection_attempt` present, priority not raised, `distress` flag). Policy-level pass rules (OUT_OF_SCOPE) are [P4.11](P4_product_backend.md#p4-11)'s `RedTeamScorer`.
     - **Errors:** misclassified `our_test` rows and OOF-official scenarios, each with its top-3 neighbours, set sizes and lang.
     - **EDA:** counts by split/lang/label/source/review status, and wrapper stats.
     - **`conformal_scores.npz`:** OOF scores, labels and lang, for notebook 03's mapie cross-check.
  3. Errors:
     - exit 2 on `ArtifactError`
     - `--use-llm` without a key → rows `n/a`, not an error
     - no network otherwise
  4. Tests (`test_reports_schema.py`, `@pytest.mark.artifacts`): one schema test per output (`metrics`, `benchmark`, `coverage`, `fairness`, `ablations`, `confusions`, `errors`, `eda`) = 8. The `ablations` test passes once P2.9 lands; until then it is `xfail(strict=True)`.
  5. Implementation:
     - use `build_offline` + `BatchPredictUseCase(debug=True)` for `our_test` and probes
     - every JSON carries `artifact_version`, `sha`, `generated_at`, `protocol` and `n` per cell
- **Acceptance:**
  - `python services/ai/evaluate.py --all` → last line as in the P2 exit criteria
  - `pytest services/ai/tests/e2e/test_reports_schema.py -q` → `8 passed` (after P2.9)
  - `python scripts/diff_reports.py` (after a second `--all`) → `identical modulo generated_at`
- **Hands off:** `reports/*` for P3/P5 (`GET /v1/metrics`, Model lab) and the report.
- **Notes:**
  - Non-negotiables: only scenario-held-out OOF and our own test set are reported (CLAUDE.md). `evaluate.py` is the **only** reader of `our_test/` and `robustness/` besides the validators.
  - The red-team CLI (`--redteam`) is added in [P4.11](P4_product_backend.md#p4-11) (§2.4).
  - **Files added:** `adapters/training/metrics.py`, `reports/{errors.json,eda.json,conformal_scores.npz}`, `scripts/diff_reports.py`.

<a id="p2-9"></a>
## P2.9 — Add ablations to `evaluate.py`

- [x] Done (ML batch 4): 16 arms incl. D-014/D-016 arms and the labelled unreviewed-augmentation arm, each with a paired group bootstrap; `-arabizi_translit` cut as planned.
- **Goal:** the SPEC §6.2 ablations, every arm scored on the **same** rows (OOF on official rows plus `our_test`).
- **Depends on:** P2.8
- **Est / Cut:** 1.5 h · Cut: no. Only the extra `−Arabizi transliteration` arm is cut: yes (not SPEC-required).
- **Files:**
  - `services/ai/campuspulse_ai/frameworks/cli/evaluate.py` (`--ablations`)
  - `services/ai/campuspulse_ai/adapters/training/cv.py` (`fit_pipeline`)
  - `reports/ablations.json`
- **Interfaces:**
  ```python
  def fit_pipeline(pool: Pool, encoder: SentenceEncoder, cfg: TrainCfg, toggles: PipelineToggles) -> TriageCore: ...   # in-memory, no artifacts written
  ```
- **Config keys:** `PipelineToggles` fields. Arms:
  1. `full`
  2. `-wrapper_stripping`
  3. `-augmentation`
  4. `-urgency_features`
  5. `-m1`
  6. `-m2lr`
  7. `-m2knn`
  8. `-m3` (if M3 is in)
  9. `hard_targets`
  10. `-arabizi_translit` (cut: yes)
  11. `mask_deadline`: the full model, evaluated with every `deadline_today` lexicon span replaced by a neutral token in the evaluation rows. It reports priority macro-F1 on OOF-official, `our_test` and the `deadline_shortcut` probes, which measures the "today → high" reliance ([LD-34](../PLAN.md#ld-34)).
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: per arm, `run_cv` (OOF-official) + `fit_pipeline` on the full pool → `our_test`; Δ vs `full` with counts.
  3. Errors: none beyond P2.8's.
  4. Tests: the `ablations` schema test in `test_reports_schema.py` (≥ 9 arms, each with category and priority macro-F1 on both row sets).
  5. Implementation: one process, `CachingEncoder` shared across arms.
- **Acceptance:**
  - `python services/ai/evaluate.py --ablations` → `ablations: <≥10> arms written to reports/ablations.json`
  - `pytest services/ai/tests/e2e/test_reports_schema.py -q -k ablations` → `1 passed`
- **Hands off:** the ablation table for the report and notebook 04/05. It also gives the fairness "before/after mitigation" numbers (`-augmentation`, `-arabizi_translit` arms).
- **Notes:** each arm still uses the frozen `cv_fold` folds (whole `cv_group`s held out), never a random split.

<a id="p2-10"></a>
## P2.10 — Apply the conformal and fairness follow-up rules (ASK rate, Mondrian switch)

- [x] Done (ML batch 4): `0.0588 0.1 True` (ASK proxy with Mondrian; it was 0.319 ≤ 0.35 with global quantiles, so alpha_priority stays 0.10; Mondrian fired for category: AR 0.813 / Arabizi 0.719 < 0.85, EN 0.949). `MondrianByLang` built; `pytest services/ai/tests/unit/test_conformal.py -q` → `5 passed`.
- **Goal:** apply the two config-only rules the brief prescribes, logged as decisions:
  - `alpha_priority`: 0.10 → 0.15 if the ASK-proxy rate on `our_test` is above 35 % (§6.1 #8)
  - `mondrian_by_lang` on if AR or Arabizi coverage is below 0.85 while EN is at least 0.90 (§3.5)
- **Depends on:** P2.8
- **Est / Cut:** 0.75 h
  - Rules: Cut: no.
  - **The `MondrianByLang` wrapper is cut: yes.** It is built only if the rule fires.
- **Files:**
  - `config/train.yaml` (`alpha.priority`, `conformal.mondrian_by_lang`)
  - `services/ai/campuspulse_ai/adapters/uncertainty/conformal.py` (`MondrianByLang`, conditional)
  - `services/ai/tests/unit/test_conformal.py` (+1 test if built)
- **Interfaces:**
  ```python
  class MondrianByLang:       # ConformalPredictor wrapper, only if triggered
      def __init__(self, inner_by_lang: Mapping[Lang, LACConformal], fallback: LACConformal) -> None: ...
      def predict_set_for(self, p: ProbVector, lang: Lang) -> PredictionSet: ...
  ```
- **Config keys:** `ask_rate_max`, `alpha_priority_fallback`, `mondrian.*` ([P1.4](P1_scored_core.md#p1-4)); `FrozenConfig.conformal.mondrian_by_lang`.
- **Steps:**
  1. Read the ASK proxy and the per-language coverage from `reports/coverage.json`.
  2. Apply the rules.
  3. Run `python services/ai/train.py --retune`, then `evaluate.py --coverage`.
  4. Log both decisions with their numbers. The report discloses that `our_test` informed these two config switches, as the brief prescribes.
- **Acceptance:**
  - `python -c "import json;c=json.load(open('reports/coverage.json'));print(c['ask_proxy_rate'],c['config']['alpha_priority'],c['config']['mondrian_by_lang'])"` → three values consistent with the rules
  - If built: `pytest services/ai/tests/unit/test_conformal.py -q` → `5 passed`
- **Hands off:** the final conformal config for P3's `DecisionPolicy`.
- **Notes:** no other value may be tuned on `our_test`.

<a id="p2-11"></a>
## P2.11 — M3 fine-tune, time-boxed (cut-order #4)

> **Not built: user decision [UD-4](../PLAN.md#ud-4).** Kept below for reference and future work only. `"m3"` is never in `ensemble.members`.

- [ ] Done
- **Goal:** test whether a CPU fine-tune adds ≥ 0.01 OOF category macro-F1 (§3.6). Otherwise cut it with no code change (`"m3"` absent from `members`).
- **Depends on:** P2.7, P2.8
- **Est / Cut:** **4 h time box** ([LD-6](../PLAN.md#ld-6)). **Default decision: cut** ([LD-32](../PLAN.md#ld-32)): fine-tuning on 42 unique texts is low value. Start it only if every other P2 task is done and time remains, and include it only if OOF shows the gain. · **Cut: yes (cut-order #4)**. Scheduled last in P2, so it only spends leftover time.
- **Files:**
  - `services/ai/campuspulse_ai/adapters/models/transformer_ft.py`
  - `services/ai/tests/unit/test_transformer_ft.py`
  - `models/frozen/v1/m3/` (fetched tier, only if included)
- **Interfaces:**
  ```python
  class TransformerFT:      # ProbabilisticClassifier, name = "m3"; joint 6+3 heads, soft cross-entropy
      def __init__(self, target: Literal["category", "priority"], backbone_id: str, revision: str, epochs: int, lr: float, max_tokens: int, seed: int) -> None: ...
      def fit(self, texts, y, sample_weight=None) -> None: ...      # imports torch lazily (train machine only)
      def save(self, dir: Path) -> None: ...                         # exports ONNX int8 (same quantize_dynamic recipe as P1.6)
      @classmethod
      def load(cls, dir: Path) -> "TransformerFT": ...               # onnxruntime only; never imports torch
  ```
- **Config keys:** `config/train.yaml` `m3.{min_gain, max_predict_s_per_1000, time_box_h, backbone, epochs, lr}`.
  - **Needs decision:** backbone default = the encoder **not** chosen in P2.6, for error diversity (RESEARCH §2b).
  - `ensemble.members` gets `m3` only if every condition holds.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: 5 OOF fine-tunes + 1 full fine-tune (about 1–2 h CPU in total, RESEARCH §2b).
  3. Errors: the time box expires → stop, record "cut (time box)".
  4. Tests:
     - `test_fit_predict_tiny` (`@pytest.mark.train`)
     - `test_load_does_not_import_torch` (`@pytest.mark.artifacts`, subprocess `sys.modules` check)
  5. Implementation, then the decision:
     - include only if ΔOOF category macro-F1 ≥ `min_gain`
     - and `predict.py` on 1,000 rows stays < 60 s
     - and the fetched tier stays ≤ 200 MB
     - and the Render memory budget holds: `python scripts/no_network.py services/ai/predict.py --input data/raw/validation.csv --output .tmp/p_m3.csv --debug` with `m3` loaded prints `peak_rss_mb`; that number plus the empty API's `/health` `rss_mb` from [P0.11](P0_foundations.md#p0-11) must be ≤ 400
     - and, if included, P4's Render memory test [X4.6](P4_product_backend.md#exit-criteria) must also pass with `m3` loaded; otherwise cut #4 ([LD-6](../PLAN.md#ld-6))
- **Acceptance:**
  - `python services/ai/train.py --with-m3 --cv-only --report .tmp/cv_m3.json` → prints `m3 decision: include=<True|False> (ΔOOF cat macro-F1=<±x.xxx>; predict_1000=<s> s; download_mb=<n>; rss_mb=<n>)`
  - PLAN.md decisions log has the M3 row
- **Hands off:** the M3 decision. If included: the `m3` member, the `m3/` artifact in the release, and a benchmark row. If cut: a `cut` row in the benchmark.
- **Notes:** §4.8 #4. Cutting means removing `"m3"` from `config.json` `ensemble.members`, so `TransformerFT` is never loaded.

<a id="p2-12"></a>
## P2.12 — Write notebooks 01–05 (thin) and `run_notebooks.py`

- [x] Done (ML batch 4): `python scripts/run_notebooks.py` → `5/5 executed`; `--check-reads-only` → `OK: notebooks read only reports/` (18 cells).
- **Goal:** the five notebooks the SPEC checklist requires. They are thin loaders of `reports/*` (≤ 30 cells in total, §6.2 flag 10) and never go stale.
- **Depends on:** P2.8, P2.9, P2.10
- **Est / Cut:** 1.5 h · Cut: no
- **Files:**
  - `notebooks/01_eda.ipynb` (reads `reports/eda.json`)
  - `notebooks/02_benchmark.ipynb` (`benchmark.md`, `metrics.json`, `confusions/*.json`: table + confusion heatmaps)
  - `notebooks/03_uncertainty_conformal.ipynb` (`coverage.json` coverage/set-size and reliability plot + a mapie 1.5.0 cross-check on `conformal_scores.npz`)
  - `notebooks/04_robustness_error_analysis.ipynb` (`metrics.json` robustness section, `errors.json` grouped by (true, pred, lang), `ablations.json`)
  - `notebooks/05_fairness.ipynb` (`fairness.json` + the before/after arms)
  - `scripts/run_notebooks.py`
- **Interfaces:**
  ```python
  # python scripts/run_notebooks.py [--check-reads-only]   # nbclient executes in place; --check-reads-only greps that every open()/read_* path starts with "reports/" (+ ../reports/)
  ```
- **Config keys:** none.
- **Steps:**
  1. Define one shared plotting helper cell per notebook. Use the matplotlib default palette; no styling work.
  2. Write each notebook.
  3. Execute.
  4. Commit the executed outputs.
- **Acceptance:**
  - `python scripts/run_notebooks.py` → `5/5 executed`
  - `python scripts/run_notebooks.py --check-reads-only` → `OK: notebooks read only reports/`
- **Hands off:** notebooks for the submission. P6 re-runs `run_notebooks.py` after the final freeze.
- **Notes:** **Files added:** `scripts/run_notebooks.py` (moved to P2 by lead decision; P6 reuses it; [LD-23](../PLAN.md#ld-23)).

<a id="p2-13"></a>
## P2.13 — Freeze `v1-rc2` and run the P2 exit gate

- [ ] Done — **partly (ML batch 4)**: v1-rc2 frozen locally (sha 9a379d97c0cd), `evaluate.py --all`, notebooks, `predict.py` offline → `wrote 62 rows`, `reports/predictions_val_check.csv` written. Not done by design: the `models-v1-rc2` GitHub pre-release (the encoder did not change, so the asset is the rc1 tarball) and the CI check (no push).
- **Goal:** the scored core is complete (SPEC §12: "The scored core is complete after Phase 2"). The final pool, encoder, weights, conformal and M3 decision are frozen, released and evaluated with one command.
- **Depends on:** P2.4, P2.6, P2.7, P2.9, P2.10, P2.11 (or its cut), P2.12
- **Est / Cut:** 1 h · Cut: no
- **Files:** `models/frozen/v1/**`, `reports/**`, the `models-v1-rc2` pre-release, `docs/PLAN.md` (numbers + decisions)
- **Interfaces / Config keys:** none new.
- **Steps:**
  1. `python scripts/check_leakage.py`
  2. `python services/ai/train.py --out models/frozen/v1 --report reports/cv_p2.json`
  3. `python services/ai/evaluate.py --all`
  4. `python scripts/run_notebooks.py`
  5. Repackage and release `models-v1-rc2` ([P1.19](P1_scored_core.md#p1-19) recipe).
  6. Re-run the P1 exit checks: the predict path must still pass after retraining.
  6b. Copy `.tmp/pred_val.csv` to `reports/predictions_val_check.csv` and commit it. This is the same-machine regression snapshot that [X3.5](P3_intelligence.md#exit-criteria) and [X4.8](P4_product_backend.md#exit-criteria) compare against.
  7. Paste the headline numbers into PLAN.md.
- **Acceptance:**
  - The four P2 exit criteria give their stated outputs.
  - `python scripts/no_network.py services/ai/predict.py --input data/raw/validation.csv --output .tmp/pred_val.csv` → `wrote 62 rows`
  - `git ls-files reports/predictions_val_check.csv` → `reports/predictions_val_check.csv`
  - `gh run list --workflow ci.yml --limit 1 --json conclusion -q ".[0].conclusion"` → `success`
- **Hands off to P3:** `v1-rc2` (`CURRENT=v1`), `reports/*`, `config.json` thresholds for `DecisionPolicy`, `probes.csv`, and `oof.npz` for P3's `tau_injection` re-run once the exemplars grow ([LD-27](../PLAN.md#ld-27)).

## P2 risks and fallbacks

Tied to SPEC §12 and §4.8. M3 is cut-order #4. P2-evaluation is never cut, so its fallbacks only simplify.

| Risk | Likelihood / impact | Fallback |
| --- | --- | --- |
| Human check is slower than 3.5 h | H / delays the final pool | Shrink to the §6.2 flag-3 minimums (≥ 2 paraphrases per scenario, ≥ 40 new scenarios). Train on whatever is reviewed. The report states the counts. Never train unreviewed rows. |
| OpenRouter key or budget not ready on Tue 3 Nov | M / no LLM drafts | Hand-write paraphrases for the scenarios with the weakest OOF (from `errors.json`). The rule-based Arabizi rows already exist. Volume drops, protocol unchanged. |
| LLM drafts in poor Jordanian dialect | M / noisy AR training data | Fix during review, or delete the row. Prefer the tier-2 pin for drafting. Labels are always human-assigned. |
| M3 gains < 0.01, or breaks the download/RSS budgets | H / none (expected) | **Cut-order #4:** leave `m3` out of `members`. The benchmark row reads "cut", and the decision is logged. |
| Conformal under-covers AR/Arabizi | M / fairness narrative | `mondrian_by_lang` (config) plus the `MondrianByLang` wrapper (cut-flagged; built only if triggered). Otherwise report the gap honestly (§6.2 flag 5). |
| ASK-proxy rate too high | M / P3 demo asks too often | `alpha_priority = 0.15` via `--retune` (§6.1 #8). |
| Ablations too slow | L / time | Arms share one `CachingEncoder`, so only LR/kNN refits repeat. Drop the cut-flagged `-arabizi_translit` arm first. k = 5 never changes. |
| Encoder decision lands late | M / P4 migration dimension | Both candidates are 384-d, so only §3.17 fallback (2) changes the dimension. Decide it in P2.6 at the latest. |
| **Thin data** (42 unique texts, 30 groups, 15 AR scenarios, 0 Arabizi) | certain / wide error bars, weak conformal guarantee | Augmentation fills the empty cells first. Every slice reports row and group counts. Coverage is stated as approximate. M3 is cut by default ([LD-32](../PLAN.md#ld-32)). |
| **"today" shortcut** learned by the priority head | high / hidden rows with "today" in low/medium, or high without it, get misclassified | `deadline_shortcut` probes (P2.5) and the `mask_deadline` ablation (P2.9) quantify it. Augmentation adds high rows without "today" and low/medium rows with it. The report states it ([LD-34](../PLAN.md#ld-34)). |
| **Arabizi slice comes only from augmentation** | certain / Arabizi numbers rest on our own rows | Reviewed Arabizi rows in training; our own test set carries hand-written Arabizi; report counts ([LD-33](../PLAN.md#ld-33)). |
| P2 overruns (19 h + 4 h box vs 2 d) | H / squeezes P3 | M3 box first (cut #4), then the `-arabizi_translit` arm, then the `MondrianByLang` build. Notebook polish is minimal by design. Exit criteria are never cut. |

## P2 decisions logged during this phase
- [x] Augmentation volumes after review: **review pending** (P2.4). Drafts: 64 paraphrases + 17 translations (claude-sonnet-5.5, 0.266 USD), 30 rule Arabizi, 390 new-scenario rows (separate writer); pre-check claude-haiku-5.5 (0.081 USD); 93 of 174 own drafts pruned as holdout neighbours
- [x] Leakage resolutions: 0 exact cross-group duplicates; LLM drafts near a holdout dropped; 65 of 78 new situations have encoder-only neighbours in our_test (listed for the reviewer)
- [ ] Probe count per style: P2.5 pending (human)
- [x] Final encoder: e5-small, revision 614241f6…, pruned int8 unchanged; OOF int8 0.777 vs fp32 0.746 (category); no fallback; dim 384 (D-016 bake-off)
- [x] Ensemble weights (D-016 fixed): category m2lr 0.5 + m2proto 0.5; priority m1/m2lr/m2knn 1/3; m1 C 2.0, m2lr C 0.5; prototype T 0.005; head T 1.0; q_category 0.779 (group rule; per language ar 0.938, en 0.668), q_priority 0.574; tau_ood 0.836, tau_injection 0.910, tau_safety 0.920, human_review_maxprob 0.534; knn.memory_min_sim 0.91
- [x] ASK-proxy rate → alpha_priority: 0.319 with global quantiles ≤ 0.35 → 0.10
- [x] Per-language coverage → mondrian_by_lang **on** for category (AR 0.813, Arabizi 0.719 < 0.85; EN 0.949)
- [x] **M3 decision:** not built (UD-4)
- [x] Headline: OOF official category 0.806 (rc1 0.490), priority 0.904; our_test pooled category 0.789 (rc1 0.710), priority 0.847; set2 category 0.674 (below rc1 0.746); our_test category EN 0.814 / AR 0.758 / Arabizi 0.530
- [ ] `models-v1-rc2` published: not in this batch (local freeze only; encoder unchanged)
- [ ] Folds appended for new groups: only into a temp file for the unreviewed arm; `data/clean/cv_folds.csv` is appended after the P2.4 review
- [x] "today" shortcut: mask_deadline priority on our_test 0.847 → 0.787; deadline_shortcut probes pending (P2.5)
