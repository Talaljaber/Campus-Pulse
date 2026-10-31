"""PgVectorMemoryStore: live-learning memory in Supabase (ARCHITECTURE §3.18, P4.2).

Staff corrections become `memory_examples` rows; kNN neighbours come from the `memory`
collection of PgVectorStore. Online only, like PgVectorStore.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from campuspulse_ai.adapters.vectors.pgvector import PgVectorStore, store_call
from campuspulse_ai.domain.entities import MemoryExample
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import Lang, MemoryStats, Neighbor, VectorItem

if TYPE_CHECKING:
    from campuspulse_ai.adapters.store.rest import RestApi as Client

COLLECTION = "memory"
TABLE = "memory_examples"
PAGE = 1000  # PostgREST's default max-rows; reads page through larger tables


class PgVectorMemoryStore:
    """MemoryStore over the `memory` collection (table memory_examples).

    - `add` upserts the example (a fresh UUID when `ex.id` is empty) and returns it with its id.
      `author_id` must be an auth.users id, or "" for none (stored as NULL).
    - `active(since)` lists active examples, oldest first (ties by id).
    - `deactivate` hides an example from `active` and `neighbors`; NotFound if the id is absent.
    - `neighbors` is a kNN search over active examples (source="memory").
    - `stats` counts total/active rows, active rows per category, and the newest created_at.

    Needs a service-role client. Raises StoreError (NotFound for a missing id); never SDK errors.
    """

    def __init__(self, vectors: PgVectorStore, client: Client) -> None:
        self._vectors = vectors
        self._client = client

    def add(self, ex: MemoryExample) -> MemoryExample:
        saved = ex if ex.id else dataclasses.replace(ex, id=str(uuid.uuid4()))
        item = VectorItem(
            id=saved.id,
            embedding=tuple(saved.embedding),
            text=saved.text_norm,
            lang=saved.lang,
            meta={
                "category": str(saved.category),
                "priority": str(saved.priority),
                "author_id": saved.author_id or None,
                "created_at": saved.created_at.isoformat(),
                "active": saved.active,
            },
        )
        self._vectors.upsert(COLLECTION, [item])
        return saved

    def active(self, since: datetime | None = None) -> list[MemoryExample]:
        columns = "id,text_norm,lang,embedding,category,priority,author_id,created_at,active"

        def page(start: int) -> list[dict[str, Any]]:
            q = self._client.table(TABLE).select(columns).eq("active", True)
            if since is not None:
                q = q.gte("created_at", since.isoformat())
            return cast(
                "list[dict[str, Any]]",
                q.order("created_at").order("id").range(start, start + PAGE - 1).execute().data,
            )

        return [_example(row) for row in self._all("active", page)]

    def deactivate(self, id: str) -> None:
        self._vectors.set_active(COLLECTION, id, False)

    def stats(self) -> MemoryStats:
        def page(start: int) -> list[dict[str, Any]]:
            q = self._client.table(TABLE).select("id,category,active,created_at")
            return cast("list[dict[str, Any]]", q.order("id").range(start, start + PAGE - 1).execute().data)

        rows = self._all("stats", page)
        active = [row for row in rows if row["active"]]
        last = max((datetime.fromisoformat(row["created_at"]) for row in rows), default=None)
        return MemoryStats(
            active=len(active),
            total=len(rows),
            by_category=dict(Counter(row["category"] for row in active)),
            last_added_at=last,
        )

    def neighbors(self, embedding: Sequence[float], k: int, min_sim: float) -> list[Neighbor]:
        hits = self._vectors.search(COLLECTION, embedding, k, min_sim, {"active": True})
        return [
            Neighbor(
                text=hit.text,
                category=Category(str(hit.meta["category"])),
                priority=Priority(str(hit.meta["priority"])),
                sim=hit.sim,
                source="memory",
                created_at=datetime.fromisoformat(str(hit.meta["created_at"]))
                if hit.meta.get("created_at")
                else None,
            )
            for hit in hits
        ]

    def _all(self, what: str, page: Callable[[int], list[dict[str, Any]]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        while True:
            batch = store_call(f"memory {what}", lambda: page(len(rows)))
            rows.extend(batch or [])
            if len(batch or []) < PAGE:
                return rows


def _example(row: dict[str, Any]) -> MemoryExample:
    raw = row["embedding"]
    return MemoryExample(
        id=str(row["id"]),
        text_norm=row["text_norm"],
        lang=Lang(row["lang"]),
        embedding=tuple(json.loads(raw) if isinstance(raw, str) else raw),
        category=Category(row["category"]),
        priority=Priority(row["priority"]),
        author_id=row.get("author_id") or "",
        created_at=datetime.fromisoformat(row["created_at"]),
        active=bool(row["active"]),
    )
