"""M2-kNN: `ExampleIndex` over the frozen `train` collection and `KnnClassifier` (P1.11, §3.6, §3.11).

The index is the model: one item per **distinct** training `model_text` (wrapper variants share a text, and
ten copies of one scenario would otherwise fill all k neighbour slots), carrying both labels in `meta`. In CV,
`train.py` builds one index per fold from that fold's training rows only.

Vote (per target): each of the k nearest training items votes for its label with weight `max(sim, 0)`; the
vote is smoothed with `laplace_mass` pseudo-votes spread evenly over the labels, so no label gets
probability 0:  p(l) = (votes(l) + laplace_mass / L) / (Σ votes + laplace_mass).

Live memory (online only, P3): up to `max_memory_neighbors` memory items with similarity ≥ `memory_min_sim`
also vote, but their total weight is scaled down so it is at most `memory_weight_cap` of the whole vote.
`ood_score` (`adapters/models/ood.py`) and the frozen index never see memory.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from campuspulse_ai.adapters.models.probs import Target, target_labels
from campuspulse_ai.domain.errors import ArtifactMissing, ArtifactVersionMismatch, StoreError
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.ports import MemoryStore, SentenceEncoder, VectorStore
from campuspulse_ai.domain.values import Lang, Neighbor, ProbVector, VectorItem

TRAIN_COLLECTION = "train"
KIND = "knn"
META_FILE = "knn.json"
SOURCE_OFFICIAL = "official"


@dataclass(frozen=True, slots=True)
class IndexEntry:
    """One training example for the index (`source` is `official` or an augmentation source)."""

    id: str
    text: str
    embedding: tuple[float, ...]
    category: str
    priority: str
    lang: Lang
    source: str
    scenario_id: str
    cv_group: str


class ExampleIndex:
    """Nearest training examples in a `VectorStore` collection (default `train`).

    Errors: `StoreError` from `query`/`max_similarity` on an empty or unknown collection.
    """

    def __init__(self, store: VectorStore, collection: str = TRAIN_COLLECTION) -> None:
        self.store = store
        self.collection = collection

    def add(self, entries: Sequence[IndexEntry]) -> None:
        """Upsert entries (the store must be writable)."""
        items = [
            VectorItem(
                id=e.id,
                embedding=e.embedding,
                text=e.text,
                lang=e.lang,
                meta={"category": e.category, "priority": e.priority, "source": e.source,
                      "scenario_id": e.scenario_id, "cv_group": e.cv_group},
            )
            for e in entries
        ]
        self.store.upsert(self.collection, items)

    def size(self) -> int:
        return self.store.count(self.collection)

    def query(self, embedding: Sequence[float], k: int) -> list[Neighbor]:
        """The k most similar items, similarity descending (ties by id)."""
        self._non_empty()
        hits = self.store.search(self.collection, embedding, k, min_sim=-1.0)
        return [
            Neighbor(
                text=h.text,
                category=Category(str(h.meta["category"])),
                priority=Priority(str(h.meta["priority"])),
                sim=float(h.sim),
                source="train" if h.meta.get("source") == SOURCE_OFFICIAL else "augmented",
            )
            for h in hits
        ]

    def max_similarity(self, embedding: Sequence[float]) -> float:
        """Cosine similarity to the nearest item."""
        self._non_empty()
        hits = self.store.search(self.collection, embedding, 1, min_sim=-1.0)
        return float(hits[0].sim)

    def _non_empty(self) -> None:
        if self.store.count(self.collection) == 0:
            raise StoreError(f"example index {self.collection!r} is empty")


class KnnClassifier:
    """Implements `domain.ports.ProbabilisticClassifier` (`name = "m2knn"`) over an `ExampleIndex`.

    `predict_from_embedding(emb, memory)` returns the smoothed vote (module docstring) and the neighbours
    used (training neighbours first, then memory neighbours). `predict_proba(texts)` embeds and calls it with
    no memory. kNN has no trainable parameters: the index is the model, so `fit` raises (`train.py` builds
    the index with `ExampleIndex.add`), and `save`/`load` only keep the settings.

    Raises:
        StoreError: an empty index. NotImplementedError: `fit`.
    """

    name = "m2knn"

    def __init__(
        self,
        target: Target,
        index: ExampleIndex,
        encoder: SentenceEncoder | None,
        k: int,
        memory_weight_cap: float,
        max_memory_neighbors: int,
        *,
        memory_min_sim: float,
        laplace_mass: float,
    ) -> None:
        """
        Args:
            target: `category` or `priority`. index: the frozen (or fold) index. encoder: for `predict_proba`.
            k, memory_weight_cap, max_memory_neighbors, memory_min_sim, laplace_mass: `FrozenConfig.knn.*`.

        Raises:
            ValueError: k < 1, a cap outside [0, 1], a negative neighbour count or a non-positive mass.
        """
        if k < 1:
            raise ValueError("k must be >= 1")
        if not 0.0 <= memory_weight_cap <= 1.0:
            raise ValueError("memory_weight_cap must be in [0, 1]")
        if max_memory_neighbors < 0:
            raise ValueError("max_memory_neighbors must be >= 0")
        if laplace_mass <= 0:
            raise ValueError("laplace_mass must be > 0")
        self.target: Target = target
        self.labels = target_labels(target)
        self.index = index
        self.encoder = encoder
        self.k = int(k)
        self.memory_weight_cap = float(memory_weight_cap)
        self.max_memory_neighbors = int(max_memory_neighbors)
        self.memory_min_sim = float(memory_min_sim)
        self.laplace_mass = float(laplace_mass)

    def fit(
        self, texts: Sequence[str], y: Sequence[str], sample_weight: Sequence[float] | None = None
    ) -> None:
        raise NotImplementedError("kNN has no parameters to fit; build the index with ExampleIndex.add")

    def predict_proba(self, texts: Sequence[str]) -> list[ProbVector]:
        if not texts:
            return []
        if self.encoder is None:
            raise ValueError("KnnClassifier has no encoder; use predict_from_embedding")
        return [self.predict_from_embedding(e, None)[0] for e in self.encoder.encode(list(texts))]

    def predict_from_embedding(
        self, emb: Sequence[float], memory: MemoryStore | None
    ) -> tuple[ProbVector, tuple[Neighbor, ...]]:
        """(smoothed vote, neighbours) for one embedding; `memory=None` uses the training index only."""
        train = self.index.query(emb, self.k)
        mem: list[Neighbor] = []
        if memory is not None and self.max_memory_neighbors > 0:
            mem = list(memory.neighbors(emb, self.max_memory_neighbors, self.memory_min_sim))
            mem = mem[: self.max_memory_neighbors]
        votes = np.zeros(len(self.labels), dtype=np.float64)
        position = {lab: i for i, lab in enumerate(self.labels)}
        for n in train:
            votes[position[self._label(n)]] += max(n.sim, 0.0)
        train_mass = float(votes.sum())
        mem_mass = sum(max(n.sim, 0.0) for n in mem)
        scale = self._memory_scale(train_mass, mem_mass)
        for n in mem:
            votes[position[self._label(n)]] += max(n.sim, 0.0) * scale
        smoothed = votes + self.laplace_mass / len(self.labels)
        probs = smoothed / smoothed.sum()
        total = float(probs.sum())
        vector = ProbVector(tuple(float(v) / total for v in probs), self.labels)
        return vector, (*train, *mem)

    def predict_from_embeddings(self, emb: NDArray[np.float32]) -> list[ProbVector]:
        """Batch form without memory (CV and the ensemble's offline path)."""
        return [self.predict_from_embedding(row.tolist(), None)[0] for row in np.asarray(emb)]

    def _memory_scale(self, train_mass: float, mem_mass: float) -> float:
        """Factor that keeps memory's share of the vote ≤ memory_weight_cap."""
        if mem_mass <= 0.0 or train_mass <= 0.0:
            return 1.0 if self.memory_weight_cap > 0 else 0.0
        if self.memory_weight_cap >= 1.0:
            return 1.0
        allowed = self.memory_weight_cap / (1.0 - self.memory_weight_cap) * train_mass
        return min(1.0, allowed / mem_mass)

    def _label(self, n: Neighbor) -> str:
        return str(n.category if self.target == "category" else n.priority)

    def save(self, dir: Path) -> None:
        """Write `<dir>/knn.json` (settings only; the index is saved with the vector store)."""
        Path(dir).mkdir(parents=True, exist_ok=True)
        data = {"kind": KIND, "target": self.target, "k": self.k, "collection": self.index.collection,
                "memory_weight_cap": self.memory_weight_cap,
                "max_memory_neighbors": self.max_memory_neighbors,
                "memory_min_sim": self.memory_min_sim, "laplace_mass": self.laplace_mass}
        with (Path(dir) / META_FILE).open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(data, indent=2, sort_keys=True) + "\n")

    @classmethod
    def load(
        cls, dir: Path, index: ExampleIndex | None = None, encoder: SentenceEncoder | None = None
    ) -> KnnClassifier:
        """Rebuild from `<dir>/knn.json` over `index` (required: the index lives in the vector store).

        Raises:
            ArtifactMissing: no file. ArtifactVersionMismatch: malformed. ValueError: no index given.
        """
        if index is None:
            raise ValueError("KnnClassifier.load needs the ExampleIndex")
        path = Path(dir) / META_FILE
        if not path.is_file():
            raise ArtifactMissing(f"{path} not found")
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            if d["kind"] != KIND:
                raise ValueError(f"kind {d['kind']!r}")
            return cls(d["target"], index, encoder, int(d["k"]), float(d["memory_weight_cap"]),
                       int(d["max_memory_neighbors"]), memory_min_sim=float(d["memory_min_sim"]),
                       laplace_mass=float(d["laplace_mass"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ArtifactVersionMismatch(f"{path}: {exc}") from exc
