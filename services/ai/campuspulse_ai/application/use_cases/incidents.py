"""Pulse incidents (P4.10): merging reports into one incident, listing and resolving incidents.

`WindowedCentroidDetector` (adapters/pulse) decides *whether* a located report belongs to an
incident (D-007, D-015). This module does what follows, inside the triage flow and from the
dashboard:
- `IncidentActions.merge`: exactly one incident ticket goes through the sinks (Linear); every member
  report keeps its own ticket in the record, status `merged`, pointing at the incident; one in-app
  broadcast per reporter, through the allow-listed notifier.
- `IncidentsUseCase.list` / `.resolve`: `GET /v1/incidents`, `POST /v1/incidents/{id}/resolve`.
"""

from __future__ import annotations

import dataclasses
import logging
import uuid
from collections.abc import Iterable, Sequence
from datetime import timedelta
from typing import Literal

from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases import responses as out
from campuspulse_ai.application.use_cases.act import ActUseCase
from campuspulse_ai.application.use_cases.messages import Messages
from campuspulse_ai.application.use_cases.mirror import INCIDENT_TAG, RECORD_SINK, TicketMirror
from campuspulse_ai.application.use_cases.ports import (
    ROLE_ADMIN,
    ROLE_STAFF,
    Actor,
    LifecycleReads,
    SimulationMarks,
)
from campuspulse_ai.domain.entities import (
    Incident,
    IncidentDecision,
    OutboxMessage,
    Prediction,
    Request,
    Ticket,
)
from campuspulse_ai.domain.errors import (
    CampusPulseError,
    NotificationError,
    RecipientNotAllowed,
    StoreError,
    Unauthorized,
)
from campuspulse_ai.domain.ports import Clock, Notifier, Repository, TicketSink
from campuspulse_ai.domain.values import ActionPlan, ActionType, Lang, TicketStatus, Understanding

log = logging.getLogger(__name__)

ACTOR = "pulse"
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100
RESOLVED: Literal["resolved"] = "resolved"


class IncidentActions:
    """The action-engine side of an incident decision (ARCHITECTURE §2.1 [13]).

    `merge(decision, request, pred, plan, understanding, provisional)` -> the `ActionOut` of the
    report (type `incident_merge`), for a decision of kind `new` or `attach`:
    1. The incident ticket: on `new` one ticket (tag `incident`, priority = the incident's, title
       "<category> reports in building X") is opened through every sink (`ActUseCase.open_ticket`);
       on `attach` the existing one is re-prioritised (and mirrored) when the incident priority rose.
    2. The report's own ticket is saved in the record only (status `merged`, `incident_id` set), so
       a burst of reports makes one Linear issue, not one per student. On `new`, the earlier member
       reports' tickets are moved to `merged` too and mirrored (their Linear issues become Duplicate).
    3. Broadcast: on `new` every member reporter, on `attach` this reporter, gets one in-app message
       (allow-listed notifier chain; in-app only, since every student maps to one demo inbox).
    Sink and notifier failures degrade (logged, recorded on the link or outbox row).
    """

    def __init__(
        self,
        act: ActUseCase,
        sinks: Sequence[TicketSink],
        repo: Repository,
        reads: LifecycleReads,
        notifier: Notifier,
        clock: Clock,
        messages: Messages,
    ) -> None:
        self._act = act
        self._mirror = TicketMirror(sinks, repo)
        self._repo = repo
        self._reads = reads
        self._notifier = notifier
        self._clock = clock
        self._messages = messages

    def merge(
        self,
        decision: IncidentDecision,
        request: Request,
        pred: Prediction,
        plan: ActionPlan,
        understanding: Understanding | None,
        *,
        provisional: bool,
    ) -> dto.ActionOut:
        incident = decision.incident
        if incident is None or decision.kind == "none":
            raise ValueError("merge needs an incident decision of kind new or attach")
        incident_ticket = self._incident_ticket(decision, incident, request, plan)
        own = Ticket(
            id=str(uuid.uuid4()),
            request_id=request.id,
            incident_id=incident.id,
            office=plan.office,
            category=pred.category,
            priority=pred.priority,
            status=TicketStatus.MERGED,
            provisional=provisional,
            sla_due_at=self._clock.now() + timedelta(hours=plan.sla_hours),
            title=understanding.ticket_title if understanding else "",
            body=understanding.ticket_body if understanding else request.raw_text,
            tags=plan.tags,
        )
        self._repo.save_ticket(own)
        reporters = [request]
        if decision.kind == "new":
            reporters = self._merge_earlier(incident, decision.members, request) + [request]
        self._broadcast(incident, reporters)
        self._event("incident.merged", incident, {"request_id": request.id, "kind": decision.kind})
        lang = request.normalized.lang if request.normalized else Lang.EN
        message = self._messages.for_lang(lang).incident_merged.format(
            building=incident.building, reports=incident.report_count
        )
        return dto.ActionOut(
            type=ActionType.INCIDENT_MERGE,
            ticket_id=own.id,
            external=out.external_refs(incident_ticket) if incident_ticket else [],
            sla_due_at=incident_ticket.sla_due_at if incident_ticket else own.sla_due_at,
            message=message,
            provisional=provisional,
            tags=list(own.tags),
            booking=None,
            faq=None,
            incident_id=incident.id,
        )

    # ------------------------------------------------------------------ steps

    def _incident_ticket(
        self, decision: IncidentDecision, incident: Incident, request: Request, plan: ActionPlan
    ) -> Ticket | None:
        if decision.kind == "attach":
            current = incident_ticket(self._repo, incident.id)
            if current is not None and incident.priority.rank > current.priority.rank:
                current = dataclasses.replace(current, priority=incident.priority)
                self._repo.save_ticket(current)
                self._mirror.push(current, skip=(RECORD_SINK,))
            return current
        ticket = Ticket(
            id=str(uuid.uuid4()),
            request_id=request.id,
            incident_id=incident.id,
            office=plan.office,
            category=incident.category,
            priority=incident.priority,
            status=TicketStatus.OPEN,
            provisional=False,
            sla_due_at=self._clock.now() + timedelta(hours=plan.sla_hours),
            title=f"{incident.title} ({incident.report_count} reports)",
            body=f"Pulse incident {incident.id}: {incident.report_count} similar reports in building "
            f"{incident.building}. First report: {request.raw_text}",
            tags=(INCIDENT_TAG,),
        )
        return self._act.open_ticket(ticket)

    def _merge_earlier(self, incident: Incident, members: Sequence[str], request: Request) -> list[Request]:
        """Move the earlier members' tickets into the incident; returns their requests (reporters)."""
        earlier = [m for m in members if m != request.id]
        reporters: list[Request] = []
        for ticket in self._reads.tickets_for_requests(earlier):
            if INCIDENT_TAG in ticket.tags or ticket.incident_id is not None:
                continue
            merged = dataclasses.replace(ticket, incident_id=incident.id, status=TicketStatus.MERGED)
            self._repo.save_ticket(merged)
            self._mirror.push(merged, skip=(RECORD_SINK,))
        for request_id in earlier:
            try:
                reporters.append(self._repo.get_request(request_id))
            except StoreError as exc:
                log.warning("reporter %s not found: %s", request_id, exc)
        return reporters

    def _broadcast(self, incident: Incident, reporters: Iterable[Request]) -> int:
        sent = 0
        for alias, lang in unique_reporters(reporters):
            text = self._messages.for_lang(lang).incident_merged.format(
                building=incident.building, reports=incident.report_count
            )
            sent += self._in_app(alias, lang, text, incident)
        return sent

    def _in_app(self, alias: str, lang: Lang, text: str, incident: Incident) -> int:
        try:
            self._notifier.send(
                OutboxMessage(
                    id="",
                    kind="in_app",
                    to_address=alias,
                    subject=self._messages.for_lang(lang).update_subject,
                    body=text,
                    provider_id=None,
                    status="queued",
                    created_at=self._clock.now(),
                    priority=incident.priority,
                )
            )
        except (RecipientNotAllowed, NotificationError, StoreError) as exc:
            log.warning("broadcast to %s not sent: %s", alias, exc)
            return 0
        return 1

    def _event(self, action: str, incident: Incident, payload: dict[str, object]) -> None:
        try:
            self._repo.append_event(ACTOR, action, f"incident:{incident.id}", payload)
        except CampusPulseError as exc:
            log.warning("event %s not saved: %s", action, exc)


class IncidentsUseCase:
    """`GET /v1/incidents` and `POST /v1/incidents/{id}/resolve` (P4.10).

    - `list(open_only, office, limit)`: incidents newest first; `office` (staff callers) keeps only
      incidents whose incident ticket belongs to that office. `simulated` is true when every member
      report was simulator traffic (`requests.simulated`).
    - `resolve(incident_id, actor, note)`: admin, or staff of the incident ticket's office
      (`Unauthorized` -> 403); `NotFound` -> 404. The incident becomes `resolved`; the incident ticket
      `resolved` (mirrored: the Linear issue moves to Done); the member tickets `closed` in the record;
      every reporter gets one in-app message (and the allow-listed student inbox, if configured, one
      email). Resolving a resolved incident changes nothing and notifies nobody.
    """

    def __init__(
        self,
        reads: LifecycleReads,
        repo: Repository,
        sinks: Sequence[TicketSink],
        notifier: Notifier,
        clock: Clock,
        messages: Messages,
        *,
        marks: SimulationMarks | None = None,
        student_inbox: str | None = None,
    ) -> None:
        self._reads = reads
        self._repo = repo
        self._mirror = TicketMirror(sinks, repo)
        self._notifier = notifier
        self._clock = clock
        self._messages = messages
        self._marks = marks
        self._student_inbox = student_inbox

    def list(
        self, *, open_only: bool, office: str | None = None, limit: int = DEFAULT_LIST_LIMIT
    ) -> list[dto.IncidentOut]:
        incidents = self._reads.list_incidents(open_only=open_only, limit=min(limit, MAX_LIST_LIMIT))
        result: list[dto.IncidentOut] = []
        for incident in incidents:
            members = self._repo.incident_members(incident.id)
            ticket = next((t for t, _ in members if INCIDENT_TAG in t.tags), None)
            if office is not None and (ticket is None or ticket.office != office):
                continue
            result.append(self._out(incident, ticket, [r.id for _, r in members]))
        return result

    def resolve(self, incident_id: str, actor: Actor, note: str | None = None) -> dto.ResolveIncidentResponse:
        incident = self._reads.get_incident(incident_id)
        members = self._repo.incident_members(incident.id)
        ticket = next((t for t, _ in members if INCIDENT_TAG in t.tags), None)
        _check_staff(actor, ticket)
        if incident.status == RESOLVED:
            return dto.ResolveIncidentResponse(
                incident=self._out(incident, ticket, [r.id for _, r in members]),
                closed_ticket_ids=[],
                notified_reporters=0,
            )
        now = self._clock.now()
        closed: list[str] = []
        for member, _ in members:
            if INCIDENT_TAG in member.tags:
                done = dataclasses.replace(member, status=TicketStatus.RESOLVED, resolved_at=now)
                self._repo.save_ticket(done)
                self._mirror.push(done, skip=(RECORD_SINK,))
            elif member.status not in (TicketStatus.CLOSED, TicketStatus.RESOLVED):
                self._repo.save_ticket(
                    dataclasses.replace(member, status=TicketStatus.CLOSED, resolved_at=now)
                )
            closed.append(member.id)
        resolved = self._repo.save_incident(
            dataclasses.replace(incident, status=RESOLVED, resolved_at=now, member_ticket_ids=[])
        )
        notified = self._notify(resolved, [r for _, r in members], note)
        try:
            self._repo.append_event(actor.alias or actor.role, "incident.resolved", f"incident:{incident.id}",
                                    {"closed": len(closed), "notified": notified})  # fmt: skip
        except CampusPulseError as exc:
            log.warning("incident.resolved event not saved: %s", exc)
        return dto.ResolveIncidentResponse(
            incident=self._out(resolved, ticket, [r.id for _, r in members]),
            closed_ticket_ids=closed,
            notified_reporters=notified,
        )

    def _notify(self, incident: Incident, reporters: Sequence[Request], note: str | None) -> int:
        notified = 0
        for alias, lang in unique_reporters(reporters):
            text = self._messages.for_lang(lang).incident_resolved.format(title=incident.title)
            if note:
                text = f"{text}\n{note}"
            subject = self._messages.for_lang(lang).update_subject
            notified += self._send("in_app", alias, subject, text, incident)
        if self._student_inbox and notified:
            email = self._messages.email
            body = email.resolved_body.format(title=incident.title, ticket_id=incident.id, note=note or "")
            self._send("email", self._student_inbox, email.resolved_subject.format(title=incident.title),
                       body, incident)  # fmt: skip
        return notified

    def _send(self, kind: str, to: str, subject: str, body: str, incident: Incident) -> int:
        try:
            self._notifier.send(
                OutboxMessage(
                    id="",
                    kind="email" if kind == "email" else "in_app",
                    to_address=to,
                    subject=subject,
                    body=body,
                    provider_id=None,
                    status="queued",
                    created_at=self._clock.now(),
                    priority=incident.priority,
                )
            )
        except (RecipientNotAllowed, NotificationError, StoreError) as exc:
            log.warning("%s to %s not sent: %s", kind, to, exc)
            return 0
        return 1

    def _out(self, incident: Incident, ticket: Ticket | None, request_ids: Sequence[str]) -> dto.IncidentOut:
        simulated = False
        if self._marks is not None and request_ids:
            try:
                simulated = set(request_ids) <= self._marks.simulated(request_ids)
            except StoreError as exc:
                log.warning("simulated marks unavailable: %s", exc)
        return out.incident_out(incident, ticket.id if ticket else None, simulated=simulated)


def incident_ticket(repo: Repository, incident_id: str) -> Ticket | None:
    """The one ticket tracking an incident (tag `incident`), or None."""
    return next((t for t, _ in repo.incident_members(incident_id) if INCIDENT_TAG in t.tags), None)


def unique_reporters(reporters: Iterable[Request]) -> list[tuple[str, Lang]]:
    """(alias, lang) of each distinct reporter with an alias, in order."""
    seen: dict[str, Lang] = {}
    for r in reporters:
        alias = r.alias.strip()
        if alias and alias not in seen:
            seen[alias] = r.normalized.lang if r.normalized else Lang.EN
    return list(seen.items())


def _check_staff(actor: Actor, ticket: Ticket | None) -> None:
    if actor.role == ROLE_ADMIN:
        return
    if actor.role == ROLE_STAFF and ticket is not None and actor.office == ticket.office:
        return
    raise Unauthorized(f"role {actor.role!r} of office {actor.office!r} may not resolve this incident")
