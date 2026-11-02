"""P9.2: ticket email templates, renderer, mailer, settings and the HTML alternative.

No test sends mail: the mailer gets a fake notifier and the Gmail notifier is only asked to `_build`.
"""

from __future__ import annotations

import dataclasses
import itertools
from pathlib import Path
from typing import Any

import pytest
import yaml
from fixtures.backend_fakes import FakeNotifier, FrozenClock, make_ticket
from pydantic import SecretStr, ValidationError

from campuspulse_ai.adapters.notify.email_templates import load_ticket_email_templates
from campuspulse_ai.adapters.notify.gmail_smtp import FOOTER, GmailSmtpNotifier
from campuspulse_ai.adapters.store import codec
from campuspulse_ai.application.use_cases.ticket_emails import (
    EVENT_AUDIENCES,
    Audience,
    EmailContext,
    EmailEvent,
    InboxBook,
    Lang,
    TicketEmailTemplates,
    TicketMailer,
)
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.entities import OutboxMessage
from campuspulse_ai.domain.errors import NotificationError, RecipientNotAllowed
from campuspulse_ai.domain.journey import Contact, ticket_number
from campuspulse_ai.domain.policy import RecipientPolicy

TEMPLATE_DIR = Path(__file__).resolve().parents[4] / "config" / "templates" / "email"
TICKET_ID = "3f2a9c1e-0000-4000-8000-000000000001"
REQUEST = "My student account cannot register CS 201 and today is the deadline"
PAIRS = [(e, a) for e, audiences in EVENT_AUDIENCES.items() for a in audiences]
LANG_LIST: list[Lang] = ["en", "ar"]
NEXT_STEP = {"en": "Next step", "ar": "الخطوة التالية"}


@pytest.fixture(scope="module")
def templates() -> TicketEmailTemplates:
    return load_ticket_email_templates(TEMPLATE_DIR)


def _ctx(lang: Lang = "en", **kw: Any) -> EmailContext:
    ticket = make_ticket("r1", id=TICKET_ID, office="it")
    base: dict[str, Any] = {"ticket": ticket, "request_text": REQUEST, "lang": lang}
    return EmailContext(**{**base, **kw})


def _yaml(lang: str) -> dict[str, Any]:
    return yaml.safe_load((TEMPLATE_DIR / f"ticket_emails.{lang}.yaml").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _keys(node: Any, prefix: str = "") -> set[str]:
    if not isinstance(node, dict):
        return {prefix}
    return set(itertools.chain.from_iterable(_keys(v, f"{prefix}.{k}") for k, v in node.items()))


def test_ten_events_and_en_ar_key_parity() -> None:
    assert len(EmailEvent) == 10
    en, ar = _yaml("en"), _yaml("ar")
    assert _keys(en) == _keys(ar)
    assert set(en["events"]) == {e.value for e in EmailEvent}
    assert set(en["events"]["reminder_2"]) == {"office", "admin"}


@pytest.mark.parametrize("lang", LANG_LIST)
@pytest.mark.parametrize(("event", "audience"), PAIRS)
def test_every_event_audience_language_renders(
    templates: TicketEmailTemplates, event: EmailEvent, audience: Audience, lang: Lang
) -> None:
    ctx = _ctx(lang, from_office="registrar", to_office="it", comment="Please check", files=1)
    mail = templates.render(event, audience, ctx, "https://app.example")
    number = ticket_number(TICKET_ID)
    department = _yaml(lang)["offices"]["it"]
    demo_line = _yaml(lang)["demo_line"]
    for part in (mail.text, mail.html):
        assert number in part and REQUEST in part and department in part
        assert NEXT_STEP[lang] in part
    assert demo_line in mail.text and demo_line in mail.html
    assert f"#{number}" in mail.subject
    assert "{" not in mail.text and "{" not in mail.subject
    assert "https://app.example" in mail.html and "https://app.example" in mail.text
    assert ("/requests/" if audience == "requester" else "/staff/tickets/") in mail.text


@pytest.mark.parametrize("lang", LANG_LIST)
def test_html_direction_and_language(templates: TicketEmailTemplates, lang: Lang) -> None:
    mail = templates.render(EmailEvent.RECEIVED, "requester", _ctx(lang), None)
    assert f'lang="{lang}"' in mail.html
    assert ('dir="rtl"' in mail.html) == (lang == "ar")
    assert "<a href" not in mail.html  # no PUBLIC_WEB_URL: no link


def test_script_in_request_text_is_escaped_in_html(templates: TicketEmailTemplates) -> None:
    evil = '<script>alert("x")</script> {demo_line} {{subject}}'
    mail = templates.render(EmailEvent.RECEIVED, "office", _ctx(request_text=evil), None)
    assert "<script>" not in mail.html and "&lt;script&gt;" in mail.html
    assert "{{subject}}" in mail.html  # user text is never expanded as a layout slot


def test_comment_block_only_when_comment_given(templates: TicketEmailTemplates) -> None:
    without = templates.render(EmailEvent.STAFF_REPLY, "requester", _ctx(), None)
    with_comment = templates.render(EmailEvent.STAFF_REPLY, "requester", _ctx(comment="Bring your ID"), None)
    assert "Message:" not in without.text and "Bring your ID" not in without.text
    assert "Message:\nBring your ID" in with_comment.text
    assert "Bring your ID" in with_comment.html
    ar = templates.render(EmailEvent.STAFF_REPLY, "requester", _ctx("ar", comment="أحضر هويتك"), None)
    assert "الرسالة:\nأحضر هويتك" in ar.text


def test_long_request_text_is_cut_and_files_line_only_with_files(templates: TicketEmailTemplates) -> None:
    mail = templates.render(EmailEvent.REQUESTER_REPLY, "office", _ctx(request_text="x" * 700, files=2), None)
    assert "x" * 500 + "..." in mail.text and "x" * 501 not in mail.text
    assert "2 file(s) attached" in mail.text
    assert "file(s)" not in templates.render(EmailEvent.REQUESTER_REPLY, "office", _ctx(), None).text


def test_reminder_2_renders_for_office_and_admin(templates: TicketEmailTemplates) -> None:
    for audience in ("office", "admin"):
        mail = templates.render(EmailEvent.REMINDER_2, audience, _ctx(), None)  # type: ignore[arg-type]
        assert "admin" in mail.text.lower() and "Second" in mail.text
    with pytest.raises(KeyError):
        templates.render(EmailEvent.REMINDER_2, "requester", _ctx(), None)
    with pytest.raises(KeyError):
        templates.render(EmailEvent.REMINDER, "admin", _ctx(), None)


def test_no_university_name(templates: TicketEmailTemplates) -> None:
    text = (TEMPLATE_DIR / "ticket_emails.en.yaml").read_text(encoding="utf-8").lower()
    text += (TEMPLATE_DIR / "ticket_emails.ar.yaml").read_text(encoding="utf-8")
    for banned in ("gju", "german jordanian", "الجامعة الألمانية"):
        assert banned not in text.lower()


def test_load_names_the_missing_key(tmp_path: Path) -> None:
    for name in ("ticket_emails.en.yaml", "ticket_emails.ar.yaml", "layout.html"):
        (tmp_path / name).write_text((TEMPLATE_DIR / name).read_text(encoding="utf-8"), encoding="utf-8")
    data = _yaml("en")
    del data["events"]["reminder_2"]["admin"]
    (tmp_path / "ticket_emails.en.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match=r"events\.reminder_2\.admin"):
        load_ticket_email_templates(tmp_path)


def test_ticket_number() -> None:
    assert ticket_number(TICKET_ID) == "3F2A9C1E"


# --------------------------------------------------------------------------- mailer


def _mailer(templates: TicketEmailTemplates, notifier: FakeNotifier) -> TicketMailer:
    return TicketMailer(templates, notifier, FrozenClock(), InboxBook(), "https://app.example")


def test_mailer_sends_one_message_per_send(templates: TicketEmailTemplates) -> None:
    fake = FakeNotifier()
    sent = _mailer(templates, fake).send(EmailEvent.RECEIVED, "office", _ctx(), "it@demo.example")
    assert sent is not None and sent.status == "sent" and fake.calls == 1
    msg = fake.sent[0]
    assert msg.kind == "email" and msg.to_address == "it@demo.example"
    assert msg.priority == make_ticket("r1").priority
    assert msg.html and "<html" in msg.html and ticket_number(TICKET_ID) in msg.subject


def test_mailer_without_address_does_not_send(templates: TicketEmailTemplates) -> None:
    fake = FakeNotifier()
    assert _mailer(templates, fake).send(EmailEvent.RECEIVED, "office", _ctx(), None) is None
    assert fake.calls == 0


@pytest.mark.parametrize("error", [RecipientNotAllowed("no"), NotificationError("down", retryable=True)])
def test_mailer_never_raises(templates: TicketEmailTemplates, error: Exception) -> None:
    fake = FakeNotifier(fail_with=error)
    assert _mailer(templates, fake).send(EmailEvent.SOLVED, "requester", _ctx(), "a@demo.example") is None
    assert fake.calls == 1


def test_mailer_survives_a_bad_pair(templates: TicketEmailTemplates) -> None:
    fake = FakeNotifier()
    assert _mailer(templates, fake).send(EmailEvent.REMINDER, "admin", _ctx(), "a@demo.example") is None
    assert fake.calls == 0


def test_inbox_book() -> None:
    book = InboxBook("student@x.com", {"it": "it@x.com"}, "office@x.com", "admin@x.com")
    assert book.requester(Contact("s1", "student")) == "student@x.com"
    assert book.requester(Contact("s1", "student", demo_inbox="own@x.com")) == "own@x.com"
    assert book.requester(Contact("u1", "staff", office="it")) == "it@x.com"
    assert book.requester(Contact("u1", "staff", office="finance")) == "office@x.com"
    assert book.office("it") == "it@x.com" and book.office("registrar") == "office@x.com"
    assert book.admin() == "admin@x.com"
    assert InboxBook(default_office_inbox="office@x.com").admin() == "office@x.com"
    assert InboxBook().requester(Contact("s1", "student")) is None and InboxBook().office("it") is None


# --------------------------------------------------------------------------- settings


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **env: str) -> Settings:
    for name in ("DEMO_OFFICE_INBOXES", "DEMO_ADMIN_INBOX", "PUBLIC_WEB_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.chdir(tmp_path)  # no stray .env
    return Settings()


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    s = _settings(monkeypatch, tmp_path)
    assert s.demo_office_inboxes == {} and s.demo_admin_inbox is None and s.public_web_url is None


def test_settings_parse_office_inboxes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    s = _settings(
        monkeypatch,
        tmp_path,
        DEMO_OFFICE_INBOXES=" IT=a@x.com, finance=b@x.com ,",
        DEMO_ADMIN_INBOX="admin@x.com",
        PUBLIC_WEB_URL="https://app.example/",
    )
    assert s.demo_office_inboxes == {"it": "a@x.com", "finance": "b@x.com"}
    assert s.demo_admin_inbox == "admin@x.com" and s.public_web_url == "https://app.example"


@pytest.mark.parametrize("bad", ["it", "it=", "=a@x.com", "it=nope", "it=a@x.com,oops"])
def test_settings_reject_invalid_office_inbox_pair(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: str
) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, tmp_path, DEMO_OFFICE_INBOXES=bad)


# --------------------------------------------------------------------------- gmail html, codec


def _gmail() -> GmailSmtpNotifier:
    return GmailSmtpNotifier(
        "smtp.invalid", 587, "campuspulse.support@gmail.com", SecretStr("fake"),
        policy=RecipientPolicy(frozenset({"a@x.com"})), clock=FrozenClock(),
        timeout_s=1.0, max_retries=0, backoff_s=0.0, daily_cap=1,
    )  # fmt: skip


def _msg(html: str | None) -> OutboxMessage:
    return OutboxMessage("", "email", "a@x.com", "S", "plain body", None, "queued",
                         FrozenClock().now(), html=html)  # fmt: skip


def test_gmail_build_uses_html_when_given_and_keeps_footer() -> None:
    email, _ = _gmail()._build(_msg("<html><body><p>Custom <b>page</b></p></body></html>"))
    page = email.get_body(("html",)).get_content()  # type: ignore[union-attr]
    assert "Custom <b>page</b>" in page and FOOTER in page and page.index("Custom") < page.index(FOOTER)
    assert FOOTER in email.get_body(("plain",)).get_content()  # type: ignore[union-attr]


def test_gmail_build_without_html_is_unchanged() -> None:
    email, _ = _gmail()._build(_msg(None))
    assert "plain body" in email.get_body(("html",)).get_content()  # type: ignore[union-attr]


def test_html_is_not_stored_in_the_outbox_row() -> None:
    row = codec.outbox_row(_msg("<html></html>"))
    assert "html" not in row


def test_reminder_count_round_trips_and_defaults_to_zero() -> None:
    ticket = make_ticket("r1", id="t1")
    assert ticket.reminder_count == 0 and codec.ticket_row(ticket)["reminder_count"] == 0
    ticket = dataclasses.replace(ticket, reminder_count=2)
    row = codec.ticket_row(ticket)
    assert row["reminder_count"] == 2 and codec.to_ticket(row, []).reminder_count == 2
    old = {k: v for k, v in row.items() if k != "reminder_count"}
    assert codec.to_ticket(old, []).reminder_count == 0
