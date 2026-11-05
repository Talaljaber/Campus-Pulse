# P10 package B — consented ticket email recipients

Implemented `InboxBook` callbacks for current requester notification address and office staff notification addresses, gated by `opt_in_enabled`. The requester receives their consented address first, falling back to the configured demo inbox. The office receives its configured inbox plus consented staff of that office; the requester alias and resolved requester email are excluded and duplicate addresses are collapsed. A failed profile lookup degrades to configured demo delivery. Each recipient gets a separate lifecycle email send and failure handling.

The outer notifier and SMTP still check `RecipientPolicy` at send time. The integrator must pass the SAME instance of the policy to both gates, with `consent_lookup=SupabaseProfileEmailStore.has_active_consent` and the settings flag. This means removal or disabling opt-in takes effect for queued email before SMTP delivery. The SMTP footer now describes both configured and consented demo recipients.

Changed files: `application/use_cases/ticket_emails.py`, `ticket_lifecycle.py`, `adapters/notify/allowlist.py`, `gmail_smtp.py`, and `tests/unit/test_ticket_emails.py`.

Integration contract: `InboxBook(..., notification_for_alias=store.notification_for_alias, staff_notifications_for_office=store.staff_notifications_for_office, opt_in_enabled=settings.email_opt_in)`. Package A added both lookup methods; they return currently consented addresses. Composition wiring is owned by package I. The opt-in flag must default false. No live email was sent.

Checks: 100 focused ticket email/lifecycle tests passed; strict mypy on both changed application modules passed. Ruff had one line-length issue in the new test, corrected afterward; rerun it during integration.

Limitations: `PlannedEmail.to` accepts a tuple for office fan-out and retains a scalar for one recipient to preserve existing behavior. Recipient callback failure is logged and skips optional recipients. The all-profile announcement audience and durable broadcast job belong to package G.
