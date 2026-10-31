"""`LogisticPriorityHead`: LogisticRegression over `[p_pri_model (3) ‖ evidence flags]` (P1.13, §3.8).

The head turns the ensemble's priority vector plus the labeller-rule evidence (`EVIDENCE_FEATURES`) into the
priority distribution. It is trained on OOF ensemble vectors (never in-sample ones), so it learns how far to
trust the members. `stated_urgency` can never be an input (rejected here, by `evidence_row` and by
`FrozenConfig`). Floors (safety, clarification answers) are not in the head: `PriorityFinalizer` applies them.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped, unused-ignore]

from campuspulse_ai.adapters.models.probs import (
    LR_MAX_ITER,
    balanced_sample_weight,
    check_labels,
    load_estimator,
    reorder,
    row_proba,
    save_estimator,
    temperature_scale,
    to_vectors,
)
from campuspulse_ai.domain.labels import PRIORITY_LABELS
from campuspulse_ai.domain.priority_rules import FORBIDDEN_FEATURES, evidence_row
from campuspulse_ai.domain.values import ClarificationConstraint, EvidenceVector, ProbVector

KIND = "priority_head"


class LogisticPriorityHead:
    """Implements `domain.ports.PriorityHead`.

    Input row = the 3 priority probabilities (low, medium, high) followed by the `features` flags as 0/1, so
    the width is `3 + len(features)`. `predict(..., constraints)` sets the flag of every `feature` constraint
    (a clarification answer such as "the deadline is today", LD-29) before scoring; `category`/`priority`
    constraints are handled by `TriageCore`/`PriorityFinalizer`. Class balancing uses weighted counts.

    Raises:
        ValueError: a forbidden feature, mismatched lengths, an unknown label, or `predict` before `fit`.
        ArtifactMissing / ArtifactVersionMismatch: from `load`.
    """

    def __init__(self, features: Sequence[str], C: float, seed: int) -> None:
        """
        Args:
            features: `FrozenConfig.priority_head.features` (= `EVIDENCE_FEATURES`).
            C: `FrozenConfig.priority_head.C`. seed: `FrozenConfig.seed`.
        """
        banned = FORBIDDEN_FEATURES.intersection(features)
        if banned:
            raise ValueError(f"{sorted(banned)} must never be a priority feature (§3.8)")
        self.features: tuple[str, ...] = tuple(features)
        self.C = float(C)
        self.seed = int(seed)
        # Calibration temperature (P2.7): probabilities are softmax(logits / T). 1.0 = the raw LR; train.py
        # picks T on OOF negative log-likelihood, so the conformal sets see honest confidence.
        self.temperature = 1.0
        self._lr: LogisticRegression | None = None

    @property
    def input_width(self) -> int:
        return len(PRIORITY_LABELS) + len(self.features)

    def row(self, p_pri_model: ProbVector, flags: dict[str, bool] | EvidenceVector) -> list[float]:
        """One input row: priority probabilities in label order, then the flags in feature order."""
        values = flags.flags if isinstance(flags, EvidenceVector) else flags
        probs = [p_pri_model.prob(lab) for lab in PRIORITY_LABELS]
        return probs + list(evidence_row(values, self.features))

    def matrix(self, p_pri: Sequence[ProbVector], evidence: Sequence[EvidenceVector]) -> NDArray[np.float64]:
        if len(p_pri) != len(evidence):
            raise ValueError(f"{len(p_pri)} priority vectors but {len(evidence)} evidence vectors")
        return np.array([self.row(p, e) for p, e in zip(p_pri, evidence, strict=True)], dtype=np.float64)

    def fit(
        self,
        p_pri_oof: Sequence[ProbVector],
        evidence: Sequence[EvidenceVector],
        y: Sequence[str],
        sample_weight: Sequence[float] | None,
    ) -> None:
        x = self.matrix(p_pri_oof, evidence)
        if x.shape[0] != len(y):
            raise ValueError(f"{x.shape[0]} rows but {len(y)} labels")
        check_labels(y, PRIORITY_LABELS)
        lr = LogisticRegression(C=self.C, max_iter=LR_MAX_ITER, random_state=self.seed)
        lr.fit(x, list(y), sample_weight=balanced_sample_weight(y, sample_weight, PRIORITY_LABELS))
        self._lr = lr

    def predict(
        self,
        p_pri_model: ProbVector,
        evidence: EvidenceVector,
        constraints: Sequence[ClarificationConstraint] = (),
    ) -> ProbVector:
        flags = dict(evidence.flags)
        for c in constraints:
            if c.kind == "feature" and c.value in self.features:
                flags[c.value] = True
        return self.predict_matrix(np.array([self.row(p_pri_model, flags)], dtype=np.float64))[0]

    def predict_matrix(self, x: NDArray[np.float64]) -> list[ProbVector]:
        """Score prepared rows (`matrix`); used by `train.py` for OOF head predictions."""
        lr = self._fitted()
        if x.ndim != 2 or x.shape[1] != self.input_width:
            raise ValueError(f"input of shape {x.shape}, expected (n, {self.input_width})")
        proba = row_proba(lr, x)  # float64, row by row: the same numbers alone or in a batch
        if self.temperature != 1.0:
            proba = temperature_scale(proba, self.temperature)
        return to_vectors(reorder(proba, [str(c) for c in lr.classes_], PRIORITY_LABELS), PRIORITY_LABELS)

    def coefficients(self) -> dict[str, dict[str, float]]:
        """{class: {input name: coefficient}} for the report and the explainer (multinomial LR)."""
        lr = self._fitted()
        names = [f"p_{lab}" for lab in PRIORITY_LABELS] + list(self.features)
        if lr.coef_.shape[0] == 1:  # binary fit (tiny data): one row for classes_[1]
            return {str(lr.classes_[1]): dict(zip(names, map(float, lr.coef_[0]), strict=True))}
        rows = zip(lr.classes_, lr.coef_, strict=True)
        return {str(c): dict(zip(names, map(float, row), strict=True)) for c, row in rows}

    def save(self, dir: Path) -> None:
        lr = self._fitted()
        meta = {"kind": KIND, "features": list(self.features), "C": self.C, "seed": self.seed,
                "labels": list(PRIORITY_LABELS), "temperature": self.temperature}
        save_estimator(dir, lr, meta)

    @classmethod
    def load(cls, dir: Path) -> LogisticPriorityHead:
        lr, meta = load_estimator(dir, KIND)
        head = cls(meta["features"], float(meta["C"]), int(meta["seed"]))
        head._lr = lr
        head.temperature = float(meta.get("temperature", 1.0))  # rc1 heads predate the temperature
        return head

    def _fitted(self) -> LogisticRegression:
        if self._lr is None:
            raise ValueError("LogisticPriorityHead is not fitted")
        return self._lr
