# Final selection result (P8.0 rule, scored once on 2026-11-01)

Holdout: 120 rows (EN 60, AR 60), sha256 `bdfee810ef38d5c06018254e37b630e07c34d0b801c15455126be6399b2a4614` (verified by `scripts/score_holdout.py` before scoring). Aggregates only; no row text is in the repo. Candidates scored in one run, both modes: C0 (rc4 weights plus the P7.2 lexicons and P7.3 floors), C1 (C0 plus the 447 model-reviewed rows), C3 (reviewed rows teach category only). C2 was left out (fails every gate, no gain over C1; the rule allows at most 3 candidates).

## Verbatim output of `scripts/score_holdout.py`
```
===== C0 offline
pooled  n=120 category F1 0.894 (acc 0.892)  priority F1 0.813 (acc 0.808)  score 0.870
AR      n= 60 category F1 0.870 (acc 0.867)  priority F1 0.753 (acc 0.750)  score 0.835
EN      n= 60 category F1 0.918 (acc 0.917)  priority F1 0.866 (acc 0.867)  score 0.903
score = 0.7 x category + 0.3 x priority (pooled): 0.8701  routing {'auto': 0.5666666666666667, 'ask': 0.16666666666666666, 'review': 0.26666666666666666}
===== C0 llm
pooled  n=120 category F1 0.909 (acc 0.908)  priority F1 0.813 (acc 0.808)  score 0.880
AR      n= 60 category F1 0.901 (acc 0.900)  priority F1 0.753 (acc 0.750)  score 0.857
EN      n= 60 category F1 0.918 (acc 0.917)  priority F1 0.866 (acc 0.867)  score 0.903
score = 0.7 x category + 0.3 x priority (pooled): 0.8803  routing {'auto': 0.625, 'ask': 0.175, 'review': 0.2}
===== C1 offline
pooled  n=120 category F1 0.886 (acc 0.883)  priority F1 0.898 (acc 0.900)  score 0.889
AR      n= 60 category F1 0.851 (acc 0.850)  priority F1 0.899 (acc 0.900)  score 0.865
EN      n= 60 category F1 0.918 (acc 0.917)  priority F1 0.898 (acc 0.900)  score 0.912
score = 0.7 x category + 0.3 x priority (pooled): 0.8894  routing {'auto': 0.5916666666666667, 'ask': 0.39166666666666666, 'review': 0.016666666666666666}
===== C1 llm
pooled  n=120 category F1 0.910 (acc 0.908)  priority F1 0.915 (acc 0.917)  score 0.912
AR      n= 60 category F1 0.903 (acc 0.900)  priority F1 0.933 (acc 0.933)  score 0.912
EN      n= 60 category F1 0.918 (acc 0.917)  priority F1 0.898 (acc 0.900)  score 0.912
score = 0.7 x category + 0.3 x priority (pooled): 0.9119  routing {'auto': 0.675, 'ask': 0.31666666666666665, 'review': 0.008333333333333333}
===== C3 offline
pooled  n=120 category F1 0.886 (acc 0.883)  priority F1 0.813 (acc 0.808)  score 0.864
AR      n= 60 category F1 0.851 (acc 0.850)  priority F1 0.753 (acc 0.750)  score 0.821
EN      n= 60 category F1 0.918 (acc 0.917)  priority F1 0.866 (acc 0.867)  score 0.903
score = 0.7 x category + 0.3 x priority (pooled): 0.8638  routing {'auto': 0.8666666666666667, 'ask': 0.13333333333333333, 'review': 0.0}
===== C3 llm
pooled  n=120 category F1 0.910 (acc 0.908)  priority F1 0.813 (acc 0.808)  score 0.881
AR      n= 60 category F1 0.903 (acc 0.900)  priority F1 0.753 (acc 0.750)  score 0.858
EN      n= 60 category F1 0.918 (acc 0.917)  priority F1 0.866 (acc 0.867)  score 0.903
score = 0.7 x category + 0.3 x priority (pooled): 0.8813  routing {'auto': 0.9333333333333333, 'ask': 0.06666666666666667, 'review': 0.0}
```

## Paired bootstrap of the offline score (B = 2000, rows resampled, seed 42, 90% CI)
```
point scores: {'C0': 0.8701, 'C1': 0.8894, 'C3': 0.8638}
C1-C0: mean +0.0191  90% CI [-0.0066, +0.0444]
C3-C0: mean -0.0064  90% CI [-0.0235, +0.0093]
C1-C3: mean +0.0254  90% CI [+0.0062, +0.0445]
priority discordant pairs C1 right/C0 wrong: 17  C0 right/C1 wrong: 6
category discordant pairs C1 right/C0 wrong: 1  C0 right/C1 wrong: 2
```

## Decision (pre-registered rule: highest score; if within noise, the simpler candidate)
- Highest offline score: C1 (0.889), then C0 (0.870), then C3 (0.864).
- C1 minus C0 is +0.019 with a 90% CI of [-0.007, +0.044]: within noise. The rule picks the simpler candidate: **C0**.
- C3 minus C0 is -0.006 [-0.024, +0.009]: within noise, and C3 is more complex.
- **Selected: C0, frozen as v1-rc5** (artifact sha `385c74bc2ab4`; only MANIFEST.json and the two lexicon files differ from rc4). The encoder and translator files are unchanged, so the model tarball of release models-v1-rc4 still serves.

## Honest notes
- On the holdout C1's priority is better than C0's (priority F1 0.898 vs 0.813; 17 rows right only for C1, 6 right only for C0), while category is equal (1 vs 2 discordant rows). C1 also doubled the ask rate (0.39 vs 0.17) because its conformal quantiles were calibrated on all 879 pool rows including the reviewed rows.
- The holdout and the dev set were written by the same model family that drafted and panel-labelled the reviewed rows, so a shared drafting style can flatter C1.
- The LLM front end lifts the holdout category F1 of C0 from 0.894 to 0.909 (Arabic 0.870 to 0.901); English is unchanged by design, and priority does not move.
- The holdout is LLM-written and has only 120 rows: differences under about 0.03 are noise.
