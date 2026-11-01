# Benchmark (artifact v1 sha 722d78d18004)

Protocol: scenario-held-out OOF over the frozen cv_fold folds (oof.npz from train.py; LD-31) + the frozen model on our own test set (pooled and per set) and the probes; nothing tuned on the test data. Macro-F1 (accuracy); n/a = not available offline; cut = not built (UD-4).

## category

| model | oof_official | oof_all | our_test | our_test_set1 | our_test_set2 | our_test_set3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ensemble (tier 0) | 0.935 (0.933) | 0.935 (0.933) | 0.864 (0.863) | 1.000 (1.000) | 0.835 (0.833) | 0.770 (0.778) |
| M1 | 0.205 (0.215) | 0.205 (0.215) | 0.559 (0.574) | 0.444 (0.517) | 0.586 (0.611) | 0.574 (0.583) |
| M2-LR | 0.613 (0.646) | 0.613 (0.646) | 0.793 (0.794) | 1.000 (1.000) | 0.663 (0.694) | 0.724 (0.722) |
| M2-kNN | 0.464 (0.481) | 0.464 (0.481) | 0.716 (0.730) | 0.785 (0.850) | 0.683 (0.708) | 0.645 (0.653) |
| M2-proto | 0.935 (0.933) | 0.935 (0.933) | 0.859 (0.858) | 1.000 (1.000) | 0.834 (0.833) | 0.756 (0.764) |
| M3 | cut | cut | cut | cut | cut | cut |
| Ensemble + router | n/a | n/a | n/a | n/a | n/a | n/a |
| LLM zero-shot (M4) | n/a | n/a | n/a | n/a | n/a | n/a |

## priority

| model | oof_official | oof_all | our_test | our_test_set1 | our_test_set2 | our_test_set3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ensemble (tier 0) | 0.904 (0.903) | 0.904 (0.903) | 0.847 (0.843) | 1.000 (1.000) | 0.782 (0.778) | 0.783 (0.778) |
| M1 | 0.542 (0.537) | 0.542 (0.537) | 0.576 (0.588) | 0.658 (0.667) | 0.638 (0.667) | 0.430 (0.444) |
| M2-LR | 0.651 (0.646) | 0.651 (0.646) | 0.776 (0.774) | 0.817 (0.817) | 0.847 (0.847) | 0.646 (0.667) |
| M2-kNN | 0.396 (0.435) | 0.396 (0.435) | 0.581 (0.574) | 0.548 (0.633) | 0.605 (0.611) | 0.423 (0.486) |
| M2-proto | n/a | n/a | n/a | n/a | n/a | n/a |
| M3 | cut | cut | cut | cut | cut | cut |
| Ensemble + router | n/a | n/a | n/a | n/a | n/a | n/a |
| LLM zero-shot (M4) | n/a | n/a | n/a | n/a | n/a | n/a |

Rows / groups: oof_official 432/30; oof_all 432/30; our_test 204/38; our_test_set1 60/6; our_test_set2 72/16; our_test_set3 72/16
