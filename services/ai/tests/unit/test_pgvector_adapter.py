"""PgVectorStore / PgVectorMemoryStore against a recording fake client (no network, P4.2).

The real-database contract lives in tests/contracts; this pins the RPC/table call shapes,
row mapping and error translation so they are checked in the default CI selection.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from campuspulse_ai.adapters.memory.pgvector_memory import PgVectorMemoryStore
from campuspulse_ai.adapters.vectors.pgvector import PgVectorStore
from campuspulse_ai.domain.entities import MemoryExample
from campuspulse_ai.domain.errors import ArtifactVersionMismatch, NotFound, StoreError
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.ports import MemoryStore, VectorStore
from campuspulse_ai.domain.values import Lang, VectorItem

DIM = 4
ID = "00000000-0000-4000-8000-000000000001"


class Result:
    def __init__(self, data: Any = None, count: int | None = None) -> None:
        self.data, self.count = data, count


class Query:
    def __init__(self, client: FakeClient, name: str) -> None:
        self.client, self.name, self.ops = client, name, []

    def __getattr__(self, op: str) -> Callable[..., Query]:
        def record(*args: Any, **kwargs: Any) -> Query:
            self.ops.append((op, args, kwargs))
            return self

        return record

    def execute(self) -> Result:
        self.client.calls.append((self.name, self.ops))
        if self.client.error is not None:
            raise self.client.error
        return self.client.responses.get(self.name, Result())


class FakeClient:
    def __init__(self, dim: int = DIM) -> None:
        self.calls: list[tuple[str, list[tuple[str, tuple[Any, ...], dict[str, Any]]]]] = []
        self.responses: dict[str, Result] = {"rpc:vector_dim": Result(dim)}
        self.error: Exception | None = None

    def rpc(self, fn: str, params: dict[str, Any] | None = None) -> Query:
        q = Query(self, f"rpc:{fn}")
        q.ops.append(("params", (params,), {}))
        return q

    def table(self, name: str) -> Query:
        return Query(self, name)

    def last(self, name: str) -> list[tuple[str, tuple[Any, ...], dict[str, Any]]]:
        return [ops for n, ops in self.calls if n == name][-1]


def test_constructor_checks_dimension() -> None:
    assert isinstance(PgVectorStore(FakeClient(), DIM), VectorStore)
    with pytest.raises(ArtifactVersionMismatch):
        PgVectorStore(FakeClient(dim=768), DIM)


def test_sdk_errors_become_store_error() -> None:
    client = FakeClient()
    store = PgVectorStore(client, DIM)
    client.error = RuntimeError("APIError 500")
    with pytest.raises(StoreError, match="search memory failed"):
        store.search("memory", (1.0, 0, 0, 0), k=1)


def test_search_sends_rpc_and_parses_hits() -> None:
    client = FakeClient()
    store = PgVectorStore(client, DIM)
    client.responses["rpc:match_vectors"] = Result(
        [
            {
                "id": ID,
                "text": "wifi",
                "lang": "ar",
                "sim": 0.93,
                "meta": {"category": "IT Support"},
                "embedding": "[0.5,0.5,0.5,0.5]",
            },
        ]
    )
    since = datetime(2026, 11, 1, tzinfo=UTC)
    hits = store.search(
        "requests",
        (1, 0, 0, 0),
        k=3,
        min_sim=0.8,
        filters={"building_id": "M", "since": since, "with_embedding": True, "category": None},
    )
    params = client.last("rpc:match_vectors")[0][1][0]
    assert params == {
        "p_collection": "requests",
        "p_query": [1.0, 0.0, 0.0, 0.0],
        "p_k": 3,
        "p_min_sim": 0.8,
        "p_filters": {"building_id": "M", "since": since.isoformat(), "with_embedding": True},
    }
    assert hits[0].id == ID and hits[0].lang == Lang.AR and hits[0].sim == 0.93
    assert hits[0].embedding == (0.5, 0.5, 0.5, 0.5)
    assert hits[0].meta == {"category": "IT Support"}


def test_unknown_collection_and_bad_input_raise_store_error() -> None:
    store = PgVectorStore(FakeClient(), DIM)
    with pytest.raises(StoreError):
        store.search("train", (1, 0, 0, 0), k=1)
    with pytest.raises(StoreError):
        store.upsert("memory", [VectorItem(id="not-a-uuid", embedding=(1, 0, 0, 0), text="t", lang=Lang.EN)])
    with pytest.raises(StoreError):
        store.upsert("memory", [VectorItem(id=ID, embedding=(1, 0), text="t", lang=Lang.EN)])
    with pytest.raises(StoreError):
        store.set_active("faq", ID, False)


def test_upsert_maps_items_to_table_rows() -> None:
    client = FakeClient()
    store = PgVectorStore(client, DIM)
    store.upsert(
        "faq",
        [
            VectorItem(
                id=ID,
                embedding=(1, 0, 0, 0),
                text="q?",
                lang=Lang.EN,
                meta={"answer": "a.", "is_demo": True, "ignored": 1},
            )
        ],
    )
    op, args, kwargs = client.last("faq")[0]
    assert op == "upsert" and kwargs["on_conflict"] == "id" and kwargs["default_to_null"] is False
    assert args[0] == [
        {
            "id": ID,
            "embedding": [1.0, 0.0, 0.0, 0.0],
            "lang": "en",
            "question": "q?",
            "answer": "a.",
            "is_demo": True,
        }
    ]
    store.upsert(
        "requests",
        [
            VectorItem(
                id=ID,
                embedding=(0, 1, 0, 0),
                text="",
                lang=Lang.ARABIZI,
                meta={"building_id": "M", "category": "IT Support"},
            )
        ],
    )
    row = client.last("request_embeddings")[0][1][0][0]
    assert row == {
        "request_id": ID,
        "embedding": [0.0, 1.0, 0.0, 0.0],
        "lang": "arabizi",
        "building_id": "M",
        "category": "IT Support",
    }


def test_set_active_missing_row_raises_not_found() -> None:
    client = FakeClient()
    store = PgVectorStore(client, DIM)
    client.responses["memory_examples"] = Result([])
    with pytest.raises(NotFound):
        store.set_active("memory", ID, False)
    client.responses["memory_examples"] = Result([{"id": ID}])
    store.set_active("memory", ID, False)
    assert ("update", ({"active": False},), {}) in client.last("memory_examples")


def test_memory_store_add_and_neighbors() -> None:
    client = FakeClient()
    memory = PgVectorMemoryStore(PgVectorStore(client, DIM), client)
    assert isinstance(memory, MemoryStore)
    created = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    saved = memory.add(
        MemoryExample(
            id="",
            text_norm="bus late",
            lang=Lang.EN,
            embedding=(0, 0, 1, 0),
            category=Category.TRANSPORTATION,
            priority=Priority.MEDIUM,
            author_id="",
            created_at=created,
        )
    )
    row = client.last("memory_examples")[0][1][0][0]
    assert saved.id and row["id"] == saved.id and row["author_id"] is None and row["active"] is True
    assert row["created_at"] == created.isoformat()
    client.responses["rpc:match_vectors"] = Result(
        [
            {
                "id": saved.id,
                "text": "bus late",
                "lang": "en",
                "sim": 0.97,
                "embedding": None,
                "meta": {
                    "category": "Transportation",
                    "priority": "medium",
                    "created_at": created.isoformat(),
                },
            },
        ]
    )
    [hit] = memory.neighbors((0, 0, 1, 0), k=5, min_sim=0.8)
    assert (hit.category, hit.priority, hit.source, hit.created_at) == (
        Category.TRANSPORTATION,
        Priority.MEDIUM,
        "memory",
        created,
    )
    assert client.last("rpc:match_vectors")[0][1][0]["p_filters"] == {"active": True}


def test_memory_store_stats_and_active_parse_rows() -> None:
    client = FakeClient()
    memory = PgVectorMemoryStore(PgVectorStore(client, DIM), client)
    client.responses["memory_examples"] = Result(
        [
            {
                "id": ID,
                "text_norm": "t",
                "lang": "ar",
                "embedding": "[1,0,0,0]",
                "category": "Finance",
                "priority": "low",
                "author_id": None,
                "created_at": "2026-11-02T09:00:00+00:00",
                "active": True,
            },
            {
                "id": ID.replace("1", "2"),
                "text_norm": "u",
                "lang": "en",
                "embedding": "[0,1,0,0]",
                "category": "Finance",
                "priority": "low",
                "author_id": None,
                "created_at": "2026-11-03T09:00:00+00:00",
                "active": False,
            },
        ]
    )
    stats = memory.stats()
    assert (stats.total, stats.active, dict(stats.by_category)) == (2, 1, {"Finance": 1})
    assert stats.last_added_at == datetime(2026, 11, 3, 9, tzinfo=UTC)
    first = memory.active()[0]
    assert first.embedding == (1.0, 0.0, 0.0, 0.0) and first.author_id == "" and first.lang == Lang.AR
