# CampusPulse results, as measured

Status: 2026-11-02. Model: `models/frozen/v1` = **v1-rc7**, artifact sha `e5317d41d49e`.
This file lists every result we have, where it came from, and what it does not prove. Numbers are macro-F1 unless marked. Nothing here is the organisers' hidden test: **we have no hidden-test score and will not get one.**

## 1. Short version

- On the official data (our own scenario-held-out cross-validation): category **0.935**, priority **0.904**.
- On test sets written by us or by an LLM, scores are lower: roughly **0.81 to 0.92 category** and **0.75 to 0.86 priority**, depending on language and mode.
- The LLM front end clearly helps **Arabic and Arabizi category** (Arabizi blind set: 0.61 offline, 0.88 with the LLM). It does not help English, which is never sent to it.
- **Offline Arabizi category is poor (0.61)**, and offline is what a judge sees if they run without a key.
- Six known weaknesses remain (section 8).
- Test sets are small (about 60 to 70 rows per language). Differences under about 0.03 are noise; blind-set intervals are about ±0.07 to ±0.10.

## 2. What each number is, and how far to trust it

| Source | Rows | Who wrote it | How it was used | Trust |
|---|---|---|---|---|
| Official cross-validation (OOF) | 432 official rows, 30 scenario groups | Organisers | Scenario-held-out folds; the model never sees a scenario's group in training | Our own estimate on templated data. Likely closer to the hidden test than the others, but not the same thing |
| `our_test` (4 sets) | 396 rows | LLM-written (Claude), kept apart from training | Never used for training; regression check after each change | Fair, but we have looked at it many times |
| Dev set | 216 rows (108 tune, 108 check) | LLM-assisted | Tune split used to design rules; check split read once per agent | The check split has now been read by **two** separate agents, so it is no longer untouched |
| Locked holdout | 120 rows, English and Arabic | LLM authors, LLM labellers | Scored **once**, on candidates C0, C1, C3, before P7.8 to P7.12 | LLM-written, so friendlier than real student text. Cannot be reused |
| QA set 1 | independent QA agent's rows | QA agent | Regression check (we saw it) | Not blind |
| QA blind set B | about 70 agreed rows per language | QA agent | Run once per mode on rc6, then spent | Best honest number we have, but not run on rc7 |

## 3. Official data, cross-validation (rc7, `reports/benchmark.md`)

| | Category | Priority |
|---|---|---|
| Ensemble (the shipped model) | 0.935 (accuracy 0.933) | 0.904 (0.903) |

- 432 rows, 30 groups. Category comes almost entirely from the prototype member (0.935 alone); the other members are much weaker on their own.
- Identical to rc5 and rc6: the later changes (P7.8 to P7.12) changed only lexicon rules, and the benchmark was re-run after each refreeze with only the sha changing.

## 4. Our own test sets (offline model, `reports/benchmark.md`)

| Set | Rows | Category | Priority |
|---|---|---|---|
| `our_test` pooled | 396 | 0.769 | 0.752 |
| Set 1 (unseen scenarios, official style) | 72 | 0.800 | 0.782 |
| Set 2 (unseen scenarios, free student style) | 72 | 0.828 | 0.809 |
| Set 3 (hard realistic) | 108 | 0.731 | 0.793 |
| Set 4 (final blind set) | 144 | 0.751 | 0.676 |

These are the offline model alone. With the LLM front end and tie-breaker (the default when a key is set), set 4
reaches 0.925 category and 0.958 priority (README, "Prediction").

## 5. Locked holdout (120 rows: 60 English, 60 Arabic), scored once

Candidates were scored in one run; the rule for choosing was written before scoring. These are **C0 numbers from before P7.8 to P7.12**. rc7 has never been scored on this set and now cannot be (one look only).

| | Category | Priority | Weighted score (0.7 x cat + 0.3 x pri) |
|---|---|---|---|
| C0 offline (what we shipped as rc5) | 0.894 | 0.813 | 0.870 |
| C0 with LLM front end | 0.909 | 0.813 | 0.880 |
| C1 offline (not shipped) | 0.886 | 0.898 | 0.889 |
| C1 with LLM front end (not shipped) | 0.910 | 0.915 | 0.912 |
| C3 offline (not shipped) | 0.886 | 0.813 | 0.864 |

- By language, C0 offline: English 0.918 category / 0.866 priority; Arabic 0.870 / 0.753.
- **C1 scored higher than C0 on priority.** The difference in the weighted score (+0.019, 90% interval [-0.007, +0.044]) includes zero, so the rule we set beforehand picked the simpler C0. This is a judgment call, not a clear win for C0.
- Caveats on C1: it asked clarifying questions about twice as often (0.39 against 0.17), its extra training rows were labelled by AI models, not humans. The holdout's writers belong to the same model family as the labellers of those extra rows, which may flatter C1.
- C0 does not use the 447 AI-reviewed rows.

## 6. Dev set (LLM-assisted, 216 rows) and QA set 1

Dev set, priority macro-F1 on the check split (108 rows), reported by the two fix agents separately, each against rc5:

| Change | Before | After |
|---|---|---|
| P7.8 lexicons (outage, transport, deadline, distress; distress raises priority to high) | 0.743 | 0.764 (paired gain +0.022, interval [0.000, +0.050]) |
| P7.9 LLM cue floor (LLM flow, Arabic and Arabizi only) | 0.743 | 0.802 (Arabizi 0.674 to 0.800, Arabic 0.815 to 0.865) |

- These were measured separately; the two combined were not re-measured on the dev set.
- P7.9 on the tune split gained only +0.009 with an interval that touches zero. The check split and the pooled result are clearly above zero.
- False escalation by the LLM floor on low and medium Arabic/Arabizi rows: 0 of 84.
- Deadline within 24 hours is still not fixed: high recall only 0.50 to 0.67 (P7.9) and 0 of 3 on the check split (P7.8).

QA set 1 (we saw it; regression check on C0 against the earlier model):

- Priority: English 0.78 to 0.83, Arabic 0.70 to 0.77, Arabizi 0.58 to 0.68 (20 rows fixed, none broken).
- Arabic category 0.77 to 0.88 with the LLM; Arabizi about 0.79 to 0.80 with the LLM against 0.62 offline.
- A bilingual reviewer rated 37 of 40 translations good and 3 minor, with none major.

## 7. Blind set B on rc6 (run once per mode, QA agent)

About 70 agreed rows per language. rc6 differs from rc7 by P7.11 and P7.12 only (section 9).

| Language | Category, offline | Category, with LLM | Priority, offline | Priority, with LLM |
|---|---|---|---|---|
| English | 0.860 | 0.860 | 0.849 | 0.849 |
| Arabic | 0.805 | 0.915 | 0.793 | 0.862 |
| Arabizi | **0.610** | 0.878 | 0.752 | 0.860 |

- English is identical in both modes because it is never sent to the LLM.
- False-high rate on gold low and medium rows: 0 to 4.2% in every cell.
- Rows that really are urgent but never say so, flagged high: offline English 9 of 15, Arabic 7 of 15, Arabizi 5 of 15; with the LLM Arabic 15 of 15, Arabizi 14 of 15.
- Auto-answered accuracy at least 0.83 in every cell. Routing with the LLM: Arabic 13 auto, 30 ask, 28 review; Arabizi 18 auto, 25 ask, 28 review; English 60 auto and 11 empty.
- QA's own report: `C:\Users\hp\Desktop\campuspulse_eval\testset_B\run_rc6\REPORT_rc6_testB.md` (kept outside the repo; the lead has not opened it).

English priority (0.849) and Arabic offline category (0.805) sit about 0.05 to 0.10 below the cross-validation numbers, which is the gap we expect between templated and freer wording.

## 8. Known weaknesses (from set B and QA, unfixed unless marked)

1. **Arabizi offline category is 0.61.** No cheap fix known.
2. Implicit account compromise was caught 0 of 10 offline on set B. **P7.12 addresses this; not yet measured on blind data.**
3. An injected "send this to Finance" steered the department on set B (Arabizi 2 of 2, English 1 of 2). **P7.11 addresses this; not yet measured on blind data.** The agent did not trace whether QA's rows were flagged by regex or by the similarity check used online, and the similarity path strips nothing, so steering may remain online.
4. Queue-jump: the flag fires, but one Arabic row still ended at high priority.
5. Distress: none of 6 distress probes got a distress flag, even after P7.8 widened the patterns.
6. English vague or off-topic input is still auto-answered.
7. Deadline within 24 hours is still partly missed (section 6).
8. Online distress requests stop before labelling, so the high priority shows only in batch and in the stored result.

## 9. What changed between rc5 and rc7, and how each change was checked

| Version | Change | Checks |
|---|---|---|
| rc5 | C0 selected under the pre-registered rule | Holdout one-look (section 5) |
| rc6 | P7.8 lexicons and distress floor; P7.9 LLM cue floor, injection to review, queue-jump and vague guards | Benchmark unchanged; set B run on this version |
| rc7 | P7.11 injected routing orders flagged and stripped; P7.12 implicit account compromise floor | Benchmark unchanged (only sha changed); 1232 default tests and 24 artifact tests pass; four hand-written probes behaved as intended; **no blind-data measurement** |

- Weights, encoder and translator are the same in all three; only lexicons, guards and the manifest changed.
- The fix agents for P7.11 and P7.12 could not run the full no-regression checks in their own worktrees. I ran the benchmark and the tests after merging, and a full row-by-row diff of the 432 official predictions against rc6 was **not** run. Zero false hits on non-high official rows was verified at lexicon level (P7.8, P7.12) and at guard level (P7.11).
- The new Arabic and Arabizi patterns were written and tested by the agents; **no native speaker has verified them.**

## 10. What we do not know

- The hidden-test score, or how other teams score.
- How the model does on real student messages (all non-official test text was written by us, an LLM or a QA agent).
- Whether the judges run with an API key. Without one the offline numbers apply, and the LLM floor and translation do not run.
- Latency, memory and LLM cost of rc7. The earlier candidates showed no latency or memory regression, but I have no rc7 timings to report. In one agent run a 1000-row speed test took 68.7 s against a 60 s limit; it passed in my full runs, so treat timing as unverified.
- Whether the 447 AI-reviewed rows would help on real text (C1 stays an unshipped alternative).

## 11. Disclosures tied to these results

- LLM front end: DeepSeek v4.1 Flash via OpenRouter, behind `--use-llm` / `LLM_FRONTEND=true`; sends Arabic and Arabizi text to a third party; English is not sent.
- Offline translation: opus-mt (CTranslate2 int8). Encoder: multilingual-e5-small (int8 ONNX).
- Model panel for the 447 review rows: draft model, checker, gpt-4o-mini, Qwen3.8 max, GLM-5.3. These rows are AI-labelled, not human-reviewed, and are **not** in the shipped model.
- The explanation column is internal and was saved for a later retrain; it did not improve scores and is not used by the shipped model.

## 12. How to reproduce

- Cross-validation and our tests: `python services/ai/evaluate.py --benchmark` (writes `reports/`).
- Default tests: `pytest services/ai/tests -q -m "not train and not artifacts and not supabase"` (1232 passed, 1 skipped). Artifact tests: `-m artifacts` (24 passed).
- Static checks: `ruff check services/ai` and `mypy --strict services/ai/campuspulse_ai` (both clean).
- CI on `main` at commit `af28cc2` (rc7): all Python jobs green; the web job was skipped because no web files changed.
- Holdout and set B are kept outside the repo and cannot be re-scored without breaking their one-look rule. Selection record: `docs/plan/p7/SELECTION_RESULT.md`.
