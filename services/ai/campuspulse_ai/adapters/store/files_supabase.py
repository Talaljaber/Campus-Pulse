"""SupabaseFileStore: the `FileStore` port over PostgREST (service role). Online only."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, TypeVar

from campuspulse_ai.adapters.store import codec
from campuspulse_ai.adapters.store.codec import Row
from campuspulse_ai.domain.errors import StoreError
from campuspulse_ai.domain.journey import TicketFile, Visibility

if TYPE_CHECKING:
    from campuspulse_ai.adapters.store.rest import RestApi as Client

T = TypeVar("T")


def _call(what: str, fn: Callable[[], T]) -> T:
    try:
        return fn()
    except StoreError:
        raise
    except Exception as exc:  # postgrest.APIError, httpx errors, ...
        raise StoreError(f"files {what} failed: {exc}") from exc


def _to_file(row: Row) -> TicketFile:
    created = codec.parse_dt(row["created_at"])
    assert created is not None
    return TicketFile(
        id=str(row["id"]),
        ticket_id=str(row["ticket_id"]),
        activity_id=str(row["activity_id"]) if row.get("activity_id") else None,
        uploader_alias=row.get("uploader_alias"),
        uploader_role=row["uploader_role"],
        visibility=Visibility(row.get("visibility") or "public"),
        storage_path=row["storage_path"],
        mime=row["mime"],
        size_bytes=int(row["size_bytes"]),
        ext=row["ext"],
        created_at=created,
    )


class SupabaseFileStore:
    def __init__(self, client: Client) -> None:
        self._db = client

    def add_file(self, f: TicketFile) -> TicketFile:
        row: Row = {
            "ticket_id": f.ticket_id,
            "activity_id": f.activity_id,
            "uploader_alias": f.uploader_alias,
            "uploader_role": f.uploader_role,
            "visibility": str(f.visibility),
            "storage_path": f.storage_path,
            "mime": f.mime,
            "size_bytes": f.size_bytes,
            "ext": f.ext,
            "created_at": codec.iso(f.created_at),
        }
        rows: list[Row] = _call("add", lambda: self._db.table("ticket_files").insert(row).execute().data)
        if not rows:
            raise StoreError("files add failed: no row returned")
        return _to_file(rows[0])

    def get_file(self, file_id: str) -> TicketFile | None:
        query = self._db.table("ticket_files").select("*").eq("id", file_id).limit(1)
        rows: list[Row] = _call("get", lambda: query.execute().data)
        return _to_file(rows[0]) if rows else None

    def files_for_ticket(self, ticket_id: str) -> list[TicketFile]:
        rows: list[Row] | None = _call(
            "list",
            lambda: (
                self._db.table("ticket_files")
                .select("*")
                .eq("ticket_id", ticket_id)
                .order("created_at")
                .order("id")
                .execute()
                .data
            ),
        )
        return [_to_file(r) for r in rows or []]

    def attach(self, file_ids: Sequence[str], activity_id: str) -> None:
        if not file_ids:
            return
        ids = list(file_ids)

        def run() -> Any:
            return (
                self._db.table("ticket_files")
                .update({"activity_id": activity_id})
                .in_("id", ids)
                .is_("activity_id", "null")
                .execute()
            )

        _call("attach", run)
