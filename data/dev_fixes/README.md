# data/dev_fixes (P7.0)

A development set for the P7 fixes: 216 fictional requests (EN, AR, AZ x persona A/B x 36 rows each), written by
LLM authors who had not seen the classifier, then labelled blind by a second LLM pass per language.
`source=llm_dev_fixes`, `needs_human_check=True`. Not native-verified.

Protocol
- Never used for training or conformal calibration. It is our own test data.
- `tune` (persona A) may be read and iterated on. `check` (persona B): aggregate numbers only, once per package,
  nothing is changed because of them.
- `category`/`priority` in `dev_fixes.csv` are the author label where author and blind labeller agree, else empty
  (probes keep the author label). Disagreements are reported, never relabelled.
- `x_*` columns are the blind labeller's extraction fields (gold for the P8.11 extraction task).
- Rebuild: `python scripts/build_dev_fixes.py {blind,merge,leak,score}`. Leakage against official and our_test is
  checked by `leak` (exact and char cosine; counts only).
- `baseline/` holds rc4 `predict.py --debug` outputs and `baseline_metrics.{json,md}`.
