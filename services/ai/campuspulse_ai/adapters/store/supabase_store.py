"""SupabaseRepository: the Repository port over Supabase/PostgREST (P4.3). Online only.

Uses the service-role client (bypasses RLS) and the row mapping in adapters/store/codec.py, the
same rows InMemoryRepository keeps. `supabase` is imported for typing only.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from campuspulse_ai.adapters.store import codec
from campuspulse_ai.adapters.store.codec import Row
from campuspulse_ai.adapters.store.inmemory import (
    OPEN_TICKET_STATUSES,
    advisor_contact,
    new_id,
    router_stats_from_rows,
)
from campuspulse_ai.adapters.vectors.pgvector import store_call
from campuspulse_ai.application.use_cases.ports import AdvisorContact
from campuspulse_ai.domain.entities import (
    Case,
    Clarification,
    Incident,
    OutboxMessage,
    Prediction,
    Request,
    ReviewItem,
    Scorecard,
    Ticket,
)
from campuspulse_ai.domain.errors import NotFound
from campuspulse_ai.domain.labels import Category
from campuspulse_ai.domain.ports import Clock
from campuspulse_ai.domain.values import Advisor, RequestStatus, RouterStats, Slot, StudentSignals, TicketLink

if TYPE_CHECKING:
    from campuspulse_ai.adapters.store.rest import RestApi as Client

PAGE = 1000  # PostgREST default max-rows


class SupabaseRepository:
    """Repository port over the tables of supabase/migrations (service role).

    Semantics match InMemoryRepository exactly (tests/contracts/test_repository_contract.py):
    - `save_*` upsert by id (an empty id gets a fresh UUID); the saved entity is returned.
    - A missing row raises NotFound from `get_request`, `get_ticket`, `latest_prediction`,
      `ticket_by_link`, `set_request_status` and `resolve_review`.
    - Foreign-key/unique violations and every PostgREST or network failure raise StoreError.
    - `claim_slot` is a conditional update (`where booked_by is null`): True only for the
      caller that booked it.
    - `bump_student_signals` is atomic (RPC `bump_student_signals`, migration 0007).

    Datetimes are written as ISO-8601 UTC. `clock` stamps events, notifications, review
    resolution and slot booking; created_at columns use the database default.
    """

    def __init__(self, client: Client, clock: Clock) -> None:
        self._db = client
        self._clock = clock

    # ------------------------------------------------------------------ requests

    def save_request(self, r: Request) -> Request:
        saved = dataclasses.replace(r, id=new_id(r.id))
        self._upsert("requests", codec.request_row(saved))
        return saved

    def get_request(self, id: str) -> Request:
        return codec.to_request(self._one("requests", "id", id))

    def set_request_status(self, id: str, status: RequestStatus) -> None:
        self._update("requests", {"status": str(status)}, "id", id)

    # ------------------------------------------------------------------ predictions / clarifications / review

    def save_prediction(self, p: Prediction) -> Prediction:
        saved = dataclasses.replace(p, id=new_id(p.id))
        self._upsert("predictions", codec.prediction_row(saved))
        return saved

    def latest_prediction(self, request_id: str) -> Prediction:
        rows = self._rows(
            "latest_prediction",
            lambda: (
                self._db.table("predictions")
                .select("*")
                .eq("request_id", request_id)
                .order("created_at", desc=True)
                .order("id", desc=True)
                .limit(1)
                .execute()
            ),
        )
        if not rows:
            raise NotFound(f"no prediction for request {request_id}")
        return codec.to_prediction(rows[0])

    def save_clarification(self, c: Clarification) -> Clarification:
        saved = dataclasses.replace(c, id=new_id(c.id))
        self._upsert("clarifications", codec.clarification_row(saved))
        return saved

    def clarifications_for(self, request_id: str) -> list[Clarification]:
        rows = self._rows(
            "clarifications_for",
            lambda: (
                self._db.table("clarifications")
                .select("*")
                .eq("request_id", request_id)
                .order("asked_at")
                .order("id")
                .execute()
            ),
        )
        return [codec.to_clarification(r) for r in rows]

    def enqueue_review(self, item: ReviewItem) -> ReviewItem:
        saved = dataclasses.replace(item, id=new_id(item.id))
        self._upsert("review_queue", codec.review_row(saved))
        return saved

    def resolve_review(self, item: ReviewItem) -> None:
        row = codec.review_row(item)
        update = {
            k: row[k] for k in ("status", "reviewer_id", "corrected_category", "corrected_priority", "note")
        }
        update["resolved_at"] = codec.iso(self._clock.now())
        self._update("review_queue", update, "id", item.id)

    # ------------------------------------------------------------------ tickets / incidents

    def save_ticket(self, t: Ticket) -> Ticket:
        saved = dataclasses.replace(t, id=new_id(t.id))
        self._upsert("tickets", codec.ticket_row(saved))
        links = [dataclasses.replace(link, ticket_id=saved.id) for link in saved.links]
        for link in links:
            self.save_ticket_link(link)
        saved.links = links
        return saved

    def get_ticket(self, id: str) -> Ticket:
        return self._tickets([self._one("tickets", "id", id)])[0]

    def overdue_open_tickets(self, now: datetime) -> list[Ticket]:
        rows = self._rows(
            "overdue_open_tickets",
            lambda: (
                self._db.table("tickets")
                .select("*")
                .in_("status", list(OPEN_TICKET_STATUSES))
                .lt("sla_due_at", codec.iso(now))
                .order("sla_due_at")
                .order("id")
                .execute()
            ),
        )
        return self._tickets(rows)

    def save_ticket_link(self, link: TicketLink) -> None:
        self._upsert("ticket_links", codec.link_row(link), on_conflict="ticket_id,sink")

    def save_incident(self, i: Incident) -> Incident:
        saved = dataclasses.replace(i, id=new_id(i.id))
        self._upsert("incidents", codec.incident_row(saved))
        if saved.member_ticket_ids:
            store_call(
                "save_incident members",
                lambda: (
                    self._db.table("tickets")
                    .update({"incident_id": saved.id})
                    .in_("id", list(saved.member_ticket_ids))
                    .execute()
                ),
            )
        return self._incidents([self._one("incidents", "id", saved.id)])[0]

    def open_incidents(
        self, building: str | None, category: Category | None, since: datetime
    ) -> list[Incident]:
        def run() -> Any:
            q = self._db.table("incidents").select("*").eq("status", "open")
            q = q.eq("building_id", building) if building is not None else q.is_("building_id", "null")
            if category is not None:
                q = q.eq("category", str(category))
            return q.gte("opened_at", codec.iso(since)).order("opened_at").order("id").execute()

        return self._incidents(self._rows("open_incidents", run))

    def incident_members(self, incident_id: str) -> list[tuple[Ticket, Request]]:
        tickets = self._tickets(self._member_rows([incident_id]))
        if not tickets:
            return []
        request_rows = self._rows(
            "incident_members requests",
            lambda: (
                self._db.table("requests").select("*").in_("id", [t.request_id for t in tickets]).execute()
            ),
        )
        requests = {str(r["id"]): codec.to_request(r) for r in request_rows}
        return [(t, requests[t.request_id]) for t in tickets]

    def ticket_by_link(self, sink: str, external_id: str) -> Ticket:
        rows = self._rows(
            "ticket_by_link",
            lambda: (
                self._db.table("ticket_links")
                .select("ticket_id")
                .eq("sink", sink)
                .eq("external_id", external_id)
                .limit(1)
                .execute()
            ),
        )
        if not rows:
            raise NotFound(f"no ticket linked to {sink}:{external_id}")
        return self.get_ticket(str(rows[0]["ticket_id"]))

    # ------------------------------------------------------------------ LifecycleReads (P3.11, P4.10)

    def get_prediction(self, id: str) -> Prediction:
        return codec.to_prediction(self._one("predictions", "id", id))

    def open_review_for(self, prediction_id: str) -> ReviewItem | None:
        rows = self._rows(
            "open_review_for",
            lambda: (
                self._db.table("review_queue")
                .select("*")
                .eq("prediction_id", prediction_id)
                .eq("status", "open")
                .order("created_at")
                .order("id")
                .limit(1)
                .execute()
            ),
        )
        return codec.to_review_item(rows[0]) if rows else None

    def tickets_for_requests(self, request_ids: Sequence[str]) -> list[Ticket]:
        ids = list(dict.fromkeys(request_ids))
        if not ids:
            return []
        rows = self._rows(
            "tickets_for_requests",
            lambda: (
                self._db.table("tickets")
                .select("*")
                .in_("request_id", ids)
                .order("created_at")
                .order("id")
                .execute()
            ),
        )
        return self._tickets(rows)

    def get_incident(self, id: str) -> Incident:
        return self._incidents([self._one("incidents", "id", id)])[0]

    def list_incidents(self, *, open_only: bool, limit: int) -> list[Incident]:
        def run() -> Any:
            q = self._db.table("incidents").select("*")
            if open_only:
                q = q.eq("status", "open")
            return q.order("opened_at", desc=True).order("id", desc=True).limit(limit).execute()

        return self._incidents(self._rows("list_incidents", run))

    def get_review(self, id: str) -> ReviewItem:
        return codec.to_review_item(self._one("review_queue", "id", id))

    def list_reviews(self, *, status: str | None, office: str | None, limit: int) -> list[ReviewItem]:
        def run() -> Any:
            q = self._db.table("review_queue").select("*")
            if status is not None:
                q = q.eq("status", status)
            if office is not None:
                q = q.eq("office", office)
            return q.order("created_at", desc=True).order("id", desc=True).limit(limit).execute()

        return [codec.to_review_item(r) for r in self._rows("list_reviews", run)]

    def predictions_by_ids(self, ids: Sequence[str]) -> list[Prediction]:
        wanted = list(dict.fromkeys(ids))
        if not wanted:
            return []
        rows = self._rows(
            "predictions_by_ids",
            lambda: self._db.table("predictions").select("*").in_("id", wanted).execute(),
        )
        return [codec.to_prediction(r) for r in rows]

    def requests_by_ids(self, ids: Sequence[str]) -> list[Request]:
        wanted = list(dict.fromkeys(ids))
        if not wanted:
            return []
        rows = self._rows(
            "requests_by_ids", lambda: self._db.table("requests").select("*").in_("id", wanted).execute()
        )
        return [codec.to_request(r) for r in rows]

    # ------------------------------------------------------------------ AdvisorDirectory (UD-13, DB 0012)

    def advisor_of(self, student_alias: str) -> AdvisorContact | None:
        alias = student_alias.strip()
        if not alias:
            return None
        students = self._rows(
            "advisor_of profile",
            lambda: self._db.table("profiles").select("advisor_id").eq("alias", alias).limit(1).execute(),
        )
        advisor_id = students[0].get("advisor_id") if students else None
        if not advisor_id:
            return None
        advisors = self._rows(
            "advisor_of advisor",
            lambda: (
                self._db.table("advisors")
                .select("id,fictional_name,demo_email,profile_id")
                .eq("id", advisor_id)
                .limit(1)
                .execute()
            ),
        )
        profile_id = advisors[0].get("profile_id") if advisors else None
        if not profile_id:
            return None
        logins = self._rows(
            "advisor_of login",
            lambda: (
                self._db.table("profiles").select("id,alias,office").eq("id", profile_id).limit(1).execute()
            ),
        )
        return advisor_contact(advisors[0], logins[0]) if logins else None

    def profile_id_of(self, alias: str) -> str | None:
        wanted = alias.strip()
        if not wanted:
            return None
        rows = self._rows(
            "profile_id_of",
            lambda: self._db.table("profiles").select("id").eq("alias", wanted).limit(1).execute(),
        )
        return str(rows[0]["id"]) if rows else None

    def mark_simulated(self, request_id: str) -> None:
        self._update("requests", {"simulated": True}, "id", request_id)

    def simulated(self, request_ids: Sequence[str]) -> set[str]:
        ids = list(dict.fromkeys(request_ids))
        if not ids:
            return set()
        rows = self._rows(
            "simulated",
            lambda: self._db.table("requests").select("id").in_("id", ids).eq("simulated", True).execute(),
        )
        return {str(r["id"]) for r in rows}

    # ------------------------------------------------------------------ outbox / signals / audit

    def save_outbox(self, m: OutboxMessage) -> OutboxMessage:
        saved = dataclasses.replace(m, id=new_id(m.id))
        self._upsert("outbox", codec.outbox_row(saved))
        return saved

    def bump_student_signals(
        self, alias: str, claimed_urgent: bool, was_high: bool, injection: bool
    ) -> StudentSignals:
        params = {
            "p_alias": alias,
            "p_claimed_urgent": claimed_urgent,
            "p_was_high": was_high,
            "p_injection": injection,
        }
        data = store_call(
            "bump_student_signals", lambda: self._db.rpc("bump_student_signals", params).execute().data
        )
        row = data[0] if isinstance(data, list) else data
        return codec.to_signals(cast(Row, row))

    def append_event(self, actor: str, action: str, entity: str, payload: Mapping[str, object]) -> None:
        row = {
            "actor": actor,
            "action": action,
            "entity": entity,
            "payload": codec.jsonify(payload),
            "at": codec.iso(self._clock.now()),
        }
        self._insert("events", row)

    def save_redteam_run(self, scorecard: Scorecard) -> str:
        run_id = scorecard.run_id if codec.is_uuid(scorecard.run_id) else str(uuid.uuid4())
        self._upsert(
            "redteam_runs",
            {
                "id": run_id,
                "scorecard": codec.scorecard_json(scorecard, run_id),
                "created_at": codec.iso(scorecard.created_at),
            },
        )
        return run_id

    def redteam_history(self, limit: int = 20) -> list[Scorecard]:
        rows = self._rows(
            "redteam_history",
            lambda: (
                self._db.table("redteam_runs")
                .select("scorecard, created_at")
                .order("created_at", desc=True)
                .order("id", desc=True)
                .limit(limit)
                .execute()
            ),
        )
        return [codec.to_scorecard(r["scorecard"], r.get("created_at")) for r in rows]

    def save_notification(self, alias: str, kind: str, payload: Mapping[str, object]) -> None:
        row = {
            "alias": alias,
            "kind": kind,
            "payload": codec.jsonify(payload),
            "created_at": codec.iso(self._clock.now()),
        }
        self._insert("notifications", row)

    # ------------------------------------------------------------------ advisors / slots / cases

    def free_slots(self, advisor_ids: Sequence[str], window: tuple[datetime, datetime]) -> list[Slot]:
        if not advisor_ids:
            return []
        rows = self._rows(
            "free_slots",
            lambda: (
                self._db.table("advisor_slots")
                .select("id,advisor_id,starts_at,ends_at")
                .in_("advisor_id", list(advisor_ids))
                .is_("booked_by", "null")
                .gte("starts_at", codec.iso(window[0]))
                .lte("ends_at", codec.iso(window[1]))
                .order("starts_at")
                .order("id")
                .execute()
            ),
        )
        return [codec.to_slot(r) for r in rows]

    def claim_slot(self, slot: Slot, booked_by: str) -> bool:
        rows = self._rows(
            "claim_slot",
            lambda: (
                self._db.table("advisor_slots")
                .update({"booked_by": booked_by, "booked_at": codec.iso(self._clock.now())})
                .eq("id", slot.id)
                .is_("booked_by", "null")
                .execute()
            ),
        )
        return bool(rows)

    def save_case(self, c: Case) -> Case:
        saved = dataclasses.replace(c, id=new_id(c.id))
        self._upsert("cases", codec.case_row(saved))
        return saved

    def advisors_for(self, department: str) -> list[Advisor]:
        rows = self._rows(
            "advisors_for",
            lambda: (
                self._db.table("advisors")
                .select("id,fictional_name,department,demo_email")
                .eq("department", department)
                .order("fictional_name")
                .order("id")
                .execute()
            ),
        )
        return [codec.to_advisor(r) for r in rows]

    def router_stats(self, since: datetime | None = None) -> RouterStats:
        def paged(table: str, columns: str) -> list[Row]:
            def page(start: int) -> Any:
                q = self._db.table(table).select(columns)
                if since is not None:
                    q = q.gte("created_at", codec.iso(since))
                return q.order("id").range(start, start + PAGE - 1).execute()

            out: list[Row] = []
            while True:
                start = len(out)
                batch = self._rows(f"router_stats {table}", lambda: page(start))  # noqa: B023
                out.extend(batch)
                if len(batch) < PAGE:
                    return out

        return router_stats_from_rows(paged("predictions", "tier,cost_usd"), paged("llm_calls", "cached"))

    # ------------------------------------------------------------------ internals

    def _rows(self, what: str, fn: Callable[[], Any]) -> list[Row]:
        return cast(list[Row], store_call(what, lambda: fn().data) or [])

    def _one(self, table: str, column: str, value: str) -> Row:
        rows = self._rows(
            f"get {table}", lambda: self._db.table(table).select("*").eq(column, value).limit(1).execute()
        )
        if not rows:
            raise NotFound(f"{table} {value} not found")
        return rows[0]

    def _upsert(self, table: str, row: Row, on_conflict: str = "id") -> None:
        # Drop columns / map values the live schema does not have yet (codec.PENDING_*; empty since 0009).
        live = codec.for_live_schema(table, row)
        clean = {k: v for k, v in live.items() if not (k == "created_at" and v is None)}
        store_call(
            f"save {table}",
            lambda: (
                self._db.table(table).upsert(clean, on_conflict=on_conflict, default_to_null=False).execute()
            ),
        )

    def _insert(self, table: str, row: Row) -> None:
        store_call(f"insert {table}", lambda: self._db.table(table).insert(row).execute())

    def _update(self, table: str, values: Row, column: str, value: str) -> None:
        rows = self._rows(
            f"update {table}", lambda: self._db.table(table).update(values).eq(column, value).execute()
        )
        if not rows:
            raise NotFound(f"{table} {value} not found")

    def _member_rows(self, incident_ids: list[str]) -> list[Row]:
        return self._rows(
            "incident members",
            lambda: (
                self._db.table("tickets")
                .select("*")
                .in_("incident_id", incident_ids)
                .order("created_at")
                .order("id")
                .execute()
            ),
        )

    def _tickets(self, rows: list[Row]) -> list[Ticket]:
        if not rows:
            return []
        ids = [str(r["id"]) for r in rows]
        link_rows = self._rows(
            "ticket links",
            lambda: self._db.table("ticket_links").select("*").in_("ticket_id", ids).order("sink").execute(),
        )
        links: dict[str, list[TicketLink]] = {}
        for lr in link_rows:
            links.setdefault(str(lr["ticket_id"]), []).append(codec.to_link(lr))
        return [codec.to_ticket(r, links.get(str(r["id"]), [])) for r in rows]

    def _incidents(self, rows: list[Row]) -> list[Incident]:
        if not rows:
            return []
        members: dict[str, list[str]] = {}
        for t in self._member_rows([str(r["id"]) for r in rows]):
            members.setdefault(str(t["incident_id"]), []).append(str(t["id"]))
        return [codec.to_incident(r, members.get(str(r["id"]), [])) for r in rows]
