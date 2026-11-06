# data/our_test/: our own holdout test set

**Never trained on.** This folder is never read by `train.py`; only `evaluate.py` and the validators read it (ARCHITECTURE §3.2).
`train.py` and `load_pool` refuse any input path that contains `our_test` (`campuspulse_ai.config.paths.is_holdout`).

## Sets

Each set uses the official hidden-test layout: `<set>_text.csv` (`request_id,text`) and
`<set>_labels.csv` (`request_id,category,priority,scenario_family`). `scenario_family` names the
language and scenario, e.g. `t1_en_Facilities_1` or `t1_arabizi_Finance_0`.

| Set | Ids | Rows | Author | What it measures |
|---|---|---|---|---|
| `set1` | `T1-0001`… | 72 | Claude (`author_method=claude`) | **Unseen scenarios, official style.** 18 new scenarios, one per cell, each with 4 variants (plain + official wrappers). Includes `URGENT:` on low and medium rows (the prefix must not change the label). |
| `set2` | `T2-0001`… | 72 | Claude (`author_method=claude`) | **Unseen scenarios, free student style.** 18 new scenarios, one per cell, each written 4 ways: paraphrases, dialect, typos, code-switching. |
| `set3` | `T3-0001`… | 108 | Claude (`author_method=claude`) | **Hard realistic.** 41 new scenarios, 2–3 per cell, 6 rows per cell: near-miss priority pairs (same topic at two priorities), `URGENT!!!` tone on low/medium and calm wording on high, topic-vs-channel traps (fees asked via e-learning, study plan on MyGJU, attendance on e-learning), irrelevant detail before the request, typos and code-switching, campus vocabulary (MyGJU, e-learning, Teams, buildings A–M, the bank). `scenario_family` uses the category without spaces, e.g. `t3_arabizi_Finance_2`. |
| `set4` | `T4-0001`… | 144 | Claude (`author_method=claude`) | **Final blind set.** Written without any model access (no predictions, reports or prompts read) and never used for tuning. 54 new scenarios, 3 per cell, 8 rows per cell: about half plain requests, the rest with typos, code-switching, irrelevant detail, `URGENT!!!` on low/medium, calm wording on high, near-miss pairs (refund delay vs refund deadline today, probation question vs probation hold) and topic-vs-channel cases (fee asked on e-learning, quiz grade on e-learning, bus tracking app). Arabic/Arabizi medium rows that mention "this morning" only as when it happened. Measure it once, at the end. |

Sets 1 and 2: 32 en, 24 ar, 16 arabizi rows each; set3: 45 en, 36 ar, 27 arabizi; set4: 64 en, 48 ar, 32 arabizi. In every set no normalized
text equals an official `text_norm`; set3 also shares no normalized text with sets 1–2, and set4 none with sets 1–3.
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
(original request ids are kept; `author_method` is `claude`).
Validate with `python scripts/validate_dataset.py --kind our_test data/our_test/our_test.csv`.
