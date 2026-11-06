# Benchmark (artifact v1 sha a8e2f1e58da5)

Protocol: scenario-held-out OOF over the frozen cv_fold folds (oof.npz from train.py; LD-31) + the frozen model on our own test set (pooled and per set) and the probes; nothing tuned on the test data. Macro-F1 (accuracy); n/a = not available offline; cut = not built (UD-4).

## category

| model | oof_official | oof_all | our_test | our_test_set1 | our_test_set2 | our_test_set3 | our_test_set4 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ensemble (tier 0) | 0.935 (0.933) | 0.935 (0.933) | 0.769 (0.765) | 0.800 (0.792) | 0.828 (0.833) | 0.731 (0.722) | 0.751 (0.750) |
| M1 | 0.205 (0.215) | 0.205 (0.215) | 0.562 (0.563) | 0.586 (0.611) | 0.560 (0.569) | 0.540 (0.546) | 0.547 (0.549) |
| M2-LR | 0.613 (0.646) | 0.613 (0.646) | 0.766 (0.763) | 0.668 (0.681) | 0.774 (0.778) | 0.778 (0.778) | 0.788 (0.785) |
| M2-kNN | 0.464 (0.481) | 0.464 (0.481) | 0.634 (0.636) | 0.663 (0.681) | 0.597 (0.611) | 0.599 (0.602) | 0.651 (0.653) |
| M2-proto | 0.935 (0.933) | 0.935 (0.933) | 0.767 (0.763) | 0.800 (0.792) | 0.815 (0.819) | 0.731 (0.722) | 0.751 (0.750) |
| M3 | cut | cut | cut | cut | cut | cut | cut |
| Ensemble + router | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| LLM zero-shot (M4) | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

## priority

| model | oof_official | oof_all | our_test | our_test_set1 | our_test_set2 | our_test_set3 | our_test_set4 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ensemble (tier 0) | 0.904 (0.903) | 0.904 (0.903) | 0.752 (0.748) | 0.782 (0.778) | 0.809 (0.806) | 0.793 (0.787) | 0.676 (0.674) |
| M1 | 0.542 (0.537) | 0.542 (0.537) | 0.481 (0.497) | 0.638 (0.667) | 0.430 (0.444) | 0.465 (0.472) | 0.437 (0.458) |
| M2-LR | 0.651 (0.646) | 0.651 (0.646) | 0.592 (0.614) | 0.665 (0.667) | 0.606 (0.625) | 0.581 (0.630) | 0.511 (0.569) |
| M2-kNN | 0.396 (0.435) | 0.396 (0.435) | 0.396 (0.447) | 0.605 (0.611) | 0.414 (0.472) | 0.363 (0.417) | 0.271 (0.375) |
| M2-proto | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| M3 | cut | cut | cut | cut | cut | cut | cut |
| Ensemble + router | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| LLM zero-shot (M4) | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

Rows / groups: oof_official 432/30; oof_all 432/30; our_test 396/268; our_test_set1 72/16; our_test_set2 72/16; our_test_set3 108/102; our_test_set4 144/134
