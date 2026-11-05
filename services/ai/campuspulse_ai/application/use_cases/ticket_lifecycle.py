"""TicketLifecycleUseCase: comments, notes, status, forward, priority and requester actions (P9.3).

The state machine is table (d) of `docs/plan/p9/PLAN.md`. Every action loads the ticket and its
request, decides the caller's role, checks the transition, saves the ticket, writes one thread row
(`ticket_activity`), audits an `events` row and returns a `LifecycleChange` that holds the planned
emails. Two steps, like the old `SyncTicketUseCase`:

1. the action (the route waits for it); errors: `Unauthorized` 403, `InvalidInput` 422 (a transition
   the table does not allow reads `transition <from> -> <to> not allowed`), `NotFound` 404,
   `StoreError` 503;
2. `deliver(change)` (a background task): mirror to the sinks, in-app notes, then the emails through
   `TicketMailer`. Never raises.

Roles: "requester" is the caller whose alias owns the request (any role; it wins, so staff never work
their own request as staff), "office" is staff of the ticket's office, "admin" is an admin.
Every clock restart sets `clock_started_at`, `sla_due_at`, `reminder_sent_at = None`, `reminder_count = 0`.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Any, Literal

from campuspulse_ai.application.use_cases.file_ports import FileStore
from campuspulse_ai.application.use_cases.journey_ports import JourneyStore
from campuspulse_ai.application.use_cases.messages import Messages
from campuspulse_ai.application.use_cases.mirror import RECORD_SINK, TicketMirror, relabelled
from campuspulse_ai.application.use_cases.offices import OfficeMap
from campuspulse_ai.application.use_cases.ports import ROLE_ADMIN, ROLE_STAFF, USER_ROLES, Actor
from campuspulse_ai.application.use_cases.reviews import notify_forward
from campuspulse_ai.application.use_cases.sync_ticket import ticket_title
from campuspulse_ai.application.use_cases.ticket_emails import (
    Audience,
    EmailContext,
    EmailEvent,
    TicketMailer,
)
from campuspulse_ai.application.use_cases.ticket_files import validate_attachments
from campuspulse_ai.domain.entities import Request, Ticket
from campuspulse_ai.domain.errors import InvalidInput, NotFound, StoreError, Unauthorized
from campuspulse_ai.domain.journey import (
    ActivityKind,
    Contact,
    StudentAction,
    TicketActivity,
    TicketHint,
    Visibility,
)
from campuspulse_ai.domain.labels import Category, Priority
from campuspulse_ai.domain.ports import Clock, Repository, SentenceEncoder, TicketSink
from campuspulse_ai.domain.values import TicketStatus

log = logging.getLogger(__name__)

Role = Literal["requester", "office", "admin"]
ACTOR = "ticket_lifecycle"
FORWARDED_TAG = "forwarded"
"""Added to a forwarded ticket: the admin inbox then also gets the requester's replies."""
NOTIFICATION_KIND = "ticket_status"
"""docs/api/README.md › Notifications payload: `{ticket_id, status, title, message?}`."""
RUNNING = frozenset({TicketStatus.NEW, TicketStatus.IN_PROGRESS})
DONE = frozenset({TicketStatus.SOLVED, TicketStatus.CLOSED})
BODY_MAX = 4000
PAST_CORRECTION = "past correction"
SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class PlannedEmail:
    """One email to send after the response: the template, the address (None = skipped) and its context."""

    event: EmailEvent
    audience: Audience
    ctx: EmailContext
    to: str | tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class LifecycleChange:
    """One applied action. `activity` is None for a no-op (same status, same priority).

    `mirror`: push the ticket to the sinks; `requester_note`: in-app note for the requester (a message
    text, or "" for none); `from_office`: set when the ticket moved offices (the new office is told).
    """

    ticket: Ticket
    activity: TicketActivity | None
    emails: tuple[PlannedEmail, ...] = ()
    mirror: bool = False
    requester_alias: str = ""
    notify_requester: bool = False
    message: str = ""
    from_office: str | None = None


class TicketLifecycleUseCase:
    def __init__(
        self,
        repo: Repository,
        journey: JourneyStore,
        mailer: TicketMailer,
        sinks: Sequence[TicketSink],
        clock: Clock,
        sla_hours: Mapping[Priority, int],
        offices: OfficeMap,
        messages: Messages,
        encoder: SentenceEncoder | None = None,
        files: FileStore | None = None,
    ) -> None:
        self._repo = repo
        self._journey = journey
        self._mailer = mailer
        self._mirror = TicketMirror(sinks, self._repo)
        self._clock = clock
        self._sla = dict(sla_hours)
        self._offices = offices
        self._messages = messages
        self._encoder = encoder
        self._files = files

    # ------------------------------------------------------------------ actions

    def comment(
        self,
        ticket_id: str,
        actor: Actor,
        body: str,
        internal: bool = False,
        status: TicketStatus | None = None,
        file_ids: Sequence[str] = (),
    ) -> LifecycleChange:
        """Rows 2-4 and 11-12 (a staff comment with a status is a status change, rows 5-8).

        `file_ids` (P9.10): files the caller already uploaded to this ticket; they are checked first (422),
        linked to the new thread row, and counted in the email's files line."""
        attach: list[str] = []
        if file_ids:
            if self._files is None:
                raise InvalidInput("files are not available in this deployment")
            attach = validate_attachments(self._files, ticket_id, actor, file_ids, internal)
        change = self._comment(ticket_id, actor, body, internal, status)
        if attach and self._files is not None and change.activity is not None:
            self._files.attach(attach, change.activity.id)
            n = len(attach)
            counted = tuple(
                dataclasses.replace(e, ctx=dataclasses.replace(e.ctx, files=n)) for e in change.emails
            )
            change = dataclasses.replace(change, emails=counted)
        return change

    def _comment(
        self, ticket_id: str, actor: Actor, body: str, internal: bool, status: TicketStatus | None
    ) -> LifecycleChange:
        ticket, request = self._load(ticket_id)
        role = self._role(actor, ticket, request)
        text = self._text(body)
        if role == "requester":
            if internal or status is not None:
                raise Unauthorized("a requester can only add a public comment")
            return self._requester_comment(ticket, request, actor, text)
        if internal:
            if status is not None:
                raise InvalidInput("an internal note cannot change the status")
            return self._note(ticket, request, actor, text)
        if status is not None and status != ticket.status:
            return self._staff_status(ticket, request, actor, status, text)
        return self._staff_comment(ticket, request, actor, text)

    def change_status(
        self, ticket_id: str, actor: Actor, status: TicketStatus, note: str | None = None
    ) -> LifecycleChange:
        """Rows 5-8. Same status: a no-op, or a plain comment when there is a note."""
        ticket, request = self._load(ticket_id)
        role = self._role(actor, ticket, request)
        if role == "requester":
            raise Unauthorized("you cannot act as staff on your own request")
        text = (note or "").strip()
        if status == ticket.status:
            if not text:
                return LifecycleChange(ticket, None)
            return self._staff_comment(ticket, request, actor, self._text(text))
        return self._staff_status(ticket, request, actor, status, self._text(text) if text else "")

    def forward(self, ticket_id: str, actor: Actor, office: str, note: str | None = None) -> LifecycleChange:
        """Row 9: new office and category, status `new`, clock restarts; one hint row."""
        ticket, request = self._load(ticket_id)
        self._staff_only(self._role(actor, ticket, request))
        target = office.strip()
        category = self._offices.category_for(target)  # InvalidInput for an unknown office
        if ticket.status not in RUNNING:
            raise InvalidInput(f"transition {ticket.status} -> new not allowed")
        if target == ticket.office:
            raise InvalidInput(f"ticket {ticket.id} is already in office {target!r}")
        now = self._clock.now()
        text = (note or "").strip()
        tags = tuple(dict.fromkeys((*ticket.tags, FORWARDED_TAG)))
        moved = relabelled(ticket, category, ticket.priority, office=target, tags=tags)
        updated = self._save(
            dataclasses.replace(
                moved, status=TicketStatus.NEW, awaiting_student=False, **self._restart(ticket.priority, now)
            )
        )
        activity = self._activity(
            updated, ActivityKind.FORWARD, actor, now, body=text,
            from_office=ticket.office, to_office=target,
            from_status=str(ticket.status), to_status=str(updated.status),
        )  # fmt: skip
        self._audit(
            actor, "ticket.forwarded", updated, {"from": ticket.office, "to": target, "note": text or None}
        )
        self._hint("forward", updated, request, actor, text)
        contact = self._contact(request.alias)
        emails = (
            self._email(EmailEvent.FORWARDED, "requester", updated, request, contact, note=text,
                        from_office=ticket.office, to_office=target),
            self._email(EmailEvent.FORWARDED, "office", updated, request, contact, note=text,
                        from_office=ticket.office, to_office=target),
        )  # fmt: skip
        return LifecycleChange(updated, activity, emails, mirror=True, from_office=ticket.office)

    def change_priority(
        self, ticket_id: str, actor: Actor, priority: Priority, note: str | None = None
    ) -> LifecycleChange:
        """Row 10: the clock restarts with the new period; one hint row; no email. Same priority: no-op."""
        ticket, request = self._load(ticket_id)
        self._staff_only(self._role(actor, ticket, request))
        if ticket.status not in RUNNING:
            raise InvalidInput(f"transition {ticket.status} -> {ticket.status} not allowed")
        if priority == ticket.priority:
            return LifecycleChange(ticket, None)
        now = self._clock.now()
        text = (note or "").strip()
        updated = self._save(
            dataclasses.replace(relabelled(ticket, ticket.category, priority), **self._restart(priority, now))
        )
        activity = self._activity(
            updated, ActivityKind.PRIORITY, actor, now, body=text,
            from_priority=str(ticket.priority), to_priority=str(priority),
        )  # fmt: skip
        self._audit(actor, "ticket.priority", updated, {"from": str(ticket.priority), "to": str(priority)})
        self._hint("priority", updated, request, actor, text)
        return LifecycleChange(updated, activity, (), mirror=True)

    def student_action(self, ticket_id: str, actor: Actor, action: StudentAction) -> LifecycleChange:
        """Rows 13-15 (the requester only)."""
        ticket, request = self._load(ticket_id)
        if self._role(actor, ticket, request) != "requester":
            raise Unauthorized("only the requester can use these buttons")
        src = ticket.status
        now = self._clock.now()
        changes: dict[str, Any]
        event: EmailEvent
        if action == StudentAction.SOLVED:
            if src not in (TicketStatus.IN_PROGRESS, TicketStatus.SOLVED):
                raise InvalidInput(f"transition {src} -> solved not allowed")
            if src == TicketStatus.SOLVED and not ticket.awaiting_student:
                return LifecycleChange(ticket, None)
            changes, event = {"status": TicketStatus.SOLVED, "awaiting_student": False}, EmailEvent.SOLVED
            changes["resolved_at"] = ticket.resolved_at or now
        elif action == StudentAction.CLOSE:
            if src == TicketStatus.CLOSED:
                return LifecycleChange(ticket, None)
            if src not in (TicketStatus.NEW, TicketStatus.IN_PROGRESS, TicketStatus.SOLVED):
                raise InvalidInput(f"transition {src} -> closed not allowed")
            changes, event = {"status": TicketStatus.CLOSED, "awaiting_student": False}, EmailEvent.CLOSED
            changes["resolved_at"] = ticket.resolved_at or now
        else:
            waiting = src == TicketStatus.IN_PROGRESS and ticket.awaiting_student
            if not (waiting or src == TicketStatus.SOLVED):
                raise InvalidInput(f"transition {src} -> in_progress not allowed")
            changes = {"status": TicketStatus.IN_PROGRESS, "awaiting_student": False, "resolved_at": None}
            changes.update(self._restart(ticket.priority, now))
            event = EmailEvent.REOPENED
        updated = self._save(dataclasses.replace(ticket, **changes))
        activity = self._activity(
            updated, ActivityKind.STUDENT_ACTION, actor, now, body=str(action),
            from_status=str(src), to_status=str(updated.status),
        )  # fmt: skip
        self._audit(actor, "ticket.student_action", updated, {"action": str(action), "from": str(src)})
        contact = self._contact(request.alias)
        emails = (self._email(event, "office", updated, request, contact),)
        return LifecycleChange(updated, activity, emails, mirror=src != updated.status)

    def apply_hint(self, ticket_id: str, category: Category, priority: Priority) -> LifecycleChange:
        """Row 17: a past correction re-routes a new ticket (system actor; raise-only priority; no hint)."""
        ticket, request = self._load(ticket_id)
        self._not_merged(ticket)
        if ticket.status != TicketStatus.NEW:
            raise InvalidInput(f"transition {ticket.status} -> new not allowed")
        office = self._offices.office_for(category)
        raised = max(ticket.priority, priority, key=lambda p: p.rank)
        if office == ticket.office and raised == ticket.priority:
            return LifecycleChange(ticket, None)
        now = self._clock.now()
        moved = relabelled(ticket, category, raised, office=office)
        updated = self._save(dataclasses.replace(moved, awaiting_student=False, **self._restart(raised, now)))
        by = _SystemActor()
        kind = ActivityKind.FORWARD if office != ticket.office else ActivityKind.PRIORITY
        activity = self._activity(
            updated, kind, by, now, body=PAST_CORRECTION,
            from_office=ticket.office if office != ticket.office else None,
            to_office=office if office != ticket.office else None,
            from_priority=str(ticket.priority) if raised != ticket.priority else None,
            to_priority=str(raised) if raised != ticket.priority else None,
        )  # fmt: skip
        self._audit(
            by, "ticket.hint_applied", updated, {"from": ticket.office, "to": office, "priority": str(raised)}
        )
        return LifecycleChange(updated, activity, (), mirror=True, from_office=ticket.office)

    def on_created(self, ticket_id: str) -> None:
        """Row 1 (a background task, idempotent): the `created` thread row and the two `received` emails."""
        try:
            ticket, request = self._load(ticket_id)
            if ticket.status == TicketStatus.MERGED:
                return
            if any(a.kind == ActivityKind.CREATED for a in self._journey.activity_for(ticket.id)):
                return
            now = self._clock.now()
            contact = self._contact(request.alias)
            role = contact.role if contact.role in USER_ROLES else "student"
            activity = self._journey.add_activity(
                TicketActivity(
                    ticket_id=ticket.id,
                    kind=ActivityKind.CREATED,
                    actor_role=role,
                    actor_alias=request.alias or None,
                    body=request.raw_text[:BODY_MAX],
                    created_at=now,
                )  # fmt: skip
            )
            self._audit(_SystemActor(), "ticket.created", ticket, {})
            emails = (
                self._email(EmailEvent.RECEIVED, "requester", ticket, request, contact),
                self._email(EmailEvent.RECEIVED, "office", ticket, request, contact),
            )
            self.deliver(LifecycleChange(ticket, activity, emails))
        except Exception:  # background boundary
            log.exception("on_created for ticket %s failed", ticket_id)

    # ------------------------------------------------------------------ step 2

    def deliver(self, change: LifecycleChange) -> None:
        """Mirror, in-app notes, emails. Never raises; one failing part does not stop the others."""
        ticket = change.ticket
        if change.mirror:
            self._guard("mirror", ticket, lambda: self._mirror.push(ticket, skip=(RECORD_SINK,)))
        if change.notify_requester and change.requester_alias:
            self._guard("requester note", ticket, lambda: self._notify_requester(change))
        if change.from_office is not None and change.activity is not None:
            self._guard("office note", ticket, lambda: self._notify_office(change))
        for planned in change.emails:
            recipients = planned.to if isinstance(planned.to, tuple) else (planned.to,)
            for recipient in recipients:
                self._guard(
                    "email",
                    ticket,
                    partial(self._mailer.send, planned.event, planned.audience, planned.ctx, recipient),
                )

    # ------------------------------------------------------------------ staff paths

    def _note(self, ticket: Ticket, request: Request, actor: Actor, text: str) -> LifecycleChange:
        """Row 4: an internal note changes nothing else."""
        now = self._clock.now()
        activity = self._activity(
            ticket, ActivityKind.NOTE, actor, now, body=text, visibility=Visibility.INTERNAL
        )
        self._audit(actor, "ticket.note", ticket, {})
        return LifecycleChange(ticket, activity)

    def _staff_comment(self, ticket: Ticket, request: Request, actor: Actor, text: str) -> LifecycleChange:
        """Rows 2 and 3: a public reply keeps the clock, waits for the requester, tells them."""
        if ticket.status not in RUNNING:
            raise InvalidInput(
                f"a public comment on a {ticket.status} ticket is not allowed; reopen it first"
            )
        now = self._clock.now()
        status = TicketStatus.IN_PROGRESS
        updated = self._save(dataclasses.replace(ticket, status=status, awaiting_student=True))
        activity = self._activity(
            updated, ActivityKind.COMMENT, actor, now, body=text,
            from_status=str(ticket.status), to_status=str(status),
        )  # fmt: skip
        self._audit(actor, "ticket.comment", updated, {"from": str(ticket.status), "to": str(status)})
        contact = self._contact(request.alias)
        emails = (self._email(EmailEvent.STAFF_REPLY, "requester", updated, request, contact, comment=text),)
        return LifecycleChange(
            updated, activity, emails, mirror=status != ticket.status,
            requester_alias=request.alias, notify_requester=True, message=text,
        )  # fmt: skip

    def _staff_status(
        self, ticket: Ticket, request: Request, actor: Actor, target: TicketStatus, text: str
    ) -> LifecycleChange:
        """Rows 5-8 (`text` is the optional public comment, shown inside the status email)."""
        src = ticket.status
        now = self._clock.now()
        changes: dict[str, Any]
        event: EmailEvent
        if target == TicketStatus.IN_PROGRESS and src == TicketStatus.NEW:  # row 5
            changes = {"status": target, "awaiting_student": True if text else ticket.awaiting_student}
            event = EmailEvent.IN_PROGRESS
        elif target == TicketStatus.IN_PROGRESS and src in DONE:  # row 8
            changes = {"status": target, "awaiting_student": False, "resolved_at": None}
            changes.update(self._restart(ticket.priority, now))
            event = EmailEvent.REOPENED
        elif target == TicketStatus.SOLVED and src in RUNNING:  # row 6: the clock pauses
            changes = {"status": target, "awaiting_student": True, "resolved_at": ticket.resolved_at or now}
            event = EmailEvent.SOLVED
        elif target == TicketStatus.CLOSED and src in (*RUNNING, TicketStatus.SOLVED):  # row 7
            changes = {"status": target, "awaiting_student": False, "resolved_at": ticket.resolved_at or now}
            event = EmailEvent.CLOSED
        else:
            raise InvalidInput(f"transition {src} -> {target} not allowed")
        updated = self._save(dataclasses.replace(ticket, **changes))
        activity = self._activity(
            updated, ActivityKind.STATUS, actor, now, body=text,
            from_status=str(src), to_status=str(target),
        )  # fmt: skip
        self._audit(
            actor, "ticket.status", updated, {"from": str(src), "to": str(target), "note": text or None}
        )
        contact = self._contact(request.alias)
        emails = (self._email(event, "requester", updated, request, contact, comment=text),)
        return LifecycleChange(
            updated, activity, emails, mirror=True,
            requester_alias=request.alias, notify_requester=True, message=text,
        )  # fmt: skip

    # ------------------------------------------------------------------ requester path

    def _requester_comment(
        self, ticket: Ticket, request: Request, actor: Actor, text: str
    ) -> LifecycleChange:
        """Rows 11 and 12."""
        now = self._clock.now()
        contact = self._contact(request.alias)
        if ticket.status in RUNNING:  # row 11
            updated = self._save(dataclasses.replace(ticket, awaiting_student=False))
            activity = self._activity(updated, ActivityKind.COMMENT, actor, now, body=text)
            self._audit(actor, "ticket.comment", updated, {})
            emails = [
                self._email(EmailEvent.REQUESTER_REPLY, "office", updated, request, contact, comment=text)
            ]
            if FORWARDED_TAG in updated.tags:  # the admin also reads replies on a forwarded ticket
                emails.append(
                    self._email(
                        EmailEvent.REQUESTER_REPLY,
                        "office",
                        updated,
                        request,
                        contact,
                        comment=text,
                        to=self._mailer.inboxes.admin(),
                    )  # fmt: skip
                )
            return LifecycleChange(updated, activity, tuple(emails))
        if ticket.status in DONE:  # row 12: a reply reopens it
            reopened = dataclasses.replace(
                ticket, status=TicketStatus.IN_PROGRESS, awaiting_student=False, resolved_at=None,
                **self._restart(ticket.priority, now),
            )  # fmt: skip
            updated = self._save(reopened)
            activity = self._activity(
                updated, ActivityKind.COMMENT, actor, now, body=text,
                from_status=str(ticket.status), to_status=str(updated.status),
            )  # fmt: skip
            self._audit(
                actor, "ticket.comment", updated, {"from": str(ticket.status), "to": str(updated.status)}
            )
            emails_ = (self._email(EmailEvent.REOPENED, "office", updated, request, contact, comment=text),)
            return LifecycleChange(updated, activity, emails_, mirror=True)
        raise InvalidInput(f"transition {ticket.status} -> {ticket.status} not allowed")

    # ------------------------------------------------------------------ helpers

    def _load(self, ticket_id: str) -> tuple[Ticket, Request]:
        ticket = self._repo.get_ticket(ticket_id)
        self._not_merged(ticket)
        return ticket, self._repo.get_request(ticket.request_id)

    @staticmethod
    def _not_merged(ticket: Ticket) -> None:
        if ticket.status == TicketStatus.MERGED:
            raise InvalidInput("a merged ticket accepts no action")

    @staticmethod
    def _role(actor: Actor, ticket: Ticket, request: Request) -> Role:
        if actor.alias and actor.role in USER_ROLES and actor.alias == request.alias:
            return "requester"
        if actor.role == ROLE_ADMIN:
            return "admin"
        if actor.role == ROLE_STAFF and actor.office is not None and actor.office == ticket.office:
            return "office"
        raise Unauthorized(f"role {actor.role!r} of office {actor.office!r} may not act on this ticket")

    @staticmethod
    def _staff_only(role: Role) -> None:
        if role == "requester":
            raise Unauthorized("you cannot act as staff on your own request")

    @staticmethod
    def _text(body: str) -> str:
        text = body.strip()
        if not text:
            raise InvalidInput("the text is empty")
        if len(text) > BODY_MAX:
            raise InvalidInput(f"the text is longer than {BODY_MAX} characters")
        return text

    def _restart(self, priority: Priority, now: datetime) -> dict[str, Any]:
        """The clock fields of a restart (PLAN (d)): a new period from `now`, no reminder sent yet."""
        return {
            "clock_started_at": now,
            "sla_due_at": now + timedelta(hours=self._sla[priority]),
            "reminder_sent_at": None,
            "reminder_count": 0,
        }

    def _save(self, ticket: Ticket) -> Ticket:
        return self._repo.save_ticket(ticket)

    def _activity(
        self, ticket: Ticket, kind: ActivityKind, actor: Actor, now: datetime, **fields: Any
    ) -> TicketActivity:
        role = actor.role if actor.role in (*USER_ROLES, SYSTEM) else SYSTEM
        office = actor.office if actor.role == ROLE_STAFF else None
        return self._journey.add_activity(
            TicketActivity(
                ticket_id=ticket.id,
                kind=kind,
                actor_role=role,
                actor_alias=actor.alias,
                actor_office=office,
                created_at=now,
                **fields,
            )  # fmt: skip
        )

    def _audit(self, actor: Actor, action: str, ticket: Ticket, payload: Mapping[str, object]) -> None:
        body = {"by": actor.alias or actor.role, "role": actor.role, **payload}
        try:
            self._repo.append_event(ACTOR, action, f"ticket:{ticket.id}", body)
        except StoreError as exc:
            log.warning("%s event not saved: %s", action, exc)

    def _contact(self, alias: str) -> Contact:
        try:
            found = self._journey.contact_for_alias(alias) if alias else None
        except StoreError as exc:
            log.warning("contact of %r not read: %s", alias, exc)
            found = None
        return found or Contact(alias=alias, role="student")

    def _email(
        self,
        event: EmailEvent,
        audience: Audience,
        ticket: Ticket,
        request: Request,
        contact: Contact,
        *,
        comment: str = "",
        note: str = "",
        from_office: str = "",
        to_office: str = "",
        to: str | None = None,
    ) -> PlannedEmail:
        inboxes = self._mailer.inboxes
        requester = audience == "requester"
        lang: Literal["en", "ar"] = "en"
        if requester and request.normalized is not None and str(request.normalized.lang) in ("ar", "arabizi"):
            lang = "ar"
        ctx = EmailContext(
            ticket=ticket, request_text=request.raw_text, lang=lang,
            recipient_name=contact.display_name if requester else "",
            comment=comment, note=note, from_office=from_office, to_office=to_office,
        )  # fmt: skip
        recipients: str | tuple[str, ...] | None = to
        if recipients is None:
            if requester:
                recipients = inboxes.requester(contact)
            elif audience == "office":
                office_addresses = inboxes.office_recipients(
                    ticket.office, exclude_alias=contact.alias, exclude_email=inboxes.requester(contact)
                )
                recipients = office_addresses[0] if len(office_addresses) == 1 else office_addresses
            else:
                recipients = inboxes.admin()
        return PlannedEmail(event, audience, ctx, recipients)

    def _hint(self, kind: str, ticket: Ticket, request: Request, actor: Actor, note: str) -> None:
        """Keep the staff correction for the chat agent (best effort: a failure never fails the action)."""
        try:
            model_category: str | None = None
            model_priority: str | None = None
            try:
                prediction = self._repo.latest_prediction(request.id)
                model_category, model_priority = str(prediction.category), str(prediction.priority)
            except NotFound:
                pass
            lang = str(request.normalized.lang) if request.normalized is not None else None
            self._journey.add_hint(
                TicketHint(
                    kind=kind,
                    request_text=request.raw_text,
                    lang=lang,
                    embedding=self._embed(request),
                    model_category=model_category,
                    model_priority=model_priority,
                    corrected_category=str(ticket.category),
                    corrected_priority=str(ticket.priority),
                    ticket_id=ticket.id,
                    note=note or None,
                    author_alias=actor.alias,
                    author_role=actor.role,
                )  # fmt: skip
            )
        except Exception:  # noqa: BLE001 - hints are auxiliary
            log.exception("hint for ticket %s not saved", ticket.id)

    def _embed(self, request: Request) -> tuple[float, ...] | None:
        if self._encoder is None:
            return None
        text = request.normalized.text_norm if request.normalized is not None else request.raw_text
        try:
            return tuple(float(x) for x in self._encoder.encode([text or request.raw_text])[0])
        except Exception:  # noqa: BLE001 - no embedding means the hint is stored but never retrieved
            log.exception("hint embedding failed")
            return None

    def _notify_requester(self, change: LifecycleChange) -> None:
        ticket = change.ticket
        payload: dict[str, object] = {
            "ticket_id": ticket.id,
            "status": str(ticket.status),
            "title": ticket_title(ticket),
        }
        if change.message:
            payload["message"] = change.message
        self._repo.save_notification(change.requester_alias, NOTIFICATION_KIND, payload)

    def _notify_office(self, change: LifecycleChange) -> None:
        activity = change.activity
        assert activity is not None
        notify_forward(
            self._repo, self._messages, ticket_id=change.ticket.id, title=ticket_title(change.ticket),
            from_office=change.from_office or "", office=change.ticket.office, note=activity.body,
        )  # fmt: skip

    @staticmethod
    def _guard(what: str, ticket: Ticket, fn: Callable[[], object]) -> None:
        try:
            fn()
        except Exception:  # background boundary: a failed side effect never surfaces
            log.exception("%s for ticket %s failed", what, ticket.id)


@dataclass(frozen=True, slots=True)
class _SystemActor:
    """The actor of system changes (a past correction, the created row)."""

    role: str = SYSTEM
    office: str | None = None
    alias: str | None = None
