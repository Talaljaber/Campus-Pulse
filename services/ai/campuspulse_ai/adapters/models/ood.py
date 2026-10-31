"""The out-of-distribution score (P1.11, §2.1 [7b]): cosine similarity to the nearest training example.

It reads only the frozen `train` collection, never live memory (§3.11), so the same text always gets the
same score. The online policy compares it with `FrozenConfig.thresholds.tau_ood` (the 5th percentile of the
OOF scores of in-distribution rows, `train.py` stage B).
"""

from __future__ import annotations

from collections.abc import Sequence

from campuspulse_ai.adapters.models.knn import ExampleIndex


def ood_score(index: ExampleIndex, emb: Sequence[float]) -> float:
    """Max cosine similarity of `emb` to the index (higher = more in-distribution). StoreError if empty."""
    return index.max_similarity(emb)
