"""SupabaseAnnouncementStore: the AnnouncementStore port over PostgREST, service role (P9.5). Online only."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from campuspulse_ai.adapters.store.codec import Row, iso, parse_dt
from campuspulse_ai.adapters.store.inmemory import new_id
from campuspulse_ai.adapters.vectors.pgvector import store_call
from campuspulse_ai.domain.announcements import Announcement, AnnouncementKind
from campuspulse_ai.domain.errors import NotFound

if TYPE_CHECKING:
    from campuspulse_ai.adapters.store.rest import RestApi as Client

TABLE = "announcements"


class SupabaseAnnouncementStore:
    """`announcements` rows (migration 0013). Same semantics as `InMemoryAnnouncementStore`; every
    PostgREST or network failure raises `StoreError`, a missing row `NotFound`."""

    def __init__(self, client: Client) -> None:
        self._db = client

    def save_announcement(self, a: Announcement) -> Announcement:
        saved = dataclasses.replace(a, id=new_id(a.id))
        row: Row = {
            "id": saved.id,
            "office": saved.office,
            "kind": saved.kind,
            "title": saved.title,
            "body": saved.body,
            "starts_at": iso(saved.starts_at),
            "ends_at": iso(saved.ends_at),
            "archived_at": iso(saved.archived_at),
            "created_by": saved.created_by,
        }
        store_call(
            "save announcements",
            lambda: self._db.table(TABLE).upsert(row, on_conflict="id", default_to_null=False).execute(),
        )
        return saved

    def get_announcement(self, id: str) -> Announcement:
        rows = self._rows(
            "get announcements", lambda: self._db.table(TABLE).select("*").eq("id", id).limit(1).execute()
        )
        if not rows:
            raise NotFound(f"announcements {id} not found")
        return _to_announcement(rows[0])

    def live_announcements(self, now: datetime, limit: int = 20) -> list[Announcement]:
        stamp = iso(now)
        rows = self._rows(
            "list announcements",
            lambda: (
                self._db.table(TABLE)
                .select("*")
                .is_("archived_at", "null")
                .lte("starts_at", stamp)
                .or_(f"ends_at.is.null,ends_at.gt.{stamp}")
                .order("starts_at", desc=True)
                .limit(limit)
                .execute()
            ),
        )
        return [_to_announcement(r) for r in rows]

    @staticmethod
    def _rows(what: str, fn: Any) -> list[Row]:
        return cast(list[Row], store_call(what, lambda: fn().data) or [])


def _to_announcement(row: Row) -> Announcement:
    starts_at = parse_dt(row["starts_at"])
    assert starts_at is not None  # not null in the table
    return Announcement(
        id=str(row["id"]),
        office=row.get("office"),
        kind=cast(AnnouncementKind, row["kind"]),
        title=row["title"],
        body=row["body"],
        starts_at=starts_at,
        ends_at=parse_dt(row.get("ends_at")),
        archived_at=parse_dt(row.get("archived_at")),
        created_by=row.get("created_by"),
        created_at=parse_dt(row.get("created_at")),
    )
