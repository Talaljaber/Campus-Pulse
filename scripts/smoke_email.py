"""Opt-in live email check (P4.4): send ONE demo email through the real notifier chain.

It sends only when BOTH hold, and refuses otherwise without opening a connection:
- `--to` is on DEMO_EMAIL_ALLOWLIST (the same RecipientPolicy the service uses), and
- `--yes` is passed.

The chain is the production one: AllowlistedNotifier(GmailSmtpNotifier) with an in-memory outbox,
so the printed outbox row is what the service would store. Settings (GMAIL_SMTP_USER,
GMAIL_APP_PASSWORD, SMTP_HOST, SMTP_PORT, SMTP_TIMEOUT_S, SMTP_MAX_RETRIES, SMTP_BACKOFF_S,
SMTP_DAILY_CAP, DEMO_EMAIL_ALLOWLIST) come from the env or the repo `.env`. The password is never
printed.

    python scripts/smoke_email.py --to <allow-listed inbox> --yes
    ->  SMTP OK port=587 message_id=<...@gmail.com> outbox=sent

Exit codes: 0 sent; 1 the send failed (reason printed); 2 refused (not allow-listed, no --yes, or
SMTP not configured).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from campuspulse_ai.adapters.notify.allowlist import AllowlistedNotifier
from campuspulse_ai.adapters.notify.gmail_smtp import GmailSmtpNotifier
from campuspulse_ai.adapters.store.inmemory import InMemoryRepository
from campuspulse_ai.config.settings import Settings
from campuspulse_ai.domain.entities import OutboxMessage
from campuspulse_ai.domain.errors import NotificationError, RecipientNotAllowed
from campuspulse_ai.domain.policy import RecipientPolicy

ROOT = Path(__file__).resolve().parents[1]
TZ = "Asia/Amman"
EXIT_SENT, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
SUBJECT = "CampusPulse smoke test (demo)"
BODY = "This is a one-off smoke test of the CampusPulse email channel. No action is needed."


class AmmanClock:
    def now(self) -> datetime:
        return datetime.now(ZoneInfo(TZ))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--to", required=True, help="recipient; must be on DEMO_EMAIL_ALLOWLIST")
    parser.add_argument("--yes", action="store_true", help="really send (without it nothing is sent)")
    args = parser.parse_args(argv)

    settings = Settings(_env_file=ROOT / ".env")  # type: ignore[call-arg]
    policy = RecipientPolicy(settings.demo_email_allowlist)
    try:
        policy.check(args.to)
    except RecipientNotAllowed:
        print(f"REFUSED: {args.to!r} is not on DEMO_EMAIL_ALLOWLIST; nothing was sent.", file=sys.stderr)
        return EXIT_REFUSED
    if not args.yes:
        print(f"REFUSED: pass --yes to send one email to {args.to}; nothing was sent.", file=sys.stderr)
        return EXIT_REFUSED
    if not settings.gmail_smtp_user or settings.gmail_app_password is None:
        print("REFUSED: set GMAIL_SMTP_USER and GMAIL_APP_PASSWORD; nothing was sent.", file=sys.stderr)
        return EXIT_REFUSED

    clock = AmmanClock()
    repo = InMemoryRepository(clock)
    smtp = GmailSmtpNotifier(
        settings.smtp_host,
        settings.smtp_port,
        settings.gmail_smtp_user,
        settings.gmail_app_password,
        policy=policy,
        clock=clock,
        timeout_s=settings.smtp_timeout_s,
        max_retries=settings.smtp_max_retries,
        backoff_s=settings.smtp_backoff_s,
        daily_cap=settings.smtp_daily_cap,
    )
    notifier = AllowlistedNotifier(smtp, policy, repo)
    msg = OutboxMessage(
        id="",
        kind="email",
        to_address=args.to,
        subject=SUBJECT,
        body=BODY,
        provider_id=None,
        status="queued",
        created_at=clock.now(),
    )
    try:
        sent = notifier.send(msg)
    except (NotificationError, RecipientNotAllowed) as exc:
        retryable = getattr(exc, "retryable", False)
        print(f"SMTP FAILED port={settings.smtp_port} retryable={retryable}: {exc}", file=sys.stderr)
        return EXIT_FAILED
    print(f"SMTP OK port={settings.smtp_port} message_id={sent.provider_id} outbox={sent.status}")
    return EXIT_SENT


if __name__ == "__main__":
    sys.exit(main())
