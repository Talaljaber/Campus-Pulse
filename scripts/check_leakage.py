#!/usr/bin/env python3
"""Leakage gate across cv_groups and against the holdouts (P0.3e, P2.1; ARCHITECTURE §3.2).

    python scripts/check_leakage.py --official
    python scripts/check_leakage.py [--encoder {onnx,hashing}] [--threshold <encoder cosine>]
                                    [--out reports/leakage.json]

`--official` (P0.3e) reads data/clean/train_val_combined.csv and, on unique text_norm values, fails on an
identical text_norm in two cv_groups or on any cross-group pair with char_wb 3-5-gram TF-IDF cosine >=
`leakage.char_cosine` (config/datasets.yaml). Output line on success:
  0 identical text_norm across groups; 0 cross-group pairs >= 0.8 (max 0.375)

The default (P2.1) mode checks the **whole candidate pool**: the official rows plus every
data/augmented/*.csv row, reviewed or not (an unreviewed draft is a future training row), each normalized
exactly as at inference. It also reads the holdouts (`data/our_test/our_test.csv` and, when present,
`data/robustness/probes.csv`) for comparison; it is the only tool that does, and it writes nothing that
`train.py` reads.
  1. exact cross-group duplicates (identical `text_norm` in two cv_groups)             -> exit 1
  2. cross-group pool pairs with encoder cosine >= `leakage.cosine_merge`              -> listed only, for a
     manual merge (the author sets the new scenario's cv_group to the existing group); never auto-fixed
  3. holdout near-duplicates: a holdout row whose normalized text equals a pool text, or whose char cosine
     >= `leakage.char_cosine`, or encoder cosine >= `leakage.cosine_merge` with a pool row
       - against an **augmented** row, by a measure in `leakage.holdout_fail_on` (exact, char) -> exit 1
         (fix or drop the augmented row; the holdout never moves into training). An encoder-only neighbour
         is listed for review: an e5 cosine of 0.90 marks a shared topic, not a copy (config/datasets.yaml)
       - against an **official** row                                                   -> listed only: a
         shared topic with an official row is context, not an error
Output line:
  exact cross-group duplicates: 0; near pairs >=0.90: <n> (listed); holdout near-duplicates: <m> (listed;
  augmented <a>, official <o>)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from numpy.typing import NDArray
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parent.parent
COMBINED = ROOT / "data" / "clean" / "train_val_combined.csv"
DATASETS_YAML = ROOT / "config" / "datasets.yaml"
TRAIN_YAML = ROOT / "config" / "train.yaml"
LEXICONS = ROOT / "config" / "lexicons"
OUR_TEST_CSV = ROOT / "data" / "our_test" / "our_test.csv"
PROBES_CSV = ROOT / "data" / "robustness" / "probes.csv"
ENCODER_DIR = ROOT / "models" / "frozen" / "v1" / "encoder"
DEFAULT_OUT = ROOT / "reports" / "leakage.json"
SOURCE_OFFICIAL = "official"


@dataclass(frozen=True)
class NearPair:
    """Two texts from different cv_groups (or a pool text and a holdout text) at or above a threshold."""

    sim: float
    text_a: str
    text_b: str
    group_a: str
    group_b: str


@dataclass(frozen=True)
class HoldoutPair:
    """A holdout row that is a near-duplicate of a pool row."""

    sim: float
    measure: str  # exact | char | encoder
    holdout_id: str
    holdout_text: str
    pool_id: str
    pool_text: str
    pool_group: str
    pool_is_official: bool


# --- the official checks (P0.3e; also used by scripts/test_data_audit.py) -------------------------------


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

    Args:
        df: rows with at least `text_norm` and `cv_group` (the official frame, or `pool_frame(pool)`).

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


# --- the pool checks (P2.1) -------------------------------------------------------------------------------


def pool_frame(pool: Any) -> pd.DataFrame:
    """The leakage view of a `Pool`: one row per pool row (id, text_norm, model_text, group, source)."""
    return pd.DataFrame(
        {
            "request_id": list(pool.request_id),
            "text_norm": list(pool.text_norm),
            "model_text": list(pool.model_text),
            "cv_group": list(pool.cv_group),
            "source": list(pool.source),
            "is_official": list(pool.is_official),
        }
    )


def near_pairs(frame: pd.DataFrame, emb: NDArray[np.float32], threshold: float) -> list[NearPair]:
    """Cross-group pairs of distinct `model_text`s whose encoder cosine is >= threshold, most similar first.

    Args:
        frame: `pool_frame(pool)` (row i <-> `emb[i]`).
        emb: unit-norm encoder vectors of `frame.model_text`, shape (n, d).
        threshold: `leakage.cosine_merge`.
    """
    first: dict[str, int] = {}
    for i, text in enumerate(frame["model_text"]):
        first.setdefault(str(text), i)
    idx = np.array(sorted(first.values()), dtype=np.int64)
    if idx.size < 2:
        return []
    vecs = np.asarray(emb, dtype=np.float64)[idx]
    sims = vecs @ vecs.T
    groups = frame["cv_group"].to_numpy()[idx]
    mask = np.triu(groups[:, None] != groups[None, :], k=1) & (sims >= threshold)
    texts = frame["model_text"].to_numpy()[idx]
    pairs = [
        NearPair(float(sims[a, b]), str(texts[a]), str(texts[b]), str(groups[a]), str(groups[b]))
        for a, b in zip(*np.nonzero(mask), strict=True)
    ]
    return sorted(pairs, key=lambda p: (-p.sim, p.text_a, p.text_b))


def holdout_near(
    frame: pd.DataFrame,
    pool_emb: NDArray[np.float32],
    holdout: pd.DataFrame,
    holdout_emb: NDArray[np.float32],
    *,
    encoder_threshold: float,
    char_threshold: float,
) -> list[HoldoutPair]:
    """Holdout rows that duplicate or nearly duplicate a pool row (the closest pool row per measure).

    Args:
        frame: `pool_frame(pool)`; `pool_emb` its encoder vectors.
        holdout: columns `request_id`, `text_norm`, `model_text`; `holdout_emb` its encoder vectors.
        encoder_threshold: `leakage.cosine_merge`. char_threshold: `leakage.char_cosine`.

    Returns:
        One `HoldoutPair` per (holdout row, measure) that fires: `exact` (identical `text_norm`), `char`
        (char_wb 3-5-gram cosine), `encoder` (encoder cosine), sorted by holdout id then measure.
    """
    out: list[HoldoutPair] = []
    if holdout.empty or frame.empty:
        return out
    pool_norm = frame["text_norm"].astype(str).tolist()
    hold_norm = holdout["text_norm"].astype(str).tolist()
    tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
    tfidf.fit(pool_norm + hold_norm)
    char_sims = (tfidf.transform(hold_norm) @ tfidf.transform(pool_norm).T).toarray()
    enc_sims = np.asarray(holdout_emb, dtype=np.float64) @ np.asarray(pool_emb, dtype=np.float64).T
    exact_of: dict[str, int] = {}
    for i, text in enumerate(pool_norm):
        exact_of.setdefault(text, i)

    def pair(h: int, p: int, sim: float, measure: str) -> HoldoutPair:
        return HoldoutPair(
            sim=round(sim, 6), measure=measure, holdout_id=str(holdout.iloc[h]["request_id"]),
            holdout_text=hold_norm[h], pool_id=str(frame.iloc[p]["request_id"]), pool_text=pool_norm[p],
            pool_group=str(frame.iloc[p]["cv_group"]), pool_is_official=bool(frame.iloc[p]["is_official"]),
        )

    for h in range(len(holdout)):
        if hold_norm[h] in exact_of:
            out.append(pair(h, exact_of[hold_norm[h]], 1.0, "exact"))
        for measure, sims, threshold in (("char", char_sims, char_threshold),
                                         ("encoder", enc_sims, encoder_threshold)):
            above = np.nonzero(sims[h] >= threshold)[0]
            # every augmented hit is listed (each one must be fixed or dropped); for official rows only the
            # closest one (a shared topic with an official row is context, not an error)
            augmented = [int(p) for p in above if not bool(frame.iloc[int(p)]["is_official"])]
            out.extend(pair(h, p, float(sims[h, p]), measure) for p in augmented)
            official = [int(p) for p in above if bool(frame.iloc[int(p)]["is_official"])]
            if official:
                best = max(official, key=lambda p: (sims[h, p], -p))
                out.append(pair(h, best, float(sims[h, best]), measure))
    return sorted(out, key=lambda q: (q.holdout_id, q.measure, q.pool_is_official, q.pool_id))


# --- I/O ------------------------------------------------------------------------------------------------


def _read_holdout(path: Path, normalizer: Any) -> pd.DataFrame:
    """request_id, text_norm and model_text of a holdout CSV, normalized as at inference."""
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    records = []
    for r in rows:
        req = normalizer.normalize(r["text"])
        records.append(
            {"request_id": r["request_id"], "text_norm": req.text_norm, "model_text": req.model_text}
        )
    return pd.DataFrame(records, columns=["request_id", "text_norm", "model_text"])


def _encoder(kind: str) -> Any:
    from campuspulse_ai.adapters.models.hashing_encoder import HashingEncoder

    train = yaml.safe_load(TRAIN_YAML.read_text(encoding="utf-8"))
    if kind == "hashing":
        return HashingEncoder(dim=int(train["encoder"]["dim"]), seed=int(train["seed"]))
    from campuspulse_ai.adapters.models.encoder import CachingEncoder, OnnxEncoder

    return CachingEncoder(OnnxEncoder(ENCODER_DIR, query_prefix=str(train["encoder"]["query_prefix"]),
                                      max_tokens=int(train["encoder"]["max_tokens"])))


def _embed(encoder: Any, texts: Sequence[str]) -> NDArray[np.float32]:
    if not texts:
        return np.zeros((0, 1), dtype=np.float32)
    return np.asarray(encoder.encode(list(texts)), dtype=np.float32)


def run_pool_check(encoder_kind: str, threshold: float | None, out: Path | None) -> int:
    """The P2.1 mode (module docstring). Returns the exit code."""
    from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
    from campuspulse_ai.adapters.training.pool import default_pool_paths, load_pool

    cfg = yaml.safe_load(DATASETS_YAML.read_text(encoding="utf-8"))["leakage"]
    train = yaml.safe_load(TRAIN_YAML.read_text(encoding="utf-8"))
    enc_threshold = float(threshold if threshold is not None else cfg["cosine_merge"])
    char_threshold = float(cfg["char_cosine"])
    normalizer = DefaultNormalizer.from_lexicons(LEXICONS, int(train["guards"]["max_tokens"]))
    pool = load_pool(default_pool_paths(), normalizer, include_unreviewed=True)
    frame = pool_frame(pool)
    encoder = _encoder(encoder_kind)
    pool_emb = _embed(encoder, frame["model_text"].tolist())

    exact = exact_cross_group(frame)
    near = near_pairs(frame, pool_emb, enc_threshold)
    holdouts = [p for p in (OUR_TEST_CSV, PROBES_CSV) if p.is_file()]
    hold_pairs: list[HoldoutPair] = []
    for path in holdouts:
        hold = _read_holdout(path, normalizer)
        hold_pairs += holdout_near(frame, pool_emb, hold, _embed(encoder, hold["model_text"].tolist()),
                                   encoder_threshold=enc_threshold, char_threshold=char_threshold)
    fail_on = {str(m) for m in cfg["holdout_fail_on"]}
    aug_hold = [p for p in hold_pairs if not p.pool_is_official]
    aug_fail = [p for p in aug_hold if p.measure in fail_on]
    off_hold = [p for p in hold_pairs if p.pool_is_official]

    for text, a, b in exact:
        print(f"IDENTICAL text_norm in {a} and {b}: {text}")
    for p in near:
        print(f"NEAR {p.sim:.3f} {p.group_a} / {p.group_b}: {p.text_a} | {p.text_b}")
    for q in hold_pairs:
        side = "official" if q.pool_is_official else (
            "AUGMENTED-FAIL" if q.measure in fail_on else "augmented-review")
        print(f"HOLDOUT {q.measure} {q.sim:.3f} {q.holdout_id} ~ {side} {q.pool_id} ({q.pool_group}): "
              f"{q.holdout_text} | {q.pool_text}")
    n_aug = int((~frame["is_official"]).sum())
    report: dict[str, Any] = {
        "encoder": encoder_kind,
        "thresholds": {"cosine_merge": enc_threshold, "char_cosine": char_threshold,
                       "holdout_fail_on": sorted(fail_on)},
        "pool": {"rows": len(frame), "official_rows": len(frame) - n_aug, "augmented_rows": n_aug,
                 "groups": int(frame["cv_group"].nunique())},
        "holdouts": [p.relative_to(ROOT).as_posix() for p in holdouts],
        "exact_cross_group": [{"text_norm": t, "group_a": a, "group_b": b} for t, a, b in exact],
        "near_pairs": [asdict(p) for p in near],
        "holdout_near": [asdict(q) for q in hold_pairs],
        "holdout_near_rows": {"augmented": len({q.holdout_id for q in aug_hold}),
                              "official": len({q.holdout_id for q in off_hold})},
        "offending_augmented_ids": sorted({q.pool_id for q in aug_fail}),
        "review_augmented_ids": sorted({q.pool_id for q in aug_hold} - {q.pool_id for q in aug_fail}),
    }
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                       encoding="utf-8", newline="\n")
    n_hold = len({q.holdout_id for q in hold_pairs})
    print(f"exact cross-group duplicates: {len(exact)}; "
          f"near pairs >={enc_threshold:.2f}: {len(near)} (listed); "
          f"holdout near-duplicates: {n_hold} (listed; augmented {len(aug_fail)} failing + "
          f"{len(aug_hold) - len(aug_fail)} encoder-only for review, official {len(off_hold)})")
    return 1 if exact or aug_fail else 0


def run_official() -> int:
    """The P0.3e mode on data/clean/train_val_combined.csv (module docstring). Returns the exit code."""
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


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(description="Leakage gate across cv_groups and against the holdouts.")
    parser.add_argument("--official", action="store_true", help="P0.3e: check data/clean only (char n-grams)")
    parser.add_argument("--encoder", choices=("onnx", "hashing"), default="onnx",
                        help="encoder for the cosine checks (onnx = frozen int8 encoder; hashing = tests)")
    parser.add_argument("--threshold", type=float, default=None,
                        help="encoder cosine cut-off (default: config/datasets.yaml leakage.cosine_merge)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="JSON report (default %(default)s)")
    args = parser.parse_args(argv)
    if args.official:
        return run_official()
    return run_pool_check(args.encoder, args.threshold, args.out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # pair lines may contain Arabic (cp1252 consoles)
    sys.exit(main())
