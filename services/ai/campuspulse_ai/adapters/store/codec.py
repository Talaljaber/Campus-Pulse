"""Entity <-> table-row mapping shared by InMemoryRepository and SupabaseRepository (P4.3).

Both repositories store exactly these row dicts (JSON-safe; datetimes as ISO-8601 UTC), so the
in-memory reference behaves like Supabase down to what survives a round trip. Column names are
those of supabase/migrations/0001-0007; see docs/db/schema.md › Repository mapping.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from campuspulse_ai.domain.entities import (
    Case,
    Clarification,
    CoreResult,
    Explanation,
    Incident,
    OutboxMessage,
    Prediction,
    Request,
    ReviewItem,
    Scorecard,
    Ticket,
)
from campuspulse_ai.domain.errors import StoreError
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.values import (
    Advisor,
    ArtifactVersion,
    Booking,
    ClarificationConstraint,
    ClarificationOption,
    Counterfactual,
    Evidence,
    EvidenceVector,
    GuardVerdict,
    Lang,
    Location,
    Money,
    Neighbor,
    NormalizedRequest,
    PredictionSet,
    ProbVector,
    RequestStatus,
    Slot,
    StudentSignals,
    TicketLink,
    TicketStatus,
    Tier,
)

Row = dict[str, Any]

# --------------------------------------------------------------------------- live-schema guard (D-011)
#
# When the domain writes something the live Supabase schema does not have yet (a DB change request
# in flight), SupabaseRepository passes every row through `for_live_schema`, which drops the
# missing columns and maps the missing enum values, so a write never fails on them.
# InMemoryRepository keeps the full rows (it models the target schema). D-011 (tickets.tags,
# outbox status 'deferred') landed in migration 0009, so both mappings are empty; refill them
# while the next change request is pending.
PENDING_COLUMNS: Mapping[str, frozenset[str]] = {}
"""table -> columns the codec writes that the live schema lacks (dropped on write, read as default)."""
PENDING_VALUES: Mapping[tuple[str, str], Mapping[str, str]] = {}
"""(table, column) -> {value the check constraint rejects: the value written instead}."""


def for_live_schema(table: str, row: Row) -> Row:
    """`row` as the live schema accepts it (see PENDING_COLUMNS / PENDING_VALUES).

    A mapped value keeps its meaning in `error` when the table has one (e.g. a `deferred` outbox row
    is written as `queued` with error `deferred: <reason>`).
    """
    out = {k: v for k, v in row.items() if k not in PENDING_COLUMNS.get(table, frozenset())}
    for (tbl, column), mapping in PENDING_VALUES.items():
        value = out.get(column)
        if tbl != table or not isinstance(value, str) or value not in mapping:
            continue
        out[column] = mapping[value]
        if "error" in out:
            reason = out.get("error") or ""
            out["error"] = reason if reason.startswith(f"{value}:") else f"{value}: {reason}".rstrip(": ")
    return out


# --------------------------------------------------------------------------- scalars


def iso(dt: datetime | None) -> str | None:
    """ISO-8601 in UTC; naive datetimes are taken to be UTC already."""
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC).isoformat()


def jsonify(payload: Mapping[str, object]) -> Row:
    """A JSON-safe copy (jsonb round trip): datetimes and other objects become strings."""
    return dict(json.loads(json.dumps(dict(payload), default=str)))


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _req_dt(value: str) -> datetime:
    dt = parse_dt(value)
    assert dt is not None
    return dt


def prob(p: ProbVector) -> Row:
    return {"labels": list(p.labels), "values": list(p.values)}


def to_prob(d: Mapping[str, Any]) -> ProbVector:
    return ProbVector(values=tuple(float(v) for v in d["values"]), labels=tuple(d["labels"]))


def _evidence(e: Evidence) -> Row:
    return {"type": e.type, "span": e.span, "lang": str(e.lang)}


def _to_evidence(d: Mapping[str, Any]) -> Evidence:
    return Evidence(type=d["type"], span=d["span"], lang=Lang(d["lang"]))


def _neighbor(n: Neighbor) -> Row:
    return {
        "text": n.text,
        "category": str(n.category),
        "priority": str(n.priority),
        "sim": n.sim,
        "source": n.source,
        "created_at": iso(n.created_at),
    }


def _to_neighbor(d: Mapping[str, Any]) -> Neighbor:
    return Neighbor(
        text=d["text"],
        category=Category(d["category"]),
        priority=Priority(d["priority"]),
        sim=float(d["sim"]),
        source=d["source"],
        created_at=parse_dt(d.get("created_at")),
    )


# --------------------------------------------------------------------------- requests


def request_row(r: Request) -> Row:
    n = r.normalized
    loc = n.location if n else None
    return {
        "id": r.id,
        "alias": r.alias,
        "raw_text": r.raw_text,
        "input_mode": r.input_mode,
        "status": str(r.status),
        "created_at": iso(r.created_at),
        "conversation_id": r.conversation_id,
        "core": n.core if n else None,
        "text_norm": n.text_norm if n else None,
        "model_text": n.model_text if n else None,
        "lang": str(n.lang) if n else None,
        "is_arabizi": n.is_arabizi if n else None,
        "stated_urgency": n.stated_urgency if n else None,
        "truncated": n.truncated if n else False,
        "building_id": loc.building if loc else None,
        "room": loc.room if loc else None,
        "location_source": loc.source if loc else None,
    }


def to_request(row: Mapping[str, Any]) -> Request:
    normalized = None
    if row.get("text_norm") is not None and row.get("lang") is not None:
        location = None
        if row.get("building_id"):
            location = Location(
                building=row["building_id"],
                room=row.get("room"),
                source=row.get("location_source") or "picked",
            )
        normalized = NormalizedRequest(
            raw=row["raw_text"],
            core=row.get("core") or row["text_norm"],
            text_norm=row["text_norm"],
            model_text=row.get("model_text") or row["text_norm"],
            lang=Lang(row["lang"]),
            is_arabizi=bool(row.get("is_arabizi")),
            stated_urgency=bool(row.get("stated_urgency")),
            truncated=bool(row.get("truncated")),
            location=location,
        )
    return Request(
        id=str(row["id"]),
        alias=row.get("alias") or "",
        raw_text=row["raw_text"],
        normalized=normalized,
        input_mode=row.get("input_mode") or "text",
        status=RequestStatus(row["status"]),
        created_at=_req_dt(row["created_at"]),
        conversation_id=row.get("conversation_id"),
    )


# --------------------------------------------------------------------------- predictions


def core_json(c: CoreResult) -> Row:
    return {
        "p_cat": prob(c.p_cat),
        "p_pri": prob(c.p_pri),
        "per_model": {k: prob(v) for k, v in sorted(c.per_model.items())},
        "flags": sorted(c.flags),
        "set_cat": sorted(c.set_cat.labels),
        "set_pri": sorted(c.set_pri.labels),
        "ood_score": c.ood_score,
        "neighbors": [_neighbor(n) for n in c.neighbors],
        "evidence": {"flags": dict(c.evidence.flags), "spans": [_evidence(e) for e in c.evidence.spans]},
        "guard": {
            "kind": c.guard.kind,
            "matched_spans": list(c.guard.matched_spans),
            "stripped_text": c.guard.stripped_text,
            "score": c.guard.score,
        },
        "safety": c.safety,
        "floors_applied": list(c.floors_applied),
        "tier": str(c.tier),
        "latency_ms": c.latency_ms,
        "artifact": {"name": c.artifact.name, "sha256": c.artifact.sha256},
    }


def to_core(d: Mapping[str, Any]) -> CoreResult:
    g = d["guard"]
    return CoreResult(
        p_cat=to_prob(d["p_cat"]),
        p_pri=to_prob(d["p_pri"]),
        per_model={k: to_prob(v) for k, v in d["per_model"].items()},
        flags=frozenset(d["flags"]),
        set_cat=PredictionSet(frozenset(d["set_cat"])),
        set_pri=PredictionSet(frozenset(d["set_pri"])),
        ood_score=float(d["ood_score"]),
        neighbors=tuple(_to_neighbor(n) for n in d["neighbors"]),
        evidence=EvidenceVector(
            flags=dict(d["evidence"]["flags"]),
            spans=tuple(_to_evidence(e) for e in d["evidence"]["spans"]),
        ),
        guard=GuardVerdict(
            kind=g["kind"],
            matched_spans=tuple(g["matched_spans"]),
            stripped_text=g["stripped_text"],
            score=g["score"],
        ),
        safety=bool(d["safety"]),
        floors_applied=tuple(d["floors_applied"]),
        tier=Tier(d["tier"]),
        latency_ms=int(d["latency_ms"]),
        artifact=ArtifactVersion(name=d["artifact"]["name"], sha256=d["artifact"]["sha256"]),
    )


def explanation_json(e: Explanation) -> Row:
    cf = e.counterfactual
    return {
        "top_tokens": [[token, weight] for token, weight in e.top_tokens],
        "urgency_reasons": [_evidence(x) for x in e.urgency_reasons],
        "neighbors": [_neighbor(n) for n in e.neighbors],
        "counterfactual": (
            {"drop": cf.drop, "category": str(cf.category), "priority": str(cf.priority)} if cf else None
        ),
        "trace": dict(e.trace),
    }


def to_explanation(d: Mapping[str, Any]) -> Explanation:
    cf = d.get("counterfactual")
    return Explanation(
        top_tokens=[(str(t), float(w)) for t, w in d["top_tokens"]],
        urgency_reasons=[_to_evidence(x) for x in d["urgency_reasons"]],
        neighbors=[_to_neighbor(n) for n in d["neighbors"]],
        counterfactual=(
            Counterfactual(
                drop=cf["drop"], category=Category(cf["category"]), priority=Priority(cf["priority"])
            )
            if cf
            else None
        ),
        trace=dict(d.get("trace") or {}),
    )


def prediction_row(p: Prediction) -> Row:
    c = p.core
    return {
        "id": p.id,
        "request_id": p.request_id,
        "category": str(p.category),
        "priority": str(p.priority),
        "p_cat": c.p_cat.as_dict(),
        "p_pri": c.p_pri.as_dict(),
        "set_cat": sorted(c.set_cat.labels),
        "set_pri": sorted(c.set_pri.labels),
        "per_model": {k: v.as_dict() for k, v in sorted(c.per_model.items())},
        "tier": str(p.tier),
        "models_used": sorted({key.split(".", 1)[0] for key in c.per_model}),
        "cost_usd": round(p.cost.usd, 6),
        "latency_ms": c.latency_ms,
        "flags": sorted(p.flags),
        "explanation": explanation_json(p.explanation) if p.explanation else None,
        "artifact_version": p.artifact_version,
        "core": core_json(c),
    }


def to_prediction(row: Mapping[str, Any]) -> Prediction:
    return Prediction(
        id=str(row["id"]),
        request_id=str(row["request_id"]),
        category=Category(row["category"]),
        priority=Priority(row["priority"]),
        core=to_core(row["core"]),
        tier=Tier(row["tier"]),
        flags=set(row.get("flags") or ()),
        explanation=to_explanation(row["explanation"]) if row.get("explanation") else None,
        cost=Money(usd=float(row.get("cost_usd") or 0.0)),
        artifact_version=row.get("artifact_version") or "",
    )


# --------------------------------------------------------------------------- clarifications / review


def clarification_row(c: Clarification) -> Row:
    return {
        "id": c.id,
        "request_id": c.request_id,
        "question_id": c.question_id,
        "options": [
            {
                "id": o.id,
                "text": o.text,
                "constraint": {"kind": o.constraint.kind, "value": o.constraint.value}
                if o.constraint
                else None,
            }
            for o in c.options
        ],
        "answer": c.answer,
        "asked_at": iso(c.asked_at),
        "answered_at": iso(c.answered_at),
    }


def to_clarification(row: Mapping[str, Any]) -> Clarification:
    return Clarification(
        id=str(row["id"]),
        request_id=str(row["request_id"]),
        question_id=row["question_id"],
        options=tuple(
            ClarificationOption(
                id=o["id"],
                text=o["text"],
                constraint=ClarificationConstraint(**o["constraint"]) if o.get("constraint") else None,
            )
            for o in row.get("options") or ()
        ),
        answer=row.get("answer"),
        asked_at=_req_dt(row["asked_at"]),
        answered_at=parse_dt(row.get("answered_at")),
    )


def review_row(item: ReviewItem) -> Row:
    return {
        "id": item.id,
        "prediction_id": item.prediction_id,
        "reason": item.reason,
        "status": item.status,
        "reviewer_id": item.reviewer_id,
        "corrected_category": str(item.corrected_category) if item.corrected_category else None,
        "corrected_priority": str(item.corrected_priority) if item.corrected_priority else None,
        "note": item.note,
        "assignee": item.assignee,
        "office": item.office,
    }


def to_review_item(row: Mapping[str, Any]) -> ReviewItem:
    return ReviewItem(
        id=str(row["id"]),
        prediction_id=str(row["prediction_id"]),
        reason=row["reason"],
        status=row["status"],
        reviewer_id=row.get("reviewer_id"),
        corrected_category=Category(row["corrected_category"]) if row.get("corrected_category") else None,
        corrected_priority=Priority(row["corrected_priority"]) if row.get("corrected_priority") else None,
        note=row.get("note"),
        assignee=str(row["assignee"]) if row.get("assignee") else None,
        office=row.get("office"),
    )


# --------------------------------------------------------------------------- tickets / incidents


def ticket_row(t: Ticket) -> Row:
    return {
        "id": t.id,
        "request_id": t.request_id,
        "incident_id": t.incident_id,
        "office": t.office,
        "category": str(t.category),
        "priority": str(t.priority),
        "status": str(t.status),
        "provisional": t.provisional,
        "sla_due_at": iso(t.sla_due_at),
        "title": t.title,
        "body": t.body,
        "escalated_at": iso(t.escalated_at),
        "resolved_at": iso(t.resolved_at),
        "tags": list(t.tags),
    }


def link_row(link: TicketLink) -> Row:
    return {
        "ticket_id": link.ticket_id,
        "sink": link.sink,
        "external_id": link.external_id,
        "external_url": link.url,
        "last_error": link.error,
    }


def to_link(row: Mapping[str, Any]) -> TicketLink:
    return TicketLink(
        ticket_id=str(row["ticket_id"]),
        sink=row["sink"],
        external_id=row["external_id"],
        url=row.get("external_url"),
        error=row.get("last_error"),
    )


def to_ticket(row: Mapping[str, Any], links: list[TicketLink]) -> Ticket:
    return Ticket(
        id=str(row["id"]),
        request_id=str(row["request_id"]),
        incident_id=str(row["incident_id"]) if row.get("incident_id") else None,
        office=row["office"],
        category=Category(row["category"]),
        priority=Priority(row["priority"]),
        status=TicketStatus(row["status"]),
        provisional=bool(row["provisional"]),
        sla_due_at=_req_dt(row["sla_due_at"]),
        title=row.get("title") or "",
        body=row.get("body") or "",
        escalated_at=parse_dt(row.get("escalated_at")),
        resolved_at=parse_dt(row.get("resolved_at")),
        links=links,
        tags=tuple(row.get("tags") or ()),
    )


def incident_row(i: Incident) -> Row:
    return {
        "id": i.id,
        "building_id": i.building,
        "category": str(i.category),
        "title": i.title,
        "priority": str(i.priority),
        "report_count": i.report_count,
        "status": i.status,
        "opened_at": iso(i.opened_at),
        "resolved_at": iso(i.resolved_at),
    }


def to_incident(row: Mapping[str, Any], member_ticket_ids: list[str]) -> Incident:
    return Incident(
        id=str(row["id"]),
        building=row["building_id"],
        category=Category(row["category"]),
        title=row.get("title") or "",
        priority=Priority(row["priority"]),
        report_count=int(row["report_count"]),
        status=row["status"],
        member_ticket_ids=member_ticket_ids,
        opened_at=_req_dt(row["opened_at"]),
        resolved_at=parse_dt(row.get("resolved_at")),
    )


# --------------------------------------------------------------------------- outbox / signals / misc


def outbox_row(m: OutboxMessage) -> Row:
    # The domain kind is the transport; it is also the closest purpose value (SPEC outbox.kind).
    return {
        "id": m.id,
        "kind": m.kind,
        "channel": m.kind,
        "to_address": m.to_address,
        "subject": m.subject,
        "body": m.body,
        "provider_id": m.provider_id,
        "status": m.status,
        "priority": str(m.priority) if m.priority else None,
        "flags": sorted(m.flags),
        "error": m.error,
        "created_at": iso(m.created_at),
    }


def to_signals(row: Mapping[str, Any]) -> StudentSignals:
    return StudentSignals(
        alias=row["alias"],
        requests=int(row["n_requests"]),
        claimed_urgent=int(row["n_claimed_urgent"]),
        claimed_urgent_not_high=int(row["n_claimed_urgent_not_high"]),
        injection_attempts=int(row["n_injection"]),
        gaming_suspected=bool(row["gaming_flag"]),
    )


def scorecard_json(s: Scorecard, run_id: str) -> Row:
    """`redteam_runs.scorecard` (jsonb). `created_at`, `n` and `seed` are the D-013 fields."""
    return {
        "run_id": run_id,
        "created_at": iso(s.created_at),
        "n": s.n,
        "seed": s.seed,
        "by_style": dict(s.by_style),
        "by_lang": dict(s.by_lang),
        "overall": s.overall,
        "failures": [jsonify(f) for f in s.failures],
    }


LEGACY_SCORECARD_N = 0
LEGACY_SCORECARD_SEED = 0
"""`n` and `seed` read from a scorecard stored before D-013."""


def to_scorecard(d: Mapping[str, Any], row_created_at: str | None = None) -> Scorecard:
    """A stored scorecard. A scorecard written before D-013 has no `created_at` in its JSON: the
    row's `created_at` column is used instead, and `n`/`seed` read as 0. Raises `StoreError` when
    neither carries a timestamp."""
    created = parse_dt(d.get("created_at")) or parse_dt(row_created_at)
    if created is None:
        raise StoreError(f"red-team run {d.get('run_id')!r} has no created_at")
    return Scorecard(
        run_id=d["run_id"],
        by_style={k: float(v) for k, v in d["by_style"].items()},
        by_lang={k: float(v) for k, v in d["by_lang"].items()},
        overall=float(d["overall"]),
        failures=list(d.get("failures") or ()),
        created_at=created,
        n=int(d.get("n", LEGACY_SCORECARD_N)),
        seed=int(d.get("seed", LEGACY_SCORECARD_SEED)),
    )


def to_slot(row: Mapping[str, Any]) -> Slot:
    return Slot(
        id=str(row["id"]),
        advisor_id=str(row["advisor_id"]),
        starts_at=_req_dt(row["starts_at"]),
        ends_at=_req_dt(row["ends_at"]),
    )


def case_row(c: Case) -> Row:
    b: Booking | None = c.booking
    return {
        "id": c.id,
        "request_id": c.request_id,
        "ticket_id": c.ticket_id,
        "advisor_id": b.slot.advisor_id if b else None,
        "slot_id": b.slot.id if b else None,
        "slot_start": iso(b.slot.starts_at) if b else None,
        "booking": (
            {
                "slot": {
                    "id": b.slot.id,
                    "advisor_id": b.slot.advisor_id,
                    "starts_at": iso(b.slot.starts_at),
                    "ends_at": iso(b.slot.ends_at),
                },
                "attendees": list(b.attendees),
                "title": b.title,
                "provider": b.provider,
                "external_id": b.external_id,
            }
            if b
            else None
        ),
        "created_at": iso(c.created_at),
    }


def to_advisor(row: Mapping[str, Any]) -> Advisor:
    return Advisor(
        id=str(row["id"]),
        name=row["fictional_name"],
        department=row["department"],
        email=row.get("demo_email") or "",
    )
