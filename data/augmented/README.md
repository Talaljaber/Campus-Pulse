# data/augmented/: training augmentation

Rows here **are** training data (unlike `data/our_test/` and `data/robustness/`). `train.py` uses only rows with
`needs_human_check == False`.

## Schema (ARCHITECTURE §4.2): every file, columns exactly

| column | meaning |
| --- | --- |
| `request_id` | unique id, e.g. `AUG-AZ-0001` |
| `text` | the request text as a student would type it |
| `lang` | `en`, `ar` or `arabizi` |
| `source` | how the row was made: `arabizi_rule`, `llm_paraphrase`, `llm_arabizi`, `new_scenario`, `hand` (the list in `config/datasets.yaml` `augmented.sources`) |
| `source_scenario_id` | the official scenario the row derives from (e.g. `TR-S14`), or the new scenario id `NEW-Sxx`. **Required.** |
| `cv_group` | the leakage unit: inherited from the source scenario, or `NEW-Sxx` for a new scenario |
| `needs_human_check` | `True` until the developer has checked the row; only `False` rows are trained on |
| `author_method` | `rule`, `llm` (disclosed model) or `hand` |
| `category` | exact official category spelling |
| `priority` | `low`, `medium` or `high` |

## Rules
- A paraphrase or transliteration keeps the `cv_group` of its source scenario, so it is always held out together
  with it (ARCHITECTURE §3.2).
- New groups get a fold from `python scripts/make_folds.py --include-augmented`, which never moves an official group.
- Run `python scripts/check_leakage.py` after adding rows: an identical `text_norm` across groups fails.
- Labels are never adjusted here; soft targets live only in `data/clean/label_flags.csv`.
