"""ActUseCase: the action engine (SPEC §5.1 [11]-[12], ARCHITECTURE §2.1 [11], P3.9 v0 + P4.8).

It turns a decided prediction into what happens next: a retrieved FAQ answer, a ticket in Supabase
and Linear, an advisor booking, or a safety alert. Every side effect degrades instead of failing the
request (LD-15): a sink error is kept on the ticket link (`ticket_links.last_error`), a notification
error on its outbox row (written by `AllowlistedNotifier`), and a calendar error falls back to the
ticket alone.
"""

from __future__ import annotations

import dataclasses
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from campuspulse_ai.application import dto
from campuspulse_ai.application.use_cases.messages import Messages, StudentMessages
from campuspulse_ai.application.use_cases.mirror import FAILED_LINK_PREFIX, RECORD_SINK, TicketMirror
from campuspulse_ai.domain.entities import Case, CoreResult, OutboxMessage, Prediction, Request, Ticket
from campuspulse_ai.domain.errors import (
    CalendarUnavailable,
    NotificationError,
    RecipientNotAllowed,
    SinkError,
    StoreError,
)
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.policy import RecipientPolicy
from campuspulse_ai.domain.ports import (
    ActionPlanner,
    CalendarProvider,
    Clock,
    FAQRetriever,
    Notifier,
    Repository,
    TicketSink,
)
from campuspulse_ai.domain.routing import DEFERRED_TAG_PREFIX, SAFETY_FLAG
from campuspulse_ai.domain.values import (
    ActionPlan,
    ActionType,
    Advisor,
    Booking,
    FAQHit,
    Lang,
    OfficeHours,
    TicketLink,
    TicketStatus,
    Understanding,
)

log = logging.getLogger(__name__)

TRANSPORT_ALERT_TAG = "transport-alert"
"""`config/actions.yaml` Transportation x high: the ticket also alerts the transport office."""
ACTOR = "act"
_ACT_KEYS = frozenset({"version", "faq_top_k", "booking"})
_BOOKING_KEYS = frozenset({"department", "office_hours"})
_HOURS_KEYS = frozenset({"tz", "weekdays", "start", "end"})
_LAST_WEEKDAY = 6  # Monday = 0 ... Sunday = 6 (datetime.weekday)


@dataclass(frozen=True, slots=True)
class ActConfig:
    """Non-routing action settings: `config/act.yaml` plus the demo inboxes from Settings.

    - `faq_top_k`: FAQ hits fetched; the best is used when its score >= `tau_faq`.
    - `booking_department` / `office_hours`: whose advisors are booked and when (UD-1).
    - `student_inbox` (`DEMO_STUDENT_INBOX`): the allow-listed demo inbox that stands in for every
      student's email; None = no student emails and the advisor is the only booking attendee.
    - `office_inbox` (`DEMO_OFFICE_INBOX`): the allow-listed demo inbox for safety and transport
      alerts; None = alerts are not emailed (the ticket still carries them).
    """

    faq_top_k: int
    booking_department: str
    office_hours: OfficeHours
    student_inbox: str | None = None
    office_inbox: str | None = None

    @classmethod
    def from_dict(
        cls, data: Mapping[str, object], *, student_inbox: str | None = None, office_inbox: str | None = None
    ) -> ActConfig:
        """Validate a parsed `config/act.yaml`. Raises `ValueError` naming the bad key."""
        _keys(data, _ACT_KEYS, "act.yaml", {"faq_top_k", "booking"})
        k = data["faq_top_k"]
        if isinstance(k, bool) or not isinstance(k, int) or k < 1:
            raise ValueError("act.yaml: faq_top_k must be a positive integer")
        booking = _mapping(data["booking"], "booking")
        _keys(booking, _BOOKING_KEYS, "booking", _BOOKING_KEYS)
        department = booking["department"]
        if not isinstance(department, str) or not department:
            raise ValueError("booking.department must be a non-empty string")
        hours = _mapping(booking["office_hours"], "booking.office_hours")
        _keys(hours, _HOURS_KEYS, "booking.office_hours", _HOURS_KEYS)
        weekdays = hours["weekdays"]
        if (
            not isinstance(weekdays, list)
            or not weekdays
            or not all(
                isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= _LAST_WEEKDAY for d in weekdays
            )
        ):
            raise ValueError("booking.office_hours.weekdays must list weekday numbers 0-6 (Monday = 0)")
        tz = hours["tz"]
        if not isinstance(tz, str) or not tz:
            raise ValueError("booking.office_hours.tz must be an IANA zone name")
        ZoneInfo(tz)  # raises for an unknown zone
        start, end = _clock_time(hours["start"], "start"), _clock_time(hours["end"], "end")
        if start >= end:
            raise ValueError("booking.office_hours.start must be before end")
        return cls(
            faq_top_k=k,
            booking_department=department,
            office_hours=OfficeHours(tz=tz, weekdays=tuple(weekdays), start=start, end=end),
            student_inbox=student_inbox or None,
            office_inbox=office_inbox or None,
        )


@dataclass(frozen=True, slots=True)
class _Ctx:
    """What one action needs to know about its request."""

    request: Request
    lang: Lang
    text: str
    category: Category
    priority: Priority
    provisional: bool
    understanding: Understanding | None
    building: str | None


class ActUseCase:
    """The action engine (implements ARCHITECTURE §2.1 [11]-[12]).

    `run(pred, req, provisional, understanding)` plans with `ActionPlanner` (prediction flags plus the
    fired evidence names, `config/actions.yaml`) and returns the `ActionOut` of the response:
    - `faq_answer`: the best FAQ hit when its score >= `tau_faq` -> the retrieved answer, its source
      and `[demo]` (never generated text); otherwise a ticket and "I'm not sure…".
    - `ticket`: a ticket (below). Tag `transport-alert` also emails the office inbox, unless
      provisional (it then waits for `finalize`).
    - `booking` (Academic Support x high, never provisional): a ticket, then the earliest advisor slot
      within the SLA window and office hours; every attendee is checked with `RecipientPolicy` before
      `CalendarProvider.book`; a `cases` row and a confirmation email to each attendee. No slot, a
      calendar error or a refused attendee -> the ticket alone (`type: ticket`, "couldn't book").
    - `safety_alert` (flag `safety` or Facilities x high): always fires, even provisional: an alert
      email to the office inbox ("call campus security now (demo)") and a ticket tagged `safety`
      (Linear priority 1).

    A ticket gets `sla_due_at = now + sla_hours`, title/body from the understanding (UD-10; else the
    request text) and the plan's tags. It is saved through the repository first (the record), then
    pushed to each sink in order; a `SinkError` becomes a link with `error` (stored as
    `ticket_links.last_error`) and the next sink still runs. The student gets one in-app message with
    `understanding.student_reply` when the request has an alias.

    `open_ticket(ticket)` saves a ready-made ticket and pushes it to the sinks (the incident ticket).

    `finalize(ticket)` runs after staff confirm a provisional ticket: it re-plans from the ticket's
    (possibly corrected) labels, clears the `unconfirmed`/`deferred:*` tags, mirrors the change to the
    sinks and fires what was deferred (booking, transport alert; a safety alert only if it did not
    fire already). It returns one `ActionOut` per fired action ([] if nothing was deferred).

    Errors: nothing from a sink, notifier, calendar or FAQ store escapes (each is logged and recorded);
    `finalize` raises `NotFound` for an unknown request.
    """

    def __init__(
        self,
        planner: ActionPlanner,
        faq: FAQRetriever,
        sinks: Sequence[TicketSink],
        calendar: CalendarProvider,
        notifier: Notifier,
        recipients: RecipientPolicy,
        repo: Repository,
        clock: Clock,
        *,
        tau_faq: float,
        config: ActConfig,
        messages: Messages,
    ) -> None:
        self._planner = planner
        self._faq = faq
        self._sinks = tuple(sinks)
        self._mirror = TicketMirror(self._sinks, repo)
        self._calendar = calendar
        self._notifier = notifier
        self._recipients = recipients
        self._repo = repo
        self._clock = clock
        self._tau_faq = tau_faq
        self._config = config
        self._messages = messages

    # ------------------------------------------------------------------ public

    def plan_for(self, pred: Prediction, provisional: bool) -> ActionPlan:
        """The routing plan for `pred` (pure): its flags plus `safety` and the fired evidence names."""
        flags = frozenset(pred.flags) | fired_evidence(pred.core)
        if pred.core.safety:
            flags |= {SAFETY_FLAG}
        return self._planner.plan(pred.category, pred.priority, flags, provisional)

    def run(
        self, pred: Prediction, req: Request, provisional: bool, understanding: Understanding | None = None
    ) -> dto.ActionOut:
        plan = self.plan_for(pred, provisional)
        normalized = req.normalized
        location = normalized.location if normalized else None
        ctx = _Ctx(
            request=req,
            lang=normalized.lang if normalized else Lang.EN,
            text=normalized.core if normalized else req.raw_text,
            category=pred.category,
            priority=pred.priority,
            provisional=provisional,
            understanding=understanding,
            building=(location.building if location else None)
            or (understanding.entities.building if understanding else None),
        )
        if plan.kind == ActionType.FAQ_ANSWER:
            return self._faq_answer(plan, ctx)
        if plan.kind == ActionType.BOOKING:
            return self._booking(plan, ctx)
        if plan.kind == ActionType.SAFETY_ALERT:
            return self._safety(plan, ctx)
        return self._ticket_only(plan, ctx)

    def finalize(self, ticket: Ticket) -> list[dto.ActionOut]:
        if not ticket.provisional:
            return []
        request = self._repo.get_request(ticket.request_id)
        normalized = request.normalized
        flags = frozenset({SAFETY_FLAG}) if SAFETY_FLAG in ticket.tags else frozenset()
        plan = self._planner.plan(ticket.category, ticket.priority, flags, provisional=False)
        provisional_only = set(self._planner.plan(ticket.category, ticket.priority, flags, True).tags) - set(
            plan.tags
        )
        kept = [t for t in ticket.tags if t not in provisional_only and not t.startswith(DEFERRED_TAG_PREFIX)]
        confirmed = dataclasses.replace(
            ticket, provisional=False, tags=tuple(dict.fromkeys((*plan.tags, *kept)))
        )
        self._save_record(confirmed)
        self._mirror.push(confirmed)
        ctx = _Ctx(
            request=request,
            lang=normalized.lang if normalized else Lang.EN,
            text=normalized.core if normalized else request.raw_text,
            category=confirmed.category,
            priority=confirmed.priority,
            provisional=False,
            understanding=None,
            building=normalized.location.building if normalized and normalized.location else None,
        )
        msgs = self._messages.for_lang(ctx.lang)
        fired: list[dto.ActionOut] = []
        if plan.kind == ActionType.BOOKING:
            booked = self._book(plan, confirmed, ctx)
            fired.append(self._booking_out(plan, confirmed, booked, msgs))
        elif plan.kind == ActionType.SAFETY_ALERT and SAFETY_FLAG not in ticket.tags:
            self._alert_safety(confirmed, ctx)
            fired.append(_action(ActionType.SAFETY_ALERT, confirmed, msgs.safety.format(office=plan.office)))
        if TRANSPORT_ALERT_TAG in plan.tags:
            self._alert_transport(confirmed, ctx)
            fired.append(_action(ActionType.TICKET, confirmed, self._ticket_message(ctx, msgs)))
        self._event("act.finalized", confirmed, {"fired": [str(a.type) for a in fired]})
        return fired

    # ------------------------------------------------------------------ action kinds

    def _faq_answer(self, plan: ActionPlan, ctx: _Ctx) -> dto.ActionOut:
        msgs = self._messages.for_lang(ctx.lang)
        best = self._best_faq(ctx)
        if best is not None:
            parts = [best.answer]
            if best.source_url:
                parts.append(msgs.faq_source.format(source=best.source_url))
            message = "\n".join(parts) + (f" {msgs.demo_marker}" if best.is_demo else "")
            faq = dto.FaqAnswerOut(
                question=best.question,
                answer=best.answer,
                source_url=best.source_url,
                is_demo=best.is_demo,
                score=min(max(best.score, 0.0), 1.0),
            )
            return dto.ActionOut(
                type=ActionType.FAQ_ANSWER,
                ticket_id=None,
                external=[],
                sla_due_at=None,
                message=message,
                provisional=False,
                tags=list(plan.tags),
                booking=None,
                faq=faq,
                incident_id=None,
            )
        ticket = self._open_ticket(plan, ctx)
        self._notify_student(ctx, msgs.faq_unsure)
        return _action(ActionType.TICKET, ticket, msgs.faq_unsure)

    def _ticket_only(self, plan: ActionPlan, ctx: _Ctx) -> dto.ActionOut:
        msgs = self._messages.for_lang(ctx.lang)
        ticket = self._open_ticket(plan, ctx)
        message = self._ticket_message(ctx, msgs)
        self._notify_student(ctx, message)
        if TRANSPORT_ALERT_TAG in plan.tags and not ctx.provisional:
            self._alert_transport(ticket, ctx)
        return _action(ActionType.TICKET, ticket, message)

    def _booking(self, plan: ActionPlan, ctx: _Ctx) -> dto.ActionOut:
        msgs = self._messages.for_lang(ctx.lang)
        ticket = self._open_ticket(plan, ctx)
        booked = self._book(plan, ticket, ctx)
        out = self._booking_out(plan, ticket, booked, msgs)
        self._notify_student(ctx, out.message)
        return out

    def _safety(self, plan: ActionPlan, ctx: _Ctx) -> dto.ActionOut:
        msgs = self._messages.for_lang(ctx.lang)
        ticket = self._open_ticket(plan, ctx)
        self._alert_safety(ticket, ctx)
        message = msgs.safety.format(office=plan.office)
        self._notify_student(ctx, message)
        return _action(ActionType.SAFETY_ALERT, ticket, message)

    # ------------------------------------------------------------------ building blocks

    def _best_faq(self, ctx: _Ctx) -> FAQHit | None:
        try:
            hits = self._faq.search(ctx.text, ctx.lang, self._config.faq_top_k)
        except StoreError as exc:
            log.warning("FAQ search failed, opening a ticket instead: %s", exc)
            return None
        best = max(hits, key=lambda h: h.score, default=None)
        return best if best is not None and best.score >= self._tau_faq else None

    def _open_ticket(self, plan: ActionPlan, ctx: _Ctx) -> Ticket:
        u = ctx.understanding
        ticket = Ticket(
            id=str(uuid.uuid4()),
            request_id=ctx.request.id,
            incident_id=None,
            office=plan.office,
            category=ctx.category,
            priority=ctx.priority,
            status=TicketStatus.OPEN,
            provisional=ctx.provisional,
            sla_due_at=self._clock.now() + timedelta(hours=plan.sla_hours),
            title=u.ticket_title if u else "",
            body=u.ticket_body if u else ctx.request.raw_text,
            tags=plan.tags,
        )
        return self.open_ticket(ticket)

    def open_ticket(self, ticket: Ticket) -> Ticket:
        """Save `ticket` (the record), then create it in every sink in order; returns it with its
        mirror links. A `SinkError` becomes a link with `error` and the next sink still runs. Also
        used for the one ticket of a Pulse incident (`IncidentActions`)."""
        self._save_record(ticket)
        links: list[TicketLink] = []
        for sink in self._sinks:
            try:
                link = sink.create(ticket)
            except SinkError as exc:
                log.warning("sink %s failed for ticket %s: %s", sink.name, ticket.id, exc)
                link = TicketLink(ticket.id, sink.name, f"{FAILED_LINK_PREFIX}{ticket.id}", None, str(exc))
            if link.sink != RECORD_SINK:
                links.append(link)
        ticket.links = links
        for link in links:
            self._save_link(link)
        self._event("act.ticket", ticket, {"office": ticket.office, "tags": list(ticket.tags)})
        return ticket

    def _book(self, plan: ActionPlan, ticket: Ticket, ctx: _Ctx) -> tuple[Booking, Advisor] | None:
        """The booking and its advisor, or None (no advisor, no slot, a calendar or allow-list refusal)."""
        try:
            advisors = {a.id: a for a in self._repo.advisors_for(self._config.booking_department)}
        except StoreError as exc:
            log.warning("advisors unavailable: %s", exc)
            return None
        if not advisors:
            return None
        now = self._clock.now()
        window = (now, now + timedelta(hours=plan.sla_hours))
        try:
            slot = self._calendar.find_slot(list(advisors), window, self._config.office_hours)
        except CalendarUnavailable as exc:
            log.warning("calendar unavailable: %s", exc)
            return None
        if slot is None or slot.advisor_id not in advisors:
            return None
        advisor = advisors[slot.advisor_id]
        attendees = [a for a in (self._config.student_inbox, advisor.email) if a]
        try:
            for address in attendees:
                self._recipients.check(address)  # before the calendar is touched (ARCHITECTURE §3.13)
        except RecipientNotAllowed as exc:
            self._event("act.booking_refused", ticket, {"reason": str(exc)})
            return None
        title = ticket.title or f"{ctx.category} ({ctx.priority})"
        try:
            booking = self._calendar.book(slot, attendees, title)
        except (CalendarUnavailable, RecipientNotAllowed) as exc:
            log.warning("booking failed: %s", exc)
            return None
        try:
            self._repo.save_case(
                Case(id="", request_id=ctx.request.id, ticket_id=ticket.id, booking=booking, created_at=now)
            )
        except StoreError as exc:
            log.warning("case row not saved: %s", exc)
        email = self._messages.email
        for address in attendees:
            self._send(
                OutboxMessage(
                    id="",
                    kind="email",
                    to_address=address,
                    subject=email.booking_subject.format(title=title),
                    body=email.booking_body.format(
                        advisor=advisor.name,
                        starts_at=self._local(booking.slot.starts_at),
                        ends_at=self._local(booking.slot.ends_at),
                        ticket_id=ticket.id,
                        text=ctx.text,
                    ),
                    provider_id=None,
                    status="queued",
                    created_at=now,
                    priority=ctx.priority,
                )
            )
        self._event("act.booking", ticket, {"slot_id": slot.id, "advisor_id": advisor.id})
        return booking, advisor

    def _booking_out(
        self, plan: ActionPlan, ticket: Ticket, booked: tuple[Booking, Advisor] | None, msgs: StudentMessages
    ) -> dto.ActionOut:
        if booked is None:
            return _action(ActionType.TICKET, ticket, msgs.booking_unavailable)
        booking, advisor = booked
        message = msgs.booking_confirmed.format(
            advisor=advisor.name, starts_at=self._local(booking.slot.starts_at)
        )
        out = _action(ActionType.BOOKING, ticket, message)
        return out.model_copy(
            update={
                "booking": dto.BookingOut(
                    advisor_name=advisor.name,
                    starts_at=booking.slot.starts_at,
                    ends_at=booking.slot.ends_at,
                    room=None,
                )
            }
        )

    def _alert_safety(self, ticket: Ticket, ctx: _Ctx) -> None:
        email = self._messages.email
        self._alert(
            email.safety_subject.format(category=ctx.category, building=ctx.building or "?"),
            email.safety_body.format(building=ctx.building or "?", ticket_id=ticket.id, text=ctx.text),
            ticket,
            "act.safety_alert",
        )

    def _alert_transport(self, ticket: Ticket, ctx: _Ctx) -> None:
        email = self._messages.email
        title = ticket.title or f"{ctx.category} ({ctx.priority})"
        self._alert(
            email.transport_subject.format(title=title),
            email.transport_body.format(ticket_id=ticket.id, text=ctx.text),
            ticket,
            "act.transport_alert",
        )

    def _alert(self, subject: str, body: str, ticket: Ticket, action: str) -> None:
        inbox = self._config.office_inbox
        if inbox:
            self._send(
                OutboxMessage(
                    id="",
                    kind="email",
                    to_address=inbox,
                    subject=subject,
                    body=body,
                    provider_id=None,
                    status="queued",
                    created_at=self._clock.now(),
                    priority=Priority.HIGH,
                    flags=frozenset({SAFETY_FLAG}) if SAFETY_FLAG in ticket.tags else frozenset(),
                )
            )
        self._event(action, ticket, {"emailed": bool(inbox)})

    def _notify_student(self, ctx: _Ctx, fallback: str) -> None:
        alias = ctx.request.alias.strip()
        if not alias:
            return
        text = ctx.understanding.student_reply if ctx.understanding else fallback
        self._send(
            OutboxMessage(
                id="",
                kind="in_app",
                to_address=alias,
                subject=self._messages.for_lang(ctx.lang).update_subject,
                body=text,
                provider_id=None,
                status="queued",
                created_at=self._clock.now(),
                priority=ctx.priority,
            )
        )

    def _ticket_message(self, ctx: _Ctx, msgs: StudentMessages) -> str:
        if ctx.understanding is not None:
            return ctx.understanding.student_reply
        return msgs.ticket_opened.format(category=ctx.category)

    def _send(self, msg: OutboxMessage) -> None:
        """Send through the notifier chain; refusals and failures are already on the outbox row."""
        try:
            self._notifier.send(msg)
        except (RecipientNotAllowed, NotificationError, StoreError) as exc:
            log.warning("%s message to %s not sent: %s", msg.kind, msg.to_address, exc)

    def _save_record(self, ticket: Ticket) -> None:
        try:
            self._repo.save_ticket(ticket)
        except StoreError as exc:
            log.error("ticket %s not saved: %s", ticket.id, exc)

    def _save_link(self, link: TicketLink) -> None:
        try:
            self._repo.save_ticket_link(link)
        except StoreError as exc:
            log.warning("link %s/%s not saved: %s", link.sink, link.ticket_id, exc)

    def _event(self, action: str, ticket: Ticket, payload: Mapping[str, object]) -> None:
        try:
            self._repo.append_event(ACTOR, action, f"ticket:{ticket.id}", payload)
        except StoreError as exc:
            log.warning("event %s not saved: %s", action, exc)

    def _local(self, at: datetime) -> str:
        return at.astimezone(ZoneInfo(self._config.office_hours.tz)).strftime("%Y-%m-%d %H:%M")


def fired_evidence(core: CoreResult) -> frozenset[str]:
    """Names of the evidence features that fired (routing uses them, e.g. `exam_now`)."""
    return frozenset(name for name, on in core.evidence.flags.items() if on)


def _action(kind: ActionType, ticket: Ticket, message: str) -> dto.ActionOut:
    return dto.ActionOut(
        type=kind,
        ticket_id=ticket.id,
        external=[
            dto.ExternalRefOut(sink=link.sink, external_id=link.external_id, url=link.url)
            for link in ticket.links
            if link.error is None
        ],
        sla_due_at=ticket.sla_due_at,
        message=message,
        provisional=ticket.provisional,
        tags=list(ticket.tags),
        booking=None,
        faq=None,
        incident_id=ticket.incident_id,
    )


def _keys(
    raw: Mapping[str, object], allowed: frozenset[str], where: str, required: frozenset[str] | set[str]
) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {unknown}")
    missing = sorted(set(required) - set(raw))
    if missing:
        raise ValueError(f"{where}: missing key(s) {missing}")


def _mapping(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(k, str) for k in value):
        raise ValueError(f"{where} must be a mapping with string keys")
    return value


def _clock_time(value: object, where: str) -> time:
    if not isinstance(value, str):
        raise ValueError(f"booking.office_hours.{where} must be HH:MM")
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise ValueError(f"booking.office_hours.{where} must be HH:MM, got {value!r}") from None
