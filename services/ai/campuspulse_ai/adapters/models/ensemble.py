"""`WeightedEnsemble`: config-driven weighted average of the tier-0 members (P1.13, §3.6).

Membership and weights come from `FrozenConfig.ensemble`; removing a member from `members` (and its weights)
is the whole of a cut (§4.8 #4), no code change. Texts are encoded once per batch, and the embedding is reused
by M2-LR, M2-kNN and the OOD score.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from campuspulse_ai.adapters.models.knn import ExampleIndex, KnnClassifier
from campuspulse_ai.domain.errors import ArtifactVersionMismatch
from campuspulse_ai.domain.ports import MemoryStore, ProbabilisticClassifier, SentenceEncoder
from campuspulse_ai.domain.values import EnsembleOutput, Neighbor, ProbVector

TARGETS: tuple[str, str] = ("category", "priority")
WEIGHT_TOLERANCE = 1e-6


@runtime_checkable
class EmbeddingClassifier(Protocol):
    """A member that can score precomputed embeddings (M2-LR)."""

    def predict_proba_from_embeddings(self, emb: NDArray[np.float32]) -> list[ProbVector]: ...


def weighted_average(vectors: Mapping[str, ProbVector], weights: Mapping[str, float]) -> ProbVector:
    """Σ_m w_m · p_m over the members in `weights`, renormalized; label order of the first vector."""
    names = list(weights)
    labels = vectors[names[0]].labels
    acc = [0.0] * len(labels)
    for name in names:
        w = weights[name]
        for j, lab in enumerate(labels):
            acc[j] += w * vectors[name].prob(lab)
    total = math.fsum(acc)
    return ProbVector(tuple(v / total for v in acc), labels)


class WeightedEnsemble:
    """Implements `domain.ports.Ensemble`.

    `predict(texts, memory)` encodes the batch once, then per text:
      - every member's category and priority vector (`per_model["<member>.<target>"]`, LD-13);
      - `p_cat`, `p_pri_model` = the weighted averages with `weights_category` / `weights_priority`;
      - `ood_score` = max cosine to the frozen index (never memory); `neighbors` = the kNN member's neighbours
        (empty when `m2knn` is not a member); `embedding` = the text's vector.
    `memory` reaches only the kNN member (online); offline it is None.

    Raises:
        ArtifactVersionMismatch: a member without a (category, priority) pair, weight keys that differ from
            the members, negative weights or weights that do not sum to 1.
    """

    def __init__(
        self,
        members: Mapping[str, tuple[ProbabilisticClassifier, ProbabilisticClassifier]],
        encoder: SentenceEncoder,
        index: ExampleIndex,
        weights_category: Mapping[str, float],
        weights_priority: Mapping[str, float],
    ) -> None:
        if not members:
            raise ArtifactVersionMismatch("the ensemble needs at least one member")
        for name, weights in (("weights_category", weights_category), ("weights_priority", weights_priority)):
            if set(weights) != set(members):
                raise ArtifactVersionMismatch(
                    f"ensemble.{name} keys {sorted(weights)} differ from members {sorted(members)}"
                )
            off = abs(math.fsum(weights.values()) - 1) > WEIGHT_TOLERANCE
            if off or any(w < 0 for w in weights.values()):
                raise ArtifactVersionMismatch(f"ensemble.{name} must be non-negative and sum to 1")
        for name, pair in members.items():
            if len(pair) != len(TARGETS) or [m.target for m in pair] != list(TARGETS):
                raise ArtifactVersionMismatch(f"member {name!r} needs a (category, priority) pair")
        self.members: tuple[str, ...] = tuple(members)
        self._members = dict(members)
        self._encoder = encoder
        self._index = index
        self._weights = {"category": dict(weights_category), "priority": dict(weights_priority)}

    @property
    def index(self) -> ExampleIndex:
        return self._index

    @property
    def encoder(self) -> SentenceEncoder:
        return self._encoder

    def predict(self, texts: Sequence[str], memory: MemoryStore | None) -> list[EnsembleOutput]:
        if not texts:
            return []
        emb = np.asarray(self._encoder.encode(list(texts)), dtype=np.float32).reshape(len(texts), -1)
        per_member: dict[str, list[ProbVector]] = {}
        neighbors: list[tuple[Neighbor, ...]] = [() for _ in texts]
        for name, pair in self._members.items():
            for target, clf in zip(TARGETS, pair, strict=True):
                key = f"{name}.{target}"
                if isinstance(clf, KnnClassifier):
                    results = [clf.predict_from_embedding(row.tolist(), memory) for row in emb]
                    per_member[key] = [p for p, _ in results]
                    if target == "category":
                        neighbors = [n for _, n in results]
                elif isinstance(clf, EmbeddingClassifier):
                    per_member[key] = clf.predict_proba_from_embeddings(emb)
                else:
                    per_member[key] = clf.predict_proba(list(texts))
        outputs: list[EnsembleOutput] = []
        for i in range(len(texts)):
            per_model = {key: vectors[i] for key, vectors in per_member.items()}
            p = {}
            for target in TARGETS:
                weights = self._weights[target]
                p[target] = weighted_average({m: per_model[f"{m}.{target}"] for m in weights}, weights)
            outputs.append(EnsembleOutput(
                p_cat=p["category"],
                p_pri_model=p["priority"],
                per_model=per_model,
                ood_score=self._index.max_similarity(emb[i].tolist()),
                neighbors=neighbors[i],
                embedding=tuple(float(x) for x in emb[i]),
            ))
        return outputs
