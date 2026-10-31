"""Stage-B threshold rules, tuned on OOF scores only (P1.16, ARCHITECTURE §3.4, LD-18).

Each rule is a small pure function so it can be tested and explained in the report. None of them ever reads
our own test set: it would burn the only honest holdout.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# The smallest positive threshold: FrozenConfig rejects thresholds <= 0 ("not trained").
_FLOOR = 1e-6


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
