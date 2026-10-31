"""`StoreExemplarSimilarity`: nearest guard exemplar in a `VectorStore` collection (P1.5, used from P1.15)."""

from __future__ import annotations

from campuspulse_ai.domain.ports import SentenceEncoder, VectorStore


class StoreExemplarSimilarity:
    """Implements `domain.ports.ExemplarSimilarity` over a vector-store collection.

    `bank` is the collection name (`injection_exemplars`, `safety_exemplars`). The text is embedded with the
    same encoder that built the collection (the encoder applies the e5 `query: ` prefix itself, LD-9), and
    the top-1 cosine hit is returned. An empty collection gives `(0.0, "")`.

    Errors: `StoreError` from the store (an unknown collection is an error, not an empty result).
    """

    def __init__(self, store: VectorStore, encoder: SentenceEncoder) -> None:
        if store.dim != encoder.dim:
            raise ValueError(f"store dim {store.dim} != encoder dim {encoder.dim}")
        self._store = store
        self._encoder = encoder

    def max_similarity(self, text: str, bank: str) -> tuple[float, str]:
        """(cosine of the nearest exemplar, its text)."""
        embedding = self._encoder.encode([text])[0]
        hits = self._store.search(bank, embedding, k=1)
        if not hits:
            return 0.0, ""
        return float(hits[0].sim), hits[0].text
