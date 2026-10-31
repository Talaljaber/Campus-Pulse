"""Evaluation metrics (P1.16 / first results; `evaluate.py` P2.8 extends this module, LD-21).

Plain numpy, no sklearn.metrics, so the definitions are visible: macro-F1 averages per-class F1 over the
labels that occur in the gold labels **or** the predictions (a class that is never gold but is predicted
counts with F1 = 0, which is the conservative choice); accuracy is the share of exact matches.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from campuspulse_ai.domain.values import PredictionSet


def macro_f1(y: Sequence[str], yhat: Sequence[str], labels: Sequence[str]) -> float:
    """Macro-averaged F1 over `labels` that appear in `y` or `yhat`. ValueError on mismatched lengths."""
    if len(y) != len(yhat):
        raise ValueError("y and yhat must have the same length")
    present = [lab for lab in labels if lab in set(y) or lab in set(yhat)]
    if not present:
        return 0.0
    scores = []
    for lab in present:
        tp = sum(1 for a, b in zip(y, yhat, strict=True) if a == lab and b == lab)
        fp = sum(1 for a, b in zip(y, yhat, strict=True) if a != lab and b == lab)
        fn = sum(1 for a, b in zip(y, yhat, strict=True) if a == lab and b != lab)
        denom = 2 * tp + fp + fn
        scores.append(2 * tp / denom if denom else 0.0)
    return sum(scores) / len(scores)


def accuracy(y: Sequence[str], yhat: Sequence[str]) -> float:
    if len(y) != len(yhat):
        raise ValueError("y and yhat must have the same length")
    return sum(a == b for a, b in zip(y, yhat, strict=True)) / len(y) if y else 0.0


def per_class_f1(y: Sequence[str], yhat: Sequence[str], labels: Sequence[str]) -> dict[str, float]:
    out = {}
    for lab in labels:
        tp = sum(1 for a, b in zip(y, yhat, strict=True) if a == lab and b == lab)
        fp = sum(1 for a, b in zip(y, yhat, strict=True) if a != lab and b == lab)
        fn = sum(1 for a, b in zip(y, yhat, strict=True) if a == lab and b != lab)
        denom = 2 * tp + fp + fn
        out[lab] = 2 * tp / denom if denom else 0.0
    return out


def confusion(y: Sequence[str], yhat: Sequence[str], labels: Sequence[str]) -> dict[str, dict[str, int]]:
    """{gold: {predicted: count}} over `labels`."""
    table = {a: dict.fromkeys(labels, 0) for a in labels}
    for a, b in zip(y, yhat, strict=True):
        table[a][b] += 1
    return table


@dataclass(frozen=True)
class CoverageStats:
    coverage: float
    mean_size: float
    singleton_rate: float
    n: int


def coverage(sets: Sequence[PredictionSet], y: Sequence[str]) -> CoverageStats:
    """Empirical coverage (gold label in the set), mean set size and singleton rate."""
    if len(sets) != len(y):
        raise ValueError("sets and y must have the same length")
    n = len(y)
    if n == 0:
        return CoverageStats(0.0, 0.0, 0.0, 0)
    hit = sum(label in s.labels for s, label in zip(sets, y, strict=True))
    return CoverageStats(hit / n, sum(s.size for s in sets) / n, sum(s.size == 1 for s in sets) / n, n)


@dataclass(frozen=True)
class ReliabilityBin:
    """One equal-width confidence bin: [lower, upper), mean confidence, accuracy and count."""

    lower: float
    upper: float
    confidence: float
    accuracy: float
    count: int


def ece(
    confidence: Sequence[float], correct: Sequence[bool], bins: int
) -> tuple[float, list[ReliabilityBin]]:
    """Expected calibration error of the top-label confidence over `bins` equal-width bins (the last bin
    includes 1.0), and the reliability bins (empty bins are kept with count 0). ValueError on bad input."""
    if len(confidence) != len(correct):
        raise ValueError("confidence and correct must have the same length")
    if bins < 1:
        raise ValueError("bins must be >= 1")
    n = len(confidence)
    out: list[ReliabilityBin] = []
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(confidence) if lo <= c < hi or (b == bins - 1 and c == hi)]
        if idx:
            conf = sum(confidence[i] for i in idx) / len(idx)
            acc = sum(bool(correct[i]) for i in idx) / len(idx)
            total += len(idx) / n * abs(acc - conf)
        else:
            conf, acc = 0.0, 0.0
        out.append(ReliabilityBin(lo, hi, conf, acc, len(idx)))
    return (total if n else 0.0), out


def _f1_from_table(table: NDArray[np.int64]) -> float:
    """Macro-F1 from a (gold x predicted) count table, over labels that occur as gold or predicted
    (the same convention as `macro_f1`)."""
    tp = np.diag(table).astype(np.float64)
    gold = table.sum(axis=1).astype(np.float64)
    pred = table.sum(axis=0).astype(np.float64)
    present = (gold + pred) > 0
    if not present.any():
        return 0.0
    denom = gold + pred
    f1 = np.where(denom > 0, 2 * tp / np.where(denom > 0, denom, 1.0), 0.0)
    return float(f1[present].mean())


def paired_group_bootstrap(
    y: Sequence[str],
    base: Sequence[str],
    cand: Sequence[str],
    groups: Sequence[str],
    labels: Sequence[str],
    *,
    resamples: int,
    seed: int,
    low_pct: float,
    high_pct: float,
) -> dict[str, float]:
    """Paired bootstrap over groups (cv_groups) of macro-F1(cand) - macro-F1(base) on the same rows.

    Whole groups are resampled with replacement, because the rows of one scenario are wrapper copies, not
    independent draws (LD-32). Returns the observed delta, the [low_pct, high_pct] percentile interval and
    the share of resamples where `cand` is better.
    """
    if not (len(y) == len(base) == len(cand) == len(groups)):
        raise ValueError("y, base, cand and groups must align")
    names = sorted(set(groups))
    code = {lab: j for j, lab in enumerate(labels)}
    yi = np.array([code[v] for v in y], dtype=np.int64)
    bi = np.array([code[v] for v in base], dtype=np.int64)
    ci = np.array([code[v] for v in cand], dtype=np.int64)
    g_of = {g: j for j, g in enumerate(names)}
    gi = np.array([g_of[g] for g in groups], dtype=np.int64)
    n_lab, n_grp = len(labels), len(names)
    # per-group confusion counts (gold, predicted), so a resample is a weighted sum of group tables
    tb = np.zeros((n_grp, n_lab, n_lab), dtype=np.int64)
    tc = np.zeros((n_grp, n_lab, n_lab), dtype=np.int64)
    np.add.at(tb, (gi, yi, bi), 1)
    np.add.at(tc, (gi, yi, ci), 1)
    rng = random.Random(seed)
    diffs = []
    for _ in range(resamples):
        counts = np.bincount([rng.randrange(n_grp) for _g in range(n_grp)], minlength=n_grp)
        diffs.append(
            _f1_from_table(np.tensordot(counts, tc, axes=1))
            - _f1_from_table(np.tensordot(counts, tb, axes=1))
        )
    diffs.sort()

    def pct(q: float) -> float:
        k = min(max(int(round(q / 100.0 * (len(diffs) - 1))), 0), len(diffs) - 1)
        return diffs[k]

    return {
        "delta": macro_f1(y, cand, labels) - macro_f1(y, base, labels),
        "ci_low": pct(low_pct),
        "ci_high": pct(high_pct),
        "p_better": sum(d > 0 for d in diffs) / len(diffs) if diffs else 0.0,
    }


def summary(
    y_cat: Sequence[str],
    p_cat: Sequence[str],
    y_pri: Sequence[str],
    p_pri: Sequence[str],
    cat_labels: Sequence[str],
    pri_labels: Sequence[str],
) -> Mapping[str, float]:
    """Category and priority macro-F1 and accuracy, plus joint accuracy (both labels right)."""
    joint = sum(a == b and c == d for a, b, c, d in zip(y_cat, p_cat, y_pri, p_pri, strict=True))
    return {
        "category_macro_f1": macro_f1(y_cat, p_cat, cat_labels),
        "category_accuracy": accuracy(y_cat, p_cat),
        "priority_macro_f1": macro_f1(y_pri, p_pri, pri_labels),
        "priority_accuracy": accuracy(y_pri, p_pri),
        "joint_accuracy": joint / len(y_cat) if y_cat else 0.0,
    }
