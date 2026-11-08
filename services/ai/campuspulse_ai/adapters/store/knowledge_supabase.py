"""SupabaseKnowledgeStore: the `KnowledgeStore` port over PostgREST (service role, P10.19). Online only.

The table is `knowledge_documents` (supabase/migrations/0020_knowledge.sql); its passages are the
`knowledge` collection of `PgVectorStore` (`knowledge_chunks`, deleted by cascade with the row).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from campuspulse_ai.adapters.store import codec
from campuspulse_ai.adapters.store.codec import Row
from campuspulse_ai.application.use_cases.knowledge_ports import KnowledgeDocument
from campuspulse_ai.domain.errors import StoreError

if TYPE_CHECKING:
    from campuspulse_ai.adapters.store.rest import RestApi as Client

T = TypeVar("T")
TABLE = "knowledge_documents"
COLUMNS = "id,title,filename,office,char_count,chunk_count,uploaded_by,created_at"


def _call(what: str, fn: Callable[[], T]) -> T:
    try:
        return fn()
    except StoreError:
        raise
    except Exception as exc:  # postgrest.APIError, httpx errors, ...
        raise StoreError(f"knowledge {what} failed: {exc}") from exc


def _to_doc(row: Row) -> KnowledgeDocument:
    created = codec.parse_dt(row["created_at"])
    assert created is not None
    return KnowledgeDocument(
        id=str(row["id"]),
        title=str(row["title"]),
        filename=row.get("filename"),
        office=row.get("office"),
        char_count=int(row.get("char_count") or 0),
        chunk_count=int(row.get("chunk_count") or 0),
        uploaded_by=row.get("uploaded_by"),
        created_at=created,
    )


class SupabaseKnowledgeStore:
    def __init__(self, client: Client) -> None:
        self._db = client

    def add(self, doc: KnowledgeDocument) -> None:
        row: Row = {
            "id": doc.id,
            "title": doc.title,
            "filename": doc.filename,
            "office": doc.office,
            "char_count": doc.char_count,
            "chunk_count": doc.chunk_count,
            "uploaded_by": doc.uploaded_by,
            "created_at": codec.iso(doc.created_at),
        }
        _call("add", lambda: self._db.table(TABLE).insert(row).execute())

    def get(self, doc_id: str) -> KnowledgeDocument | None:
        if not codec.is_uuid(doc_id):
            return None
        query = self._db.table(TABLE).select(COLUMNS).eq("id", doc_id).limit(1)
        rows: list[Row] | None = _call("get", lambda: query.execute().data)
        return _to_doc(rows[0]) if rows else None

    def list_all(self) -> list[KnowledgeDocument]:
        rows: list[Row] | None = _call(
            "list",
            lambda: (
                self._db.table(TABLE)
                .select(COLUMNS)
                .order("created_at", desc=True)
                .order("id", desc=True)
                .execute()
                .data
            ),
        )
        return [_to_doc(r) for r in rows or []]

    def delete(self, doc_id: str) -> bool:
        if not codec.is_uuid(doc_id):
            return False
        rows: list[Row] | None = _call(
            "delete", lambda: self._db.table(TABLE).delete().eq("id", doc_id).execute().data
        )
        return bool(rows)
