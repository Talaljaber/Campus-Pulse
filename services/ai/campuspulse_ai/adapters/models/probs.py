"""Shared helpers for the sklearn-backed members: label order, probability conversion, weights, I/O.

Every member returns `ProbVector`s over the fixed label order of its target (`CATEGORY_LABELS` or
`PRIORITY_LABELS`), whatever order sklearn's `classes_` has. A class absent from the training data gets
probability 0 (the vector still sums to 1).

`balanced_sample_weight` replaces sklearn's `class_weight="balanced"`: it computes the balanced class weights
from the **weighted** label counts and folds them into `sample_weight`. sklearn's own option counts rows, so a
row duplicated twice and the same row with weight 2 would get different class weights; with this helper they
are identical (soft targets are weighted duplicates, ARCHITECTURE §3.3).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import joblib  # type: ignore[import-untyped, unused-ignore]
import numpy as np
from numpy.typing import NDArray

from campuspulse_ai.domain.errors import ArtifactMissing, ArtifactVersionMismatch
from campuspulse_ai.domain.labels import CATEGORY_LABELS, PRIORITY_LABELS
from campuspulse_ai.domain.values import ProbVector

Target = Literal["category", "priority"]
TARGET_LABELS: Mapping[str, tuple[str, ...]] = {"category": CATEGORY_LABELS, "priority": PRIORITY_LABELS}
MODEL_FILE = "model.joblib"
META_FILE = "meta.json"
JOBLIB_COMPRESS = 3  # zlib level: deterministic and keeps the committed heads small (§3.12 budget)
LR_MAX_ITER = 2000  # lbfgs iteration cap (P1.10 interface); convergence, not a modelling choice


def target_labels(target: str) -> tuple[str, ...]:
    """The fixed label order of a target. Raises ValueError for an unknown target."""
    try:
        return TARGET_LABELS[target]
    except KeyError:
        raise ValueError(f"unknown target {target!r}; expected 'category' or 'priority'") from None


def check_labels(y: Sequence[str], labels: Sequence[str]) -> None:
    """Raise ValueError if a label is not in the target's vocabulary."""
    unknown = sorted(set(y) - set(labels))
    if unknown:
        raise ValueError(f"labels {unknown} are not in {list(labels)}")


def reorder(proba: NDArray[np.float64], classes: Sequence[str], labels: Sequence[str]) -> NDArray[np.float64]:
    """Columns of `proba` (in `classes` order) moved into `labels` order; missing classes get 0."""
    out = np.zeros((proba.shape[0], len(labels)), dtype=np.float64)
    position = {lab: i for i, lab in enumerate(labels)}
    for j, cls in enumerate(classes):
        out[:, position[str(cls)]] = proba[:, j]
    return out


def to_vectors(matrix: NDArray[np.float64], labels: Sequence[str]) -> list[ProbVector]:
    """One `ProbVector` per row (renormalized with fsum, so float noise never fails validation)."""
    vectors: list[ProbVector] = []
    for row in np.asarray(matrix, dtype=np.float64):
        clipped = [max(float(v), 0.0) for v in row]
        total = math.fsum(clipped)
        values = tuple(v / total for v in clipped) if total > 0 else tuple(1.0 / len(labels) for _ in labels)
        vectors.append(ProbVector(values, tuple(labels)))
    return vectors


def to_matrix(vectors: Sequence[ProbVector], labels: Sequence[str]) -> NDArray[np.float64]:
    """Stack vectors into an (n, len(labels)) array in `labels` order."""
    out = np.zeros((len(vectors), len(labels)), dtype=np.float64)
    for i, vec in enumerate(vectors):
        for j, lab in enumerate(labels):
            out[i, j] = vec.prob(lab)
    return out


def balanced_sample_weight(
    y: Sequence[str], sample_weight: Sequence[float] | None, labels: Sequence[str]
) -> NDArray[np.float64]:
    """`sample_weight × n_weight / (n_present_classes × class_weight_sum)`, sklearn's "balanced" rule
    computed on weighted counts (see the module docstring).

    Raises:
        ValueError: lengths differ, or a weight is negative or not finite.
    """
    w = np.ones(len(y), dtype=np.float64) if sample_weight is None else np.asarray(sample_weight, np.float64)
    if w.shape != (len(y),):
        raise ValueError(f"sample_weight has {w.shape[0]} entries for {len(y)} labels")
    if not np.all(np.isfinite(w)) or np.any(w < 0):
        raise ValueError("sample_weight must be finite and non-negative")
    totals: dict[str, float] = {}
    for label, weight in zip(y, w, strict=True):
        totals[label] = totals.get(label, 0.0) + float(weight)
    present = [lab for lab in labels if totals.get(lab, 0.0) > 0]
    grand = math.fsum(totals.values())
    factor = {lab: grand / (len(present) * totals[lab]) for lab in present}
    return np.array([weight * factor.get(label, 0.0) for label, weight in zip(y, w, strict=True)])


def save_estimator(directory: Path, estimator: object, meta: Mapping[str, Any]) -> None:
    """Write `<dir>/model.joblib` (compressed) and `<dir>/meta.json` (sorted keys, LF)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    joblib.dump(estimator, directory / MODEL_FILE, compress=JOBLIB_COMPRESS)
    with (directory / META_FILE).open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(dict(meta), indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def load_estimator(directory: Path, kind: str) -> tuple[Any, dict[str, Any]]:
    """Read what `save_estimator` wrote and check `meta["kind"] == kind`.

    The joblib file is a pickle: load only model directories whose sha256 `MANIFEST.json` verified
    (`build_offline` does that first, ARCHITECTURE §3.12).

    Raises:
        ArtifactMissing: a file is absent. ArtifactVersionMismatch: unreadable meta or a different kind.
    """
    directory = Path(directory)
    model_path, meta_path = directory / MODEL_FILE, directory / META_FILE
    for path in (model_path, meta_path):
        if not path.is_file():
            raise ArtifactMissing(f"model file missing: {path}; run `python services/ai/train.py`")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactVersionMismatch(f"{meta_path}: unreadable meta: {exc}") from exc
    if not isinstance(meta, dict) or meta.get("kind") != kind:
        found = meta.get("kind") if isinstance(meta, dict) else None
        raise ArtifactVersionMismatch(f"{meta_path}: kind {found!r}, expected {kind!r}")
    return joblib.load(model_path), meta


def row_proba(lr: Any, x: NDArray[Any]) -> NDArray[np.float64]:
    """`lr.predict_proba(x)` computed one row at a time in float64.

    sklearn scores the whole float32 matrix in one BLAS call, whose summation order depends on the batch
    shape, so a text's probabilities would move by ~1e-8 with its batch neighbours. Row by row in float64,
    every text gets the same vector in `classify`, `classify_many`, `train.py` and the API. Same model:
    softmax of the decision function (multinomial), or the logistic of the single score (binary fit).
    """
    coef = np.asarray(lr.coef_, dtype=np.float64)
    intercept = np.asarray(lr.intercept_, dtype=np.float64)
    rows = np.asarray(x, dtype=np.float64)
    scores = np.stack([coef @ row for row in rows]) + intercept
    if coef.shape[0] == 1:  # binary: sklearn's expit on the single score, columns (classes_[0], classes_[1])
        p1 = 1.0 / (1.0 + np.exp(-scores[:, 0]))
        return np.stack([1.0 - p1, p1], axis=1)
    scores -= scores.max(axis=1, keepdims=True)
    e = np.exp(scores)
    result: NDArray[np.float64] = e / e.sum(axis=1, keepdims=True)
    return result
