"""Evaluation metrics (P1.16 / first results; `evaluate.py` P2.8 extends this module, LD-21).

Plain numpy, no sklearn.metrics, so the definitions are visible: macro-F1 averages per-class F1 over the
labels that occur in the gold labels **or** the predictions (a class that is never gold but is predicted
counts with F1 = 0, which is the conservative choice); accuracy is the share of exact matches.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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


def summary(y_cat: Sequence[str], p_cat: Sequence[str], y_pri: Sequence[str], p_pri: Sequence[str],
            cat_labels: Sequence[str], pri_labels: Sequence[str]) -> Mapping[str, float]:
    """Category and priority macro-F1 and accuracy, plus joint accuracy (both labels right)."""
    joint = sum(a == b and c == d for a, b, c, d in zip(y_cat, p_cat, y_pri, p_pri, strict=True))
    return {
        "category_macro_f1": macro_f1(y_cat, p_cat, cat_labels),
        "category_accuracy": accuracy(y_cat, p_cat),
        "priority_macro_f1": macro_f1(y_pri, p_pri, pri_labels),
        "priority_accuracy": accuracy(y_pri, p_pri),
        "joint_accuracy": joint / len(y_cat) if y_cat else 0.0,
    }
