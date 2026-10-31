"""Stage-B threshold rules (P1.16, §3.4, LD-18)."""

from __future__ import annotations

import numpy as np
import pytest

from campuspulse_ai.adapters.training.metrics import macro_f1
from campuspulse_ai.adapters.training.oof import declared_weights
from campuspulse_ai.adapters.training.train_config import midpoint
from campuspulse_ai.adapters.training.tuning import (
    conformal_quantile,
    human_review_maxprob,
    simplex_grid,
    simplex_weights,
    tau_from_zero_hits,
    tau_ood,
    temperature_scale,
)


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


# --- P2.7 stage B ----------------------------------------------------------------------------------------

LABS = ("a", "b", "c")


def test_simplex_weights_sum_to_one_and_beat_uniform_on_synthetic() -> None:
    rng = np.random.default_rng(42)
    y_idx = rng.integers(0, 3, 300)
    y = [LABS[i] for i in y_idx]
    good = np.full((300, 3), 0.1)
    good[np.arange(300), y_idx] = 0.8  # always right
    noise = rng.dirichlet(np.ones(3), 300)  # uninformative, often confidently wrong
    probs = {"good": good, "noise": noise}
    w = simplex_weights(probs, y, 0.1, LABS)
    assert sum(w.values()) == pytest.approx(1.0) and set(w) == {"good", "noise"}
    pick = [LABS[j] for j in np.argmax(w["good"] * good + w["noise"] * noise, axis=1)]
    uni = [LABS[j] for j in np.argmax(0.5 * good + 0.5 * noise, axis=1)]
    assert macro_f1(y, pick, LABS) >= macro_f1(y, uni, LABS)
    assert len(simplex_grid(["x", "y", "z"], 0.1)) == 66  # C(12, 2)


def test_simplex_tie_breaks_towards_uniform() -> None:
    p = np.eye(3)[[0, 1, 2]]
    w = simplex_weights({"m1": p, "m2": p}, list(LABS), 0.1, LABS)  # every point scores 1.0
    assert w == {"m1": 0.5, "m2": 0.5}


def test_tau_ood_percentile() -> None:
    assert tau_ood(np.array([0.2, 0.4, 0.6, 0.8, 1.0]), 50) == pytest.approx(0.6)


def test_tau_from_zero_hits_has_no_hits() -> None:
    sims = np.array([0.5, 0.97, 0.7])
    assert not (sims >= tau_from_zero_hits(sims, 0.02)).any()


def test_human_review_maxprob_rule() -> None:
    p = np.array([0.2, 0.3, 0.9, 0.95])
    ok = np.array([False, False, True, True])
    t = human_review_maxprob(p, ok, 0.6)
    below = p < t
    assert below.any() and ok[below].mean() < 0.6 and not (p[~below] < 0.9).any()


def test_group_conformal_quantile_is_more_conservative_on_clustered_scores() -> None:
    # 27 well-predicted groups of 20 rows (score 0.1) and 3 badly predicted groups of 10 rows (score 0.9):
    # 95 % of the ROWS are fine, but only 27/30 = 90 % of the GROUPS
    scores = np.array([0.1] * 540 + [0.9] * 30)
    groups = [f"g{i // 20}" for i in range(540)] + [f"h{i // 10}" for i in range(30)]
    assert conformal_quantile(scores, groups, 0.1, "row") == pytest.approx(0.1)
    # ceil(31 * 0.9) / 30 = 28/30 of the group mass is needed, which reaches the 0.9 groups
    assert conformal_quantile(scores, groups, 0.1, "group") == pytest.approx(0.9)
    with pytest.raises(ValueError):
        conformal_quantile(scores, groups, 0.1, "other")


def test_temperature_scale_keeps_argmax_and_softens() -> None:
    p = np.array([[0.9, 0.08, 0.02]])
    soft = temperature_scale(p, 3.0)
    assert np.argmax(soft) == 0 and soft[0, 0] < 0.9 and soft.sum() == pytest.approx(1.0)
    assert np.allclose(temperature_scale(p, 1.0), p)


def test_declared_weights_renormalize_over_present_members() -> None:
    w = declared_weights({"m1": 0.0, "m2lr": 0.5, "m2proto": 0.5}, ["m1", "m2lr", "m2knn"])
    assert w == {"m1": 0.0, "m2lr": 1.0, "m2knn": 0.0}
    w = declared_weights({"m2lr": 0.5}, ["m1", "m2knn"])  # nothing declared is present: equal
    assert w == {"m1": 0.5, "m2knn": 0.5}
    pri = declared_weights({"m1": 1 / 3, "m2lr": 1 / 3, "m2knn": 1 / 3}, ["m1", "m2lr", "m2knn", "m2proto"],
                           exclude=frozenset({"m2proto"}))
    assert pri["m2proto"] == 0.0 and sum(pri.values()) == pytest.approx(1.0)
