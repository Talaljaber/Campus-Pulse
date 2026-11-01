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

## Files
- `arabizi_from_official.csv` (P2.16): 126 LLM-written Arabizi renderings (3 spellings of each of the 42 official cores, so the official data has an Arabizi view); labels, `source_scenario_id` and `cv_group` come from the source scenario. All `needs_human_check=True`; used only by the Arabizi experiment (unreviewed arm), not by `train.py`.
- `new_scenarios.csv` (P2.3): 78 new situations that are not in the official data (not paraphrases or
  translations of the 42 official cores), 390 rows. Finance has 18 situations; Registration, IT Support,
  Transportation, Facilities and Academic Support have 12 each, and each category splits evenly across
  low / medium / high. Every situation has 5 rows (`en`, `ar` Jordanian dialect, `arabizi`, an `en`
  paraphrase and an `ar` paraphrase) that share its labels and its group `NEW-Cxx`
  (`source_scenario_id == cv_group`). `source=new_scenario`, `author_method=llm`, and every row is
  `needs_human_check=True`, so nothing trains until it has been reviewed. Labels follow
  `docs/reference/label_decisions.md`. Highs use varied urgency (exam or defence happening now, a deadline
  within hours, safety, stranded students, a definitive loss of enrolment), and some lows and mediums carry
  time words ("today", "tomorrow", "next week") on purpose. `new_scenarios_notes.md` lists each situation's
  labels, the rule that decided its priority and its sub-topic, for fast review.

## Rules
- A paraphrase or transliteration keeps the `cv_group` of its source scenario, so it is always held out together
  with it (ARCHITECTURE §3.2).
- New groups get a fold from `python scripts/make_folds.py --include-augmented`, which never moves an official group.
- Run `python scripts/check_leakage.py` after adding rows: an identical `text_norm` across groups fails.
- Labels are never adjusted here; soft targets live only in `data/clean/label_flags.csv`.
