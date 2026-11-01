# Final selection: pre-registered rule and locked holdout (P8.0)

Date locked: 2026-11-01 (written before any rc candidate is scored on it).

## The locked holdout

- Location (outside the repo): `C:\Users\hp\Desktop\campuspulse_locked\locked_holdout.csv`
- sha256: `bdfee810ef38d5c06018254e37b630e07c34d0b801c15455126be6399b2a4614`
- Columns: id, lang, text, category, priority, wrapper. No row text is in the repo. Nobody opens it before the selection step; no model has been run on it.
- Authoring: 4 author subagents (EN-1, EN-2, AR-1, AR-2), 30 rows each, official templated style, new scenarios, all 18 category x priority cells, about 20 % wrapper noise. They read no file. One blind labeller per language; only rows where the labeller agreed on both category and priority are kept.
- Agreement authors vs blind labellers: EN 60/60 category and 60/60 priority; AR 60/60 and 60/60. All 120 rows kept. (100 % agreement is higher than expected; the labellers were told to read only their input, but this cannot be verified. Treat labels as likely but not certainly independent.)

### Counts (low / medium / high)

| category | EN | AR |
|---|---|---|
| Registration | 3 / 4 / 3 | 3 / 4 / 3 |
| IT Support | 4 / 4 / 2 | 3 / 4 / 3 |
| Finance | 4 / 3 / 3 | 4 / 3 / 3 |
| Transportation | 4 / 4 / 2 | 4 / 3 / 3 |
| Facilities | 2 / 4 / 4 | 2 / 4 / 4 |
| Academic Support | 4 / 3 / 3 | 4 / 4 / 2 |
| total | 60 (12 wrapper) | 60 (12 wrapper) |

Every cell has at least 2 rows per language.

## Pre-registered rule (section 1A.4, verbatim)

2. **Candidates:**
   - at most 3 rc candidates (for example rc5 = rc4 + P7; rc6 = rc5 + reviewed data; rc6b = rc6 + the P8.2 or P8.3 winner);
   - each must already pass its own D-016 gate on official OOF, plus our_test no-regression.
3. **Pre-registered rule:**
   - score = 0.7 x category macro-F1 + 0.3 x priority macro-F1 (the 35:15 rubric ratio) on the locked holdout, offline configuration;
   - pick the highest;
   - if two candidates are within the paired-bootstrap noise (CI of the difference includes 0), pick the **simpler one** (fewer moving parts, smaller RAM);
   - official OOF breaks ties.
4. **One look.** The holdout is opened once, every candidate is scored in the same run, and the result is recorded verbatim in models.md section 40. Then the winner goes through P7.7, followed by the evaluator's one-shot re-test as the external confirmation.
5. Report the locked-holdout numbers honestly in the README, including the losers.
