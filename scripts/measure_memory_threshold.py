#!/usr/bin/env python3
"""Measure `knn.memory_min_sim` from data (live rc1 finding, ML batch 4).

    python scripts/measure_memory_threshold.py [--out reports/memory_threshold.json]

A staff correction stored in memory may vote on a new request only when it says the same thing. With the
frozen
encoder (e5-small int8, `query: ` prefix) this script compares two distributions of cosine similarity over the
training pool (official rows and every augmented draft; no holdout is read):
  - **same scenario**: pairs of different texts that share a cv_group and a language (paraphrases and
    rewordings of one situation; wrapper variants are identical after stripping and are skipped);
  - **cross scenario**: pairs of texts from different cv_groups (different situations).
It proposes the smallest value on a 0.01 grid that is at or above the `quantile` of the cross-scenario
similarities (config/train.yaml `memory_threshold.cross_quantile`), and reports how many same-scenario pairs
it keeps. The value goes into `config/train.yaml knn.memory_min_sim` by hand (it is then copied into
config.json). Re-run it whenever the encoder changes: similarity scales differ between encoders.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import yaml

from campuspulse_ai.adapters.models.encoder import CachingEncoder, OnnxEncoder
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.adapters.training.pool import default_pool_paths, load_pool
from campuspulse_ai.config.paths import LEXICONS, MODELS_FROZEN, REPORTS

ROOT = Path(__file__).resolve().parent.parent
GRID = 100  # thresholds on a 0.01 grid


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=REPORTS / "memory_threshold.json")
    args = ap.parse_args(argv)
    train = yaml.safe_load((ROOT / "config" / "train.yaml").read_text(encoding="utf-8"))
    q = float(train["memory_threshold"]["cross_quantile"])
    normalizer = DefaultNormalizer.from_lexicons(LEXICONS, int(train["guards"]["max_tokens"]))
    pool = load_pool(default_pool_paths(), normalizer, include_unreviewed=True)
    first: dict[str, int] = {}
    for i, t in enumerate(pool.model_text):
        first.setdefault(t, i)
    idx = sorted(first.values())
    texts = [pool.model_text[i] for i in idx]
    enc = CachingEncoder(OnnxEncoder(MODELS_FROZEN / "v1" / "encoder"))
    emb = np.asarray(enc.encode(texts), dtype=np.float64)
    sims = emb @ emb.T
    groups = np.array([pool.cv_group[i] for i in idx])
    langs = np.array([str(pool.lang[i]) for i in idx])
    upper = np.triu(np.ones_like(sims, dtype=bool), k=1)
    same = upper & (groups[:, None] == groups[None, :]) & (langs[:, None] == langs[None, :])
    cross = upper & (groups[:, None] != groups[None, :])
    s_same, s_cross = sims[same], sims[cross]
    cut = float(np.quantile(s_cross, q))
    proposal = math.ceil(cut * GRID) / GRID
    report = {
        "encoder": {
            "model_id": enc.model_id if hasattr(enc, "model_id") else "e5-small",
            "dir": "models/frozen/v1",
        },
        "texts": len(texts),
        "pairs": {"same_scenario_same_lang": int(same.sum()), "cross_scenario": int(cross.sum())},
        "same_scenario_percentiles": {p: round(float(np.percentile(s_same, p)), 4) for p in (5, 25, 50, 75)},
        "cross_scenario_percentiles": {
            p: round(float(np.percentile(s_cross, p)), 4) for p in (50, 90, 99, 99.5)
        },
        "cross_scenario_max": round(float(s_cross.max()), 4),
        "cross_quantile": q,
        "proposed_memory_min_sim": proposal,
        "same_scenario_kept_at_proposal": round(float((s_same >= proposal).mean()), 4),
        "cross_scenario_above_proposal": round(float((s_cross >= proposal).mean()), 5),
        "note": "pool texts only (official + every augmented draft); no holdout is read",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(
        f"proposed knn.memory_min_sim={proposal:.2f} (cross-scenario q{q} = {cut:.4f}, max "
        f"{s_cross.max():.4f}); keeps {report['same_scenario_kept_at_proposal']:.1%} of same-scenario pairs"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
