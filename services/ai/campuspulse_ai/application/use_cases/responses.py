"""Domain -> `/v1` DTO mapping shared by the triage and clarify use cases (SPEC §7).

Pure functions; no I/O. Every builder fills every DTO key (the contract keeps keys present, null when
unused).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from campuspulse_ai.application import dto
from campuspulse_ai.domain.entities import CoreResult, Explanation, Incident, Scorecard, Ticket
from campuspulse_ai.domain.labels import CATEGORY_ORDER, PRIORITY_ORDER, Category, Priority
from campuspulse_ai.domain.values import (
    FLAGS,
    ClarificationQuestion,
    Neighbor,
    NormalizedRequest,
    Understanding,
)

# `NormalizedRequest.model_text` for Arabizi is "<transliteration> | <original>"; this is the same
# separator as adapters/preprocess/arabizi.MODEL_TEXT_SEPARATOR (a test pins them together).
ARABIZI_MODEL_TEXT_SEPARATOR = " | "
TOP_TOKENS = 5  # SPEC §7: explanation.top_tokens holds the top 5 [token, importance] pairs
API_FLAGS: frozenset[str] = FLAGS - dto.DEBUG_ONLY_FLAGS
CATEGORY_SUFFIX = ".category"


def decided_labels(core: CoreResult) -> tuple[Category, Priority]:
    """The final labels (ARCHITECTURE §2.1 [9]): a singleton set's label, else the argmax.

    A safety core is always high, whatever the vectors say: the floor is asserted again here and a
    violation is resolved towards safety (never under-prioritise physical danger).
    """
    cat = next(iter(core.set_cat.labels)) if core.set_cat.is_singleton else core.p_cat.argmax()
    pri = next(iter(core.set_pri.labels)) if core.set_pri.is_singleton else core.p_pri.argmax()
    priority = Priority.HIGH if core.safety else Priority(pri)
    return Category(cat), priority


def category_out(core: CoreResult, label: Category) -> dto.CategoryOut:
    members = [c for c in CATEGORY_ORDER if c.value in core.set_cat.labels]
    return dto.CategoryOut(label=label, prob=_prob(core.p_cat.prob(label.value)), set=members)


def priority_out(core: CoreResult, label: Priority) -> dto.PriorityOut:
    members = [p for p in PRIORITY_ORDER if p.value in core.set_pri.labels]
    evidence = [dto.EvidenceOut(type=e.type, span=e.span) for e in core.evidence.spans]
    return dto.PriorityOut(
        label=label, prob=_prob(core.p_pri.prob(label.value)), set=members, evidence=evidence
    )


def clarification_out(q: ClarificationQuestion) -> dto.ClarificationOut:
    return dto.ClarificationOut(
        question_id=q.id,
        text=q.text,
        options=[dto.ClarificationOptionOut(id=o.id, text=o.text) for o in q.options],
    )


def neighbor_out(n: Neighbor) -> dto.NeighborOut:
    return dto.NeighborOut(
        text=n.text,
        label=n.category,
        priority=n.priority,
        sim=_prob(n.sim),
        source=n.source,
        created_at=n.created_at,
    )


def models_agree(core: CoreResult, category: Category) -> bool:
    """True when every member's category vote equals the decided category (True with no members)."""
    votes = [p.argmax() for key, p in core.per_model.items() if key.endswith(CATEGORY_SUFFIX)]
    return all(v == category.value for v in votes)


def trace_out(
    core: CoreResult,
    category: Category,
    *,
    policy_path: Sequence[str],
    clarified: bool,
    cost_usd: float,
    debug_members: bool,
) -> dto.TraceOut:
    return dto.TraceOut(
        sets=dto.SetSizesOut(cat=core.set_cat.size, pri=core.set_pri.size),
        models_agree=models_agree(core, category),
        cost_usd=max(cost_usd, 0.0),
        latency_ms=max(core.latency_ms, 0),
        policy_path=list(policy_path),
        clarified=clarified,
        artifact_version=core.artifact.name,
        per_model={k: v.as_dict() for k, v in sorted(core.per_model.items())} if debug_members else None,
    )


def explanation_out(explanation: Explanation, trace: dto.TraceOut) -> dto.ExplanationOut:
    cf = explanation.counterfactual
    return dto.ExplanationOut(
        top_tokens=[(t, float(w)) for t, w in explanation.top_tokens[:TOP_TOKENS]],
        neighbors=[neighbor_out(n) for n in explanation.neighbors],
        counterfactual=dto.CounterfactualOut(drop=cf.drop, category=cf.category, priority=cf.priority)
        if cf
        else None,
        trace=trace,
    )


def understanding_out(u: Understanding) -> dto.UnderstandingOut:
    e = u.entities
    return dto.UnderstandingOut(
        summary_en=u.summary_en,
        summary_ar=u.summary_ar,
        entities=dto.EntitiesOut(
            building=e.building, room=e.room, course_code=e.course_code, deadline=e.deadline, system=e.system
        ),
        student_reply=u.student_reply,
        ticket_title=u.ticket_title,
        ticket_body=u.ticket_body,
        source=u.source,
        prompt_version=u.prompt_version,
    )


def understood_as(req: NormalizedRequest) -> str | None:
    """The Arabic transliteration shown for Arabizi input (LD-25), else None."""
    if not req.is_arabizi:
        return None
    translit = req.model_text.split(ARABIZI_MODEL_TEXT_SEPARATOR, 1)[0].strip()
    return translit or None


def flags_out(flags: Iterable[str]) -> list[str]:
    """Sorted API flags; debug-only and unknown names (e.g. evidence names) are dropped."""
    return sorted(set(flags) & API_FLAGS)


def scorecard_out(s: Scorecard) -> dto.ScorecardOut:
    """A red-team scorecard (P4.11) for `/v1/redteam/run` and the `/v1/metrics` history.

    Raises `ValueError` (pydantic) when a stored scorecard does not fit the contract.
    """
    return dto.ScorecardOut(
        run_id=s.run_id,
        created_at=s.created_at,
        n=s.n,
        seed=s.seed,
        overall=_prob(s.overall),
        by_style=dict(s.by_style),
        by_lang=dict(s.by_lang),
        failures=[dto.RedTeamFailureOut.model_validate(f) for f in s.failures],
    )


def _prob(p: float) -> float:
    return min(max(p, 0.0), 1.0)


def ticket_out(ticket: Ticket) -> dto.TicketOut:
    """`TicketOut` of a ticket. Links that record a failed push (`error` set, D-011) are not mirrors,
    so they are left out, as in `action.external` (same rule as `frameworks/presenters.ticket_out`)."""
    return dto.TicketOut(
        id=ticket.id,
        request_id=ticket.request_id,
        incident_id=ticket.incident_id,
        office=ticket.office,
        category=ticket.category,
        priority=ticket.priority,
        status=ticket.status,
        provisional=ticket.provisional,
        sla_due_at=ticket.sla_due_at,
        escalated_at=ticket.escalated_at,
        resolved_at=ticket.resolved_at,
        title=ticket.title,
        links=external_refs(ticket),
    )


def external_refs(ticket: Ticket) -> list[dto.ExternalRefOut]:
    """The ticket's mirrors (links without an error)."""
    return [
        dto.ExternalRefOut(sink=link.sink, external_id=link.external_id, url=link.url)
        for link in ticket.links
        if link.error is None
    ]


def incident_out(incident: Incident, ticket_id: str | None, *, simulated: bool = False) -> dto.IncidentOut:
    """`IncidentOut`; `ticket_id` is the one incident ticket (None before it exists)."""
    return dto.IncidentOut(
        id=incident.id,
        building=incident.building,
        category=incident.category,
        title=incident.title,
        priority=incident.priority,
        report_count=incident.report_count,
        status=incident.status,
        member_ticket_ids=[t for t in incident.member_ticket_ids if t != ticket_id],
        ticket_id=ticket_id,
        opened_at=incident.opened_at,
        resolved_at=incident.resolved_at,
        simulated=simulated,
    )
