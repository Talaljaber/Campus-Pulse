"""Stage-B threshold rules (P1.16, §3.4, LD-18)."""

from __future__ import annotations

import numpy as np
import pytest

from campuspulse_ai.adapters.training.train_config import midpoint
from campuspulse_ai.adapters.training.tuning import human_review_maxprob, tau_from_zero_hits, tau_ood


def test_tau_ood_is_the_percentile() -> None:
    sims = np.linspace(0.5, 1.0, 101)
    assert tau_ood(sims, 5) == pytest.approx(0.525)
    with pytest.raises(ValueError):
        tau_ood(np.array([]), 5)


def test_tau_from_zero_hits_leaves_no_hit() -> None:
    scores = np.array([0.31, 0.88, 0.42])
    tau = tau_from_zero_hits(scores, 0.02)
    assert tau == pytest.approx(0.90)
    assert not (scores >= tau).any()


def test_human_review_maxprob() -> None:
    p = np.array([0.30, 0.35, 0.40, 0.60, 0.80, 0.90])
    ok = np.array([False, False, True, True, True, True])
    # below 0.40 accuracy is 0/2; below 0.60 it is 1/3 (< 0.6); below 0.80 it is 2/4 (< 0.6); below 0.90: 3/5
    assert human_review_maxprob(p, ok, 0.6) == pytest.approx(0.80)
    # always accurate: nothing should fall below the threshold
    assert human_review_maxprob(p, np.ones(6, dtype=bool), 0.6) == pytest.approx(0.30)


def test_grid_midpoint() -> None:
    assert midpoint((0.5, 1, 2, 4, 8)) == 2
