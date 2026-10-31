"""VectorStore contract (ARCHITECTURE §3.18, X4.5): the same cases run against every store.

LocalNumpyVectorStore always runs; PgVectorStore runs when SUPABASE_TEST_URL /
SUPABASE_TEST_SERVICE_ROLE_KEY are set.
"""

from __future__ import annotations

import math
import random
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import pytest
from fixtures.supabase_test import supabase_test_client

from campuspulse_ai.adapters.vectors.local_numpy import LocalNumpyVectorStore
from campuspulse_ai.domain.errors import ArtifactMissing, ArtifactVersionMismatch, NotFound, StoreError
from campuspulse_ai.domain.ports import VectorStore
from campuspulse_ai.domain.values import Lang, VectorItem

DIM = 384
TEST_BUILDING = "zz-contract-test"


def unit_vector(seed: int) -> tuple[float, ...]:
    rng = random.Random(seed)
    v = [rng.gauss(0.0, 1.0) for _ in range(DIM)]
    norm = math.sqrt(sum(x * x for x in v))
    return tuple(x / norm for x in v)


class Harness(Protocol):
    store: VectorStore

    def memory_item(self, vec: tuple[float, ...], *, category: str = "Finance") -> VectorItem: ...
    def faq_item(self, vec: tuple[float, ...], lang: Lang) -> VectorItem: ...
    def request_item(self, vec: tuple[float, ...], building_id: str | None) -> VectorItem: ...
    def wrong_dim_store(self) -> VectorStore: ...
    def reloaded(self) -> VectorStore: ...
    def cleanup(self) -> None: ...


class _Items:
    """Item builders shared by every harness; ids are UUIDs so pgvector accepts them."""

    def __init__(self) -> None:
        self._memory: list[str] = []
        self._faq: list[str] = []
        self._requests: list[str] = []

    def memory_item(self, vec: tuple[float, ...], *, category: str = "Finance") -> VectorItem:
        id = str(uuid.uuid4())
        self._memory.append(id)
        meta = {
            "category": category,
            "priority": "low",
            "created_at": datetime.now(UTC).isoformat(),
            "active": True,
        }
        return VectorItem(id=id, embedding=vec, text=f"contract memory {id[:8]}", lang=Lang.EN, meta=meta)

    def faq_item(self, vec: tuple[float, ...], lang: Lang) -> VectorItem:
        id = str(uuid.uuid4())
        self._faq.append(id)
        return VectorItem(
            id=id, embedding=vec, text=f"contract faq {id[:8]}", lang=lang, meta={"answer": "a"}
        )

    def request_item(self, vec: tuple[float, ...], building_id: str | None) -> VectorItem:
        id = str(uuid.uuid4())
        self._requests.append(id)
        meta = {"building_id": building_id, "category": "IT Support", "priority": "medium"}
        return VectorItem(id=id, embedding=vec, text="", lang=Lang.EN, meta=meta)


class LocalHarness(_Items):
    """LocalNumpyVectorStore with the three online collection names pre-created."""

    def __init__(self, tmp_path: Path) -> None:
        super().__init__()
        self.tmp_path = tmp_path
        self.store = LocalNumpyVectorStore(DIM, collections=("memory", "faq", "requests"))

    def wrong_dim_store(self) -> VectorStore:
        self.store.save(self.tmp_path / "wrong_dim")
        return LocalNumpyVectorStore.load(self.tmp_path / "wrong_dim", expected_dim=DIM + 1)

    def reloaded(self) -> VectorStore:
        self.store.save(self.tmp_path / "index")
        return LocalNumpyVectorStore.load(self.tmp_path / "index", expected_dim=DIM)

    def cleanup(self) -> None:
        pass


class PgHarness(_Items):
    """Creates rows in the test project and removes every one of them in cleanup()."""

    def __init__(self, tmp_path: Path) -> None:
        from campuspulse_ai.adapters.vectors.pgvector import PgVectorStore

        super().__init__()
        self.client: Any = supabase_test_client()
        self.store = PgVectorStore(self.client, DIM)
        self.client.table("buildings").upsert(
            {"id": TEST_BUILDING, "code": TEST_BUILDING, "name_en": "Contract test", "name_ar": "اختبار"}
        ).execute()

    def request_item(self, vec: tuple[float, ...], building_id: str | None) -> VectorItem:
        item = super().request_item(vec, building_id)
        self.client.table("requests").insert(
            {
                "id": item.id,
                "raw_text": "contract",
                "text_norm": f"contract request {item.id[:8]}",
                "lang": "en",
                "status": "received",
                "building_id": building_id,
            }
        ).execute()
        return item

    def wrong_dim_store(self) -> VectorStore:
        from campuspulse_ai.adapters.vectors.pgvector import PgVectorStore

        return PgVectorStore(self.client, DIM + 1)

    def reloaded(self) -> VectorStore:
        pytest.skip("pgvector persists every write; there is no save/load step")

    def cleanup(self) -> None:
        if self._memory:
            self.client.table("memory_examples").delete().in_("id", self._memory).execute()
        if self._faq:
            self.client.table("faq").delete().in_("id", self._faq).execute()
        if self._requests:  # request_embeddings rows cascade
            self.client.table("requests").delete().in_("id", self._requests).execute()
        self.client.table("buildings").delete().eq("id", TEST_BUILDING).execute()


HARNESSES = {
    "pgvector": pytest.param(PgHarness, marks=pytest.mark.supabase),
    "local_numpy": pytest.param(LocalHarness),
}


@pytest.fixture(params=list(HARNESSES.values()), ids=list(HARNESSES))
def harness(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Harness]:
    h: Harness = request.param(tmp_path)
    try:
        yield h
    finally:
        h.cleanup()


def test_store_satisfies_port(harness: Harness) -> None:
    assert isinstance(harness.store, VectorStore)
    assert harness.store.dim == DIM


def test_upsert_then_search_returns_item_with_sim_one(harness: Harness) -> None:
    vec = unit_vector(1)
    item = harness.memory_item(vec)
    harness.store.upsert("memory", [item])
    hits = harness.store.search("memory", vec, k=1)
    assert hits[0].id == item.id
    assert hits[0].sim == pytest.approx(1.0, abs=1e-4)
    assert hits[0].text == item.text
    assert hits[0].meta["category"] == "Finance"


def test_upsert_is_idempotent_by_id(harness: Harness) -> None:
    vec = unit_vector(2)
    item = harness.memory_item(vec)
    harness.store.upsert("memory", [item])
    harness.store.upsert("memory", [item])
    hits = harness.store.search("memory", vec, k=5, min_sim=0.99)
    assert [h.id for h in hits].count(item.id) == 1


def test_min_sim_excludes_far_items(harness: Harness) -> None:
    item = harness.memory_item(unit_vector(3))
    harness.store.upsert("memory", [item])
    hits = harness.store.search("memory", unit_vector(4), k=50, min_sim=0.9)
    assert item.id not in {h.id for h in hits}


def test_requests_filter_by_building(harness: Harness) -> None:
    vec = unit_vector(5)
    inside = harness.request_item(vec, TEST_BUILDING)
    outside = harness.request_item(vec, None)
    harness.store.upsert("requests", [inside, outside])
    hits = harness.store.search("requests", vec, k=10, min_sim=0.99, filters={"building_id": TEST_BUILDING})
    assert [h.id for h in hits] == [inside.id]
    assert hits[0].meta["building_id"] == TEST_BUILDING
    both = harness.store.search("requests", vec, k=10, min_sim=0.99)
    assert {inside.id, outside.id} <= {h.id for h in both}


def test_faq_filter_by_lang(harness: Harness) -> None:
    vec = unit_vector(6)
    en, ar = harness.faq_item(vec, Lang.EN), harness.faq_item(vec, Lang.AR)
    harness.store.upsert("faq", [en, ar])
    hits = harness.store.search("faq", vec, k=10, min_sim=0.99, filters={"lang": "ar"})
    assert [h.id for h in hits] == [ar.id]
    assert hits[0].lang == Lang.AR


def test_set_active_false_hides_item(harness: Harness) -> None:
    vec = unit_vector(7)
    item = harness.memory_item(vec)
    harness.store.upsert("memory", [item])
    harness.store.set_active("memory", item.id, False)
    assert item.id not in {h.id for h in harness.store.search("memory", vec, k=10)}
    harness.store.set_active("memory", item.id, True)
    assert item.id in {h.id for h in harness.store.search("memory", vec, k=10)}


def test_set_active_unknown_id_raises_not_found(harness: Harness) -> None:
    with pytest.raises(NotFound):
        harness.store.set_active("memory", str(uuid.uuid4()), False)


def test_ties_break_on_id(harness: Harness) -> None:
    vec = unit_vector(8)
    items = [harness.memory_item(vec) for _ in range(3)]
    harness.store.upsert("memory", items)
    hits = harness.store.search("memory", vec, k=3, min_sim=0.99)
    assert [h.id for h in hits] == sorted(i.id for i in items)


def test_embedding_returned_only_on_request(harness: Harness) -> None:
    vec = unit_vector(9)
    item = harness.memory_item(vec)
    harness.store.upsert("memory", [item])
    plain = harness.store.search("memory", vec, k=1)
    assert plain[0].embedding is None
    full = harness.store.search("memory", vec, k=1, filters={"with_embedding": True})
    assert full[0].embedding is not None
    assert full[0].embedding == pytest.approx(vec, abs=1e-6)


def test_count_tracks_active_items(harness: Harness) -> None:
    before = harness.store.count("memory", {"category": "Transportation"})
    item = harness.memory_item(unit_vector(10), category="Transportation")
    harness.store.upsert("memory", [item])
    assert harness.store.count("memory", {"category": "Transportation"}) == before + 1
    harness.store.set_active("memory", item.id, False)
    assert harness.store.count("memory", {"category": "Transportation"}) == before


def test_unknown_collection_raises_store_error(harness: Harness) -> None:
    with pytest.raises(StoreError):
        harness.store.search("nope", unit_vector(11), k=1)


def test_wrong_query_dim_raises_store_error(harness: Harness) -> None:
    with pytest.raises(StoreError):
        harness.store.search("memory", (1.0, 0.0), k=1)


def test_dim_mismatch_raises_artifact_version_mismatch(harness: Harness) -> None:
    with pytest.raises(ArtifactVersionMismatch):
        harness.wrong_dim_store()


def test_save_load_roundtrip(harness: Harness) -> None:
    vec = unit_vector(12)
    kept, hidden = harness.memory_item(vec), harness.memory_item(unit_vector(13))
    harness.store.upsert("memory", [kept, hidden])
    harness.store.set_active("memory", hidden.id, False)
    loaded = harness.reloaded()
    assert loaded.count("memory") == harness.store.count("memory")
    hits = loaded.search("memory", vec, k=5, filters={"with_embedding": True})
    assert hits[0].id == kept.id and hits[0].text == kept.text and hits[0].meta["category"] == "Finance"
    assert hits[0].embedding == pytest.approx(vec, abs=1e-6)
    assert hidden.id not in {h.id for h in hits}


def test_local_store_read_only_and_missing_files(tmp_path: Path) -> None:
    store = LocalNumpyVectorStore(DIM, collections=("train",))
    store.upsert("train", [VectorItem(id="t1", embedding=unit_vector(14), text="t", lang=Lang.AR)])
    written = store.save(tmp_path / "index")
    frozen = LocalNumpyVectorStore.load(tmp_path / "index", expected_dim=DIM)
    assert frozen.collections() == frozenset({"train"})
    with pytest.raises(StoreError):
        frozen.upsert("train", [VectorItem(id="t2", embedding=unit_vector(15), text="u", lang=Lang.EN)])
    with pytest.raises(StoreError):
        frozen.set_active("train", "t1", False)
    next(p for p in written if p.name == "items.jsonl").unlink()
    with pytest.raises(ArtifactMissing):
        LocalNumpyVectorStore.load(tmp_path / "index", expected_dim=DIM)
    with pytest.raises(ArtifactMissing):
        LocalNumpyVectorStore.load(tmp_path / "absent", expected_dim=DIM)
