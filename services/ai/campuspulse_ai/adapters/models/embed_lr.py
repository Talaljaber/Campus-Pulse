"""M2-LR `EmbedLR`: frozen-encoder embedding → LogisticRegression (P1.11, §3.6).

The encoder is frozen (ONNX int8 e5-small); only the LR head is trained. `WeightedEnsemble` and `train.py`
pass embeddings they already computed (`predict_proba_from_embeddings`, `fit_embeddings`), so each text goes
through the encoder once. Class balancing uses weighted counts (`probs.balanced_sample_weight`), so
`sample_weight` equals duplication, as for M1.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped, unused-ignore]

from campuspulse_ai.adapters.models.probs import (
    LR_MAX_ITER,
    Target,
    balanced_sample_weight,
    check_labels,
    load_estimator,
    reorder,
    row_proba,
    save_estimator,
    target_labels,
    to_vectors,
)
from campuspulse_ai.domain.errors import ArtifactVersionMismatch
from campuspulse_ai.domain.ports import SentenceEncoder
from campuspulse_ai.domain.values import ProbVector

KIND = "embed_lr"



class EmbedLR:
    """Implements `domain.ports.ProbabilisticClassifier` (`name = "m2lr"`) for one target.

    `fit`/`predict_proba` embed the texts with `encoder`; `fit_embeddings`/`predict_proba_from_embeddings`
    take an (n, dim) array instead. Probabilities are in the target's label order.

    Raises:
        ValueError: an unknown label, mismatched lengths, a wrong embedding width, `predict_proba` before
            fitting, or a text method without an encoder (a model loaded without one).
        ArtifactMissing / ArtifactVersionMismatch: from `load`.
    """

    name = "m2lr"

    def __init__(self, target: Target, encoder: SentenceEncoder | None, C: float, seed: int) -> None:
        """
        Args:
            target: `category` or `priority`.
            encoder: the frozen encoder (None only when every call passes embeddings).
            C: `FrozenConfig.m2lr.C`. seed: `FrozenConfig.seed`.
        """
        self.target: Target = target
        self.labels = target_labels(target)
        self.encoder = encoder
        self.C = float(C)
        self.seed = int(seed)
        self._lr: LogisticRegression | None = None
        self.dim: int | None = encoder.dim if encoder is not None else None

    def fit(
        self, texts: Sequence[str], y: Sequence[str], sample_weight: Sequence[float] | None = None
    ) -> None:
        self.fit_embeddings(self._embed(texts), y, sample_weight)

    def fit_embeddings(
        self, emb: NDArray[np.float32], y: Sequence[str], sample_weight: Sequence[float] | None = None
    ) -> None:
        """Fit on precomputed embeddings (rows aligned with `y`)."""
        emb = np.asarray(emb, dtype=np.float32)
        if emb.ndim != 2 or emb.shape[0] != len(y):
            raise ValueError(f"embeddings of shape {emb.shape} for {len(y)} labels")
        check_labels(y, self.labels)
        lr = LogisticRegression(C=self.C, max_iter=LR_MAX_ITER, random_state=self.seed)
        lr.fit(emb, list(y), sample_weight=balanced_sample_weight(y, sample_weight, self.labels))
        self._lr, self.dim = lr, int(emb.shape[1])

    def predict_proba(self, texts: Sequence[str]) -> list[ProbVector]:
        if not texts:
            return []
        return self.predict_proba_from_embeddings(self._embed(texts))

    def predict_proba_from_embeddings(self, emb: NDArray[np.float32]) -> list[ProbVector]:
        """One `ProbVector` per embedding row."""
        lr = self._fitted()
        emb = np.asarray(emb, dtype=np.float32)
        if emb.ndim != 2 or emb.shape[1] != self.dim:
            raise ValueError(f"embeddings of shape {emb.shape}, expected (n, {self.dim})")
        if emb.shape[0] == 0:
            return []
        proba = row_proba(lr, emb)
        return to_vectors(reorder(proba, [str(c) for c in lr.classes_], self.labels), self.labels)

    def save(self, dir: Path) -> None:
        """Write `<dir>/model.joblib` (the LR) and `<dir>/meta.json`."""
        lr = self._fitted()
        meta = {"kind": KIND, "name": self.name, "target": self.target, "labels": list(self.labels),
                "C": self.C, "seed": self.seed, "dim": self.dim}
        save_estimator(dir, lr, meta)

    @classmethod
    def load(cls, dir: Path, encoder: SentenceEncoder | None = None) -> EmbedLR:
        """Read a directory written by `save`; pass the frozen encoder to use the text methods.

        Raises:
            ArtifactMissing, ArtifactVersionMismatch: a missing file, or an encoder of another width.
        """
        lr, meta = load_estimator(dir, KIND)
        if encoder is not None and int(meta["dim"]) != encoder.dim:
            raise ArtifactVersionMismatch(f"{dir}: head dim {meta['dim']} != encoder dim {encoder.dim}")
        model = cls(meta["target"], encoder, float(meta["C"]), int(meta["seed"]))
        model._lr, model.dim = lr, int(meta["dim"])
        return model

    def _embed(self, texts: Sequence[str]) -> NDArray[np.float32]:
        if self.encoder is None:
            raise ValueError("EmbedLR has no encoder; pass embeddings instead")
        return np.asarray(self.encoder.encode(list(texts)), dtype=np.float32).reshape(len(texts), -1)

    def _fitted(self) -> LogisticRegression:
        if self._lr is None:
            raise ValueError("EmbedLR is not fitted")
        return self._lr
