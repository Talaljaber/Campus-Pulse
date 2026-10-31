"""VectorFAQRetriever: FAQ answer-first retrieval over the VectorStore "faq" collection (P4.5).

One class for both stores: LocalNumpyVectorStore in tests, PgVectorStore online. It only
retrieves; the action engine applies `tau_faq` and never generates policy text (SPEC §5.1).
"""

from __future__ import annotations

from campuspulse_ai.domain.ports import SentenceEncoder, VectorStore
from campuspulse_ai.domain.values import FAQHit, Lang


class VectorFAQRetriever:
    """FAQRetriever: embed the question, cosine-search the FAQ in the request language.

    - The query is embedded by `encoder` exactly as every other text (the encoder applies the
      e5 `query: ` prefix itself, LD-9), so it lives in the same space as `seed_faq.py` rows.
    - Language: `en` → EN entries, `ar` and `arabizi` → AR entries (the FAQ has no Arabizi text).
    - Returns at most `k` hits, score descending (ties by id), each with its `answer`,
      `source_url` ("" when none) and `is_demo` flag; [] when nothing matches or k <= 0.
    - StoreError from the vector store propagates (the action engine degrades to a ticket).
    """

    def __init__(self, vectors: VectorStore, encoder: SentenceEncoder, collection: str = "faq") -> None:
        self._vectors = vectors
        self._encoder = encoder
        self._collection = collection

    def search(self, text: str, lang: Lang, k: int) -> list[FAQHit]:
        if k <= 0:
            return []
        faq_lang = Lang.EN if lang == Lang.EN else Lang.AR
        query = self._encoder.encode([text])[0]
        hits = self._vectors.search(
            self._collection, query, k=k, min_sim=0.0, filters={"lang": str(faq_lang)}
        )
        return [
            FAQHit(
                id=hit.id,
                question=hit.text,
                answer=str(hit.meta.get("answer") or ""),
                source_url=str(hit.meta.get("source_url") or ""),
                is_demo=bool(hit.meta.get("is_demo")),
                score=hit.sim,
            )
            for hit in hits
        ]
