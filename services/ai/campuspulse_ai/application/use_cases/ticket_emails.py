"""Ticket emails (P9.2): the templates, the renderer and the mailer.

`TicketEmailTemplates.load(dir)` reads `ticket_emails.<lang>.yaml` and `layout.html` from
`config/templates/email/` and validates them. `render(event, audience, ctx, link_base)` returns the
subject, the plain text and the HTML. The renderer always appends the demo line and never names the
university. `TicketMailer` addresses and sends a rendered email through the notifier chain (the
allow-list is the outermost decorator) and never raises: a failed email must not fail the action.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta, timezone, tzinfo
from enum import StrEnum
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from campuspulse_ai.domain.entities import OutboxMessage, Ticket
from campuspulse_ai.domain.errors import NotificationError, RecipientNotAllowed, StoreError
from campuspulse_ai.domain.journey import Contact, ticket_number
from campuspulse_ai.domain.ports import Clock, Notifier

log = logging.getLogger(__name__)

Audience = Literal["requester", "office", "admin"]
Lang = Literal["en", "ar"]
LANGS: tuple[Lang, ...] = ("en", "ar")
REQUEST_TEXT_MAX = 500
TEMPLATE_VERSION = 1


class EmailEvent(StrEnum):
    RECEIVED = "received"
    IN_PROGRESS = "in_progress"
    FORWARDED = "forwarded"
    STAFF_REPLY = "staff_reply"
    SOLVED = "solved"
    CLOSED = "closed"
    REOPENED = "reopened"
    REMINDER = "reminder"
    REMINDER_2 = "reminder_2"
    REQUESTER_REPLY = "requester_reply"


EVENT_AUDIENCES: Mapping[EmailEvent, tuple[Audience, ...]] = {
    EmailEvent.RECEIVED: ("requester", "office"),
    EmailEvent.IN_PROGRESS: ("requester",),
    EmailEvent.FORWARDED: ("requester", "office"),
    EmailEvent.STAFF_REPLY: ("requester",),
    EmailEvent.SOLVED: ("requester", "office"),
    EmailEvent.CLOSED: ("requester", "office"),
    EmailEvent.REOPENED: ("requester", "office"),
    EmailEvent.REMINDER: ("office",),
    EmailEvent.REMINDER_2: ("office", "admin"),
    EmailEvent.REQUESTER_REPLY: ("office",),
}

_LABEL_KEYS = ("comment", "note", "files", "open", "there")
_OFFICE_KEYS = ("registrar", "it", "finance", "transport", "facilities", "academic")
_STATUS_KEYS = ("new", "in_progress", "solved", "closed", "merged")
_PRIORITY_KEYS = ("low", "medium", "high")
_VARIABLES = (
    "ticket_number", "title", "request_text", "department", "from_department", "to_department",
    "status", "priority", "due_at", "recipient_name", "comment_block", "note_block", "files_line",
    "link",
)  # fmt: skip
_LAYOUT_SLOT = re.compile(r"\{\{(lang|dir|subject|body_html|link_html|demo_line)\}\}")


@dataclass
class EmailContext:
    ticket: Ticket
    request_text: str
    lang: Lang
    recipient_name: str = ""
    comment: str = ""
    note: str = ""
    from_office: str = ""
    to_office: str = ""
    files: int = 0


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text: str
    html: str


@dataclass(frozen=True)
class _LangTemplates:
    demo_line: str
    labels: Mapping[str, str]
    offices: Mapping[str, str]
    statuses: Mapping[str, str]
    priorities: Mapping[str, str]
    events: Mapping[str, Mapping[str, Mapping[str, str]]]


def _amman() -> tzinfo:
    try:
        return ZoneInfo("Asia/Amman")
    except ZoneInfoNotFoundError:  # Windows without tzdata; Jordan is UTC+3 all year
        return timezone(timedelta(hours=3), "Asia/Amman")


def _str_map(data: Any, where: str, keys: tuple[str, ...]) -> dict[str, str]:
    if not isinstance(data, dict):
        raise ValueError(f"{where}: missing key")
    out: dict[str, str] = {}
    for key in keys:
        if not isinstance(data.get(key), str):
            raise ValueError(f"{where}.{key}: missing key")
        out[key] = data[key]
    return out


def _parse(data: Any, where: str) -> _LangTemplates:
    if not isinstance(data, dict):
        raise ValueError(f"{where}: not a mapping")
    if data.get("version") != TEMPLATE_VERSION:
        raise ValueError(f"{where}.version: expected {TEMPLATE_VERSION}")
    if not isinstance(data.get("demo_line"), str) or not data["demo_line"].strip():
        raise ValueError(f"{where}.demo_line: missing key")
    labels = _str_map(data.get("labels"), f"{where}.labels", _LABEL_KEYS)
    offices = _str_map(data.get("offices"), f"{where}.offices", _OFFICE_KEYS)
    statuses = _str_map(data.get("statuses"), f"{where}.statuses", _STATUS_KEYS)
    priorities = _str_map(data.get("priorities"), f"{where}.priorities", _PRIORITY_KEYS)
    raw_events = data.get("events")
    if not isinstance(raw_events, dict):
        raise ValueError(f"{where}.events: missing key")
    dummy = {name: "x" for name in _VARIABLES}
    events: dict[str, dict[str, dict[str, str]]] = {}
    for event, audiences in EVENT_AUDIENCES.items():
        by_audience = raw_events.get(event.value)
        if not isinstance(by_audience, dict):
            raise ValueError(f"{where}.events.{event.value}: missing key")
        events[event.value] = {}
        for audience in audiences:
            path = f"{where}.events.{event.value}.{audience}"
            tpl = _str_map(by_audience.get(audience), path, ("subject", "body"))
            if "{ticket_number}" not in tpl["subject"]:
                raise ValueError(f"{path}.subject: missing placeholder ticket_number")
            for part in ("subject", "body"):
                try:
                    tpl[part].format(**dummy)
                except KeyError as exc:
                    raise ValueError(f"{path}.{part}: unknown placeholder {exc.args[0]}") from exc
            for needed in ("{ticket_number}", "{request_text}", "{department}"):
                if needed not in tpl["body"]:
                    raise ValueError(f"{path}.body: missing placeholder {needed.strip('{}')}")
            events[event.value][audience] = tpl
    return _LangTemplates(data["demo_line"], labels, offices, statuses, priorities, events)


def _paragraphs(text: str) -> str:
    """Each blank-line separated paragraph, escaped, inside `<p>`; single newlines become `<br>`."""
    paras = [p.strip("\n") for p in re.split(r"\n\s*\n", text) if p.strip()]
    escaped = [html.escape(p).replace("\n", "<br>\n") for p in paras]
    return "\n".join(f"<p>{p}</p>" for p in escaped)


def _tidy(text: str) -> str:
    """Drop the blank lines left by empty variables; keep one blank line between paragraphs."""
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


class TicketEmailTemplates:
    """The validated ticket email templates (both languages) and the HTML layout."""

    def __init__(self, langs: Mapping[str, _LangTemplates], layout: str) -> None:
        self._langs = dict(langs)
        self._layout = layout

    @classmethod
    def from_dicts(cls, parsed: Mapping[str, Any], layout: str) -> TicketEmailTemplates:
        """Validate the parsed `ticket_emails.<lang>.yaml` files (keys `en`, `ar`) and the layout text.

        Pure: this layer does not read files or YAML (architecture rule). `load_ticket_email_templates`
        in `adapters/notify/email_templates.py` reads the directory. `ValueError` names the bad key.
        """
        langs: dict[str, _LangTemplates] = {}
        for lang in LANGS:
            langs[lang] = _parse(parsed.get(lang), f"ticket_emails.{lang}")
        for slot in ("lang", "dir", "subject", "body_html", "link_html", "demo_line"):
            if "{{" + slot + "}}" not in layout:
                raise ValueError(f"layout.html: missing slot {{{{{slot}}}}}")
        return cls(langs, layout)

    def render(
        self, event: EmailEvent, audience: Audience, ctx: EmailContext, link_base: str | None
    ) -> RenderedEmail:
        """Render one email. `KeyError` when the (event, audience) pair has no template."""
        lang = self._langs[ctx.lang]
        tpl = lang.events[EmailEvent(event).value][audience]
        t = ctx.ticket
        link = ""
        if link_base:
            base = link_base.rstrip("/")
            link = f"{base}/requests/{t.id}" if audience == "requester" else f"{base}/staff/tickets/{t.id}"
        request_text = ctx.request_text.strip()
        if len(request_text) > REQUEST_TEXT_MAX:
            request_text = request_text[:REQUEST_TEXT_MAX] + "..."
        office = lang.offices.get(t.office, t.office)
        variables = {
            "ticket_number": ticket_number(t.id),
            "title": t.title,
            "request_text": request_text,
            "department": office,
            "from_department": lang.offices.get(ctx.from_office, ctx.from_office),
            "to_department": lang.offices.get(ctx.to_office, ctx.to_office),
            "status": lang.statuses.get(str(t.status), str(t.status)),
            "priority": lang.priorities.get(str(t.priority), str(t.priority)),
            "due_at": t.sla_due_at.astimezone(_amman()).strftime("%Y-%m-%d %H:%M"),
            "recipient_name": ctx.recipient_name or lang.labels["there"],
            "comment_block": f"{lang.labels['comment']}:\n{ctx.comment}\n" if ctx.comment.strip() else "",
            "note_block": f"{lang.labels['note']}:\n{ctx.note}\n" if ctx.note.strip() else "",
            "files_line": lang.labels["files"].format(n=ctx.files) if ctx.files > 0 else "",
            "link": link,
        }
        subject = " ".join(tpl["subject"].format(**variables).split())
        text_body = _tidy(tpl["body"].format(**variables))
        html_body = _tidy(tpl["body"].format(**{**variables, "link": ""}))
        link_html = ""
        if link:
            label = html.escape(lang.labels["open"])
            link_html = f'<p><a href="{html.escape(link, quote=True)}">{label}</a></p>'
        slots = {
            "lang": ctx.lang,
            "dir": "rtl" if ctx.lang == "ar" else "ltr",
            "subject": html.escape(subject),
            "body_html": _paragraphs(html_body),
            "link_html": link_html,
            "demo_line": html.escape(lang.demo_line),
        }
        page = _LAYOUT_SLOT.sub(lambda m: slots[m.group(1)], self._layout)  # one pass: no re-expansion
        return RenderedEmail(subject, f"{text_body}\n{lang.demo_line}\n", page)


@dataclass(frozen=True)
class InboxBook:
    """Demo inboxes the mailer may address (all must also be in DEMO_EMAIL_ALLOWLIST)."""

    student_inbox: str | None = None
    office_inboxes: Mapping[str, str] = field(default_factory=dict)
    default_office_inbox: str | None = None
    admin_inbox: str | None = None

    def requester(self, contact: Contact) -> str | None:
        """The contact's own demo inbox, else the student inbox, else (staff requester) their office inbox."""
        if contact.demo_inbox:
            return contact.demo_inbox
        if contact.role == "student":
            return self.student_inbox
        return self.office(contact.office) if contact.office else None

    def office(self, code: str | None) -> str | None:
        return (self.office_inboxes.get(code) if code else None) or self.default_office_inbox

    def admin(self) -> str | None:
        return self.admin_inbox or self.default_office_inbox


class TicketMailer:
    """Render and send one ticket email. `send` never raises (a failed email must not fail the action)."""

    def __init__(
        self,
        templates: TicketEmailTemplates,
        notifier: Notifier,
        clock: Clock,
        inboxes: InboxBook,
        link_base: str | None,
    ) -> None:
        self.templates = templates
        self.inboxes = inboxes
        self._notifier = notifier
        self._clock = clock
        self._link_base = link_base

    def send(
        self, event: EmailEvent, audience: Audience, ctx: EmailContext, to: str | None
    ) -> OutboxMessage | None:
        """The delivered message, or None when there is no address or the send failed."""
        ticket = ctx.ticket
        if not to:
            log.info("email %s/%s for ticket %s skipped: no address", event, audience, ticket.id)
            return None
        try:
            rendered = self.templates.render(event, audience, ctx, self._link_base)
            msg = OutboxMessage(
                id="",
                kind="email",
                to_address=to,
                subject=rendered.subject,
                body=rendered.text,
                provider_id=None,
                status="queued",
                created_at=self._clock.now(),
                priority=ticket.priority,
                html=rendered.html,
            )
            return self._notifier.send(msg)
        except (RecipientNotAllowed, NotificationError, StoreError) as exc:
            log.warning("email %s/%s for ticket %s not sent: %s", event, audience, ticket.id, exc)
        except Exception:  # noqa: BLE001 - an email problem must never break the ticket action
            log.exception("email %s/%s for ticket %s failed", event, audience, ticket.id)
        return None
