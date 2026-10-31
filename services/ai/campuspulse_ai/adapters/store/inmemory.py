"""InMemoryRepository: the reference Repository for tests and the offline red team (P4.3).

It stores the same row dicts as SupabaseRepository (adapters/store/codec.py) and enforces the
same foreign keys, unique keys, NotFound cases and orderings, so a test that passes here passes
against Supabase. Not thread-safe; one instance per test or CLI run.
"""

from __future__ import annotations

import copy
import dataclasses
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from campuspulse_ai.adapters.store import codec
from campuspulse_ai.adapters.store.codec import Row
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
from campuspulse_ai.domain.errors import NotFound, StoreError
from campuspulse_ai.domain.labels import Category
from campuspulse_ai.domain.ports import Clock
from campuspulse_ai.domain.values import (
    Advisor,
    RequestStatus,
    RouterStats,
    Slot,
    StudentSignals,
    TicketLink,
    Tier,
)

OPEN_TICKET_STATUSES = ("open", "in_progress")


class _UtcClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def new_id(value: str = "") -> str:
    """Keep a caller-supplied id, else mint a UUID (every table key is a uuid)."""
    return value or str(uuid.uuid4())


class InMemoryRepository:
    """Repository port over Python dicts, behaving like SupabaseRepository.

    - `save_*` are upserts by id (an empty id gets a fresh UUID; the saved entity is returned).
    - Foreign keys are enforced: saving a prediction/ticket/clarification for an unknown request,
      a review for an unknown prediction, or a link for an unknown ticket raises StoreError.
    - `get_*`, `latest_prediction`, `ticket_by_link`, `set_request_status`, `resolve_review`
      raise NotFound when the row is absent.
    - Orderings: clarifications by asked_at; incidents by opened_at; overdue tickets by
      sla_due_at; slots by starts_at; members by creation; always then by id.
    - Seeding helpers outside the port: `add_advisor`, `add_slot`, `add_llm_call`.

    `clock` stamps created_at/at/resolved_at/booked_at where the entity has no timestamp.
    """

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock: Clock = clock or _UtcClock()
        self._seq = 0
        self.tables: dict[str, dict[Any, Row]] = {
            name: {}
            for name in (
                "requests", "predictions", "clarifications", "review_queue", "tickets", "ticket_links",
                "incidents", "outbox", "student_signals", "events", "redteam_runs", "advisors",
                "advisor_slots", "cases", "notifications", "llm_calls",
            )
        }  # fmt: skip

    # ------------------------------------------------------------------ requests

    def save_request(self, r: Request) -> Request:
        saved = dataclasses.replace(r, id=new_id(r.id))
        self._upsert("requests", saved.id, codec.request_row(saved))
        return saved

    def get_request(self, id: str) -> Request:
        return codec.to_request(self._get("requests", id))

    def set_request_status(self, id: str, status: RequestStatus) -> None:
        self._get("requests", id)["status"] = str(status)

    # ------------------------------------------------------------------ predictions / clarifications / review

    def save_prediction(self, p: Prediction) -> Prediction:
        saved = dataclasses.replace(p, id=new_id(p.id))
        self._fk("requests", saved.request_id)
        self._upsert("predictions", saved.id, codec.prediction_row(saved))
        return saved

    def latest_prediction(self, request_id: str) -> Prediction:
        rows = [r for r in self.tables["predictions"].values() if r["request_id"] == request_id]
        if not rows:
            raise NotFound(f"no prediction for request {request_id}")
        return codec.to_prediction(max(rows, key=lambda r: (r["created_at"], r["_seq"])))

    def save_clarification(self, c: Clarification) -> Clarification:
        saved = dataclasses.replace(c, id=new_id(c.id))
        self._fk("requests", saved.request_id)
        self._upsert("clarifications", saved.id, codec.clarification_row(saved))
        return saved

    def clarifications_for(self, request_id: str) -> list[Clarification]:
        rows = [r for r in self.tables["clarifications"].values() if r["request_id"] == request_id]
        return [codec.to_clarification(r) for r in sorted(rows, key=lambda r: (r["asked_at"], r["id"]))]

    def enqueue_review(self, item: ReviewItem) -> ReviewItem:
        saved = dataclasses.replace(item, id=new_id(item.id))
        self._fk("predictions", saved.prediction_id)
        self._upsert("review_queue", saved.id, codec.review_row(saved))
        return saved

    def resolve_review(self, item: ReviewItem) -> None:
        row = self._get("review_queue", item.id)
        update = codec.review_row(item)
        for key in ("status", "reviewer_id", "corrected_category", "corrected_priority", "note"):
            row[key] = update[key]
        row["resolved_at"] = codec.iso(self._clock.now())

    # ------------------------------------------------------------------ tickets / incidents

    def save_ticket(self, t: Ticket) -> Ticket:
        saved = dataclasses.replace(t, id=new_id(t.id))
        self._fk("requests", saved.request_id)
        if saved.incident_id:
            self._fk("incidents", saved.incident_id)
        self._upsert("tickets", saved.id, codec.ticket_row(saved))
        links = [dataclasses.replace(link, ticket_id=saved.id) for link in saved.links]
        for link in links:
            self.save_ticket_link(link)
        saved.links = links
        return saved

    def get_ticket(self, id: str) -> Ticket:
        return self._ticket(self._get("tickets", id))

    def overdue_open_tickets(self, now: datetime) -> list[Ticket]:
        cutoff = codec.iso(now) or ""
        rows = [
            r
            for r in self.tables["tickets"].values()
            if r["status"] in OPEN_TICKET_STATUSES and _ts(r["sla_due_at"]) < _ts(cutoff)
        ]
        return [self._ticket(r) for r in sorted(rows, key=lambda r: (_ts(r["sla_due_at"]), r["id"]))]

    def save_ticket_link(self, link: TicketLink) -> None:
        self._fk("tickets", link.ticket_id)
        for key, row in self.tables["ticket_links"].items():
            if (row["sink"], row["external_id"]) == (link.sink, link.external_id) and key != (
                link.ticket_id,
                link.sink,
            ):
                raise StoreError(f"duplicate ticket link {link.sink}:{link.external_id}")
        self._upsert("ticket_links", (link.ticket_id, link.sink), codec.link_row(link))

    def save_incident(self, i: Incident) -> Incident:
        saved = dataclasses.replace(i, id=new_id(i.id))
        self._upsert("incidents", saved.id, codec.incident_row(saved))
        for ticket_id in saved.member_ticket_ids:
            if ticket_id in self.tables["tickets"]:
                self.tables["tickets"][ticket_id]["incident_id"] = saved.id
        return self._incident(self.tables["incidents"][saved.id])

    def open_incidents(self, building: str, category: Category, since: datetime) -> list[Incident]:
        start = _ts(codec.iso(since) or "")
        rows = [
            r
            for r in self.tables["incidents"].values()
            if r["status"] == "open"
            and r["building_id"] == building
            and r["category"] == str(category)
            and _ts(r["opened_at"]) >= start
        ]
        return [self._incident(r) for r in sorted(rows, key=lambda r: (_ts(r["opened_at"]), r["id"]))]

    def incident_members(self, incident_id: str) -> list[tuple[Ticket, Request]]:
        return [
            (self._ticket(row), self.get_request(row["request_id"])) for row in self._member_rows(incident_id)
        ]

    def ticket_by_link(self, sink: str, external_id: str) -> Ticket:
        for row in self.tables["ticket_links"].values():
            if (row["sink"], row["external_id"]) == (sink, external_id):
                return self.get_ticket(row["ticket_id"])
        raise NotFound(f"no ticket linked to {sink}:{external_id}")

    # ------------------------------------------------------------------ LifecycleReads (P3.11, P4.10)

    def get_prediction(self, id: str) -> Prediction:
        return codec.to_prediction(self._get("predictions", id))

    def open_review_for(self, prediction_id: str) -> ReviewItem | None:
        rows = [
            r
            for r in self.tables["review_queue"].values()
            if r["prediction_id"] == prediction_id and r["status"] == "open"
        ]
        if not rows:
            return None
        return codec.to_review_item(min(rows, key=lambda r: (r["created_at"], r["_seq"])))

    def tickets_for_requests(self, request_ids: Sequence[str]) -> list[Ticket]:
        wanted = set(request_ids)
        rows = [r for r in self.tables["tickets"].values() if r["request_id"] in wanted]
        return [self._ticket(r) for r in sorted(rows, key=lambda r: (r["created_at"], r["_seq"]))]

    def get_incident(self, id: str) -> Incident:
        return self._incident(self._get("incidents", id))

    def list_incidents(self, *, open_only: bool, limit: int) -> list[Incident]:
        rows = [r for r in self.tables["incidents"].values() if not open_only or r["status"] == "open"]
        rows.sort(key=lambda r: (_ts(r["opened_at"]), r["id"]), reverse=True)
        return [self._incident(r) for r in rows[:limit]]

    def mark_simulated(self, request_id: str) -> None:
        self._get("requests", request_id)["simulated"] = True

    def simulated(self, request_ids: Sequence[str]) -> set[str]:
        rows = self.tables["requests"]
        return {i for i in request_ids if i in rows and rows[i].get("simulated")}

    # ------------------------------------------------------------------ outbox / signals / audit

    def save_outbox(self, m: OutboxMessage) -> OutboxMessage:
        saved = dataclasses.replace(m, id=new_id(m.id))
        self._upsert("outbox", saved.id, codec.outbox_row(saved))
        return saved

    def bump_student_signals(
        self, alias: str, claimed_urgent: bool, was_high: bool, injection: bool
    ) -> StudentSignals:
        row = self.tables["student_signals"].setdefault(
            alias,
            {
                "alias": alias, "n_requests": 0, "n_claimed_urgent": 0, "n_claimed_urgent_not_high": 0,
                "n_high": 0, "n_injection": 0, "gaming_flag": False,
            },
        )  # fmt: skip
        row["n_requests"] += 1
        row["n_claimed_urgent"] += int(claimed_urgent)
        row["n_claimed_urgent_not_high"] += int(claimed_urgent and not was_high)
        row["n_high"] += int(was_high)
        row["n_injection"] += int(injection)
        return codec.to_signals(row)

    def append_event(self, actor: str, action: str, entity: str, payload: Mapping[str, object]) -> None:
        self._seq += 1
        self.tables["events"][self._seq] = {
            "id": self._seq,
            "actor": actor,
            "action": action,
            "entity": entity,
            "payload": codec.jsonify(payload),
            "at": codec.iso(self._clock.now()),
        }

    def save_redteam_run(self, scorecard: Scorecard) -> str:
        run_id = scorecard.run_id if codec.is_uuid(scorecard.run_id) else str(uuid.uuid4())
        self._upsert(
            "redteam_runs",
            run_id,
            {
                "id": run_id,
                "scorecard": codec.scorecard_json(scorecard, run_id),
                "created_at": codec.iso(scorecard.created_at),
            },
        )
        return run_id

    def redteam_history(self, limit: int = 20) -> list[Scorecard]:
        rows = sorted(
            self.tables["redteam_runs"].values(), key=lambda r: (r["created_at"], r["_seq"]), reverse=True
        )
        return [codec.to_scorecard(r["scorecard"], r["created_at"]) for r in rows[:limit]]

    def save_notification(self, alias: str, kind: str, payload: Mapping[str, object]) -> None:
        id = str(uuid.uuid4())
        self._upsert(
            "notifications",
            id,
            {"id": id, "alias": alias, "kind": kind, "payload": codec.jsonify(payload), "read_at": None},
        )

    # ------------------------------------------------------------------ advisors / slots / cases

    def free_slots(self, advisor_ids: Sequence[str], window: tuple[datetime, datetime]) -> list[Slot]:
        start, end = _ts(codec.iso(window[0]) or ""), _ts(codec.iso(window[1]) or "")
        wanted = set(advisor_ids)
        rows = [
            r
            for r in self.tables["advisor_slots"].values()
            if r["booked_by"] is None
            and r["advisor_id"] in wanted
            and _ts(r["starts_at"]) >= start
            and _ts(r["ends_at"]) <= end
        ]
        return [codec.to_slot(r) for r in sorted(rows, key=lambda r: (_ts(r["starts_at"]), r["id"]))]

    def claim_slot(self, slot: Slot, booked_by: str) -> bool:
        row = self.tables["advisor_slots"].get(slot.id)
        if row is None or row["booked_by"] is not None:
            return False
        row["booked_by"], row["booked_at"] = booked_by, codec.iso(self._clock.now())
        return True

    def save_case(self, c: Case) -> Case:
        saved = dataclasses.replace(c, id=new_id(c.id))
        self._fk("requests", saved.request_id)
        if saved.ticket_id:
            self._fk("tickets", saved.ticket_id)
        self._upsert("cases", saved.id, codec.case_row(saved))
        return saved

    def advisors_for(self, department: str) -> list[Advisor]:
        rows = [r for r in self.tables["advisors"].values() if r["department"] == department]
        return [codec.to_advisor(r) for r in sorted(rows, key=lambda r: (r["fictional_name"], r["id"]))]

    def router_stats(self, since: datetime | None = None) -> RouterStats:
        start = _ts(codec.iso(since)) if since else None
        preds = [
            r for r in self.tables["predictions"].values() if start is None or _ts(r["created_at"]) >= start
        ]
        calls = [
            r for r in self.tables["llm_calls"].values() if start is None or _ts(r["created_at"]) >= start
        ]
        return router_stats_from_rows(preds, calls)

    # ------------------------------------------------------------------ seeding helpers (not in the port)

    def add_advisor(self, name: str, department: str, email: str = "", id: str = "") -> Advisor:
        """Insert an advisor row (seed data; Supabase gets these from supabase/seed/02_advisors.sql)."""
        row = {"id": new_id(id), "fictional_name": name, "department": department, "demo_email": email}
        self._upsert("advisors", row["id"], row)
        return codec.to_advisor(row)

    def add_slot(self, advisor_id: str, starts_at: datetime, ends_at: datetime, id: str = "") -> Slot:
        """Insert a free slot (seed data; Supabase gets these from supabase/seed/03_advisor_slots.sql)."""
        self._fk("advisors", advisor_id)
        row = {
            "id": new_id(id),
            "advisor_id": advisor_id,
            "starts_at": codec.iso(starts_at),
            "ends_at": codec.iso(ends_at),
            "booked_by": None,
            "booked_at": None,
        }
        self._upsert("advisor_slots", row["id"], row)
        return codec.to_slot(row)

    def add_llm_call(self, tier: Tier, cost_usd: float, cached: bool) -> None:
        """Record an LLM call row (in production SupabaseCostLogger writes llm_calls)."""
        id = str(uuid.uuid4())
        self._upsert("llm_calls", id, {"id": id, "tier": str(tier), "cost_usd": cost_usd, "cached": cached})

    # ------------------------------------------------------------------ internals

    def _upsert(self, table: str, key: Any, row: Row) -> None:
        # Like an upsert that omits created_at: the column default fills it on insert and an
        # update keeps the original. _seq orders rows saved within one clock tick.
        stored = copy.deepcopy(row)
        if stored.get("created_at") is None:
            stored.pop("created_at", None)
        existing = self.tables[table].get(key)
        if existing is None:
            self._seq += 1
            stored.setdefault("created_at", codec.iso(self._clock.now()))
            stored["_seq"] = self._seq
            self.tables[table][key] = stored
        else:
            existing.update(stored)

    def _get(self, table: str, id: str) -> Row:
        row = self.tables[table].get(id)
        if row is None:
            raise NotFound(f"{table} {id} not found")
        return row

    def _fk(self, table: str, id: str | None) -> None:
        if id is not None and id not in self.tables[table]:
            raise StoreError(f"foreign key violation: {table} {id} does not exist")

    def _member_rows(self, incident_id: str) -> list[Row]:
        rows = [r for r in self.tables["tickets"].values() if r.get("incident_id") == incident_id]
        return sorted(rows, key=lambda r: (r["created_at"], r["_seq"]))

    def _ticket(self, row: Row) -> Ticket:
        links = sorted(
            (codec.to_link(r) for r in self.tables["ticket_links"].values() if r["ticket_id"] == row["id"]),
            key=lambda link: link.sink,
        )
        return codec.to_ticket(row, links)

    def _incident(self, row: Row) -> Incident:
        return codec.to_incident(row, [r["id"] for r in self._member_rows(row["id"])])


def router_stats_from_rows(predictions: Iterable[Row], llm_calls: Iterable[Row]) -> RouterStats:
    """Shared by both repositories: tier mix and cost over prediction rows, cache hits over calls."""
    preds = list(predictions)
    by_tier: dict[str, int] = {}
    for row in preds:
        by_tier[row["tier"]] = by_tier.get(row["tier"], 0) + 1
    total = len(preds)
    return RouterStats(
        total=total,
        by_tier=by_tier,
        resolved_tier0_pct=round(100.0 * by_tier.get("tier0", 0) / total, 2) if total else 0.0,
        cost_usd=round(sum(float(r.get("cost_usd") or 0.0) for r in preds), 6),
        cached_calls=sum(1 for r in llm_calls if r.get("cached")),
    )


def _ts(value: str | None) -> datetime:
    parsed = codec.parse_dt(value)
    return parsed if parsed is not None else datetime.min.replace(tzinfo=UTC)
