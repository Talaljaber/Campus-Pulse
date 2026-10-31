"""PgVectorStore: the VectorStore port over Supabase pgvector (ARCHITECTURE §3.18, P4.2).

Online only: composition/online.py is the only importer. `supabase` is imported for typing
only, so importing this module never pulls the SDK into an offline process.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypeVar, cast

from campuspulse_ai.domain.errors import ArtifactVersionMismatch, NotFound, StoreError
from campuspulse_ai.domain.values import Lang, MetaValue, VectorHit, VectorItem

if TYPE_CHECKING:
    from supabase import Client

T = TypeVar("T")

# collection -> (table, id column); the schema is supabase/migrations/0005_vectors.sql.
COLLECTIONS: Mapping[str, tuple[str, str]] = {
    "requests": ("request_embeddings", "request_id"),
    "memory": ("memory_examples", "id"),
    "faq": ("faq", "id"),
}
# Filters each collection understands (match_vectors ignores any other key).
FILTER_KEYS: Mapping[str, frozenset[str]] = {
    "requests": frozenset({"building_id", "category", "since"}),
    "memory": frozenset({"active", "lang", "category", "since"}),
    "faq": frozenset({"lang"}),
}


class PgVectorStore:
    """VectorStore over the `match_vectors` / `vector_dim` RPCs and the vector tables.

    Collections: `requests` (request_embeddings), `memory` (memory_examples), `faq`.
    Needs a service-role client: the RPCs and request_embeddings are closed to client roles.

    - `search` returns cosine hits, sim descending, ties broken by id. `filters["with_embedding"]`
      fills `VectorHit.embedding` (LD-14); the other filter keys are listed in FILTER_KEYS.
      `memory` returns active rows only unless `filters["active"]` is given.
    - `upsert` writes rows by id. `requests` items need an existing `requests` row (FK); their
      `text` is not stored (search returns the request's text_norm). `memory`/`faq` ids must
      be UUIDs. Meta keys: requests {lang, category, priority, building_id, room, created_at},
      memory {category, priority, author_id, created_at, active}, faq {answer, source_url, is_demo}.
    - `set_active` works on `memory` only.

    Raises ArtifactVersionMismatch at construction when the database dimension differs from
    `dim`, NotFound from `set_active` on a missing id, and StoreError for everything else
    (unknown collection, bad item, PostgREST/network failure). Never raises SDK exceptions.
    """

    def __init__(self, client: Client, dim: int) -> None:
        self._client = client
        self.dim = dim
        db_dim = store_call("vector_dim", lambda: client.rpc("vector_dim").execute().data)
        if db_dim != dim:
            raise ArtifactVersionMismatch(f"pgvector dimension is {db_dim}, the encoder needs {dim}")

    def upsert(self, collection: str, items: Sequence[VectorItem]) -> None:
        table, id_col = _table(collection)
        if not items:
            return
        rows = [self._row(collection, item) for item in items]
        store_call(
            f"upsert {collection}",
            lambda: (
                self._client.table(table)
                .upsert(rows, on_conflict=id_col, default_to_null=False, returning=_minimal())
                .execute()
            ),
        )

    def search(
        self,
        collection: str,
        query: Sequence[float],
        k: int,
        min_sim: float = 0.0,
        filters: Mapping[str, object] | None = None,
    ) -> list[VectorHit]:
        _table(collection)
        self._check_dim(query)
        params = {
            "p_collection": collection,
            "p_query": [float(x) for x in query],
            "p_k": k,
            "p_min_sim": min_sim,
            "p_filters": _jsonable(filters or {}),
        }
        rows = store_call(
            f"search {collection}", lambda: self._client.rpc("match_vectors", params).execute().data
        )
        return [_hit(row) for row in cast("list[dict[str, Any]]", rows or [])]

    def set_active(self, collection: str, id: str, active: bool) -> None:
        if collection != "memory":
            raise StoreError(f"set_active is only supported on 'memory', not {collection!r}")
        data = store_call(
            "set_active memory",
            lambda: (
                self._client.table("memory_examples").update({"active": active}).eq("id", id).execute().data
            ),
        )
        if not data:
            raise NotFound(f"memory example {id} not found")

    def count(self, collection: str, filters: Mapping[str, object] | None = None) -> int:
        table, id_col = _table(collection)
        f = dict(filters or {})

        def run() -> int | None:
            q = self._client.table(table).select(id_col, count=_exact(), head=True)
            if collection == "memory":
                q = q.eq("active", bool(f.get("active", True)))
            for key in ("building_id", "category", "lang"):
                if key in FILTER_KEYS[collection] and f.get(key) is not None:
                    q = q.eq(key, str(f[key]))
            if "since" in FILTER_KEYS[collection] and f.get("since") is not None:
                q = q.gte("created_at", _jsonable_value(f["since"]))
            return q.execute().count

        return store_call(f"count {collection}", run) or 0

    def _row(self, collection: str, item: VectorItem) -> dict[str, Any]:
        self._check_dim(item.embedding)
        meta = item.meta
        row: dict[str, Any] = {"embedding": [float(x) for x in item.embedding], "lang": str(item.lang)}
        if collection == "requests":
            row["request_id"] = _uuid(item.id)
            keys: tuple[str, ...] = ("category", "priority", "building_id", "room", "created_at")
        elif collection == "memory":
            row["id"] = _uuid(item.id)
            row["text_norm"] = item.text
            row["author_id"] = meta.get("author_id") or None
            keys = ("category", "priority", "created_at", "active")
        else:
            row["id"] = _uuid(item.id)
            row["question"] = item.text
            keys = ("answer", "source_url", "is_demo")
        row.update({key: meta[key] for key in keys if key in meta})
        return row

    def _check_dim(self, vector: Sequence[float]) -> None:
        if len(vector) != self.dim:
            raise StoreError(f"vector has {len(vector)} dimensions, the store expects {self.dim}")


def store_call(what: str, fn: Callable[[], T]) -> T:
    """Run one Supabase call, turning any SDK/network exception into StoreError."""
    try:
        return fn()
    except StoreError:
        raise
    except Exception as exc:  # the SDK raises postgrest.APIError, httpx errors, ...
        raise StoreError(f"pgvector {what} failed: {exc}") from exc


def _table(collection: str) -> tuple[str, str]:
    try:
        return COLLECTIONS[collection]
    except KeyError:
        raise StoreError(f"unknown pgvector collection {collection!r}") from None


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise StoreError(f"pgvector ids must be UUIDs, got {value!r}") from None


def _hit(row: Mapping[str, Any]) -> VectorHit:
    raw = row.get("embedding")
    embedding = tuple(json.loads(raw) if isinstance(raw, str) else raw) if raw is not None else None
    meta: dict[str, MetaValue] = dict(row.get("meta") or {})
    return VectorHit(
        id=str(row["id"]),
        text=row.get("text") or "",
        sim=float(row["sim"]),
        lang=Lang(row["lang"]),
        meta=meta,
        embedding=embedding,
    )


def _jsonable(filters: Mapping[str, object]) -> dict[str, object]:
    return {key: _jsonable_value(value) for key, value in filters.items() if value is not None}


def _jsonable_value(value: object) -> object:
    return value.isoformat() if isinstance(value, datetime) else value


def _minimal() -> Any:
    from postgrest.types import ReturnMethod

    return ReturnMethod.minimal


def _exact() -> Any:
    from postgrest.types import CountMethod

    return CountMethod.exact
