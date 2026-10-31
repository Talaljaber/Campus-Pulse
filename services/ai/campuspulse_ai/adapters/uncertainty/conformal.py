"""`LACConformal`: split/cross-conformal prediction sets with the LAC score (P1.14, ARCHITECTURE §3.5).

Score of a calibration example = 1 − p(true label). With n scores and miscoverage α, the threshold `q` is
the ⌈(n+1)(1−α)⌉-th smallest score; the set for a new probability vector is {labels with p ≥ 1 − q}. Under
exchangeability the set holds the true label with probability ≥ 1 − α. Calibration scores come from the
frozen-fold OOF predictions (cross-conformal), and the official data has 42 unique texts in 30 groups, so the
effective n is about the number of groups and the guarantee is approximate (§6.2 flag 5, LD-32): `n_groups`
is recorded next to `n_calib` for the report. No mapie at runtime: about 30 lines of numpy.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import numpy as np

from campuspulse_ai.domain.errors import ArtifactMissing, ArtifactVersionMismatch
from campuspulse_ai.domain.values import PredictionSet, ProbVector

Target = Literal["category", "priority"]
FILE_NAME = "conformal.json"
METHOD = "lac"
INCLUSION_TOLERANCE = 1e-12  # float noise at p == 1 − q must not drop a label that sits exactly on the edge


class LACConformal:
    """Implements `domain.ports.ConformalPredictor` (LAC score, one global quantile per target).

    `predict_set(p)` returns {l : p_l ≥ 1 − q}; when that is empty it returns {argmax p} and
    `last_was_empty` becomes True (TriageCore adds the flag `empty_set`). `predict_set_with_flag(p)` returns
    both at once without shared state (use it from concurrent code).

    Raises:
        ValueError: calibration with fewer than ⌈1/α⌉ examples, mismatched lengths, a label not in the
            probability vector, or `predict_set` before calibration.
    """

    def __init__(self, target: Target, alpha: float) -> None:
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be in (0, 1)")
        self.target: Target = target
        self.alpha = alpha
        self.q: float = math.nan
        self.n_calib: int = 0
        self.n_groups: int = 0
        self._last_empty = False

    @classmethod
    def from_quantile(
        cls, target: Target, alpha: float, q: float, n_calib: int, n_groups: int = 0
    ) -> LACConformal:
        """Rebuild a calibrated predictor from frozen values (`FrozenConfig.conformal.q_*`, `n_calib`)."""
        if not 0.0 <= q <= 1.0:
            raise ValueError("q must be in [0, 1]")
        out = cls(target, alpha)
        out.q, out.n_calib, out.n_groups = float(q), int(n_calib), int(n_groups)
        return out

    def calibrate(self, probs: Sequence[ProbVector], y: Sequence[str], groups: Sequence[str]) -> None:
        """Set `q` from calibration probabilities and true labels (`groups` only feed `n_groups`)."""
        n = len(probs)
        if n != len(y) or n != len(groups):
            raise ValueError("probs, y and groups must have the same length")
        if n < math.ceil(1.0 / self.alpha):
            raise ValueError(f"need at least {math.ceil(1.0 / self.alpha)} calibration examples, got {n}")
        try:
            scores = np.sort(np.array([1.0 - p.prob(label) for p, label in zip(probs, y, strict=True)]))
        except ValueError as exc:
            raise ValueError(f"a calibration label is not in its probability vector: {exc}") from exc
        k = min(math.ceil((n + 1) * (1.0 - self.alpha)), n)
        self.q = float(scores[k - 1])
        self.n_calib = n
        self.n_groups = len(set(groups))

    def predict_set_with_flag(self, p: ProbVector) -> tuple[PredictionSet, bool]:
        """(set, was_empty) for one probability vector."""
        if math.isnan(self.q):
            raise ValueError("LACConformal is not calibrated")
        threshold = 1.0 - self.q - INCLUSION_TOLERANCE
        labels = frozenset(lab for lab, v in zip(p.labels, p.values, strict=True) if v >= threshold)
        if labels:
            return PredictionSet(labels), False
        return PredictionSet(frozenset({p.argmax()})), True

    def predict_set(self, p: ProbVector) -> PredictionSet:
        result, self._last_empty = self.predict_set_with_flag(p)
        return result

    @property
    def last_was_empty(self) -> bool:
        """True when the last `predict_set` fell back to the argmax singleton."""
        return self._last_empty

    def save(self, dir: Path) -> None:
        """Write `<dir>/conformal.json` (one directory per target, e.g. `conformal/category/`)."""
        if math.isnan(self.q):
            raise ValueError("LACConformal is not calibrated")
        Path(dir).mkdir(parents=True, exist_ok=True)
        data = {"method": METHOD, "target": self.target, "alpha": self.alpha, "q": self.q,
                "n_calib": self.n_calib, "n_groups": self.n_groups}
        with (Path(dir) / FILE_NAME).open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(data, indent=2, sort_keys=True) + "\n")

    @classmethod
    def load(cls, dir: Path) -> LACConformal:
        """Read `<dir>/conformal.json`.

        Raises:
            ArtifactMissing: the file is absent. ArtifactVersionMismatch: malformed or not an LAC file.
        """
        path = Path(dir) / FILE_NAME
        if not path.is_file():
            raise ArtifactMissing(f"{path} not found")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["method"] != METHOD or data["target"] not in ("category", "priority"):
                raise ValueError(f"not an LAC file: method={data['method']!r} target={data['target']!r}")
            return cls.from_quantile(data["target"], float(data["alpha"]), float(data["q"]),
                                     int(data["n_calib"]), int(data.get("n_groups", 0)))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ArtifactVersionMismatch(f"{path}: {exc}") from exc
