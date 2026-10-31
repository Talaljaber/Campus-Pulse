"""P4.4: GmailSmtpNotifier against a fake SMTP connection. No test opens a socket or sends mail.

`FakeSmtp` replays scripted errors per connection attempt and records the calls; the default factory
is checked with `smtplib.SMTP`/`SMTP_SSL` monkeypatched to the same fake.
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import timedelta
from email.message import EmailMessage

import pytest
from fixtures.backend_fakes import FrozenClock, make_outbox
from pydantic import SecretStr

from campuspulse_ai.adapters.notify import gmail_smtp
from campuspulse_ai.adapters.notify.gmail_smtp import FOOTER, GmailSmtpNotifier, classify
from campuspulse_ai.domain.errors import NotificationError
from campuspulse_ai.domain.policy import RecipientPolicy
from campuspulse_ai.domain.ports import Notifier

USER = "campuspulse.support@gmail.com"
PASSWORD = "abcd efgh ijkl mnop"  # a fake app password; never a real one
TO = "campuspulse.support+student17@gmail.com"
TIMEOUT_S, BACKOFF_S, RETRIES, CAP = 10.0, 1.0, 2, 100


@dataclass
class FakeSmtp:
    """One fake connection. `fail_at` names the step that raises `error` ("connect" raises early)."""

    host: str
    port: int
    timeout: float
    use_ssl: bool
    error: OSError | None = None
    fail_at: str = ""
    calls: list[str] = field(default_factory=list)
    messages: list[EmailMessage] = field(default_factory=list)
    login_args: tuple[str, str] | None = None

    def _step(self, name: str) -> None:
        self.calls.append(name)
        if self.error is not None and self.fail_at == name:
            raise self.error

    def ehlo(self, name: str = "") -> tuple[int, bytes]:
        self._step("ehlo")
        return 250, b"ok"

    def starttls(self, *, context: ssl.SSLContext | None = None) -> tuple[int, bytes]:
        assert isinstance(context, ssl.SSLContext) and context.verify_mode == ssl.CERT_REQUIRED
        self._step("starttls")
        return 220, b"ready"

    def login(self, user: str, password: str) -> tuple[int, bytes]:
        self.login_args = (user, password)
        self._step("login")
        return 235, b"accepted"

    def send_message(self, msg: EmailMessage) -> dict[str, tuple[int, bytes]]:
        self._step("send_message")
        self.messages.append(msg)
        return {}

    def quit(self) -> tuple[int, bytes]:
        self.calls.append("quit")
        return 221, b"bye"

    def close(self) -> None:
        self.calls.append("close")


@dataclass
class Factory:
    """Builds FakeSmtp connections; `script[i]` is (step, error) for attempt i (missing = success)."""

    script: list[tuple[str, OSError]] = field(default_factory=list)
    made: list[FakeSmtp] = field(default_factory=list)

    def __call__(
        self, host: str, port: int, timeout: float, use_ssl: bool, context: ssl.SSLContext
    ) -> FakeSmtp:
        attempt = len(self.made)
        step, error = self.script[attempt] if attempt < len(self.script) else ("", None)
        conn = FakeSmtp(host, port, timeout, use_ssl, error=error, fail_at=step)
        self.made.append(conn)
        if step == "connect" and error is not None:
            raise error
        return conn


def make_notifier(
    factory: Factory, *, port: int = 587, clock: FrozenClock | None = None, cap: int = CAP
) -> tuple[GmailSmtpNotifier, list[float]]:
    sleeps: list[float] = []
    notifier = GmailSmtpNotifier(
        "smtp.test",
        port,
        USER,
        SecretStr(PASSWORD),
        policy=RecipientPolicy(frozenset({TO})),
        clock=clock or FrozenClock(),
        timeout_s=TIMEOUT_S,
        max_retries=RETRIES,
        backoff_s=BACKOFF_S,
        daily_cap=cap,
        smtp_factory=factory,
        sleep=sleeps.append,
    )
    return notifier, sleeps


def test_implements_the_port() -> None:
    assert isinstance(make_notifier(Factory())[0], Notifier)


def test_starttls_flow_and_message_id_recorded() -> None:
    factory = Factory()
    notifier, sleeps = make_notifier(factory)
    sent = notifier.send(make_outbox(TO, subject="Ticket opened", body="Line one\n<b>two</b>"))
    [conn] = factory.made
    assert (conn.host, conn.port, conn.timeout, conn.use_ssl) == ("smtp.test", 587, TIMEOUT_S, False)
    assert conn.calls == ["ehlo", "starttls", "ehlo", "login", "send_message", "quit"]
    assert conn.login_args == (USER, PASSWORD)
    [email] = conn.messages
    assert sent.status == "sent" and sent.provider_id == email["Message-ID"]
    assert sent.provider_id.startswith("<") and sent.provider_id.endswith("@gmail.com>")
    assert email["To"] == TO and email["Subject"] == "Ticket opened" and USER in email["From"]
    plain = email.get_body(("plain",))
    html_part = email.get_body(("html",))
    assert plain is not None and html_part is not None
    assert FOOTER in plain.get_content() and "Line one" in plain.get_content()
    assert "&lt;b&gt;two&lt;/b&gt;" in html_part.get_content()  # the body is escaped in HTML
    assert sleeps == []


def test_port_465_uses_implicit_tls_without_starttls() -> None:
    factory = Factory()
    notifier, _ = make_notifier(factory, port=465)
    notifier.send(make_outbox(TO))
    [conn] = factory.made
    assert conn.use_ssl and "starttls" not in conn.calls


def test_auth_failure_535_is_not_retried() -> None:
    rejected = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
    factory = Factory([("login", rejected)])
    notifier, sleeps = make_notifier(factory)
    with pytest.raises(NotificationError) as info:
        notifier.send(make_outbox(TO))
    assert info.value.retryable is False and "535" in str(info.value)
    assert len(factory.made) == 1 and sleeps == []
    assert PASSWORD not in str(info.value)


def test_421_is_retried_twice_then_raised_retryable() -> None:
    busy = smtplib.SMTPResponseException(421, b"4.7.0 Try again later")
    factory = Factory([("send_message", busy)] * 3)
    notifier, sleeps = make_notifier(factory)
    with pytest.raises(NotificationError) as info:
        notifier.send(make_outbox(TO))
    assert info.value.retryable is True
    assert len(factory.made) == 1 + RETRIES and sleeps == [BACKOFF_S, 2 * BACKOFF_S]
    assert all(c.calls[-1] == "quit" for c in factory.made)


def test_transient_failure_then_success() -> None:
    factory = Factory([("connect", smtplib.SMTPConnectError(421, b"busy"))])
    notifier, sleeps = make_notifier(factory)
    assert notifier.send(make_outbox(TO)).status == "sent"
    assert len(factory.made) == 2 and sleeps == [BACKOFF_S]


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (smtplib.SMTPAuthenticationError(535, b"bad credentials"), False),
        (smtplib.SMTPRecipientsRefused({TO: (550, b"no such user")}), False),
        (smtplib.SMTPSenderRefused(553, b"sender rejected", USER), False),
        (smtplib.SMTPDataError(554, b"message rejected"), False),
        (smtplib.SMTPDataError(451, b"try later"), True),
        (smtplib.SMTPServerDisconnected("connection closed"), True),
        (smtplib.SMTPConnectError(421, b"busy"), True),
        (smtplib.SMTPNotSupportedError("STARTTLS extension not supported"), False),
        (TimeoutError("timed out"), True),
        (TimeoutError("timed out"), True),
        (ConnectionRefusedError(10061, "port blocked"), True),
        (OSError("network unreachable"), True),
    ],
    ids=lambda v: type(v).__name__ if isinstance(v, BaseException) else str(v),
)
def test_error_mapping(error: OSError, retryable: bool) -> None:
    assert classify(error).retryable is retryable


def test_timeout_on_connect_is_retried() -> None:
    factory = Factory([("connect", TimeoutError("timed out"))] * 3)
    notifier, _ = make_notifier(factory)
    with pytest.raises(NotificationError) as info:
        notifier.send(make_outbox(TO))
    assert info.value.retryable is True and len(factory.made) == 1 + RETRIES


def test_repr_masks_the_password() -> None:
    notifier, _ = make_notifier(Factory())
    assert PASSWORD not in repr(notifier) and "**********" in repr(notifier)


def test_daily_cap_is_per_amman_day() -> None:
    clock = FrozenClock()
    factory = Factory()
    notifier, _ = make_notifier(factory, clock=clock, cap=1)
    notifier.send(make_outbox(TO))
    with pytest.raises(NotificationError) as info:
        notifier.send(make_outbox(TO))
    assert info.value.retryable is False and len(factory.made) == 1
    clock.at = clock.at + timedelta(days=1)
    assert notifier.send(make_outbox(TO)).status == "sent"


def test_only_email_messages_and_configured_credentials() -> None:
    notifier, _ = make_notifier(Factory())
    with pytest.raises(NotificationError):
        notifier.send(make_outbox("student-17", kind="in_app"))
    with pytest.raises(NotificationError):
        GmailSmtpNotifier(
            "smtp.test",
            587,
            USER,
            SecretStr(""),
            policy=RecipientPolicy(frozenset({TO})),
            clock=FrozenClock(),
            timeout_s=TIMEOUT_S,
            max_retries=RETRIES,
            backoff_s=BACKOFF_S,
            daily_cap=CAP,
        )


def test_default_factory_uses_stdlib_smtplib(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[tuple[str, str, int, float]] = []

    def plain(host: str, port: int, timeout: float) -> FakeSmtp:
        opened.append(("SMTP", host, port, timeout))
        return FakeSmtp(host, port, timeout, False)

    def implicit(host: str, port: int, timeout: float, context: ssl.SSLContext) -> FakeSmtp:
        opened.append(("SMTP_SSL", host, port, timeout))
        return FakeSmtp(host, port, timeout, True)

    monkeypatch.setattr(gmail_smtp.smtplib, "SMTP", plain)
    monkeypatch.setattr(gmail_smtp.smtplib, "SMTP_SSL", implicit)
    for port in (587, 465):
        GmailSmtpNotifier(
            "smtp.test",
            port,
            USER,
            SecretStr(PASSWORD),
            policy=RecipientPolicy(frozenset({TO})),
            clock=FrozenClock(),
            timeout_s=TIMEOUT_S,
            max_retries=0,
            backoff_s=0.0,
            daily_cap=CAP,
        ).send(make_outbox(TO))
    assert opened == [("SMTP", "smtp.test", 587, TIMEOUT_S), ("SMTP_SSL", "smtp.test", 465, TIMEOUT_S)]
