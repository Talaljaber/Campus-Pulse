"""VectorFAQRetriever (P4.5): LocalNumpyVectorStore always, pgvector with `-m supabase`.

The encoder is a deterministic bag-of-words hashing encoder (a stand-in for the HashingEncoder
fake, which does not exist yet): texts that share words get high cosine, so ordering is testable.
"""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from collections.abc import Iterator, Sequence
from typing import Any, Protocol

import pytest
from fixtures.supabase_test import supabase_test_client

from campuspulse_ai.adapters.faq.retriever import VectorFAQRetriever
from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.domain.errors import StoreError
from campuspulse_ai.domain.ports import FAQRetriever, VectorStore
from campuspulse_ai.domain.values import Lang, VectorItem

DIM = 384


class BagOfWordsEncoder:
    dim = DIM
    model_id = "test-bow-hash"

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        out = []
        for text in texts:
            v = [0.0] * DIM
            for token in re.findall(r"\w+", text.lower()):
                digest = hashlib.sha256(token.encode()).digest()
                for i in (0, 4):  # two signed buckets per token: collisions rarely add up
                    h = int.from_bytes(digest[i : i + 4], "big")
                    v[h % DIM] += 1.0 if digest[8 + i] & 1 else -1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


ENC = BagOfWordsEncoder()
FAQ = [  # (key, lang, question, answer, source_url, is_demo)
    ("cs_hours", "en", "How many credit hours is the computer science bachelor", "145 credit hours.",
     "https://www.gju.edu.jo/content/faqs-14844", False),
    ("fees", "en", "How much is the fee per credit hour", "JD 100 per credit hour.",
     "https://www.gju.edu.jo/content/faqs-14844", False),
    ("wifi", "en", "How do I reset my password or fix wifi login", "[demo] Use self-service.", None, True),
    ("cs_hours_ar", "ar", "كم عدد الساعات المعتمدة لبكالوريوس علم الحاسوب", "145 ساعة معتمدة.",
     "https://www.gju.edu.jo/content/faqs-14844", False),
    ("wifi_ar", "ar", "كيف أصلح الدخول إلى الواي فاي wifi", "[demo] استخدم الخدمة الذاتية.", None, True),
]  # fmt: skip


class Harness(Protocol):
    vectors: VectorStore
    ids: dict[str, str]

    def cleanup(self) -> None: ...


def _items() -> tuple[dict[str, str], list[VectorItem]]:
    ids = {key: str(uuid.uuid4()) for key, *_ in FAQ}
    items = [
        VectorItem(ids[key], tuple(ENC.encode([q])[0]), q, Lang(lang),
                   {"answer": a, "source_url": url, "is_demo": demo})
        for key, lang, q, a, url, demo in FAQ
    ]  # fmt: skip
    return ids, items


class LocalHarness:
    def __init__(self) -> None:
        self.vectors = LocalNumpyVectorStore(DIM, collections=("faq",))
        self.ids, items = _items()
        self.vectors.upsert("faq", items)

    def cleanup(self) -> None:
        pass


class SupabaseHarness:
    """Adds five tagged rows to the live faq table (seed rows without embeddings never match)."""

    def __init__(self) -> None:
        from campuspulse_ai.adapters.vectors.pgvector import PgVectorStore

        self.db: Any = supabase_test_client()
        self.vectors = PgVectorStore(self.db, DIM)
        self.ids, items = _items()
        self.vectors.upsert("faq", items)

    def cleanup(self) -> None:
        self.db.table("faq").delete().in_("id", list(self.ids.values())).execute()


@pytest.fixture(
    params=[pytest.param(LocalHarness), pytest.param(SupabaseHarness, marks=pytest.mark.supabase)],
    ids=["local", "supabase"],
)
def h(request: pytest.FixtureRequest) -> Iterator[Harness]:
    harness: Harness = request.param()
    try:
        yield harness
    finally:
        harness.cleanup()


def ours(h: Harness, hits: list[Any]) -> list[Any]:
    """Live faq may hold other embedded rows; keep the ones this test added."""
    mine = set(h.ids.values())
    return [hit for hit in hits if hit.id in mine]


def test_satisfies_port(h: Harness) -> None:
    assert isinstance(VectorFAQRetriever(h.vectors, ENC), FAQRetriever)


def test_best_match_first_with_source_and_demo_flag(h: Harness) -> None:
    hits = ours(
        h,
        VectorFAQRetriever(h.vectors, ENC).search(
            "credit hours for the computer science bachelor", Lang.EN, 3
        ),
    )
    assert hits[0].id == h.ids["cs_hours"]
    assert hits[0].answer == "145 credit hours." and not hits[0].is_demo
    assert hits[0].source_url == "https://www.gju.edu.jo/content/faqs-14844"
    assert [x.score for x in hits] == sorted((x.score for x in hits), reverse=True)
    wifi = ours(h, VectorFAQRetriever(h.vectors, ENC).search("wifi login broken", Lang.EN, 1))
    assert wifi[0].id == h.ids["wifi"] and wifi[0].is_demo and wifi[0].source_url == ""


def test_search_stays_in_the_request_language(h: Harness) -> None:
    retriever = VectorFAQRetriever(h.vectors, ENC)
    en = ours(h, retriever.search("wifi", Lang.EN, 10))
    ar = ours(h, retriever.search("wifi", Lang.AR, 10))
    arabizi = ours(h, retriever.search("wifi", Lang.ARABIZI, 10))
    english_ids = {h.ids[k] for k in ("cs_hours", "fees", "wifi")}
    assert {x.id for x in en} <= english_ids
    assert {x.id for x in ar} <= {h.ids["cs_hours_ar"], h.ids["wifi_ar"]}
    assert arabizi[0].id == ar[0].id == h.ids["wifi_ar"]


def test_k_limits_results(h: Harness) -> None:
    retriever = VectorFAQRetriever(h.vectors, ENC)
    assert len(retriever.search("credit hours fee", Lang.EN, 1)) == 1
    assert retriever.search("credit hours fee", Lang.EN, 0) == []


def test_empty_store_returns_nothing_and_missing_collection_raises() -> None:
    empty = LocalNumpyVectorStore(DIM, collections=("faq",))
    assert VectorFAQRetriever(empty, ENC).search("anything", Lang.EN, 5) == []
    with pytest.raises(StoreError):
        VectorFAQRetriever(LocalNumpyVectorStore(DIM), ENC).search("anything", Lang.EN, 5)
