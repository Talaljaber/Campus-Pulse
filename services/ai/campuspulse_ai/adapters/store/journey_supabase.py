"""SupabaseJourneyStore: the JourneyStore port over Supabase/PostgREST (service role). Online only.

Same semantics as `InMemoryJourneyStore` (tests/contracts/test_journey_store_contract.py). Every
PostgREST or network failure raises `StoreError`.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypeVar

from campuspulse_ai.adapters.store import codec
from campuspulse_ai.adapters.store.codec import Row
from campuspulse_ai.domain.errors import StoreError
from campuspulse_ai.domain.journey import (
    ActivityKind,
    Contact,
    HintMatch,
    TicketActivity,
    TicketHint,
    Visibility,
)
from campuspulse_ai.domain.ports import Clock

if TYPE_CHECKING:
    from campuspulse_ai.adapters.store.rest import RestApi as Client

T = TypeVar("T")
OPEN_STATUSES = ["new", "in_progress"]


def _call(what: str, fn: Callable[[], T]) -> T:
    try:
        return fn()
    except StoreError:
        raise
    except Exception as exc:  # postgrest.APIError, httpx errors, ...
        raise StoreError(f"journey {what} failed: {exc}") from exc


def _activity_row(a: TicketActivity) -> Row:
    row: Row = {
        "ticket_id": a.ticket_id,
        "kind": str(a.kind),
        "visibility": str(a.visibility),
        "actor_role": a.actor_role,
        "actor_alias": a.actor_alias,
        "actor_office": a.actor_office,
        "body": a.body,
        "from_status": a.from_status,
        "to_status": a.to_status,
        "from_office": a.from_office,
        "to_office": a.to_office,
        "from_priority": a.from_priority,
        "to_priority": a.to_priority,
        "created_at": codec.iso(a.created_at),
    }
    if a.id:
        row["id"] = a.id
    return row


def _to_activity(row: Row) -> TicketActivity:
    created = codec.parse_dt(row["created_at"])
    assert created is not None
    return TicketActivity(
        id=str(row["id"]),
        ticket_id=str(row["ticket_id"]),
        kind=ActivityKind(row["kind"]),
        visibility=Visibility(row.get("visibility") or "public"),
        actor_role=row["actor_role"],
        actor_alias=row.get("actor_alias"),
        actor_office=row.get("actor_office"),
        body=row.get("body") or "",
        from_status=row.get("from_status"),
        to_status=row.get("to_status"),
        from_office=row.get("from_office"),
        to_office=row.get("to_office"),
        from_priority=row.get("from_priority"),
        to_priority=row.get("to_priority"),
        created_at=created,
    )


def _vector(embedding: Sequence[float] | None) -> list[float] | None:
    return None if embedding is None else [float(x) for x in embedding]


class SupabaseJourneyStore:
    def __init__(self, client: Client, clock: Clock) -> None:
        self._db = client
        self._clock = clock

    def add_activity(self, a: TicketActivity) -> TicketActivity:
        rows = self._rows(
            "add activity", lambda: self._db.table("ticket_activity").insert(_activity_row(a)).execute()
        )
        if not rows:
            raise StoreError("journey add activity failed: no row returned")
        return _to_activity(rows[0])

    def activity_for(self, ticket_id: str) -> list[TicketActivity]:
        rows = self._rows(
            "activity",
            lambda: (
                self._db.table("ticket_activity")
                .select("*")
                .eq("ticket_id", ticket_id)
                .order("created_at")
                .order("id")
                .execute()
            ),
        )
        return [_to_activity(r) for r in rows]

    def add_hint(self, h: TicketHint) -> TicketHint:
        row: Row = {
            "ticket_id": h.ticket_id,
            "kind": h.kind,
            "request_text": h.request_text,
            "lang": h.lang,
            "embedding": _vector(h.embedding),
            "model_category": h.model_category,
            "model_priority": h.model_priority,
            "corrected_category": h.corrected_category,
            "corrected_priority": h.corrected_priority,
            "note": h.note,
            "author_alias": h.author_alias,
            "author_role": h.author_role,
        }
        if h.id:
            row["id"] = h.id
        rows = self._rows("add hint", lambda: self._db.table("ticket_hints").insert(row).execute())
        if not rows:
            raise StoreError("journey add hint failed: no row returned")
        return dataclasses.replace(
            h, id=str(rows[0]["id"]), created_at=codec.parse_dt(rows[0].get("created_at"))
        )

    def nearest_hints(self, embedding: Sequence[float], k: int, min_sim: float) -> list[HintMatch]:
        params: dict[Any, Any] = {"p_query": _vector(embedding), "p_k": k, "p_min_sim": min_sim}
        rows = self._rows("nearest hints", lambda: self._db.rpc("match_ticket_hints", params).execute())
        return [
            HintMatch(
                hint_id=str(r["id"]),
                request_text=r["request_text"],
                corrected_category=r["corrected_category"],
                corrected_priority=r["corrected_priority"],
                model_category=r.get("model_category"),
                model_priority=r.get("model_priority"),
                sim=float(r["sim"]),
            )
            for r in rows
        ]

    def contact_for_alias(self, alias: str) -> Contact | None:
        wanted = alias.strip()
        if not wanted:
            return None
        rows = self._rows(
            "contact",
            lambda: self._db.table("profiles").select("*").eq("alias", wanted).limit(1).execute(),
        )
        if not rows:
            return None
        r = rows[0]
        return Contact(
            alias=wanted,
            role=str(r.get("role") or "student"),
            office=r.get("office") or None,
            display_name=str(r.get("display_name") or ""),
            demo_inbox=r.get("demo_inbox") or None,
        )

    def claim_reminder(self, ticket_id: str, level: int, now: datetime) -> bool:
        values: Row = {"reminder_count": level, "reminder_sent_at": codec.iso(now)}
        rows = self._rows(
            "claim reminder",
            lambda: (
                self._db.table("tickets")
                .update(values)
                .eq("id", ticket_id)
                .eq("reminder_count", level - 1)
                .in_("status", OPEN_STATUSES)
                .lt("sla_due_at", codec.iso(now))
                .execute()
            ),
        )
        return bool(rows)

    def _rows(self, what: str, fn: Callable[[], Any]) -> list[Row]:
        data = _call(what, lambda: fn().data) or []
        if isinstance(data, str):  # an RPC that answers a JSON string
            data = json.loads(data)
        rows: list[Row] = list(data)
        return rows
