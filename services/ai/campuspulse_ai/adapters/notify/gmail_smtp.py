"""GmailSmtpNotifier: email through Gmail SMTP with an app password, stdlib only (P4.4, LD-3).

Port 587: `SMTP` -> EHLO -> STARTTLS (default SSL context, so the certificate is verified) -> EHLO
-> LOGIN -> `send_message`. Port 465 (or `use_ssl=True`): `SMTP_SSL` with the same context. There is
no mail SDK anywhere (LD-3).

Recipients: the notifier holds its own `RecipientPolicy` and refuses a non-allow-listed address
before opening a connection. This is defence in depth: `AllowlistedNotifier` (the outermost
decorator) is where rejections are recorded, but a mis-wired chain still cannot reach a real person.
"""

from __future__ import annotations

import dataclasses
import html
import smtplib
import ssl
import time
from collections.abc import Callable
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Protocol

from pydantic import SecretStr

from campuspulse_ai.domain.entities import OutboxMessage
from campuspulse_ai.domain.errors import NotificationError
from campuspulse_ai.domain.policy import RecipientPolicy
from campuspulse_ai.domain.ports import Clock

SSL_PORT = 465  # implicit TLS; any other port uses STARTTLS
DEFAULT_SENDER_NAME = "CampusPulse (demo)"
FOOTER = "Demo message from an integration-ready prototype; sent to a developer-owned inbox."
PROVIDER = "gmail_smtp"
_TRANSIENT_MIN, _TRANSIENT_MAX = 400, 500  # SMTP 4yz replies are transient (RFC 5321 §4.2.1)


class SmtpConnection(Protocol):
    """The part of `smtplib.SMTP` this notifier uses (fakes implement it in tests)."""

    def ehlo(self, name: str = "") -> tuple[int, bytes]: ...

    def starttls(self, *, context: ssl.SSLContext | None = None) -> tuple[int, bytes]: ...

    def login(self, user: str, password: str) -> tuple[int, bytes]: ...

    def send_message(self, msg: EmailMessage) -> dict[str, tuple[int, bytes]]: ...

    def quit(self) -> tuple[int, bytes]: ...

    def close(self) -> None: ...


# (host, port, timeout_s, use_ssl, ssl context) -> an open connection
SmtpFactory = Callable[[str, int, float, bool, ssl.SSLContext], SmtpConnection]


def default_smtp_factory(
    host: str, port: int, timeout_s: float, use_ssl: bool, context: ssl.SSLContext
) -> SmtpConnection:
    """Open a real stdlib connection (`SMTP_SSL` for implicit TLS, else plain `SMTP`)."""
    if use_ssl:
        return smtplib.SMTP_SSL(host, port, timeout=timeout_s, context=context)
    return smtplib.SMTP(host, port, timeout=timeout_s)


class GmailSmtpNotifier:
    """`Notifier` for `kind="email"` over Gmail SMTP.

    `send(msg)` returns `msg` with `status="sent"` and `provider_id` = the RFC 5322 Message-ID it
    generated. The body is sent as plain text and HTML, each with the demo footer.

    Errors, all `NotificationError(retryable=...)` (LD-15):
    - not retryable: authentication failure (535), recipients refused, a 5xx reply, STARTTLS not
      supported, a non-email message; also `RecipientNotAllowed` (not an allow-listed address,
      raised before any connection);
    - retryable: a 4xx reply, a disconnect, a connect error, a timeout, or `OSError` (e.g. the port
      is blocked). These are retried `max_retries` times with backoff `backoff_s * 2**attempt`,
      then raised.

    Daily cap: at most `daily_cap` successful sends per day of `clock` (Asia/Amman), counted in
    this process (Gmail's own limit is 500 recipients a day; the cap keeps the demo far below it).
    Above the cap nothing is sent and `send` returns the message with `status="deferred"` and the
    reason in `error` (P4.4 step 4, D-011); `AllowlistedNotifier` records that row as returned.
    The app password is a `SecretStr`, read only for `login`, and masked in `repr`.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        app_password: SecretStr,
        *,
        policy: RecipientPolicy,
        clock: Clock,
        timeout_s: float,
        max_retries: int,
        backoff_s: float,
        daily_cap: int,
        use_ssl: bool | None = None,
        sender_name: str = DEFAULT_SENDER_NAME,
        smtp_factory: SmtpFactory | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not user or not app_password.get_secret_value():
            raise NotificationError(
                "Gmail SMTP is not configured (user or app password missing)", retryable=False
            )
        if max_retries < 0 or daily_cap < 0 or timeout_s <= 0 or backoff_s < 0:
            raise ValueError("timeout_s must be > 0; max_retries, backoff_s and daily_cap must be >= 0")
        self._host = host
        self._port = port
        self._user = user
        self._password = app_password
        self._policy = policy
        self._clock = clock
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._backoff_s = backoff_s
        self._daily_cap = daily_cap
        self._use_ssl = port == SSL_PORT if use_ssl is None else use_ssl
        self._sender_name = sender_name
        self._factory: SmtpFactory = smtp_factory or default_smtp_factory
        self._sleep = sleep
        self._sent_on: tuple[date, int] | None = None

    def __repr__(self) -> str:
        return (
            f"GmailSmtpNotifier(host={self._host!r}, port={self._port}, user={self._user!r}, "
            f"app_password={self._password!r}, use_ssl={self._use_ssl})"
        )

    def send(self, msg: OutboxMessage) -> OutboxMessage:
        if msg.kind != "email":
            raise NotificationError(f"GmailSmtpNotifier only sends email, not {msg.kind!r}", retryable=False)
        self._policy.check(msg.to_address)  # RecipientNotAllowed before any connection
        today = self._clock.now().date()
        sent_today = self._sent_on[1] if self._sent_on and self._sent_on[0] == today else 0
        if sent_today >= self._daily_cap:
            reason = f"daily email cap of {self._daily_cap} reached"
            return dataclasses.replace(msg, status="deferred", provider_id=None, error=reason)

        email, message_id = self._build(msg)
        last: NotificationError | None = None
        for attempt in range(self._max_retries + 1):
            if attempt:
                self._sleep(self._backoff_s * 2 ** (attempt - 1))
            try:
                self._deliver(email)
            except OSError as exc:  # smtplib.SMTPException is an OSError subclass
                last = classify(exc)
                if not last.retryable:
                    raise last from exc
                continue
            self._sent_on = (today, sent_today + 1)
            return dataclasses.replace(msg, status="sent", provider_id=message_id)
        assert last is not None
        raise NotificationError(f"{last} (gave up after {self._max_retries} retries)", retryable=True)

    def _deliver(self, email: EmailMessage) -> None:
        context = ssl.create_default_context()
        conn = self._factory(self._host, self._port, self._timeout_s, self._use_ssl, context)
        try:
            conn.ehlo()
            if not self._use_ssl:
                conn.starttls(context=context)
                conn.ehlo()
            conn.login(self._user, self._password.get_secret_value())
            conn.send_message(email)
        finally:
            try:
                conn.quit()
            except OSError:
                conn.close()

    def _build(self, msg: OutboxMessage) -> tuple[EmailMessage, str]:
        domain = self._user.rpartition("@")[2] or None
        message_id = make_msgid(domain=domain)
        email = EmailMessage()
        email["From"] = formataddr((self._sender_name, self._user))
        email["To"] = msg.to_address
        email["Subject"] = msg.subject
        email["Message-ID"] = message_id
        email.set_content(f"{msg.body}\n\n-- \n{FOOTER}\n")
        footer_html = f"<hr><p><small>{html.escape(FOOTER)}</small></p>"
        if msg.html:
            page = (
                msg.html.replace("</body>", footer_html + "</body>", 1)
                if "</body>" in msg.html
                else msg.html + footer_html
            )
        else:
            body_html = html.escape(msg.body).replace("\n", "<br>\n")
            page = f"<html><body><p>{body_html}</p>{footer_html}</body></html>"
        email.add_alternative(page, subtype="html")
        return email, message_id


def classify(exc: OSError) -> NotificationError:
    """Map an smtplib/socket error to `NotificationError` with the right `retryable` (P4.4 step 2)."""
    name = type(exc).__name__
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return NotificationError(f"SMTP authentication failed ({exc.smtp_code})", retryable=False)
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return NotificationError("SMTP server refused the recipient", retryable=False)
    if isinstance(exc, smtplib.SMTPServerDisconnected | smtplib.SMTPConnectError):
        return NotificationError(f"SMTP connection problem ({name})", retryable=True)
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return NotificationError("SMTP server does not support a required extension", retryable=False)
    if isinstance(exc, smtplib.SMTPResponseException):
        transient = _TRANSIENT_MIN <= exc.smtp_code < _TRANSIENT_MAX
        return NotificationError(f"SMTP server replied {exc.smtp_code} ({name})", retryable=transient)
    if isinstance(exc, smtplib.SMTPException):
        return NotificationError(f"SMTP protocol error ({name})", retryable=False)
    return NotificationError(f"SMTP network error ({name})", retryable=True)  # timeout, blocked port
