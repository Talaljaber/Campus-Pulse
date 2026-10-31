"""Frozen-fold cross-validation splits (P1.8, LD-31, ARCHITECTURE §3.2).

Folds are never drawn at random: `group_folds` reads the frozen `cv_fold` column that `load_pool` joined
from `data/clean/cv_folds.csv` (`scripts/make_folds.py`, seed 42). `cv_group` stays the leakage unit, so a
scenario and its translation are always held out together. ruff bans sklearn's random splitters.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
from numpy.typing import NDArray

from campuspulse_ai.adapters.training.pool import Pool
from campuspulse_ai.domain.errors import InvalidInput

Split = tuple[NDArray[np.int64], NDArray[np.int64]]


def group_folds(pool: Pool, k: int) -> list[Split]:
    """(train_idx, test_idx) for each frozen fold 0..k-1, indices sorted ascending.

    Raises:
        InvalidInput: a row has no fold (`cv_fold == -1`: run `make_folds.py --include-augmented`), a fold
            id outside 0..k-1, a `cv_group` that spans two folds, or a fold with no test rows.
    """
    if k < 2:
        raise InvalidInput("k must be >= 2")
    folds = np.asarray(pool.cv_fold, dtype=np.int64)
    missing = sorted({g for g, f in zip(pool.cv_group, pool.cv_fold, strict=True) if f < 0})
    if missing:
        hint = "run scripts/make_folds.py --include-augmented"
        raise InvalidInput(f"rows without cv_fold for groups {missing[:5]}: {hint}")
    out_of_range = sorted({int(f) for f in folds if f >= k})
    if out_of_range:
        raise InvalidInput(f"cv_fold values {out_of_range} outside 0..{k - 1}")
    seen: dict[str, set[int]] = defaultdict(set)
    for group, fold in zip(pool.cv_group, pool.cv_fold, strict=True):
        seen[group].add(fold)
    split_groups = sorted(g for g, fs in seen.items() if len(fs) > 1)
    if split_groups:
        raise InvalidInput(f"cv_groups in more than one fold: {split_groups[:5]}")
    splits: list[Split] = []
    for fold in range(k):
        test = np.flatnonzero(folds == fold).astype(np.int64)
        if test.size == 0:
            raise InvalidInput(f"fold {fold} has no rows")
        train = np.flatnonzero(folds != fold).astype(np.int64)
        splits.append((train, test))
    return splits
