# data/clean/

Generated from `data/raw/` by `python scripts/clean_data.py` (labels are never changed). Full column reference:
[docs/ml/models.md §2](../../docs/ml/models.md#2-data-files).

| file | made by | notes |
| --- | --- | --- |
| `train_clean.csv`, `val_clean.csv`, `train_val_combined.csv`, `scenarios.csv`, `cleaning_report.md` | `scripts/clean_data.py` | deterministic; never hand-edited |
| `label_flags.csv`, `LABEL_DECISIONS.md` | label debate (by hand) | the **only** place label adjustments live, as soft targets |
| `cv_folds.csv` | `scripts/make_folds.py` | frozen category-stratified folds (`cv_group,cv_fold`) |
| `train_val_features.csv` | `scripts/add_derived_columns.py` | `request_id,lang_script,is_arabizi,stated_urgency` |

**`lang` is script-only.** In every CSV here, `lang` is `ar` or `en` by counting Arabic vs Latin letters. There is
no Arabizi value: the official data has 0 Arabizi rows, and `is_arabizi` is `False` for all 432 rows. The package
`LangIdentifier` (`campuspulse_ai.adapters.preprocess.langid`) is the only source of the Arabizi label for any
other text (LD-33). `train_val_features.csv` exposes the same value as `lang_script`, the fairness-slice key
together with `is_arabizi`.

`stated_urgency` here equals `has_urgent_marker` (`"URGENT"` in the raw text). It is a gaming signal only and
never a model feature.
