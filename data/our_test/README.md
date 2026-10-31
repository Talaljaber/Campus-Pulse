# data/our_test/: our own holdout test set

**Never trained on.** This folder is never read by `train.py`; only `evaluate.py` and the validators read it (ARCHITECTURE §3.2).
`train.py` and `load_pool` refuse any input path that contains `our_test` (`campuspulse_ai.config.paths.is_holdout`).

## Sets

Each set uses the official hidden-test layout: `<set>_text.csv` (`request_id,text`) and
`<set>_labels.csv` (`request_id,category,priority,scenario_family`). `scenario_family` names the
language and scenario, e.g. `en_Facilities_1` or `t2_arabizi_Finance_0`.

| Set | Ids | Rows | Author | What it measures |
|---|---|---|---|---|
| `set1` | `HT-0001`… | 60 | the developer, by hand | **Cross-lingual transfer.** 6 official training scenarios restated in the other language (e.g. the Arabic "last bus cancelled" scenario in English), with official wrappers. Not unseen scenarios. Covers 6 of 18 category × priority cells; no Arabizi. |
| `set2` | `T2-0001`… | 72 | Claude (`author_method=claude`) | **Unseen scenarios, official style.** 18 new scenarios, one per cell, each with 4 variants (plain + official wrappers). Includes `URGENT:` on low and medium rows (the prefix must not change the label). |
| `set3` | `T3-0001`… | 72 | Claude (`author_method=claude`) | **Unseen scenarios, free student style.** 18 new scenarios, one per cell, each written 4 ways: paraphrases, dialect, typos, code-switching. |

Sets 2 and 3: 32 en, 24 ar, 16 arabizi rows each; no normalized text equals an official `text_norm`.
Labels follow `docs/reference/label_decisions.md` (low = information request; medium = concrete
malfunction or teaching-room equipment; high = same-day deadline, safety, stranded, or definitive
loss of enrolment; topic beats channel). Report scores **per set** as well as pooled.

## Combined file

`our_test.csv` is generated from the sets; do not edit it by hand:

```
python scripts/build_our_test.py           # rebuild after changing a set
python scripts/build_our_test.py --check   # CI: fails if our_test.csv is stale
```

Columns: `request_id,text,lang,category,priority,author_method,test_set,scenario_family,notes`
(original request ids are kept; `author_method` is `hand` or `claude`).
Validate with `python scripts/validate_dataset.py --kind our_test data/our_test/our_test.csv`.
