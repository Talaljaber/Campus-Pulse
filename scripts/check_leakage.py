#!/usr/bin/env python3
"""Leakage gate across cv_groups (P0.3e; ARCHITECTURE §3.2). Extended to augmented rows in P2.1.

    python scripts/check_leakage.py --official

Official mode reads data/clean/train_val_combined.csv and, on unique text_norm values:
  (a) fails on any identical text_norm in two different cv_groups;
  (b) fails on any cross-group pair whose char_wb 3-5-gram TF-IDF cosine is >= leakage.char_cosine
      (config/datasets.yaml), printing every such pair for a manual merge decision.
No encoder is needed. The encoder-cosine check (leakage.cosine_merge) arrives with P2.1.

Exit 0 when clean, 1 otherwise. Output line on success:
  0 identical text_norm across groups; 0 cross-group pairs >= 0.8 (max 0.375)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parent.parent
COMBINED = ROOT / "data" / "clean" / "train_val_combined.csv"
DATASETS_YAML = ROOT / "config" / "datasets.yaml"


@dataclass(frozen=True)
class NearPair:
    """Two texts from different cv_groups whose char n-gram cosine is at or above the threshold."""

    sim: float
    text_a: str
    text_b: str
    group_a: str
    group_b: str


def _unique_texts(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (text_norm, cv_group), sorted, so results are deterministic."""
    return (
        df[["text_norm", "cv_group"]]
        .drop_duplicates()
        .sort_values(["text_norm", "cv_group"])
        .reset_index(drop=True)
    )


def exact_cross_group(df: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Identical text_norm values that occur in more than one cv_group.

    Returns:
        (text_norm, group_a, group_b) for every pair of groups sharing a text (group_a < group_b).
    """
    out: list[tuple[str, str, str]] = []
    for text, part in _unique_texts(df).groupby("text_norm", sort=True):
        groups = sorted(part["cv_group"])
        out.extend((str(text), a, b) for i, a in enumerate(groups) for b in groups[i + 1 :])
    return out


def _cross_group_cosines(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Unique texts, their char 3-5-gram TF-IDF cosine matrix, and the cross-group upper-triangle mask."""
    unique = df[["text_norm", "cv_group"]].drop_duplicates("text_norm").sort_values("text_norm")
    unique = unique.reset_index(drop=True)
    tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
    matrix = tfidf.fit_transform(unique["text_norm"])
    sims = (matrix @ matrix.T).toarray()
    groups = unique["cv_group"].to_numpy()
    mask = np.triu(groups[:, None] != groups[None, :], k=1)
    return unique, sims, mask


def max_cross_group_cosine(df: pd.DataFrame) -> float:
    """The largest char 3-5-gram cosine between texts of different cv_groups (0.0 if none)."""
    _, sims, mask = _cross_group_cosines(df)
    return float(sims[mask].max()) if mask.any() else 0.0


def char_near_pairs(df: pd.DataFrame, threshold: float) -> list[NearPair]:
    """Cross-group pairs with char_wb 3-5-gram TF-IDF cosine >= threshold, most similar first.

    Args:
        df: rows with at least text_norm and cv_group.
        threshold: cosine cut-off (config/datasets.yaml leakage.char_cosine).
    """
    unique, sims, mask = _cross_group_cosines(df)
    rows, cols = np.nonzero(mask & (sims >= threshold))
    pairs = [
        NearPair(
            sim=float(sims[i, j]),
            text_a=str(unique.at[i, "text_norm"]),
            text_b=str(unique.at[j, "text_norm"]),
            group_a=str(unique.at[i, "cv_group"]),
            group_b=str(unique.at[j, "cv_group"]),
        )
        for i, j in zip(rows, cols, strict=True)
    ]
    return sorted(pairs, key=lambda p: (-p.sim, p.text_a, p.text_b))


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(description="Leakage gate across cv_groups.")
    parser.add_argument("--official", action="store_true", help="check data/clean/train_val_combined.csv")
    args = parser.parse_args(argv)
    if not args.official:
        parser.error("only --official is implemented (augmented mode arrives in P2.1)")

    cfg = yaml.safe_load(DATASETS_YAML.read_text(encoding="utf-8"))
    threshold = float(cfg["leakage"]["char_cosine"])
    df = pd.read_csv(COMBINED, encoding="utf-8", dtype=str, keep_default_na=False)

    exact = exact_cross_group(df)
    near = char_near_pairs(df, threshold)
    for text, a, b in exact:
        print(f"IDENTICAL text_norm in {a} and {b}: {text}")
    for pair in near:
        print(f"NEAR {pair.sim:.3f} {pair.group_a} / {pair.group_b}: {pair.text_a} | {pair.text_b}")
    print(
        f"{len(exact)} identical text_norm across groups; {len(near)} cross-group pairs >= {threshold:g} "
        f"(max {max_cross_group_cosine(df):.3f})"
    )
    return 1 if exact or near else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # pair lines may contain Arabic (cp1252 consoles)
    sys.exit(main())
