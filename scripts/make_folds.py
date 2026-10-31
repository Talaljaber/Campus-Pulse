#!/usr/bin/env python3
"""Freeze a category-stratified cv_fold assignment (P0.3a, LD-31, ARCHITECTURE §3.2).

    python scripts/make_folds.py [--k 5] [--seed 42] [--include-augmented] [--out PATH]

Plain GroupKFold(5) on the 30 official cv_groups leaves validation folds with only 4-5 of the
6 categories for every seed tried (data audit F1). Every category has exactly 5 groups, so we
assign one group per category to each fold, and search (seeded, fixed iteration cap) for the
assignment that also has all 3 priorities and >= min_arabic_groups_per_fold Arabic groups in every
fold while keeping fold sizes and priority mixes as even as possible.

Output: data/clean/cv_folds.csv with columns cv_group,cv_fold (fold ids 0..k-1), sorted by
cv_group, LF line endings. No existing CSV is edited; the training pool joins cv_fold on cv_group.
cv_group stays the leakage unit; folds only decide which whole groups are held out together.

--include-augmented appends new groups from data/augmented/*.csv (NEW-S.., MEM-..) without moving
any official group: each new group goes to the fold with the fewest groups of its category
(ties -> lowest fold id).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
COMBINED = ROOT / "data" / "clean" / "train_val_combined.csv"
FOLDS_OUT = ROOT / "data" / "clean" / "cv_folds.csv"
AUGMENTED = ROOT / "data" / "augmented"
TRAIN_YAML = ROOT / "config" / "train.yaml"


class FoldSearchError(RuntimeError):
    """No assignment satisfies the constraints within the search budget."""


def read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV as strings (utf-8-sig tolerates a BOM), keeping empty cells as ''."""
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def group_table(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per cv_group: category, priority, n_rows, has_ar (sorted by cv_group).

    Raises:
        FoldSearchError: a group carries more than one category or priority.
    """
    agg = rows.groupby("cv_group", sort=True).agg(
        category=("category", "first"),
        priority=("priority", "first"),
        n_cat=("category", "nunique"),
        n_pri=("priority", "nunique"),
        n_rows=("request_id", "size"),
        has_ar=("lang", lambda s: bool((s == "ar").any())),
    )
    bad = agg[(agg.n_cat != 1) | (agg.n_pri != 1)]
    if len(bad):
        raise FoldSearchError(f"groups with mixed labels: {sorted(bad.index)}")
    return agg.drop(columns=["n_cat", "n_pri"]).reset_index()


def assign_folds(
    groups: pd.DataFrame,
    k: int,
    seed: int,
    *,
    iterations: int,
    min_arabic_groups: int,
) -> dict[str, int]:
    """Assign every group to one of k folds: exactly one group per category per fold.

    Args:
        groups: one row per cv_group with columns cv_group, category, priority, n_rows, has_ar.
        k: number of folds; every category must have exactly k groups.
        seed: seed of the numpy RandomState driving the search (deterministic).
        iterations: fixed search budget (number of random per-category permutations tried).
        min_arabic_groups: every fold must contain at least this many groups with Arabic rows.

    Returns:
        cv_group -> fold id in 0..k-1. Among feasible draws (all 3 priorities in every fold and the
        Arabic floor), the one minimising (row-count range + priority-group-count range) wins; the
        first draw wins ties.

    Raises:
        FoldSearchError: a category does not have exactly k groups, or no feasible draw was found.
    """
    cats = sorted(groups["category"].unique())
    cat_idx = {c: np.flatnonzero(groups["category"].to_numpy() == c) for c in cats}
    wrong = {c: len(ix) for c, ix in cat_idx.items() if len(ix) != k}
    if wrong:
        raise FoldSearchError(f"need exactly {k} groups per category (one per fold), got {wrong}")
    pri_codes = pd.Categorical(groups["priority"]).codes
    n_pri = int(pri_codes.max()) + 1
    n_rows = groups["n_rows"].to_numpy(dtype=float)
    has_ar = groups["has_ar"].to_numpy(dtype=float)

    rng = np.random.RandomState(seed)
    best: tuple[float, np.ndarray] | None = None
    for _ in range(iterations):
        fold = np.zeros(len(groups), dtype=int)
        for c in cats:
            fold[cat_idx[c]] = rng.permutation(k)
        pri_per_fold = np.zeros((k, n_pri), dtype=int)
        np.add.at(pri_per_fold, (fold, pri_codes), 1)
        rows_per_fold = np.bincount(fold, n_rows, k)
        ar_per_fold = np.bincount(fold, has_ar, k)
        if pri_per_fold.min() < 1 or ar_per_fold.min() < min_arabic_groups:
            continue
        score = float(rows_per_fold.max() - rows_per_fold.min() + pri_per_fold.max() - pri_per_fold.min())
        if best is None or score < best[0]:
            best = (score, fold.copy())
    if best is None:
        raise FoldSearchError(f"no feasible assignment in {iterations} iterations (seed {seed})")
    return {str(g): int(f) for g, f in zip(groups["cv_group"], best[1], strict=True)}


def append_new_groups(folds: dict[str, int], new_groups: pd.DataFrame, k: int) -> dict[str, int]:
    """Add augmentation-only groups without moving any existing assignment.

    Args:
        folds: existing cv_group -> fold (official groups); never modified.
        new_groups: one row per cv_group with columns cv_group, category. Rows whose group is
            already in `folds` only count towards the per-fold category totals (official groups
            are spread one per category per fold, so omitting them changes nothing). New groups
            are placed in sorted cv_group order (deterministic).
        k: number of folds.

    Returns:
        A new dict: the old assignments plus each new group in the fold with the fewest groups of
        its category so far (ties -> lowest fold id).
    """
    out = dict(folds)
    cat_of = dict(zip(new_groups["cv_group"], new_groups["category"], strict=True))
    counts: dict[str, list[int]] = {}

    def count_for(category: str) -> list[int]:
        if category not in counts:
            counts[category] = [0] * k
        return counts[category]

    for g, f in folds.items():
        if g in cat_of:
            count_for(cat_of[g])[f] += 1
    for g in sorted(cat_of):
        if g in out:
            continue
        per_fold = count_for(cat_of[g])
        target = min(range(k), key=lambda i: (per_fold[i], i))
        out[g] = target
        per_fold[target] += 1
    return out


def load_augmented_groups(official_groups: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rows and new-group table from data/augmented/*.csv (only groups not in the official data).

    Raises:
        FoldSearchError: an augmented file lacks cv_group/category, or a new group mixes categories.
    """
    files = sorted(AUGMENTED.glob("*.csv"))
    if not files:
        empty = pd.DataFrame(columns=["cv_group", "category", "request_id", "priority", "lang"])
        return empty, empty[["cv_group", "category"]]
    rows = pd.concat([read_csv(p) for p in files], ignore_index=True)
    missing = {"cv_group", "category"} - set(rows.columns)
    if missing:
        raise FoldSearchError(f"augmented files lack columns {sorted(missing)}")
    new = rows[~rows["cv_group"].isin(official_groups)]
    per_group = new.groupby("cv_group")["category"].nunique()
    mixed = sorted(per_group[per_group > 1].index)
    if mixed:
        raise FoldSearchError(f"new augmented groups with mixed categories: {mixed}")
    table = new.drop_duplicates("cv_group")[["cv_group", "category"]].reset_index(drop=True)
    return rows, table


def summarize(rows: pd.DataFrame, folds: dict[str, int], k: int) -> tuple[int, int, list[int]]:
    """(min categories per fold, min priorities per fold, rows per fold) for rows joined to folds."""
    joined = rows.assign(cv_fold=rows["cv_group"].map(folds))
    cats = [int(joined.loc[joined.cv_fold == f, "category"].nunique()) for f in range(k)]
    pris = [int(joined.loc[joined.cv_fold == f, "priority"].nunique()) for f in range(k)]
    sizes = [int((joined.cv_fold == f).sum()) for f in range(k)]
    return min(cats), min(pris), sizes


def write_folds(folds: dict[str, int], out: Path) -> None:
    """Write cv_group,cv_fold sorted by cv_group, UTF-8, LF (byte-stable across OSes)."""
    frame = pd.DataFrame(sorted(folds.items()), columns=["cv_group", "cv_fold"])
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False, encoding="utf-8", lineterminator="\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    cfg = yaml.safe_load(TRAIN_YAML.read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--k", type=int, default=int(cfg["cv"]["k"]))
    parser.add_argument("--seed", type=int, default=int(cfg["seed"]))
    parser.add_argument("--include-augmented", action="store_true")
    parser.add_argument("--out", type=Path, default=FOLDS_OUT)
    args = parser.parse_args(argv)

    official = read_csv(COMBINED)
    try:
        folds = assign_folds(
            group_table(official),
            args.k,
            args.seed,
            iterations=int(cfg["cv"]["search_iterations"]),
            min_arabic_groups=int(cfg["cv"]["min_arabic_groups_per_fold"]),
        )
        rows = official
        if args.include_augmented:
            aug_rows, new_groups = load_augmented_groups(set(folds))
            folds = append_new_groups(folds, new_groups, args.k)
            if len(aug_rows):
                rows = pd.concat([official, aug_rows[official.columns.intersection(aug_rows.columns)]])
    except FoldSearchError as exc:
        print(f"make_folds: {exc}", file=sys.stderr)
        return 1

    min_cats, min_pris, sizes = summarize(rows, folds, args.k)
    n_cats, n_pris = official["category"].nunique(), official["priority"].nunique()
    write_folds(folds, args.out)
    try:
        shown = args.out.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        shown = str(args.out)
    print(
        f"wrote {shown}: {len(folds)} groups, {args.k} folds, categories {min_cats}/{n_cats} and "
        f"priorities {min_pris}/{n_pris} in every fold, rows/fold {'/'.join(map(str, sizes))}"
    )
    return 0 if (min_cats, min_pris) == (n_cats, n_pris) else 1


if __name__ == "__main__":
    sys.exit(main())
