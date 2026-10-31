"""`TrainCfg`: the typed view of `config/train.yaml` + `config/hand_tuned.yaml` that `train.py` reads (P1.16).

`train.yaml` holds training **inputs** (knobs, grids, tuning rules, sections copied into `config.json`);
`config.json` holds the outputs and is written only by `train.py` (ARCHITECTURE §1.6).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from campuspulse_ai.config.paths import CONFIG_DIR

TRAIN_YAML = CONFIG_DIR / "train.yaml"
HAND_TUNED_YAML = CONFIG_DIR / "hand_tuned.yaml"


@dataclass(frozen=True)
class TrainCfg:
    """The knobs `train.py` uses, plus the raw mappings it copies into `config.json`."""

    seed: int
    artifact_version: str
    k: int
    alpha_category: float
    alpha_priority: float
    m1_C_grid: tuple[float, ...]
    m2lr_C_grid: tuple[float, ...]
    weight_step: float
    tau_ood_percentile: float
    tau_margin: float
    human_review_min_acc: float
    members: tuple[str, ...]
    raw: Mapping[str, Any]
    hand_tuned: Mapping[str, float]

    @property
    def m1_C(self) -> float:
        """Provisional stage B (P1.16): the grid midpoint. P2.7 replaces it with the OOF grid search."""
        return midpoint(self.m1_C_grid)

    @property
    def m2lr_C(self) -> float:
        return midpoint(self.m2lr_C_grid)

    def section(self, name: str) -> dict[str, Any]:
        """A copy of a `train.yaml` section (e.g. `encoder`, `m1`, `knn`, `guards`)."""
        return dict(self.raw[name])

    @classmethod
    def load(cls, train_yaml: Path = TRAIN_YAML, hand_tuned_yaml: Path = HAND_TUNED_YAML) -> TrainCfg:
        """Read both files. Raises KeyError/TypeError/ValueError on a missing or malformed key."""
        raw = yaml.safe_load(Path(train_yaml).read_text(encoding="utf-8"))
        hand = yaml.safe_load(Path(hand_tuned_yaml).read_text(encoding="utf-8"))
        grids = raw["grids"]
        return cls(
            seed=int(raw["seed"]),
            artifact_version=str(raw["artifact_version"]),
            k=int(raw["cv"]["k"]),
            alpha_category=float(raw["alpha"]["category"]),
            alpha_priority=float(raw["alpha"]["priority"]),
            m1_C_grid=tuple(float(c) for c in grids["m1_C"]),
            m2lr_C_grid=tuple(float(c) for c in grids["m2lr_C"]),
            weight_step=float(grids["weight_step"]),
            tau_ood_percentile=float(raw["tau_ood_percentile"]),
            tau_margin=float(raw["tau_margin"]),
            human_review_min_acc=float(raw["human_review_min_acc"]),
            members=tuple(str(m) for m in raw["ensemble"]["members"]),
            raw=raw,
            hand_tuned={str(k): float(v) for k, v in hand.items()},
        )


def midpoint(grid: tuple[float, ...]) -> float:
    """The middle value of a sorted grid (the lower middle for an even length). ValueError if empty."""
    if not grid:
        raise ValueError("empty grid")
    ordered = sorted(grid)
    return ordered[(len(ordered) - 1) // 2]
