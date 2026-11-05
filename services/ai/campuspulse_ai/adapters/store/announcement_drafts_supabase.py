"""Service-role store for staff announcement drafts; publication uses an atomic SQL function."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, cast

from campuspulse_ai.adapters.vectors.pgvector import store_call
from campuspulse_ai.application.use_cases.announcement_drafts import AnnouncementDraft
from campuspulse_ai.domain.errors import NotFound

if TYPE_CHECKING:
    from campuspulse_ai.adapters.store.rest import RestApi


def _draft(row: dict[str, Any]) -> AnnouncementDraft:
    return AnnouncementDraft(
        id=str(row["id"]),
        incident_id=str(row["incident_id"]),
        office=str(row["office"]),
        title=str(row["title"]),
        body=str(row["body"]),
        status=cast(Literal["pending", "published", "dismissed"], row["status"]),
        version=int(row["version"]),
        published_announcement_id=str(row["published_announcement_id"])
        if row.get("published_announcement_id")
        else None,
    )


class SupabaseDraftStore:
    def __init__(self, db: RestApi) -> None:
        self._db = db

    def list_for_office(self, office: str | None) -> list[AnnouncementDraft]:
        query = self._db.table("announcement_drafts").select("*")
        if office is not None:
            query = query.eq("office", office)
        rows = store_call(
            "list announcement drafts", lambda: query.order("created_at", desc=True).execute().data
        )
        return [_draft(row) for row in rows or []]

    def get(self, draft_id: str) -> AnnouncementDraft:
        rows = store_call(
            "get announcement draft",
            lambda: (
                self._db.table("announcement_drafts").select("*").eq("id", draft_id).limit(1).execute().data
            ),
        )
        if not rows:
            raise NotFound(f"announcement draft {draft_id} not found")
        return _draft(rows[0])

    def suggest(self, incident_id: str, office: str, title: str, body: str) -> AnnouncementDraft:
        result = store_call(
            "suggest announcement",
            lambda: (
                self._db.rpc(
                    "cp_suggest_announcement",
                    {
                        "p_incident_id": incident_id,
                        "p_office": office,
                        "p_title": title,
                        "p_body": body,
                    },
                )
                .execute()
                .data
            ),
        )
        return _draft(result)

    def change(
        self, draft_id: str, version: int, title: str, body: str, dismiss: bool
    ) -> AnnouncementDraft | None:
        result = store_call(
            "change announcement draft",
            lambda: (
                self._db.rpc(
                    "cp_change_announcement_draft",
                    {
                        "p_id": draft_id,
                        "p_version": version,
                        "p_title": title,
                        "p_body": body,
                        "p_dismiss": dismiss,
                    },
                )
                .execute()
                .data
            ),
        )
        return _draft(result) if result else None

    def publish(self, draft_id: str, version: int, author_id: str) -> AnnouncementDraft | None:
        result = store_call(
            "publish announcement draft",
            lambda: (
                self._db.rpc(
                    "cp_publish_announcement_draft",
                    {
                        "p_id": draft_id,
                        "p_version": version,
                        "p_author": author_id,
                    },
                )
                .execute()
                .data
            ),
        )
        return _draft(result) if result else None
