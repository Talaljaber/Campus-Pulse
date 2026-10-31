# data/our_test/: our own holdout test set

**Never trained on.** This folder is never read by `train.py`; only `evaluate.py` reads this folder (ARCHITECTURE §3.2).
`train.py` and `load_pool` refuse any input path that contains `our_test` (`campuspulse_ai.config.paths.is_holdout`).

- `our_test.csv` is hand-written by the developer (no LLM) **before any model exists** (task P1.0).
- Columns, exactly: `request_id,text,lang,category,priority,author_method,notes`
  - `request_id` matches `^OT-\d{3}$`; `lang` is one of `en`, `ar`, `arabizi`; `author_method` is `hand`;
  - labels use the exact official spellings; `notes` names the labelling rule used.
- Validate with `python scripts/validate_dataset.py --kind our_test data/our_test/our_test.csv`.
- Agents may not write rows here.
