"""`PrototypeClassifier` (`m2proto`): compare a request with each office's work (D-014, P2.7/P2.9).

A category member that scores a request by cosine similarity (the frozen encoder, same `query: ` prefix as
every other text) to per-category prototypes, then turns the scores into probabilities with a softmax at
temperature `T`:

- **learned** prototypes: per category, the normalized mean of its scenario centroids (each scenario's
  wrapper variants and augmented rows averaged first, so a scenario with many rows does not dominate). In
  CV they are computed inside each fold from that fold's training groups only, so OOF stays
  scenario-held-out; the frozen model uses every training row.
- **office** prototypes: one vector per responsibility line in `config/office_descriptions.yaml` (EN and
  AR, written from the challenge definitions and public GJU pages, never from training or test texts). A
  category's office score is its best-matching line.

With both parts the category score is `mix * learned + (1 - mix) * office`. `T` is chosen on OOF log-loss
(stage B); argmax does not depend on it, only the ensemble mix does. The priority side is the uniform
distribution (the member has no priority opinion; its priority weight is fixed at 0), so the ensemble
contract (a (category, priority) pair per member) holds without a change.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml
from numpy.typing import NDArray

from campuspulse_ai.adapters.models.probs import Target, target_labels, to_vectors
from campuspulse_ai.domain.errors import ArtifactMissing, ArtifactVersionMismatch
from campuspulse_ai.domain.labels import CATEGORY_LABELS
from campuspulse_ai.domain.ports import SentenceEncoder
from campuspulse_ai.domain.values import ProbVector

KIND = "prototype"
NAME = "m2proto"
PART_LEARNED, PART_OFFICE = "learned", "office"
PARTS: tuple[str, str] = (PART_LEARNED, PART_OFFICE)
VECTORS_FILE, META_FILE = "prototypes.npy", "meta.json"


@dataclass(frozen=True)
class PrototypeSet:
    """Prototype vectors (unit norm, shape (P, d)) with the category and part of each row."""

    vectors: NDArray[np.float32]
    labels: tuple[str, ...]
    parts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not (len(self.vectors) == len(self.labels) == len(self.parts)):
            raise ValueError("prototype vectors, labels and parts must align")
        if set(self.parts) - set(PARTS):
            raise ValueError(f"unknown prototype parts {sorted(set(self.parts) - set(PARTS))}")

    def only(self, parts: Sequence[str]) -> PrototypeSet:
        keep = [i for i, p in enumerate(self.parts) if p in parts]
        return PrototypeSet(
            self.vectors[keep], tuple(self.labels[i] for i in keep), tuple(self.parts[i] for i in keep)
        )

    @staticmethod
    def concat(sets: Sequence[PrototypeSet], dim: int) -> PrototypeSet:
        if not sets:
            return PrototypeSet(np.zeros((0, dim), dtype=np.float32), (), ())
        return PrototypeSet(
            np.concatenate([s.vectors for s in sets]).astype(np.float32),
            tuple(x for s in sets for x in s.labels),
            tuple(x for s in sets for x in s.parts),
        )


def _unit(x: NDArray[np.float64]) -> NDArray[np.float32]:
    norms = np.linalg.norm(x, axis=-1, keepdims=True)
    return (x / np.where(norms == 0, 1.0, norms)).astype(np.float32)


def learned_prototypes(
    emb: NDArray[np.float32], categories: Sequence[str], scenarios: Sequence[str]
) -> PrototypeSet:
    """One prototype per category present: the normalized mean of its scenario centroids.

    Args:
        emb: (n, d) encoder vectors of the training rows (one fold's training rows in CV).
        categories: the rows' official category; scenarios: the rows' scenario id (augmented rows carry
            their source or new scenario id).
    """
    emb = np.asarray(emb, dtype=np.float64)
    if not (len(emb) == len(categories) == len(scenarios)):
        raise ValueError("emb, categories and scenarios must align")
    by_scenario: dict[tuple[str, str], list[int]] = {}
    for i, (cat, sc) in enumerate(zip(categories, scenarios, strict=True)):
        by_scenario.setdefault((cat, sc), []).append(i)
    vectors, labels = [], []
    for cat in CATEGORY_LABELS:
        cents = [_unit(emb[idx].mean(axis=0)) for (c, _), idx in sorted(by_scenario.items()) if c == cat]
        if cents:
            vectors.append(_unit(np.mean(np.asarray(cents, dtype=np.float64), axis=0)))
            labels.append(cat)
    dim = emb.shape[1] if emb.ndim == 2 else 0
    return PrototypeSet(
        np.asarray(vectors, dtype=np.float32).reshape(len(vectors), dim),
        tuple(labels),
        (PART_LEARNED,) * len(labels),
    )


def office_lines(path: Path) -> list[tuple[str, str]]:
    """(category, line) pairs from `office_descriptions.yaml`, in category then file order.

    Raises:
        ValueError: an unknown category, a category without lines, or a missing `offices` mapping.
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    offices: Mapping[str, Mapping[str, Sequence[str]]] = data["offices"]
    unknown = sorted(set(offices) - set(CATEGORY_LABELS))
    if unknown:
        raise ValueError(f"{path}: unknown categories {unknown}")
    out: list[tuple[str, str]] = []
    for cat in CATEGORY_LABELS:
        lines = [str(t).strip() for lang in sorted(offices.get(cat, {})) for t in offices[cat][lang]]
        if not [t for t in lines if t]:
            raise ValueError(f"{path}: category {cat!r} has no description lines")
        out.extend((cat, t) for t in lines if t)
    return out


def office_prototypes(encoder: SentenceEncoder, path: Path) -> PrototypeSet:
    """Embed every description line once (train time only; the frozen model stores the vectors)."""
    pairs = office_lines(path)
    vecs = np.asarray(encoder.encode([t for _, t in pairs]), dtype=np.float64)
    return PrototypeSet(_unit(vecs), tuple(c for c, _ in pairs), (PART_OFFICE,) * len(pairs))


def category_scores(emb: NDArray[np.float32], protos: PrototypeSet, mix: float) -> NDArray[np.float64]:
    """(n, 6) similarity scores in `CATEGORY_LABELS` order (see the module docstring).

    Per part, a category's score is the max cosine over its prototypes of that part; a category with no
    prototype in a part gets that part's minimum score in the row (it never wins on missing evidence).
    """
    emb = np.asarray(emb, dtype=np.float64)
    sims = emb @ np.asarray(protos.vectors, dtype=np.float64).T if len(protos.labels) else None
    present = [p for p in PARTS if p in protos.parts]
    if sims is None or not present:
        return np.zeros((len(emb), len(CATEGORY_LABELS)), dtype=np.float64)
    per_part: dict[str, NDArray[np.float64]] = {}
    for part in present:
        block = np.full((len(emb), len(CATEGORY_LABELS)), np.nan)
        for j, cat in enumerate(CATEGORY_LABELS):
            cols = [
                k
                for k, (lab, pt) in enumerate(zip(protos.labels, protos.parts, strict=True))
                if lab == cat and pt == part
            ]
            if cols:
                block[:, j] = sims[:, cols].max(axis=1)
        floor = np.nanmin(block, axis=1, keepdims=True)
        per_part[part] = np.where(np.isnan(block), floor, block)
    if len(present) == 1:
        return per_part[present[0]]
    return mix * per_part[PART_LEARNED] + (1.0 - mix) * per_part[PART_OFFICE]


def softmax(scores: NDArray[np.float64], temperature: float) -> NDArray[np.float64]:
    """Row softmax of `scores / temperature` (stable). ValueError for a temperature <= 0."""
    if temperature <= 0:
        raise ValueError("temperature must be > 0")
    z = np.asarray(scores, dtype=np.float64) / temperature
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    out: NDArray[np.float64] = e / e.sum(axis=1, keepdims=True)
    return out


class PrototypeClassifier:
    """Implements `domain.ports.ProbabilisticClassifier` (`name = "m2proto"`) for one target.

    Category: softmax(category_scores / T) over the stored prototypes. Priority: the uniform distribution
    (no prototypes; weight 0 in `weights_priority`). The prototypes are built by `learned_prototypes` /
    `office_prototypes`, not by `fit`, which raises (like the kNN member, the prototypes are the model).

    Raises:
        ValueError: `fit`, a text method without an encoder, or embeddings of the wrong width.
        ArtifactMissing / ArtifactVersionMismatch: from `load`.
    """

    name = NAME

    def __init__(
        self,
        target: Target,
        prototypes: PrototypeSet | None,
        temperature: float,
        mix: float,
        encoder: SentenceEncoder | None = None,
    ) -> None:
        self.target: Target = target
        self.labels = target_labels(target)
        self.prototypes = prototypes
        self.temperature = float(temperature)
        self.mix = float(mix)
        self.encoder = encoder
        if target == "category" and (prototypes is None or not prototypes.labels):
            raise ValueError("the category prototype member needs prototypes")
        if self.temperature <= 0 or not 0.0 <= self.mix <= 1.0:
            raise ValueError("temperature must be > 0 and mix in [0, 1]")

    def fit(
        self, texts: Sequence[str], y: Sequence[str], sample_weight: Sequence[float] | None = None
    ) -> None:
        raise ValueError("PrototypeClassifier is built from prototypes; it has no fit")

    def predict_proba(self, texts: Sequence[str]) -> list[ProbVector]:
        if not texts:
            return []
        if self.encoder is None:
            raise ValueError("PrototypeClassifier has no encoder; pass embeddings instead")
        emb = np.asarray(self.encoder.encode(list(texts)), dtype=np.float32).reshape(len(texts), -1)
        return self.predict_proba_from_embeddings(emb)

    def predict_proba_from_embeddings(self, emb: NDArray[np.float32]) -> list[ProbVector]:
        emb = np.asarray(emb, dtype=np.float32)
        if emb.ndim != 2 or emb.shape[0] == 0:
            return []
        return to_vectors(self.matrix(emb), self.labels)

    def matrix(self, emb: NDArray[np.float32]) -> NDArray[np.float64]:
        """(n, L) probabilities in the target's label order."""
        n = len(emb)
        if self.target == "priority" or self.prototypes is None:
            return np.full((n, len(self.labels)), 1.0 / len(self.labels))
        if emb.shape[1] != self.prototypes.vectors.shape[1]:
            raise ValueError(
                f"embeddings of width {emb.shape[1]}, prototypes {self.prototypes.vectors.shape[1]}"
            )
        return softmax(category_scores(emb, self.prototypes, self.mix), self.temperature)

    def save(self, dir: Path) -> None:
        """Write `<dir>/prototypes.npy` (float32, no pickle) and `<dir>/meta.json`."""
        dir.mkdir(parents=True, exist_ok=True)
        protos = self.prototypes
        dim = int(protos.vectors.shape[1]) if protos is not None else 0
        if protos is not None:
            with (dir / VECTORS_FILE).open("wb") as fh:
                np.save(fh, np.asarray(protos.vectors, dtype=np.float32), allow_pickle=False)
        meta = {
            "kind": KIND,
            "name": self.name,
            "target": self.target,
            "labels": list(self.labels),
            "temperature": self.temperature,
            "mix": self.mix,
            "dim": dim,
            "prototype_labels": list(protos.labels) if protos else [],
            "prototype_parts": list(protos.parts) if protos else [],
        }
        with (dir / META_FILE).open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(meta, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, dir: Path, encoder: SentenceEncoder | None = None) -> PrototypeClassifier:
        """Read a directory written by `save`.

        Raises:
            ArtifactMissing: no meta (or no vectors for the category side).
            ArtifactVersionMismatch: another kind, misaligned prototypes, or an encoder of another width.
        """
        meta_path = Path(dir) / META_FILE
        if not meta_path.is_file():
            raise ArtifactMissing(f"{meta_path} not found")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("kind") != KIND:
            raise ArtifactVersionMismatch(f"{dir}: kind {meta.get('kind')!r} is not {KIND!r}")
        protos: PrototypeSet | None = None
        if meta["prototype_labels"]:
            vec_path = Path(dir) / VECTORS_FILE
            if not vec_path.is_file():
                raise ArtifactMissing(f"{vec_path} not found")
            vectors = np.load(vec_path, allow_pickle=False)
            try:
                protos = PrototypeSet(
                    vectors.astype(np.float32),
                    tuple(meta["prototype_labels"]),
                    tuple(meta["prototype_parts"]),
                )
            except ValueError as exc:
                raise ArtifactVersionMismatch(f"{dir}: {exc}") from exc
            if encoder is not None and vectors.shape[1] != encoder.dim:
                raise ArtifactVersionMismatch(
                    f"{dir}: prototype dim {vectors.shape[1]} != encoder {encoder.dim}"
                )
        return cls(meta["target"], protos, float(meta["temperature"]), float(meta["mix"]), encoder)
