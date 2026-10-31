"""Stage-B threshold rules, tuned on OOF scores only (P1.16, ARCHITECTURE §3.4, LD-18).

Each rule is a small pure function so it can be tested and explained in the report. None of them ever reads
our own test set: it would burn the only honest holdout.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from campuspulse_ai.adapters.models.probs import temperature_scale
from campuspulse_ai.adapters.training.metrics import macro_f1

__all__ = ["temperature_scale"]  # re-exported: stage B scales OOF head vectors with the inference function

# The smallest positive threshold: FrozenConfig rejects thresholds <= 0 ("not trained").
_FLOOR = 1e-6
_GRID_TOLERANCE = 1e-9
_SCORE_DECIMALS = 9  # scores equal to 9 decimals are ties (float noise must not pick a winner)
_EPS = 1e-12
_CDF_TOLERANCE = 1e-12


def tau_ood(max_sim_in_dist: NDArray[np.float64], percentile: float) -> float:
    """The `percentile`-th percentile of OOF max-similarity of in-distribution rows (§3.4).

    A request less similar to the training index than 95 % of held-out training rows (percentile 5) counts
    as out of distribution. Raises ValueError on an empty array or a percentile outside [0, 100].
    """
    sims = np.asarray(max_sim_in_dist, dtype=np.float64)
    if sims.size == 0:
        raise ValueError("tau_ood needs at least one similarity")
    if not 0.0 <= percentile <= 100.0:
        raise ValueError("percentile must be in [0, 100]")
    return max(float(np.percentile(sims, percentile)), _FLOOR)


def tau_from_zero_hits(scores_negative: NDArray[np.float64], margin: float) -> float:
    """`max(scores) + margin` (LD-18): no training row reaches the threshold, so the pool has zero hits.

    The result may exceed 1 for cosine scores (then exemplar similarity can never fire offline). An empty
    array gives `margin`. Raises ValueError for a negative margin.
    """
    if margin < 0:
        raise ValueError("margin must be >= 0")
    scores = np.asarray(scores_negative, dtype=np.float64)
    top = float(scores.max()) if scores.size else 0.0
    return max(top + margin, _FLOOR)


def human_review_maxprob(maxprob: NDArray[np.float64], correct: NDArray[np.bool_], min_acc: float) -> float:
    """The largest max-probability `t` such that OOF accuracy of the rows with max-prob < `t` is < `min_acc`.

    Rows below the returned value are, on held-out data, right less often than `min_acc`, so the online
    policy may send them to a human. When no such `t` exists (every low-confidence band is accurate enough),
    the result is the smallest observed max-prob, so no OOF row falls below it. Always in (0, 1].

    Raises:
        ValueError: empty input, mismatched lengths, or `min_acc` outside (0, 1].
    """
    p = np.asarray(maxprob, dtype=np.float64)
    ok = np.asarray(correct, dtype=bool)
    if p.size == 0 or p.shape != ok.shape:
        raise ValueError("maxprob and correct must be non-empty and the same length")
    if not 0.0 < min_acc <= 1.0:
        raise ValueError("min_acc must be in (0, 1]")
    order = np.argsort(p, kind="stable")
    sorted_p, sorted_ok = p[order], ok[order]
    best = float(sorted_p[0])
    for t in np.unique(sorted_p)[1:]:
        below = sorted_p < t
        if below.any() and float(sorted_ok[below].mean()) < min_acc:
            best = float(t)
    return float(min(max(best, _FLOOR), 1.0))


# --- P2.7: the OOF searches of stage B --------------------------------------------------------------------


def simplex_grid(members: Sequence[str], step: float) -> list[dict[str, float]]:
    """Every weight vector over `members` on the simplex with spacing `step` (weights sum to 1).

    Ordered lexicographically by the integer weight tuple, so the search is deterministic.
    Raises ValueError for no members or a step that does not divide 1.
    """
    if not members:
        raise ValueError("no members")
    units = round(1.0 / step)
    if units <= 0 or abs(units * step - 1.0) > _GRID_TOLERANCE:
        raise ValueError(f"weight step {step} must divide 1")
    out: list[dict[str, float]] = []

    def rec(prefix: list[int], left: int, slots: int) -> None:
        if slots == 1:
            ints = [*prefix, left]
            out.append({m: k / units for m, k in zip(members, ints, strict=True)})
            return
        for k in range(left + 1):
            rec([*prefix, k], left - k, slots - 1)

    rec([], units, len(members))
    return out


def l1_to_uniform(weights: Mapping[str, float]) -> float:
    u = 1.0 / len(weights)
    return float(sum(abs(w - u) for w in weights.values()))


def simplex_weights(
    probs: Mapping[str, NDArray[np.float64]],
    y: Sequence[str],
    step: float,
    labels: Sequence[str],
    *,
    mask: NDArray[np.bool_] | None = None,
    objective: Callable[[Mapping[str, float]], float] | None = None,
) -> dict[str, float]:
    """Ensemble weights on the simplex grid that maximize OOF macro-F1 (P2.7, ARCHITECTURE §3.4).

    Args:
        probs: member name -> (n, L) OOF probabilities (label order `labels`).
        y: the n gold labels. step: `grids.weight_step`. mask: rows that count (e.g. official, or the
            rows outside the scored fold in a nested search); None = all.
        objective: optional score of a weight vector (higher is better) replacing the argmax macro-F1,
            e.g. the macro-F1 of the priority head stacked on the weighted members.

    Tie-break: the smallest L1 distance to uniform weights, then the earliest grid point (lexicographic
    member order), so equal-scoring solutions resolve the same way every run.
    """
    members = list(probs)
    rows = np.ones(len(y), dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    gold = [lab for lab, keep in zip(y, rows, strict=True) if keep]
    best: tuple[float, float, int] | None = None
    chosen: dict[str, float] = {}
    for i, w in enumerate(simplex_grid(members, step)):
        if objective is not None:
            score = objective(w)
        else:
            mix = sum(w[m] * probs[m] for m in members)
            pred = [labels[int(j)] for j in np.argmax(np.asarray(mix)[rows], axis=1)]
            score = macro_f1(gold, pred, labels)
        key = (-round(score, _SCORE_DECIMALS), l1_to_uniform(w), i)
        if best is None or key < best:
            best, chosen = key, w
    return chosen


def select_from_grid(scores: Mapping[float, tuple[float, ...]], grid: Sequence[float]) -> float:
    """The grid value with the best score tuple (compared in order, higher is better); ties go to the value
    closest to the grid midpoint, then the smaller value. `scores` maps each grid value to its tuple."""
    mid = sorted(grid)[(len(grid) - 1) // 2]
    return min(grid, key=lambda c: (tuple(-round(s, _SCORE_DECIMALS) for s in scores[c]), abs(c - mid), c))


def nll(p: NDArray[np.float64], y_idx: NDArray[np.int64]) -> float:
    """Mean negative log-likelihood of the gold labels (probabilities clipped at 1e-12)."""
    picked = np.clip(np.asarray(p)[np.arange(len(y_idx)), y_idx], _EPS, 1.0)
    return float(-np.log(picked).mean())


def best_temperature(
    scored: Callable[[float], NDArray[np.float64]], y_idx: NDArray[np.int64], grid: Sequence[float]
) -> float:
    """The grid temperature with the lowest NLL of `scored(T)` (a proper scoring rule, so the choice is a
    calibration, not an accuracy tweak); ties go to the smaller temperature."""
    return min(grid, key=lambda t: (round(nll(scored(t), y_idx), _SCORE_DECIMALS), t))


def conformal_quantile(
    scores: NDArray[np.float64], groups: Sequence[str], alpha: float, method: str
) -> float:
    """The LAC threshold q from nonconformity scores 1 - p(true label).

    - `row`: the ⌈(n+1)(1−α)⌉-th smallest of the n row scores (P1.14).
    - `group`: the pooled-CDF rule for clustered calibration data (Dunn, Wasserman and Ramdas, 2022):
      every cv_group has total weight 1/G spread over its rows, and q is the smallest score whose weighted
      CDF reaches ⌈(G+1)(1−α)⌉/G (1 when that exceeds 1). The wrapper variants of one scenario are one
      draw, not n, so the finite-sample correction uses G ≈ 30 (LD-32) instead of n = 432.
    Raises ValueError on an unknown method or empty input.
    """
    s = np.asarray(scores, dtype=np.float64)
    if s.size == 0 or s.size != len(groups):
        raise ValueError("scores and groups must be non-empty and the same length")
    if method == "row":
        k = min(math.ceil((s.size + 1) * (1.0 - alpha)), s.size)
        return float(np.sort(s)[k - 1])
    if method != "group":
        raise ValueError(f"unknown conformal calibration method {method!r}")
    g = np.asarray(groups)
    names, inverse, counts = np.unique(g, return_inverse=True, return_counts=True)
    n_groups = len(names)
    level = math.ceil((n_groups + 1) * (1.0 - alpha)) / n_groups
    if level > 1.0:
        return 1.0
    weights = 1.0 / (n_groups * counts[inverse])
    order = np.argsort(s, kind="stable")
    cdf = np.cumsum(weights[order])
    pos = int(np.searchsorted(cdf, level - _CDF_TOLERANCE))
    return float(s[order][min(pos, s.size - 1)])
