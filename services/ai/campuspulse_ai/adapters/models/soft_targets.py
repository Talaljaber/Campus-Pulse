"""Soft targets from `data/clean/label_flags.csv` as weighted duplicate rows (P1.8, ARCHITECTURE §3.3).

sklearn's LogisticRegression has no soft-label API; duplicating a row once per label with
`sample_weight = p` gives exactly the soft-target log-loss. Official labels are never edited: the soft
target's argmax must equal the official label (checked here), and metrics always use the hard label.
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from campuspulse_ai.adapters.training.pool import Pool
from campuspulse_ai.domain.errors import InvalidInput
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS

Target = Literal["category", "priority"]
SUM_TOLERANCE = 1e-6
_LABELS: Mapping[str, tuple[str, ...]] = {"category": CATEGORY_LABELS, "priority": PRIORITY_LABELS}


class SoftTargetExpander:
    """Expands flagged scenarios into weighted rows; every other row keeps weight 1.

    `label_flags.csv` rows with `field == target` and a non-empty `soft_target` (JSON `{label: p}`) apply to
    every pool row whose `scenario_id` matches: the official rows of that scenario and every augmented row
    derived from it (`source_scenario_id`). `keep (hard)` rows have no soft target and change nothing.
    """

    def __init__(self, flags_csv: Path) -> None:
        """
        Raises:
            InvalidInput: the file is unreadable, a soft target is not a distribution over the target's
                official labels, or its argmax is not the unique official label.
        """
        try:
            with Path(flags_csv).open(encoding="utf-8-sig", newline="") as fh:
                rows = [dict(r) for r in csv.DictReader(fh)]
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            raise InvalidInput(f"{flags_csv}: unreadable: {exc}") from exc
        self._targets: dict[str, dict[str, dict[str, float]]] = {"category": {}, "priority": {}}
        self._official: dict[str, dict[str, str]] = {"category": {}, "priority": {}}
        for r in rows:
            field, sid, official = r["field"], r["scenario_id"], r["official_label"]
            if field not in self._targets or not r["soft_target"].strip():
                continue
            dist = {str(k): float(v) for k, v in json.loads(r["soft_target"]).items()}
            labels = _LABELS[field]
            if not set(dist) <= set(labels) or abs(math.fsum(dist.values()) - 1.0) > SUM_TOLERANCE:
                raise InvalidInput(f"{flags_csv} {sid}: soft_target {dist} is not a distribution")
            top = max(dist.values())
            if [lab for lab, p in dist.items() if p == top] != [official]:
                raise InvalidInput(f"{flags_csv} {sid}: argmax of {dist} != {official}")
            self._targets[field][sid] = dist
            self._official[field][sid] = official

    def flagged(self, target: Target) -> Mapping[str, Mapping[str, float]]:
        """scenario_id → soft distribution for the target."""
        return self._targets[target]

    def expand(self, pool: Pool, target: Target) -> tuple[list[int], list[str], list[float]]:
        """(pool row index, label, sample weight) triples, rows in pool order, labels in label order.

        Raises:
            InvalidInput: a flagged row whose hard label is not the flag's official label.
        """
        labels = _LABELS[target]
        hard = pool.category if target == "category" else pool.priority
        idx: list[int] = []
        out_labels: list[str] = []
        weights: list[float] = []
        for i, (scenario, label) in enumerate(zip(pool.scenario_id, hard, strict=True)):
            dist = self._targets[target].get(scenario)
            if dist is None:
                idx.append(i)
                out_labels.append(label)
                weights.append(1.0)
                continue
            if label != self._official[target][scenario]:
                rid = pool.request_id[i]
                raise InvalidInput(f"{rid}: label {label!r} != the flagged official label of {scenario}")
            for lab in labels:
                if dist.get(lab, 0.0) > 0.0:
                    idx.append(i)
                    out_labels.append(lab)
                    weights.append(dist[lab])
        return idx, out_labels, weights
