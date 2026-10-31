# P1 — Scored core

> **Status:** DRAFT — awaiting user approval. **Budget:** 2 d (ARCHITECTURE §4.0) · **Calendar:** Sun 1 – Mon 2 Nov · **Planned (not cut-flagged):** 21 h · **Cut-flagged:** ≈ 0.25 h (LocationExtractor sub-step).
>
> Conventions: [PLAN.md › Conventions](../PLAN.md#conventions). `§n` refers to [ARCHITECTURE.md](../ARCHITECTURE.md); `LD-n` and `OQ-n` link to the lead decisions and open questions in [PLAN.md](../PLAN.md). Tick `- [ ] Done` under each task as you finish it, and tick this phase's decision log at the bottom.

**Goal:** the 50-point macro-F1 path plus the 20-point reproducibility path. This is one `TriageCore` that `train.py` freezes and `predict.py` runs offline on CPU from `pip install -r services/ai/requirements.txt` plus a one-time model fetch. Scenario-held-out CV numbers are reported from day one.

**Phase contract (§4.2):**
- **Inputs:** everything P0 hands off.
- **Hands to P2:**
  - **Preprocessing and guards:** `adapters/preprocess/*`; `guards/injection.py` (`strip_regex_only`); `guards/safety.py` (danger + distress lexicons); `guards/gibberish.py`
  - **Encoder:** `frameworks/cli/export_encoder.py` (torch → ONNX int8 + parity report); `adapters/models/encoder.py` (`OnnxEncoder`)
  - **Models:** `adapters/vectors/local_numpy.py` (`LocalNumpyVectorStore`); `adapters/models/{tfidf_lr,embed_lr,knn,ensemble,priority_head,evidence,ood,soft_targets}.py`; `adapters/uncertainty/conformal.py`
  - **Application and composition:** `application/services/{triage_core,priority_finalizer}.py`; `application/use_cases/batch_predict.py`; `composition/offline.py`
  - **CLIs and artifacts:** `frameworks/cli/{train,predict}.py`; `adapters/artifacts/io.py`; `models/frozen/v1/` (committed small artifacts + `CURRENT`); `scripts/fetch_models.py`
  - **Data:** `data/our_test/our_test.csv` (authored first, ≥ 60 rows); `data/augmented/` schema with the rule-based Arabizi rows only

<a id="exit-criteria"></a>
**Exit criteria (SPEC §12 + §4.2 invariants, as checks):**
1. **Offline predict on validation:**
   - `python scripts/no_network.py services/ai/predict.py --input data/raw/validation.csv --output .tmp/pred_val.csv` → stdout contains `wrote 62 rows`, exit 0
   - `python scripts/validate_predictions.py --input data/raw/validation.csv --pred .tmp/pred_val.csv` → `OK: 62 rows; header request_id,category,priority; labels valid; order preserved; utf-8 no BOM; LF`
2. **CV macro-F1 reported:** `python -c "import json;d=json.load(open('reports/cv_p1.json'));print(d['category']['macro_f1_oof_official'],d['priority']['macro_f1_oof_official'])"` → two floats in (0, 1]
3. **Tests pass,** with artifacts fetched:
   - `pytest services/ai/tests -m "not train and not supabase" -q` → `0 failed`
   - CI green, including the new `artifacts` job
4. **Invariants (§4.2):** `pytest services/ai/tests/invariants services/ai/tests/test_architecture.py -q` → `0 failed` (URGENT-invariance, memory isolation in its P1 form, offline import graph).

**Order:**
- P1.0 (own test set) comes first, by brief rule (§6.1 #2).
- Then: preprocessing → config/artifact plumbing → guards → encoder → vector store → data/CV → models → core → train → predict → invariants → package.
- Each task leaves `pytest` green.

<a id="p1-0"></a>
## P1.0 — Hand-write our own test set before any model exists

- [ ] Done
- **Goal:** an honest holdout of new scenarios, hand-written by the developer (no LLM, which is a different method from the LLM-drafted augmentation) and committed before `train.py` exists (§6.1 #2, SPEC §6.1).
- **Depends on:** [P0.12](P0_foundations.md#p0-12)
- **Est / Cut:** 3 h (human writing; can start while [P0.11](P0_foundations.md#p0-11) deploys run) · Cut: no
- **Files:**
  - `data/our_test/our_test.csv`, columns exactly `request_id,text,lang,category,priority,author_method,notes`
  - `scripts/validate_dataset.py`
  - `config/datasets.yaml`
- **Interfaces:**
  ```python
  # scripts/validate_dataset.py
  def validate(path: Path, kind: Literal["our_test", "augmented", "probes"], spec: DatasetSpec) -> ValidationReport: ...
  # CLI: python scripts/validate_dataset.py --kind {our_test|augmented|probes} <csv>  → one "OK ..." line, or one line per error and exit 1
  ```
- **Config keys (`config/datasets.yaml`):**
  - `our_test.min_rows: 60`
  - `our_test.min_per_cell: 3` (6 categories × 3 priorities = 18 cells)
  - `our_test.min_per_lang: {en: 20, ar: 20, arabizi: 10}`
  - `augmented.columns` (§4.2 schema), `augmented.arabizi_variants: 2`
  - `probes.min_rows: 40`, `probes.styles` ([P2.5](P2_data_rigor.md#p2-5))
- **Steps:**
  1. Interface: the schema and kinds above.
  2. Inputs/outputs:
     - read with `utf-8-sig`
     - `request_id` matches `^OT-\d{3}$`
     - labels exactly as the `Category`/`Priority` values
     - `lang ∈ {en, ar, arabizi}`
     - `author_method == "hand"`
  3. Errors: one line per violation, then exit 1.
  4. Tests: none. The acceptance line exercises the validator, and a unit test is not worth it for a script.
  5. Implementation and authoring:
     - Write ≥ 60 **new** scenarios following `docs/reference/label_decisions.md`.
     - Every `notes` cell names the rule used, e.g. `low=info request`, `high=same-day deadline`, `medium=teaching-room equipment`.
     - Include Jordanian dialect, Arabizi, and 6 rows carrying official-style wrappers (`URGENT:`, `مرحبا،`).
     - The validator rejects rows whose `clean_data.normalize(core, lang)` equals an official `text_norm`. It imports `scripts/clean_data.py` read-only via `importlib`.
     - Commit **before** P1.10 starts.
- **Acceptance:**
  - `python scripts/validate_dataset.py --kind our_test data/our_test/our_test.csv` → `OK our_test: <N≥60> rows; cells 18/18 (min ≥3); langs en=<≥20> ar=<≥20> arabizi=<≥10>; 0 overlaps with official text_norm`
  - `git log -1 --format=%cI -- data/our_test/our_test.csv` → a timestamp earlier than `git log --reverse --format=%cI -- models/frozen` (first line). Both are recorded in the decisions log.
- **Hands off:** the holdout, read only by `evaluate.py` ([P2.8](P2_data_rigor.md#p2-8)) and used as base rows for probes ([P2.5](P2_data_rigor.md#p2-5)).
- **Notes:**
  - Non-negotiable: never trained on. `load_pool` refuses the path (P1.8).
  - SPEC asks for ~120 rows. The brief's floor is 60 (§6.2 flag 3). Write more if the time box allows.
  - **Files added:** `scripts/validate_dataset.py`, `config/datasets.yaml`.

<a id="p1-1"></a>
## P1.1 — Strip wrappers and normalize text with byte-for-byte parity to `clean_data.py`

- [ ] Done
- **Goal:** the package reproduces `core` and `text_norm` for all 432 official rows exactly, and sets `stated_urgency` from wrappers and markers (§3.7).
- **Depends on:** [P0.4](P0_foundations.md#p0-4)
- **Est / Cut:** 0.75 h · Cut: no
- **Files:**
  - `config/lexicons/wrappers.yaml`
  - `services/ai/campuspulse_ai/adapters/preprocess/wrappers.py`
  - `services/ai/tests/unit/test_normalizer_parity.py`
- **Interfaces:**
  ```python
  class WrapperStripper:
      def __init__(self, prefixes: Sequence[str], suffixes: Sequence[str], urgency_markers: Sequence[str], urgent_regex: str) -> None: ...
      @classmethod
      def from_yaml(cls, path: Path) -> "WrapperStripper": ...
      def strip(self, raw: str) -> StripResult: ...            # same iterative longest-first loop as clean_data.strip_wrappers
  def collapse_ws(s: str) -> str: ...                          # == clean_data.collapse_ws
  def script_lang(text: str) -> Literal["ar", "en"]: ...        # == clean_data.detect_lang
  def normalize_text(core: str, lang: Literal["ar", "en"]) -> str: ...   # == clean_data.normalize (same diacritics regex, char map, PUNCT)
  ```
- **Config keys (`wrappers.yaml`):**
  - `prefixes` and `suffixes`: the exact strings of `clean_data.{EN,AR}_{PREFIXES,SUFFIXES}`
  - `urgency_markers: ["URGENT", "عاجل", "!!!"]`
  - `urgent_regex: "(?i)^urgent[:!\\s]*"`
  - `prefix_variants: true`: known prefixes also match case-insensitively with a trailing `,`/`!`/`:`/`.` variant. Exact matches are tried first, so the 432 official rows are unaffected ([LD-35](../PLAN.md#ld-35)).
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: a raw string → `StripResult(prefix, suffix, core, stated_urgency)`.
  3. Errors: none here. Empty input is rejected by `DefaultNormalizer` (P1.3).
  4. Tests:
     - `test_core_parity_432`
     - `test_text_norm_parity_432`
     - `test_stated_urgency_matches_has_urgent_marker` (27 rows: 23 train + 4 val)
     - `test_lowercase_urgent_prefix_stripped_and_flagged`
     - `test_yaml_lists_equal_clean_data_constants`
     - `test_unseen_wrappers_stripped[...]` (4 cases, core must be `The bus is late`): `urgent: The bus is late`, `URGENT The bus is late`, `Hello! The bus is late`, `hi team, The bus is late` (data audit F6)
     - `test_urgent_variants_set_stated_urgency`
  5. Implementation: copy the regex and char map literally.
- **Acceptance:** `pytest services/ai/tests/unit/test_normalizer_parity.py -q` → `10 passed`
- **Hands off:** `WrapperStripper`, `normalize_text`, `script_lang`.
- **Notes:**
  - `clean_data.py` is not refactored; its only edit is the [P0.3c](P0_foundations.md#p0-3c) print guard (§3.7).
  - The extra case-insensitive regex never fires on official data, and the parity tests prove it.

<a id="p1-2"></a>
## P1.2 — Add language ID and Arabizi transliteration

- [ ] Done
- **Goal:** a conservative Arabizi detector (zero false positives on official English rows) and a lexicon-first transliterator. Models see `translit | original` (§3.7, SPEC §5.1[2]).
- **Depends on:** P1.1
- **Est / Cut:** 1.5 h · Cut: no. The lexicon starts at ≥ 200 entries and grows to ~300 by the end of P2.
- **Files:**
  - `config/lexicons/arabizi.yaml`
  - `services/ai/campuspulse_ai/adapters/preprocess/{langid,arabizi}.py`
  - `services/ai/tests/unit/{test_langid,test_arabizi}.py`
  - `services/ai/tests/fixtures/arabizi_golden.csv` (≥ 20 `arabizi,arabic` pairs, checked by the developer)
- **Interfaces:**
  ```python
  class LangIdentifier:
      def __init__(self, lexicon: frozenset[str], guard_tokens: frozenset[str], signal_digits: frozenset[str],
                   min_digit_tokens: int, min_lexicon_hits: int) -> None: ...
      def identify(self, text: str) -> Lang: ...   # Arabic-script ratio → AR; Latin + (≥min_digit_tokens inner-digit tokens OR ≥min_lexicon_hits hits) AND 0 guard hits → ARABIZI; else EN
  class ArabiziTransliterator:
      def __init__(self, lexicon: Mapping[str, str], digraphs: Mapping[str, str], charmap: Mapping[str, str]) -> None: ...
      def transliterate(self, text: str) -> str: ...      # whole-token lexicon, then digraphs (sh kh gh th dh), then char map (2→ء 3→ع 5→خ 6→ط 7→ح 8→ق 9→ص …)
      def model_text(self, original: str) -> str: ...     # f"{translit} | {original}"
  ```
- **Config keys (`arabizi.yaml`):**
  - `lexicon` (≥ 200 entries: `mesh/msh→مش`, `bade→بدي`, `wein→وين`, `el→ال`, …)
  - `digraphs`, `charmap`
  - `signal_digits: ["2","3","5","6","7","8","9"]`
  - `min_digit_tokens: 2`, `min_lexicon_hits: 1`
  - `guard_tokens: ["2nd","3rd","24/7","b4","4u","mp3","covid19", …]`
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: str → `Lang`; str → str.
  3. Errors: none.
  4. Tests:
     - `test_langid.py`: `test_zero_arabizi_on_432_official`, `test_ar_and_en_match_clean_lang`, `test_golden_arabizi_detected`, `test_english_with_digits_stays_en` (e.g. `I got a 2nd notice at 3pm`)
     - `test_arabizi.py`: `test_mesh_3arif` (`mesh 3arif` → `مش عارف`), `test_golden_pairs_exact`, `test_model_text_format`
  5. Implementation. Lexicon entries are drafted with LLM help and corrected by the developer, disclosed in the README Disclosures.
- **Acceptance:** `pytest services/ai/tests/unit/test_langid.py services/ai/tests/unit/test_arabizi.py -q` → `7 passed`
- **Hands off:** `LangIdentifier`, `ArabiziTransliterator`.
- **Notes:**
  - A false Arabizi positive on a hidden English row is the only way this step can cost macro-F1, so it errs toward EN (§3.7).
  - Per the brief's literal rule, a single guard-token hit vetoes Arabizi.
  - **The official data has 0 Arabizi rows, and `lang` in the CSVs is script-only** (`lang_script`, [P0.3b](P0_foundations.md#p0-3b)). The positive tests therefore rely on the golden fixture and the augmentation rows (P1.9 rule-based, [P2.3](P2_data_rigor.md#p2-3) LLM-drafted). The package `LangIdentifier` is the only source of the `is_arabizi`/ARABIZI label ([LD-33](../PLAN.md#ld-33)).

<a id="p1-3"></a>
## P1.3 — Assemble `DefaultNormalizer` (+ location extraction)

- [ ] Done
- **Goal:** the `Normalizer` port implementation that every path uses.
- **Depends on:** P1.1, P1.2
- **Est / Cut:** 0.75 h
  - Normalizer: Cut: no.
  - **`LocationExtractor` sub-step: Cut: yes.** It is consumed only online (incidents, P4). If P1 overruns, it moves to P4 and `location` stays `None` offline.
- **Files:**
  - `services/ai/campuspulse_ai/adapters/preprocess/{normalizer,location}.py`
  - `config/lexicons/gazetteer.yaml`
  - `services/ai/tests/unit/test_normalizer.py`
- **Interfaces:**
  ```python
  class LocationExtractor:
      def __init__(self, buildings: Mapping[str, Sequence[str]], room_regex: str) -> None: ...
      def extract(self, text: str) -> Location | None: ...         # "M 214" → Location("M", "M 214", "extracted")
  class DefaultNormalizer:                                          # implements Normalizer
      def __init__(self, wrappers: WrapperStripper, langid: LangIdentifier, arabizi: ArabiziTransliterator,
                   location: LocationExtractor | None, max_tokens: int) -> None: ...
      def normalize(self, raw: str, picked_location: Location | None = None) -> NormalizedRequest: ...
  ```
- **Config keys:**
  - `FrozenConfig.guards.max_tokens` (256)
  - `gazetteer.yaml`: `buildings`, `room_regex`. The fictional building codes must match P4's `buildings` seed.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs:
     - `core` is truncated to `max_tokens` whitespace tokens (`truncated=True` when cut)
     - `text_norm = normalize_text(core, script_lang(raw))`
     - `model_text` = translit + original if ARABIZI, else `text_norm`
     - a picked location beats an extracted one
  3. Errors: `InvalidInput` on empty or whitespace-only `raw`.
  4. Tests:
     - `test_empty_raises_invalid_input`
     - `test_truncation_flag`
     - `test_arabizi_model_text_has_both`
     - `test_picked_location_wins`
     - `test_room_extraction`
     - `test_official_text_norm_unaffected_by_location`
  5. Implementation.
- **Acceptance:** `pytest services/ai/tests/unit/test_normalizer.py -q` → `6 passed` (`4 passed` if the location sub-step is deferred, and the deferral is logged)
- **Hands off:** a `Normalizer` for `TriageCore` (P1.15) and `load_pool` (P1.8).
- **Notes:** `stated_urgency` is set here and consumed only by P3's gaming detector. It is never a model feature (§3.8).

<a id="p1-4"></a>
## P1.4 — Add `FrozenConfig`, `config/train.yaml` and the `ArtifactStore` (manifest + sha256)

- [ ] Done
- **Goal:** one validated schema for every learned value (§1.6) and checksummed artifact I/O (§3.12). All later tasks read thresholds from here, never from literals.
- **Depends on:** [P0.4](P0_foundations.md#p0-4)
- **Est / Cut:** 1 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/config/frozen.py`
  - `services/ai/campuspulse_ai/adapters/artifacts/io.py`
  - `config/train.yaml`
  - `config/hand_tuned.yaml`
  - `services/ai/tests/unit/{test_frozen_config,test_manifest}.py`
- **Interfaces:**
  ```python
  class FrozenConfig(BaseModel):            # pydantic, extra="forbid"; mirrors §1.6 incl. the lead-decision keys below
      schema_version: Literal[1]; artifact_version: str; trained_at: str; seed: int
      encoder: EncoderCfg; ensemble: EnsembleCfg; knn: KnnCfg; priority_head: HeadCfg; conformal: ConformalCfg
      thresholds: ThresholdsCfg; guards: GuardsCfg; cv: CvCfg; m1: M1Cfg; m2lr: M2LrCfg; priors: PriorsCfg
      @classmethod
      def load(cls, path: Path) -> "FrozenConfig": ...    # ArtifactVersionMismatch on schema/validation error
      def save(self, path: Path) -> None: ...             # sorted keys, indent 2, LF
  class FileArtifactStore:                  # implements ArtifactStore
      def write_manifest(self, model_dir: Path, files: Sequence[Path]) -> Manifest: ...
      def load_manifest(self, model_dir: Path) -> Manifest: ...   # verifies every listed file's sha256
  ```
- **Config keys:**
  - Everything in §1.6.
  - **Added by lead decision** (default in brackets; [LD-10](../PLAN.md#ld-10)):
    - `guards.gibberish_min_tokens` [2]
    - `guards.gibberish_min_letter_ratio` [0.5]
    - `guards.injection_sentence_strip_ratio` [0.6, from §3.10]
    - `thresholds.tau_safety` [tuned in P1.16]
    - `m1.{char_ngram: [2,5], word_ngram: [1,2], C}`
    - `m2lr.C`
    - `priors.{category, priority}` [pool label frequencies]
    - `encoder.query_prefix` = `"query: "` for e5
    - `llm.w_llm` [0.5], `llm.prompt_version` ["v1"], `explain.max_occlusions` [20], `knn.memory_min_sim` [0.80] ([LD-10](../PLAN.md#ld-10))
  - `config/train.yaml` (training **inputs**; `config.json` holds the outputs):
    - `seed: 42`, `cv.k: 5`
    - `alpha: {category: 0.10, priority: 0.10}`
    - `grids: {m1_C: [0.5,1,2,4,8], m2lr_C: [0.5,1,2,4,8], weight_step: 0.1}`
    - `tau_ood_percentile: 5`, `tau_margin: 0.02`
    - `human_review_min_acc: 0.6`
    - `ask_rate_max: 0.35`, `alpha_priority_fallback: 0.15`
    - `mondrian: {min_cov_minority: 0.85, min_cov_en: 0.90}`
    - `m3: {min_gain: 0.01, max_predict_s_per_1000: 60, time_box_h: 4, max_download_mb: 200, max_rss_mb: 400}`
  - `config/hand_tuned.yaml`: `tau_faq: 0.75`, `tau_inc: 0.80`. `train.py` reads it and copies the values into `config.json`; [P4.5](P4_product_backend.md#p4-5) and [P4.10](P4_product_backend.md#p4-10) edit it ([LD-11](../PLAN.md#ld-11)).
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: JSON ↔ model; directory → `Manifest`.
  3. Errors:
     - `ArtifactMissing` (message includes `python scripts/fetch_models.py`)
     - `ArtifactChecksumMismatch`
     - `ArtifactVersionMismatch`
     - any `thresholds.*` ≤ 0 → `ArtifactVersionMismatch("thresholds not trained")` (§1.6)
  4. Tests:
     - `test_frozen_config.py`: `test_rejects_zero_thresholds`, `test_roundtrip_identical`, `test_unknown_member_in_weights_rejected`, `test_weights_sum_to_one`
     - `test_manifest.py`: `test_write_then_load_ok`, `test_tampered_file_raises_checksum_mismatch`, `test_missing_file_raises_artifact_missing_with_fetch_hint`
  5. Implementation.
- **Acceptance:** `pytest services/ai/tests/unit/test_frozen_config.py services/ai/tests/unit/test_manifest.py -q` → `7 passed`
- **Hands off:** `FrozenConfig` for every component; `FileArtifactStore` for `train.py`, `predict.py` and `/health`.
- **Notes:**
  - Non-negotiable: no magic numbers. Thresholds live in `config.json`, and training knobs live in `config/train.yaml`.
  - **Files added:** `config/train.yaml`, `config/hand_tuned.yaml`.
  - **Decided:** `train.py` snapshots `config/lexicons/*.yaml` into `models/frozen/vN/lexicons/` (hashed by the manifest), and containers read lexicons from the model dir ([LD-12](../PLAN.md#ld-12)).

<a id="p1-5"></a>
## P1.5 — Build the offline guards: gibberish, injection (regex strip) and safety (danger + distress)

- [ ] Done
- **Goal:** the guards `predict.py` needs.
  - Injection strips manipulative spans, with zero false positives on official data.
  - Danger sets `safety=True`, and the finalizer then floors priority to high.
  - Distress and gibberish are flags only in batch (§2.0).
- **Depends on:** P1.3, P1.4
- **Est / Cut:** 1.25 h · Cut: no
- **Files:**
  - `config/lexicons/{injection,safety}.yaml`
  - `services/ai/campuspulse_ai/adapters/guards/{gibberish,injection,safety}.py`
  - `services/ai/tests/invariants/test_injection.py`
  - `services/ai/tests/unit/{test_safety,test_gibberish}.py`
  - `services/ai/tests/fixtures/{demo_injections.txt,distress_fixtures.txt}` (10 lines each, EN/AR/Arabizi)
- **Interfaces:**
  ```python
  class GibberishGuard:      # Guard, name = "gibberish"
      def __init__(self, min_tokens: int, min_letter_ratio: float) -> None: ...
  class InjectionGuard:      # Guard, name = "injection"
      def __init__(self, patterns: Sequence[re.Pattern[str]], mode: Literal["strip_regex_only", "full"],
                   sentence_strip_ratio: float, exemplars: ExemplarSimilarity | None = None, tau: float | None = None) -> None: ...
  class SafetyGuard:         # Guard, name = "safety"
      def __init__(self, danger: Sequence[re.Pattern[str]], distress: Sequence[re.Pattern[str]],
                   exemplars: ExemplarSimilarity | None = None, tau_safety: float | None = None) -> None: ...
  class StoreExemplarSimilarity:   # implements ExemplarSimilarity over a VectorStore collection (used from P1.15 on)
      def __init__(self, store: VectorStore, encoder: SentenceEncoder) -> None: ...
  def compile_bank(path: Path, key: str) -> list[re.Pattern[str]]: ...
  ```
- **Config keys:**
  - `injection.yaml`:
    - `patterns` (EN/AR/Arabizi: `ignore (all|previous) instructions`, `system prompt`, `you are now`, `mark (this|it) as high`, `set priority`, `تجاهل التعليمات`, `خليها عالية`, role-play markers, control-char runs)
    - `exemplars` (a seed of ≥ 10 sentences, embedded into `injection_exemplars` by P1.16; P3 grows them to ~50)
  - `safety.yaml`: `danger`, `distress`, `exemplars.{danger,distress}`
  - `FrozenConfig.guards.*`, `thresholds.{tau_safety,tau_injection}`
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: `NormalizedRequest` → `GuardVerdict(kind, matched_spans, stripped_text, score)`.
  3. Errors: guards never raise. An internal exception becomes verdict `none` plus `logging.warning`.
  4. Tests:
     - `test_injection.py` (P1 subset of §3.10): `test_zero_regex_hits_on_432_official`, `test_ten_demo_injections_flag`, `test_strip_span_and_sentence_rule`, `test_never_raises_on_fuzz`
     - `test_safety.py`: `test_official_safety_scenarios_are_danger` (TR-S03 stuck lab door, TR-S19/TR-S29 leak near electricity, TR-S31 students stranded), `test_zero_danger_on_non_high_official_rows`, `test_distress_fixtures_flag_and_zero_on_official`
     - `test_gibberish.py`: `test_flags_noise` (`""`, `"???"`, `"asdf;;;;"`), `test_zero_gibberish_on_432_official`
  5. Implementation.
- **Acceptance:** `pytest services/ai/tests/invariants/test_injection.py services/ai/tests/unit/test_safety.py services/ai/tests/unit/test_gibberish.py -q` → `9 passed`
- **Hands off:** three `Guard`s and `StoreExemplarSimilarity` for `build_offline`. Full injection mode is P3's ([P3.5](P3_intelligence.md#p3-5)).
- **Notes:**
  - In batch, a false danger hit would raise a hidden row to high. That is why every non-high official row must have zero hits, and [P2.4](P2_data_rigor.md#p2-4) repeats the check on augmentation.
  - **Decided:** offline `SafetyGuard` decides `danger` by lexicon only. Exemplar similarity only adds `distress`, which never changes a batch label ([LD-19](../PLAN.md#ld-19)).

<a id="p1-6"></a>
## P1.6 — Export the encoder to ONNX int8 and implement `OnnxEncoder` (training machine)

- [ ] Done
- **Goal:** the single frozen encoder artifact (§3.6, §3.17) that `train.py`, `predict.py` and Render all use, with a parity report and the first local RSS number (§6.2 flag 12).
- **Depends on:** [P0.2](P0_foundations.md#p0-2) (`requirements-train.txt` installed), P1.4
- **Est / Cut:** 1.5 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/frameworks/cli/export_encoder.py`
  - `services/ai/campuspulse_ai/adapters/models/encoder.py`
  - `services/ai/tests/fixtures/fakes.py` (`HashingEncoder`)
  - `services/ai/tests/fixtures/encoder_parity.txt` (50 sentences, EN/AR/Arabizi)
  - `services/ai/tests/unit/test_onnx_encoder.py`
  - `reports/encoder_export.json`
- **Interfaces:**
  ```python
  class OnnxEncoder:            # implements SentenceEncoder
      dim: int; model_id: str
      def __init__(self, encoder_dir: Path, *, query_prefix: str, max_tokens: int, intra_op_threads: int, batch_size: int = 32) -> None: ...
      def encode(self, texts: Sequence[str]) -> list[list[float]]: ...      # prefix → tokenizers (truncate, pad) → ORT → masked mean-pool → L2
  class CachingEncoder:         # same port; dict cache keyed on text (train/CV only)
      def __init__(self, inner: SentenceEncoder) -> None: ...
  class HashingEncoder:         # tests/fixtures/fakes.py; deterministic
      def __init__(self, dim: int = 384, seed: int = 42) -> None: ...
  # python -m campuspulse_ai.frameworks.cli.export_encoder --model intfloat/multilingual-e5-small --revision <sha> --out models/frozen/v1/encoder
  ```
- **Config keys:**
  - `FrozenConfig.encoder.{model_id, revision, dim, max_tokens, query_prefix, runtime, file, pooling, normalize}`
  - `Settings.ort_intra_op_threads`
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: the export writes `encoder/{model_int8.onnx, tokenizer.json, encoder_meta.json}`. `encoder_meta.json` holds the values `train.py` copies into `config.json`'s `encoder` block.
  3. Errors: `ArtifactMissing` if the directory or file is absent. At export time, parity below threshold → exit 1.
  4. Tests:
     - `test_parity_with_fp32` (`@pytest.mark.train`): cosine(int8, sentence-transformers fp32) ≥ 0.98 on all 50 sentences
     - `test_shape_and_unit_norm` (`@pytest.mark.artifacts`)
     - `test_missing_dir_raises_artifact_missing`
     - `test_hashing_encoder_deterministic`
     - `test_caching_encoder_hits`
  5. Implementation:
     - Load with sentence-transformers at the pinned revision.
     - Export with `torch.onnx.export` (dynamic batch and sequence axes; inputs `input_ids`, `attention_mask`, and `token_type_ids` if the tokenizer emits it).
     - Quantize with `onnxruntime.quantization.quantize_dynamic(weight_type=QuantType.QInt8, per_channel=True)`. This is generic int8: **do not** use HF's CPU-specific `model_qint8_avx512_vnni.onnx`.
     - In a subprocess, measure `rss_mb_after_load` and `ms_per_batch32` with psutil.
     - Write `reports/encoder_export.json`.
     - Also export the fallback (`--model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 --out .tmp/enc_minilm`) for [P2.6](P2_data_rigor.md#p2-6).
- **Acceptance:**
  - `python -m campuspulse_ai.frameworks.cli.export_encoder --model intfloat/multilingual-e5-small --revision <pinned> --out models/frozen/v1/encoder` → prints `int8 size=<≤130> MB min_cos=<≥0.980> rss_mb_after_load=<n> ms_per_batch32=<n>`
  - `pytest services/ai/tests/unit/test_onnx_encoder.py -q -m "not train and not artifacts"` → `3 passed, 2 deselected`
  - `pytest services/ai/tests/unit/test_onnx_encoder.py -q -m "train or artifacts"` → `2 passed, 3 deselected` (training machine)
- **Hands off:** `OnnxEncoder`, `CachingEncoder`, `HashingEncoder`, the encoder directory, and `reports/encoder_export.json` (the early RSS number for §3.17).
- **Notes:**
  - Non-negotiable: torch is imported only in `export_encoder.py` and in [P2.11](P2_data_rigor.md#p2-11)'s `TransformerFT.fit`. P1.18 enforces it.
  - e5 needs the `query: ` prefix. `OnnxEncoder` applies it from config, so callers never add it.
  - If `rss_mb_after_load` is above 250 MB, raise it now, because Render's 400 MB budget would be at risk. §3.17 fallback (2) is decided in [P2.6](P2_data_rigor.md#p2-6).

<a id="p1-7"></a>
## P1.7 — Implement `LocalNumpyVectorStore` (`VectorStore` port, offline)

- [ ] Done
- **Goal:** the offline store for the frozen collections `train`, `injection_exemplars` and `safety_exemplars` (§3.18). Its contract test is reused by P4's `PgVectorStore`.
- **Depends on:** [P0.4](P0_foundations.md#p0-4), P1.4
- **Est / Cut:** 0.5 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/adapters/vectors/local_numpy.py`
  - `services/ai/tests/contracts/test_vector_store_contract.py`
- **Interfaces:**
  ```python
  class LocalNumpyVectorStore:      # implements VectorStore
      def __init__(self, dim: int, *, read_only: bool = False) -> None: ...
      @classmethod
      def load(cls, index_dir: Path, *, expected_dim: int) -> "LocalNumpyVectorStore": ...   # <coll>/embeddings.npy (float32) + <coll>/items.jsonl
      def save(self, index_dir: Path) -> list[Path]: ...
      def collections(self) -> frozenset[str]: ...
      # upsert / search / set_active / count as in §1.4; search fills VectorHit.embedding only when filters["with_embedding"] is true
  ```
- **Config keys:** `FrozenConfig.encoder.dim`.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: brute-force cosine (dot product of unit vectors); descending sim; tie-break on `id`; filters on `meta` and `active`.
  3. Errors:
     - `StoreError` on upsert into a read-only store
     - `ArtifactMissing` if collection files are missing
     - `ArtifactVersionMismatch` if `dim != expected_dim`
  4. Tests, parametrized over `[LocalNumpyVectorStore]` (P4 adds `PgVectorStore` when `SUPABASE_TEST_URL` is set):
     - `test_upsert_then_search_sim_one`
     - `test_filters`
     - `test_set_active_hides`
     - `test_dim_mismatch_raises`
     - `test_tie_break_on_id`
     - `test_save_load_roundtrip`
     - `test_with_embedding_flag` (`VectorHit.embedding` is `None` by default and filled when requested)
  5. Implementation.
- **Acceptance:** `pytest services/ai/tests/contracts/test_vector_store_contract.py -q` → `7 passed`
- **Hands off:** a `VectorStore` implementation for `ExampleIndex` (P1.11), the guards' exemplar similarity (P1.5), and P4's `VectorFAQRetriever` tests.
- **Notes:** offline isolation (§3.18). This is the only store `build_offline` may construct.

<a id="p1-8"></a>
## P1.8 — Build the training pool, soft targets and the frozen-fold splitter

- [ ] Done
- **Goal:** one function builds the training pool. It refuses holdout paths, drops unreviewed augmentation, and expands `label_flags.csv` into weighted rows. Folds come from the frozen `cv_fold` column (`data/clean/cv_folds.csv`, [P0.3a](P0_foundations.md#p0-3a)), and `cv_group` stays the leakage unit ([LD-31](../PLAN.md#ld-31)).
- **Depends on:** [P0.3](P0_foundations.md#p0-3), P1.3
- **Est / Cut:** 1 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/adapters/models/soft_targets.py`
  - `services/ai/campuspulse_ai/adapters/training/{__init__,pool,cv}.py`
  - `services/ai/tests/unit/test_soft_targets.py`
  - `services/ai/tests/invariants/test_cv_protocol.py`
- **Interfaces:**
  ```python
  @dataclass(frozen=True)
  class Pool:            # aligned tuples, one entry per training text
      request_id: tuple[str, ...]; raw: tuple[str, ...]; model_text: tuple[str, ...]; text_norm: tuple[str, ...]
      lang: tuple[Lang, ...]; lang_script: tuple[str, ...]; category: tuple[str, ...]; priority: tuple[str, ...]; cv_group: tuple[str, ...]; cv_fold: tuple[int, ...]
      source: tuple[str, ...]; scenario_id: tuple[str, ...]; is_official: tuple[bool, ...]
  def load_pool(paths: Sequence[Path], normalizer: Normalizer, *, use_augmentation: bool = True, strip_wrappers: bool = True) -> Pool: ...
  class SoftTargetExpander:
      def __init__(self, flags_csv: Path) -> None: ...
      def expand(self, pool: Pool, target: Literal["category", "priority"]) -> tuple[list[int], list[str], list[float]]: ...  # (row index, label, weight)
  def group_folds(pool: Pool, k: int) -> list[tuple[np.ndarray, np.ndarray]]: ...
       # (train_idx, test_idx) per cv_fold value 0..k-1, from the frozen column; raises InvalidInput if a row has no cv_fold
  ```
- **Config keys:** `config/train.yaml` `seed` and `cv.k`; `FrozenConfig.cv.{k, group_col, fold_col, folds_file}`.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs:
     - Official rows come from `data/clean/train_val_combined.csv`.
     - Augmented rows come from `data/augmented/*.csv`, keep only `needs_human_check == False`, inherit `cv_group` (§3.2), and get `cv_fold` by joining `cv_folds.csv` on `cv_group`.
     - `lang` is the package `LangIdentifier` label (`en`/`ar`/`arabizi`); `lang_script` comes from `train_val_features.csv` for official rows and from the script ratio for augmented rows.
     - `strip_wrappers=False` ([P2.9](P2_data_rigor.md#p2-9) ablation) feeds `text` instead of `core`.
  3. Errors: `InvalidInput` on a holdout path (`paths.is_holdout`), a missing column, or an augmented row without `source_scenario_id`.
  4. Tests:
     - `test_soft_targets.py`: `test_weights_sum_to_original_count`, `test_argmax_equals_official_label`, `test_unflagged_rows_unchanged`
     - `test_cv_protocol.py`: `test_groups_disjoint_per_fold`, `test_no_text_norm_overlap_across_folds`, `test_translation_pairs_same_side`, `test_train_refuses_holdout_paths`, `test_folds_come_from_cv_folds_csv_and_cover_6_categories`
  5. Implementation.
- **Acceptance:**
  - `pytest services/ai/tests/unit/test_soft_targets.py services/ai/tests/invariants/test_cv_protocol.py -q` → `8 passed`
  - `ruff check .` → `All checks passed!` (the banned-api rule forbids random splits)
- **Hands off:** `load_pool`, `SoftTargetExpander` and `group_folds` for `train.py` and the [P2.9](P2_data_rigor.md#p2-9) ablations.
- **Notes:**
  - Non-negotiables: scenario-held-out CV only; holdouts never trained on (§3.2).
  - Metrics always use the official hard label (§3.3).
  - **Files added:** `adapters/training/{pool,cv}.py` ([LD-21](../PLAN.md#ld-21)).

<a id="p1-9"></a>
## P1.9 — Generate rule-based Arabizi augmentation rows (human-checked)

- [ ] Done
- **Goal:** P1's only augmentation (§4.2): every Arabic core reverse-transliterated into Arabizi and checked by the developer, so Arabizi exists in training and the CSV schema is fixed.
- **Depends on:** P1.2, P1.8
- **Est / Cut:** 0.75 h (about 20 min of it is human checking) · Cut: no
- **Files:**
  - `scripts/draft_augmentation.py` (subcommand `arabizi-rule` only; no network)
  - `data/augmented/arabizi.csv`
- **Interfaces:**
  ```python
  # python scripts/draft_augmentation.py arabizi-rule --out data/augmented/arabizi.csv
  def reverse_transliterate(arabic: str, lexicon_rev: Mapping[str, str], charmap_rev: Mapping[str, str], variant: int) -> str: ...
  ```
- **Config keys:** `config/lexicons/arabizi.yaml` (reversed); `config/datasets.yaml` `augmented.arabizi_variants`.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs:
     - 15 Arabic scenarios × 2 variants ≈ 30 rows
     - columns exactly `request_id,text,lang,source,source_scenario_id,cv_group,needs_human_check,author_method,category,priority`
     - `source=arabizi_rule`, `author_method=rule`, `lang=arabizi`, `needs_human_check=True`
     - labels and `cv_group` copied from the source scenario
  3. Errors: refuses to overwrite reviewed rows (`needs_human_check=False`) without `--force`.
  4. Tests: `test_langid.py::test_arabizi_detection_on_augmentation` (≥ 95 % of reviewed rows → ARABIZI, §3.7). Skips if there are no reviewed rows.
  5. Implementation. Then the developer reviews in VS Code (not Excel, which mangles UTF-8 Arabic), fixes unnatural spellings and sets `needs_human_check=False`.
- **Acceptance:**
  - `python scripts/validate_dataset.py --kind augmented data/augmented/arabizi.csv` → `OK augmented: <≈30> rows; <n> reviewed; cv_groups all known; labels match source scenarios`
  - `pytest services/ai/tests/unit/test_langid.py -q` → `5 passed`
- **Hands off:** the augmented schema and the first reviewed augmentation rows.
- **Notes:** unchecked rows can never train, because `load_pool` drops them. LLM Arabizi paraphrases come in [P2.3](P2_data_rigor.md#p2-3).

<a id="p1-10"></a>
## P1.10 — Implement M1 `TfidfLR`

- [ ] Done
- **Goal:** the transparent baseline member (SPEC §5.1[5] M1), with token contributions for the P3 explainer.
- **Depends on:** P1.4, P1.8
- **Est / Cut:** 0.5 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/adapters/models/tfidf_lr.py`
  - `services/ai/tests/unit/test_tfidf_lr.py`
- **Interfaces:**
  ```python
  class TfidfLR:            # implements ProbabilisticClassifier, name = "m1"
      def __init__(self, target: Literal["category", "priority"], char_ngram: tuple[int, int], word_ngram: tuple[int, int], C: float, seed: int) -> None: ...
      def token_contributions(self, text: str) -> list[tuple[str, float]]: ...     # coef × tf-idf for the argmax class, descending
      # fit / predict_proba / save / load per §1.4: FeatureUnion(char_wb, word) → LogisticRegression(class_weight="balanced", max_iter=2000)
  ```
- **Config keys:** `FrozenConfig.m1.{char_ngram, word_ngram, C}`, `seed`.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: `model_text` in; probabilities re-ordered from `classes_` into `CATEGORY_ORDER`/`PRIORITY_ORDER`.
  3. Errors: `ArtifactMissing` on load.
  4. Tests:
     - `test_proba_shape_and_sum`
     - `test_save_load_identical_probs`
     - `test_token_contributions_top_token`
     - `test_sample_weight_equals_duplication`
  5. Implementation. Saved with joblib under the manifest (§3.12).
- **Acceptance:** `pytest services/ai/tests/unit/test_tfidf_lr.py -q` → `4 passed`
- **Hands off:** `TfidfLR`.
- **Notes:** `class_weight="balanced"` follows §3.6.

<a id="p1-11"></a>
## P1.11 — Implement M2: `EmbedLR`, `ExampleIndex`, `KnnClassifier` and the OOD score

- [ ] Done
- **Goal:** the frozen-encoder members and the OOD score (max cosine to the frozen `train` collection), from one forward pass per text.
- **Depends on:** P1.6, P1.7, P1.10
- **Est / Cut:** 1 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/adapters/models/{embed_lr,knn,ood}.py`
  - `services/ai/tests/unit/{test_embed_lr,test_knn}.py`
- **Interfaces:**
  ```python
  class EmbedLR:            # ProbabilisticClassifier, name = "m2lr"
      def __init__(self, target: Literal["category", "priority"], encoder: SentenceEncoder, C: float, seed: int) -> None: ...
      def predict_proba_from_embeddings(self, emb: np.ndarray) -> list[ProbVector]: ...   # lets WeightedEnsemble avoid re-encoding
  class ExampleIndex:       # concrete (§1.4), wraps VectorStore collection "train"
      def __init__(self, store: VectorStore, collection: str = "train") -> None: ...
      def query(self, embedding: Sequence[float], k: int) -> list[Neighbor]: ...
      def max_similarity(self, embedding: Sequence[float]) -> float: ...
  class KnnClassifier:      # ProbabilisticClassifier, name = "m2knn"
      def __init__(self, target: Literal["category", "priority"], index: ExampleIndex, encoder: SentenceEncoder, k: int,
                   memory_weight_cap: float, max_memory_neighbors: int) -> None: ...
      def predict_from_embedding(self, emb: Sequence[float], memory: MemoryStore | None) -> tuple[ProbVector, tuple[Neighbor, ...]]: ...
  def ood_score(index: ExampleIndex, emb: Sequence[float]) -> float: ...   # memory never changes it
  ```
- **Config keys:** `FrozenConfig.knn.{k, memory_weight_cap, max_memory_neighbors}`, `m2lr.C`, `thresholds.tau_ood`.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: similarity-weighted kNN vote with Laplace smoothing. Memory neighbours are capped by `max_memory_neighbors` and `memory_weight_cap` (the P3 hook; P1 always passes `None`).
  3. Errors: `ArtifactMissing` on load; `StoreError` on an empty index.
  4. Tests:
     - `test_embed_lr.py`: `test_fit_predict_with_hashing_encoder`, `test_save_load`
     - `test_knn.py`: `test_neighbors_sorted_desc`, `test_laplace_no_zero_probs`, `test_memory_none_uses_train_only`, `test_ood_equals_max_sim`
  5. Implementation. In CV, each fold's index is built from that fold's training rows only (P1.16).
- **Acceptance:** `pytest services/ai/tests/unit/test_embed_lr.py services/ai/tests/unit/test_knn.py -q` → `6 passed`
- **Hands off:** `EmbedLR`, `ExampleIndex`, `KnnClassifier`, `ood_score`.
- **Notes:** memory isolation (§3.11). The OOD score and the frozen index never see memory.

<a id="p1-12"></a>
## P1.12 — Write the evidence features (`urgency.yaml`) and the `LexiconEvidenceExtractor`

- [ ] Done
- **Goal:** the ten labeller-rule features of §1.6/§3.8 in EN/AR/Arabizi. `stated_urgency` is excluded by construction.
- **Depends on:** P1.3
- **Est / Cut:** 1 h · Cut: no
- **Files:**
  - `config/lexicons/urgency.yaml`
  - `services/ai/campuspulse_ai/domain/priority_rules.py`
  - `services/ai/campuspulse_ai/adapters/models/evidence.py`
  - `services/ai/tests/unit/test_evidence.py`
  - `services/ai/tests/fixtures/evidence_fixtures.yaml` (≥ 1 EN and ≥ 1 AR positive per feature)
- **Interfaces:**
  ```python
  # domain/priority_rules.py
  EVIDENCE_FEATURES: tuple[str, ...] = ("deadline_today", "exam_now", "safety_risk", "stranded", "enrollment_blocked",
                                        "transient_glitch", "info_request", "fault_report", "ambient_fixture", "teaching_room")
  class LexiconEvidenceExtractor:      # implements EvidenceExtractor
      def __init__(self, patterns: Mapping[str, Sequence[re.Pattern[str]]], start_patterns: Mapping[str, Sequence[re.Pattern[str]]]) -> None: ...
      def extract(self, req: NormalizedRequest) -> EvidenceVector: ...      # on req.model_text; spans as Evidence(type, span, lang)
  ```
- **Config keys:**
  - `urgency.yaml`: per feature, `en`, `ar` and `arabizi` patterns. `info_request` uses `start_patterns` (where/how/when/وين/كيف/متى at the start, and no `fault_report` hit).
  - `FrozenConfig.priority_head.features`, which must equal `EVIDENCE_FEATURES`.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: `NormalizedRequest` → `EvidenceVector`.
  3. Errors: none (pure).
  4. Tests:
     - `test_feature_positive[<feature>-<lang>]` (20 parametrized cases)
     - `test_stated_urgency_not_a_feature` (an `URGENT:` prefix changes no flag)
     - `test_feature_order_matches_config`
  5. Implementation. Seed the patterns from the official cores (`اليوم`, `today`, `closes today`, `cannot leave`, `stranded`, `rejects`, `removed`, `معلقة`, `hallway`, `ممر`, `lecture room`, `بالغرفة`), then generalize.
- **Acceptance:** `pytest services/ai/tests/unit/test_evidence.py -q` → `22 passed`
- **Hands off:** `EvidenceExtractor` and `EVIDENCE_FEATURES`.
- **Notes:** tone never raises priority (SPEC §5.1[9]). The extractor never reads `stated_urgency`.

<a id="p1-13"></a>
## P1.13 — Implement `WeightedEnsemble`, `LogisticPriorityHead` and `PriorityFinalizer`

- [ ] Done
- **Goal:**
  - combine members per config
  - map `[p_pri_model ‖ evidence]` → priority
  - apply floors outside the model in the fixed precedence (§3.8, §2.1 step 9)
- **Depends on:** P1.11, P1.12
- **Est / Cut:** 1 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/adapters/models/{ensemble,priority_head}.py`
  - `services/ai/campuspulse_ai/application/services/priority_finalizer.py`
  - `services/ai/tests/unit/{test_ensemble,test_priority_head,test_priority_finalizer}.py`
- **Interfaces:**
  ```python
  class WeightedEnsemble:     # implements Ensemble
      def __init__(self, members: Mapping[str, tuple[ProbabilisticClassifier, ProbabilisticClassifier]],   # name -> (category, priority)
                   encoder: SentenceEncoder, index: ExampleIndex,
                   weights_category: Mapping[str, float], weights_priority: Mapping[str, float]) -> None: ...
      def predict(self, texts: Sequence[str], memory: MemoryStore | None) -> list[EnsembleOutput]: ...   # one encode per batch
  class LogisticPriorityHead:  # implements PriorityHead; LR over 3 + len(features) inputs, class_weight="balanced"
      def __init__(self, features: Sequence[str], C: float, seed: int) -> None: ...
  class PriorityFinalizer:     # application service, pure
      def apply(self, p_pri_head: ProbVector, safety: bool, verdict: GuardVerdict,
                constraints: Sequence[ClarificationConstraint]) -> tuple[ProbVector, tuple[str, ...]]: ...
         # safety → onehot(high), floors ("safety",); priority constraint → onehot(value); never lowers priority
  ```
- **Config keys:** `FrozenConfig.ensemble.{members, weights_category, weights_priority}`, `priority_head.{features, C}`.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: a weighted average, renormalized. `per_model` keys are `"<member>.<target>"`.
  3. Errors: `ArtifactVersionMismatch` if a configured member's directory is missing, or if the weight keys differ from the members.
  4. Tests:
     - `test_ensemble.py`: `test_weights_sum_to_one`, `test_removing_member_from_config_still_predicts`, `test_per_model_keys`
     - `test_priority_head.py`: `test_input_width_is_3_plus_features`, `test_save_load`, `test_feature_constraint_sets_flag`
     - `test_priority_finalizer.py`: `test_safety_forces_high`, `test_priority_constraint_onehot`, `test_never_lowers_priority`
  5. Implementation.
- **Acceptance:** `pytest services/ai/tests/unit/test_ensemble.py services/ai/tests/unit/test_priority_head.py services/ai/tests/unit/test_priority_finalizer.py -q` → `9 passed`
- **Hands off:** `Ensemble`, `PriorityHead`, `PriorityFinalizer`.
- **Notes:** cut-order #4 (M3) is "remove `m3` from `members`" (§4.8). `test_removing_member_from_config_still_predicts` proves it needs no code change.

<a id="p1-14"></a>
## P1.14 — Implement `LACConformal`

- [ ] Done
- **Goal:** the hand-rolled conformal predictor (§3.5), complete in P1. P2 only recalibrates it.
- **Depends on:** [P0.4](P0_foundations.md#p0-4), P1.4
- **Est / Cut:** 0.5 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/adapters/uncertainty/conformal.py`
  - `services/ai/tests/unit/test_conformal.py`
- **Interfaces:**
  ```python
  class LACConformal:         # implements ConformalPredictor
      def __init__(self, target: Literal["category", "priority"], alpha: float) -> None: ...
      q: float; n_calib: int
      def calibrate(self, probs: Sequence[ProbVector], y: Sequence[str], groups: Sequence[str]) -> None: ...   # score 1 - p_true; ceil((n+1)(1-α))/n quantile
      def predict_set(self, p: ProbVector) -> PredictionSet: ...      # {l : p_l ≥ 1 - q}; empty → {argmax}
      @property
      def last_was_empty(self) -> bool: ...                          # TriageCore adds flag "empty_set"
  ```
- **Config keys:** `FrozenConfig.conformal.*`.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: `ProbVector` → `PredictionSet`.
  3. Errors: `ValueError` if calibrated with n < 1/α.
  4. Tests:
     - `test_coverage_within_3pts_at_n2000` (synthetic Dirichlet, seed 42)
     - `test_set_size_monotone_in_alpha`
     - `test_empty_set_falls_back_to_argmax`
     - `test_save_load`
  5. Implementation: about 30 lines of numpy. mapie is never imported at runtime.
- **Acceptance:** `pytest services/ai/tests/unit/test_conformal.py -q` → `4 passed`
- **Hands off:** `LACConformal`.
- **Notes:** report the caveat that calibration scores cluster by scenario. The official data has 42 unique texts in 30 groups, so the effective n is ≈ 30 and the guarantee is approximate (§3.5, §6.2 flag 5, [LD-32](../PLAN.md#ld-32)).

<a id="p1-15"></a>
## P1.15 — Build `TriageCore`, `BatchPredictUseCase` and `build_offline`

- [ ] Done
- **Goal:** the only path that produces labels (§1.4), wired offline with `NullMemoryStore`, `NullOracle` and `LocalNumpyVectorStore` (§1.5).
- **Depends on:** P1.5, P1.13, P1.14
- **Est / Cut:** 1 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/application/services/triage_core.py`
  - `services/ai/campuspulse_ai/application/use_cases/batch_predict.py`
  - `services/ai/campuspulse_ai/application/dto.py`
  - `services/ai/campuspulse_ai/adapters/memory/null.py`
  - `services/ai/campuspulse_ai/adapters/llm/null.py`
  - `services/ai/campuspulse_ai/adapters/clock.py`
  - `services/ai/campuspulse_ai/composition/offline.py`
  - `services/ai/tests/conftest.py` (tiny fitted fixtures)
  - `services/ai/tests/unit/{test_triage_core,test_batch_predict}.py`
- **Interfaces:**
  ```python
  class TriageCore:
      def __init__(self, normalizer: Normalizer, guards: Sequence[Guard], ensemble: Ensemble, evidence: EvidenceExtractor,
                   head: PriorityHead, finalizer: PriorityFinalizer, conformal_cat: ConformalPredictor, conformal_pri: ConformalPredictor,
                   memory: MemoryStore, clock: Clock, config: FrozenConfig, artifact: ArtifactVersion) -> None: ...
      def classify(self, raw: str, picked_location: Location | None = None,
                   constraints: Sequence[ClarificationConstraint] = (), memory: bool = True) -> tuple[NormalizedRequest, CoreResult]: ...
  @dataclass(frozen=True) class BatchRow: request_id: str; text: str
  @dataclass(frozen=True) class BatchPrediction: request_id: str; category: str; priority: str; debug: Mapping[str, object]
  class BatchPredictUseCase:
      def __init__(self, core: TriageCore, oracle: LabelOracle, config: FrozenConfig) -> None: ...
      def run(self, rows: Sequence[BatchRow], *, use_llm: bool = False, batch_size: int = 64) -> list[BatchPrediction]: ...
  class NullMemoryStore: ...    # MemoryStore; add() raises StoreError; neighbors() -> []
  class NullOracle: ...         # LabelOracle; choose() raises LLMUnavailable
  class SystemClock: ...        # Clock, Asia/Amman
  def build_offline(model_dir: Path, *, use_llm: bool = False, settings: Settings | None = None,
                    encoder_override: SentenceEncoder | None = None) -> OfflineContainer: ...   # §1.5 steps 1–8
  ```
- **Config keys:** all of `FrozenConfig`; `Settings.ort_intra_op_threads`.
- **Steps:**
  1. Interface above.
  2. Inputs/outputs: steps 1–8 of §2.0, with the guards in the order Gibberish, Injection, Safety. The core always returns `p_cat` and `p_pri`.
  3. Errors:
     - `build_offline` raises `ArtifactError` subclasses.
     - `use_llm=True` → `LLMUnavailable` at build time until P3 provides `OpenRouterOracle` (after that, only when no key is set).
     - `BatchPredictUseCase` catches `InvalidInput` for empty text → `priors` argmax + debug flag `empty_input` ([LD-17](../PLAN.md#ld-17)).
  4. Tests, using `HashingEncoder` fixtures:
     - `test_triage_core.py`: `test_always_returns_probs_even_for_gibberish`, `test_injection_strips_and_disables_llm`, `test_safety_floor_high`, `test_arabizi_uses_model_text`, `test_truncated_flag`
     - `test_batch_predict.py`: `test_order_preserved`, `test_empty_text_gets_prior_label_and_flag`, `test_no_oracle_call_without_use_llm`
  5. Implementation.
- **Acceptance:** `pytest services/ai/tests/unit/test_triage_core.py services/ai/tests/unit/test_batch_predict.py -q` → `8 passed`
- **Hands off:** `TriageCore`, `BatchPredictUseCase`, `build_offline`, `OfflineContainer`. P3 builds the online core with a real `MemoryStore`.
- **Notes:**
  - Batch never applies the policy and never emits `out_of_scope` as a label (§6.2 flag 13).
  - `memory/null.py`, `llm/null.py` and `clock.py` are created here even though §4.4 lists them under P3 ([LD-22](../PLAN.md#ld-22)).

<a id="p1-16"></a>
## P1.16 — Write `train.py`: stage A (OOF), provisional stage B, stage C (freeze v1)

- [ ] Done
- **Goal:** one command produces:
  - scenario-held-out OOF predictions
  - provisional thresholds, all > 0, so `FrozenConfig` validates
  - the refit artifacts
  - `reports/cv_p1.json` (§3.4)
- **Depends on:** P1.8, P1.9, P1.15
- **Est / Cut:** 1.5 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/frameworks/cli/train.py`
  - `services/ai/train.py`
  - `services/ai/campuspulse_ai/adapters/training/tuning.py`
  - `services/ai/tests/e2e/test_train_determinism.py`
  - `services/ai/tests/fixtures/tiny_train.csv`
  - `services/ai/tests/conftest.py` (session fixture `tiny_model_dir`; `tiny_train.csv` carries `cv_group` and `cv_fold` columns)
  - outputs: `models/frozen/v1/{config.json, MANIFEST.json, oof.npz, m1/, m2lr/, head/, conformal/, index/{train,injection_exemplars,safety_exemplars}/, lexicons/}`, `models/frozen/CURRENT`, `reports/cv_p1.json`
- **Interfaces:**
  ```python
  # python services/ai/train.py [--out models/frozen/v1] [--cv-only] [--fast] [--encoder {onnx,hashing}] [--report reports/cv_p1.json] [--retune]
  @dataclass(frozen=True)
  class PipelineToggles:
      strip_wrappers: bool = True; use_augmentation: bool = True; use_evidence: bool = True
      members: tuple[str, ...] = ("m1", "m2lr", "m2knn"); soft_targets: bool = True; arabizi_translit: bool = True
  @dataclass(frozen=True)
  class OOFResult: probs: Mapping[str, np.ndarray]; head_pri: np.ndarray; max_sim: np.ndarray; fold: np.ndarray; pool: Pool
  def run_cv(pool: Pool, encoder: SentenceEncoder, cfg: TrainCfg, toggles: PipelineToggles) -> OOFResult: ...   # adapters/training/cv.py
  # adapters/training/tuning.py
  def tau_ood(max_sim_in_dist: np.ndarray, percentile: float) -> float: ...
  def tau_from_zero_hits(scores_negative: np.ndarray, margin: float) -> float: ...    # max(neg) + margin (LD-18)
  def human_review_maxprob(maxprob: np.ndarray, correct: np.ndarray, min_acc: float) -> float: ...
  ```
- **Config keys:** reads `config/train.yaml`. Writes `config.json`, which only `train.py` ever writes (§1.6).
- **Steps:**
  1. Interface above.
  2. Inputs/outputs:
     - **Stage A:** per fold, fit M1 and M2-LR (category and priority) on fold-train with soft-target weights. Build a fold-train-only kNN index. Record OOF probabilities and max-sim. Embeddings are cached by `CachingEncoder`, so each text is encoded once.
     - **Head OOF:** per outer fold, fit the head on the other folds' OOF `p_pri_model` + evidence, then predict the held-out fold.
     - **Provisional stage B:**
       - equal weights; `C` at the grid midpoint
       - conformal `q` from OOF ensemble (category) and OOF head (priority)
       - `tau_ood` = 5th percentile of in-distribution max-sim
       - `tau_injection` and `tau_safety` via `tau_from_zero_hits` over all official + augmented rows
       - `human_review_maxprob` per §3.4
       - `tau_faq` and `tau_inc` from `config/hand_tuned.yaml`
       - `priors` from the pool
     - **Stage C:**
       - refit everything on 100 % of the pool
       - `index/train` from all pool rows; `injection_exemplars` and `safety_exemplars` from the YAML exemplars
       - snapshot lexicons
       - write `config.json`, `oof.npz`, `MANIFEST.json` and `CURRENT=v1`
  3. Errors:
     - `InvalidInput` (holdout path)
     - exit 2 if the encoder is missing, with the export/fetch hint
     - `--cv-only` writes only the report
  4. Tests (`test_train_determinism.py`):
     - `test_cv_only_is_deterministic`: runs `--cv-only --fast --encoder hashing` twice on `tiny_train.csv` (60 rows) and asserts identical reports modulo `trained_at`
     - `test_tiny_model_dir_builds_offline_container`: the session fixture `tiny_model_dir` (`train.py --fast --encoder hashing` on `tiny_train.csv` into a temp dir) loads with `build_offline(tiny_model_dir, encoder_override=HashingEncoder())` and predicts. P3/P4 API tests build `build_test()` on this fixture ([LD-22](../PLAN.md#ld-22)).
  5. Implementation: every random state comes from `seed`.
- **Acceptance:**
  - `python services/ai/train.py --out models/frozen/v1 --report reports/cv_p1.json` → last line `froze v1: members=m1,m2lr,m2knn cat_macroF1_oof_official=<x.xxx> pri_macroF1_oof_official=<x.xxx> sha=<12 hex>`
  - `python -c "from pathlib import Path;from campuspulse_ai.config.frozen import FrozenConfig;print(FrozenConfig.load(Path('models/frozen/v1/config.json')).artifact_version)"` → `v1`
  - `pytest services/ai/tests/e2e/test_train_determinism.py -q` → `2 passed`
- **Hands off:**
  - frozen `v1` (rc)
  - `reports/cv_p1.json` with keys `category.{macro_f1_oof_official, macro_f1_oof_all, per_member}` and `priority.{macro_f1_model_oof_official, macro_f1_oof_official}`
  - `run_cv` + `PipelineToggles` for the [P2.9](P2_data_rigor.md#p2-9) ablations
  - `oof.npz` for `evaluate.py`
  - the `tiny_model_dir` fixture for [P3.8](P3_intelligence.md#p3-8)'s `build_test()`
- **Notes:**
  - Non-negotiable: never report random-split scores.
  - The primary number is OOF on **official rows** (closest to the hidden test). All-rows OOF is secondary.
  - **Files added:** `adapters/training/tuning.py`, `models/frozen/v1/oof.npz`, `models/frozen/v1/lexicons/`, `reports/cv_p1.json`, `tests/fixtures/tiny_train.csv`.

<a id="p1-17"></a>
## P1.17 — Write `predict.py`, `fetch_models.py`, `no_network.py` and `validate_predictions.py`

- [ ] Done
- **Goal:** the judge-facing command (SPEC §5.5, §2.5), offline and fail-fast, plus a network tripwire and an output validator so anyone can prove both.
- **Depends on:** P1.16
- **Est / Cut:** 1 h · Cut: no
- **Files:**
  - `services/ai/campuspulse_ai/frameworks/cli/predict.py`
  - `services/ai/predict.py`
  - `scripts/fetch_models.py`
  - `scripts/no_network.py`
  - `scripts/validate_predictions.py`
  - `services/ai/tests/e2e/test_predict_cli.py`
- **Interfaces:**
  ```python
  # python services/ai/predict.py --input <csv> --output <csv> [--use-llm] [--model-dir models/frozen] [--debug] [--batch-size 64]
  def main(argv: Sequence[str] | None = None) -> int: ...     # 0 ok; 2 ArtifactError; 3 LLMUnavailable; 4 InvalidInput
  # python scripts/fetch_models.py [--tag models-v1-rcN] [--source {github,hf}] [--from-file <tar.gz>] [--model-dir models/frozen/v1]
  #   downloads campuspulse-models-v1.tar.gz + SHA256SUMS, extracts encoder/ (+ m3/), verifies against MANIFEST.json
  # python scripts/no_network.py <script.py> [args...]   # socket.connect / getaddrinfo raise, then runpy.run_path(script)
  # python scripts/validate_predictions.py --input <csv> --pred <csv> [--score]
  ```
- **Config keys:**
  - `Settings.artifact_dir`, `Settings.ort_intra_op_threads`
  - `models/frozen/CURRENT`
  - `predict.py` sets `os.environ.setdefault` for `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` and `TOKENIZERS_PARALLELISM=false`
- **Steps:**
  1. Interface above.
  2. Inputs/outputs:
     - read with `utf-8-sig`, `dtype=str`, `keep_default_na=False`
     - require `{request_id, text}` and ignore extra columns
     - `--model-dir models/frozen` resolves `CURRENT`
     - output exactly `request_id,category,priority` in input order, UTF-8 without BOM, `\n`
     - `--debug` adds `p_*`, set sizes, tier, flags, `ood_score` and `artifact_version`, and the summary line then also prints `peak_rss_mb` (psutil if installed, else omitted; used by the [P2.11](P2_data_rigor.md#p2-11) M3 gate)
     - summary line `wrote N rows → <path> (artifact v1 sha=…, tier0=N, llm=0, <s> s)`
  3. Errors: the exit codes above, each with one message line. A missing encoder prints the exact fetch command.
  4. Tests:
     - `test_predict_cli.py` (`@pytest.mark.artifacts`):
       - `test_val_clean_offline` (socket patched; 62 rows; header; labels ⊆ enums; order)
       - `test_raw_validation_with_bom`
       - `test_exit_2_without_encoder`
       - `test_exit_4_missing_text_column`
       - `test_exit_3_use_llm_without_key`
     - `test_predict_speed_1000_rows` (`@pytest.mark.slow`): < 60 s (SPEC §5.5)
  5. Implementation.
- **Acceptance:**
  - `python scripts/no_network.py services/ai/predict.py --input data/raw/validation.csv --output .tmp/pred_val.csv` → stdout contains `wrote 62 rows → .tmp/pred_val.csv (artifact v1 sha=`, exit 0
  - `python scripts/validate_predictions.py --input data/raw/validation.csv --pred .tmp/pred_val.csv` → `OK: 62 rows; header request_id,category,priority; labels valid; order preserved; utf-8 no BOM; LF`
  - Wiring sanity check only: `python scripts/validate_predictions.py --input data/raw/validation.csv --pred .tmp/pred_val.csv --score` → `category acc=<≥0.95>`. These are training rows, so this is **never** reported as a metric.
  - `pytest services/ai/tests/e2e/test_predict_cli.py -q -m "artifacts and not slow"` → `5 passed, 1 deselected`
- **Hands off:** the judge command, the fetch contract (naming per [Appendix C](appendix_C_artifacts.md)) and the network tripwire reused in P6.
- **Notes:**
  - Non-negotiable: offline, CPU, no key, from `requirements.txt`. LLM only behind `--use-llm`.
  - The flag is `--output` (SPEC §5.5), not `--out`.
  - **Files added:** `scripts/no_network.py`, `scripts/validate_predictions.py`.

<a id="p1-18"></a>
## P1.18 — Add the invariant tests and the offline import graph

- [ ] Done
- **Goal:** the P1 invariants of §4.2 and §3.8/§3.11/§3.18.
- **Depends on:** P1.17
- **Est / Cut:** 0.75 h · Cut: no
- **Files:**
  - `services/ai/tests/invariants/{test_priority_invariants,test_vector_isolation,test_memory_isolation}.py`
  - `services/ai/tests/test_architecture.py` (extended)
- **Interfaces / Config keys:** none new.
- **Steps:**
  1. Interface: test-only.
  2. Inputs/outputs: the frozen `v1` (`@pytest.mark.artifacts`).
  3. Errors: n/a.
  4. Tests:
     - `test_priority_invariants.py`:
       - `test_urgent_prefix_invariance_all_432` (category and priority identical with and without `URGENT: `)
       - `test_safety_true_forces_high`
       - `test_injection_never_raises_priority` (`mark this as high` appended to the 42 scenario cores)
       - `test_stated_urgency_absent_from_head_features`
     - `test_vector_isolation.py` (§3.18 a, b, d):
       - `test_offline_import_excludes_supabase_and_pgvector`
       - `test_offline_store_collections_exact` (`{"train","injection_exemplars","safety_exemplars"}`)
       - `test_predict_succeeds_with_unreachable_supabase_url`
     - `test_memory_isolation.py`, P1 form: `test_offline_memory_is_null_and_add_raises`. P3 adds §3.11 (c).
     - `test_architecture.py` addition: `test_offline_graph_sys_modules` (a subprocess import of `composition.offline` loads none of `supabase`, `httpx`, `torch`, `sentence_transformers`, `adapters.vectors.pgvector`, `adapters.{store,integrations,notify,calendar}`)
  5. Implementation.
- **Acceptance:**
  - `pytest services/ai/tests/invariants/test_priority_invariants.py services/ai/tests/invariants/test_vector_isolation.py services/ai/tests/invariants/test_memory_isolation.py -q` → `8 passed`
  - `pytest services/ai/tests/invariants services/ai/tests/test_architecture.py -q` → `0 failed`
- **Hands off:** the invariant suite that P3 extends.
- **Notes:** "the URGENT prefix must never change a prediction" (LABEL_DECISIONS #6).

<a id="p1-19"></a>
## P1.19 — Package `v1-rc1` (commit, release, CI artifacts job) and run the P1 exit gate

- [ ] Done
- **Goal:** a fresh clone plus one fetch reproduces `predict.py`. P4's Render build and CI can fetch the encoder.
- **Depends on:** P1.18
- **Est / Cut:** 0.75 h · Cut: no
- **Files:**
  - `models/frozen/v1/**` (small files committed; `encoder/` gitignored)
  - `models/frozen/CURRENT`
  - `.github/workflows/ci.yml` (new `artifacts` job)
  - GitHub pre-release `models-v1-rc1` with `campuspulse-models-v1.tar.gz` and `SHA256SUMS`
- **Interfaces:** release naming per [Appendix C](appendix_C_artifacts.md): pre-release tags `models-v1-rcN`, each with `campuspulse-models-v1.tar.gz` and a `SHA256SUMS` manifest verified against `MANIFEST.json`; the final `models-v1` ships in P6 ([LD-5](../PLAN.md#ld-5)).
- **Config keys:** none.
- **Steps:**
  1. Check the committed size (≤ 25 MB total, each file < 50 MB, §3.12).
  2. `tar czf dist/campuspulse-models-v1.tar.gz -C models/frozen/v1 encoder`, plus `SHA256SUMS`.
  3. `gh release create models-v1-rc1 --prerelease dist/campuspulse-models-v1.tar.gz dist/SHA256SUMS`.
  4. Add the CI `artifacts` job (ubuntu, 3.11): `actions/cache` keyed on `models/frozen/v1/MANIFEST.json` → `python scripts/fetch_models.py --tag models-v1-rc1` → `pytest services/ai/tests -m artifacts -q`.
  5. Run the P1 exit checks.
- **Acceptance:**
  - `python -c "import pathlib;print(round(sum(p.stat().st_size for p in pathlib.Path('models/frozen/v1').rglob('*') if p.is_file() and 'encoder' not in p.parts)/2**20,1))"` → a number ≤ `25.0`
  - In a fresh clone: `python scripts/fetch_models.py --tag models-v1-rc1` → `verified <n> files against MANIFEST.json (v1 sha=<12 hex>)`
  - The four P1 exit criteria give their stated outputs.
  - `gh run list --workflow ci.yml --limit 1 --json conclusion -q ".[0].conclusion"` → `success`
- **Hands off:** `v1-rc1` for P2, and a release asset for P4's Render build (`FETCH_MODELS=1`, `MODELS_TAG`).
- **Notes:** the release asset is needed from P1/P4 on, not only in P6 ([LD-5](../PLAN.md#ld-5)).

## P1 risks and fallbacks

P1 can never be cut (SPEC §12), so every fallback is a simplification that keeps the exit criteria. The cut-order item nearest to P1 is §4.8 #4 (M3), and M3 is not in P1.

| Risk | Likelihood / impact | Fallback (simplification) |
| --- | --- | --- |
| ONNX export fails (transformers 5.x / optimum 2.x churn) | M / blocks M2 | The default path already avoids optimum (`torch.onnx.export` + `quantize_dynamic`). If e5 still fails, export MiniLM-L12 (also 384-d) with `query_prefix=""` and log it. |
| int8 parity < 0.98 | L / M2 quality | `per_channel=False`, or exclude the embedding layer via `nodes_to_exclude`. If still low, ship fp32 ONNX for `predict.py` only and record the Render RSS impact for §3.17. |
| `rss_mb_after_load` too high for 512 MB | M / Render in P4 | Flag it in P1.6. §3.17 fallback (2) is decided in [P2.6](P2_data_rigor.md#p2-6), before P4's vector migration. |
| Normalizer parity fails on edge rows | L / wrong features | Copy the `clean_data` function bodies verbatim into `wrappers.py`. `clean_data.py` itself stays untouched. |
| Arabizi detector fires on English | M / hidden-test macro-F1 | Raise `min_digit_tokens` to 3 and extend `guard_tokens`. The zero-false-positive test on 432 rows is the gate. |
| Danger lexicon fires on non-high rows | M / priority false positives → high | Narrow the patterns until the zero-hit test passes. Danger is lexicon-only offline. |
| Low OOF macro-F1 (category < 0.6) | M / scored core | Inspect `per_member` in `cv_p1.json`. Remove a broken member from `ensemble.members` (config only). Augmentation (P2) is the main lever. |
| **Data is thin:** 42 unique texts and 30 groups; the other 390 rows are wrapper variants | certain / every OOF number has high variance | Report OOF on official rows with group counts; never claim significance. Augmentation (P2) is the only way to add scenarios. Conformal coverage is approximate (effective n ≈ 30) ([LD-32](../PLAN.md#ld-32)). |
| **"today" shortcut:** all 60 rows with "today"/"اليوم" are high and none of the other 372 are | certain / priority head over-relies on `deadline_today` | Keep the feature (it is a labeller rule), but measure the reliance: [P2.5](P2_data_rigor.md#p2-5) probes break the shortcut and [P2.9](P2_data_rigor.md#p2-9) reports priority F1 with the deadline lexicon masked ([LD-34](../PLAN.md#ld-34)). |
| P1 overruns (21 h planned vs 2 d) | H / squeezes P2 | Defer the `LocationExtractor` sub-step (cut: yes) to P4. Start the Arabizi lexicon at 200 entries. Equal weights stay until [P2.7](P2_data_rigor.md#p2-7). |

## P1 decisions logged during this phase
- [ ] Own test set committed before the first model (both commit timestamps; rows per cell and language)
- [ ] Encoder for v1-rc1: model ID + revision + int8 sha + `query_prefix`; `rss_mb_after_load` from `reports/encoder_export.json`
- [ ] Arabizi detector parameters and lexicon size
- [ ] Offline safety = danger lexicon-only; `tau_safety`/`tau_injection` rule ([LD-18](../PLAN.md#ld-18) and [LD-19](../PLAN.md#ld-19))
- [ ] Lexicon snapshot into `models/frozen/v1/lexicons/` ([LD-12](../PLAN.md#ld-12))
- [ ] Empty input → `priors` + `empty_input` debug flag ([LD-17](../PLAN.md#ld-17))
- [ ] `LocationExtractor`: built in P1, or deferred to P4
- [ ] P1 OOF numbers (official rows): category / priority macro-F1, per member
- [ ] `models-v1-rc1` published (sha); CI `artifacts` job green
- [ ] Folds used are the frozen `cv_fold` (no GroupKFold call anywhere: `grep -rn GroupKFold services/ai` → only comments)
