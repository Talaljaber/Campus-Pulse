# S1 — WhatsApp urgent channel (stretch)

> **Status:** DRAFT — awaiting user approval. **Budget:** stretch (ARCHITECTURE §4.0) · **Calendar:** only after P6.7 is green · **Planned (not cut-flagged):** 0 h · **Cut-flagged:** 2.5 h (all of S1, cut #0).
>
> Conventions: [PLAN.md › Conventions](../PLAN.md#conventions). `§n` refers to [ARCHITECTURE.md](../ARCHITECTURE.md); `LD-n` and `OQ-n` link to the lead decisions and open questions in [PLAN.md](../PLAN.md). Tick `- [ ] Done` under each task as you finish it, and tick this phase's decision log at the bottom.

> **Future work: out of scope for this submission (user decision [UD-3](../PLAN.md#ud-3)).** Not built before 10 Nov. Kept as the design for a later version and listed in the README "Future work".

Cut-order **#0**: the first thing cut, before voice. Budget 2.5 h, started only after [P6.7](P6_ship.md#p6-7) is green.

**Goal.** For requests whose final priority is `high`, or which carry the `safety` flag, deliver the outgoing staff/student alert by **WhatsApp (Meta WhatsApp Cloud API, Graph API, not Twilio)** instead of Gmail. Fall back to Gmail if WhatsApp is unconfigured, rejected or failing.

**Pure extension:**
- no existing notifier is edited;
- with **no `WHATSAPP_*` env vars, nothing is constructed and behaviour is byte-identical to P4**;
- it blocks no exit criterion of any phase.

**Where it plugs in.** `build_online` wraps the existing chain:
```
notifier = AllowlistedNotifier(                                   # email allow-list (unchanged, outermost)
             RoutingNotifier(primary=GmailSmtpNotifier | InAppNotifier,
                             urgent=AllowlistedNotifier(WhatsAppCloudNotifier, RecipientPolicy(DEMO_PHONE_ALLOWLIST), repo),
                             policy=ThresholdChannelPolicy(...), directory=DemoContactDirectory(...)),
             RecipientPolicy(DEMO_EMAIL_ALLOWLIST), repo)
# when WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID is unset: RoutingNotifier is not constructed at all.
```

<a id="s1-1"></a>
## S1.1 — Write the channel policy and RoutingNotifier

- [ ] Done
- Depends on: [P4.4](P4_product_backend.md#p4-4)
- Est: 1 h · Cut: yes (#0)
- Files:
  - services/ai/campuspulse_ai/domain/notify_policy.py (Files added)
  - services/ai/campuspulse_ai/adapters/notify/routing.py (Files added)
  - config/demo_contacts.yaml (Files added: email → E.164 phone, developer-owned only)
  - services/ai/tests/unit/test_routing_notifier.py
- Interfaces: a new small port `NotificationChannelPolicy` (it has a test fake, so it qualifies under §1.0.3).
  ```python
  class NotificationChannelPolicy(Protocol):
      def choose(self, msg: OutboxMessage) -> Literal["email", "whatsapp"]: ...
  class ThresholdChannelPolicy:   # domain, pure
      def __init__(self, min_priority: Priority, on_safety: bool, kinds: frozenset[str]) -> None: ...
  class RoutingNotifier:  # Notifier (decorator; does not modify GmailSmtpNotifier)
      def __init__(self, primary: Notifier, urgent: Notifier, policy: NotificationChannelPolicy, directory: "DemoContactDirectory") -> None: ...
      def send(self, msg: OutboxMessage) -> OutboxMessage: ...   # whatsapp path → on RecipientNotAllowed | NotificationError | no phone → primary.send(msg); outbox records both attempts
  ```
- Config keys: Settings `WHATSAPP_MIN_PRIORITY` (`high`), `WHATSAPP_ON_SAFETY` (true), `WHATSAPP_KINDS` (`alert,booking,broadcast`)
- Steps:
  1. The decision needs the priority and flags on the message. `OutboxMessage` gains optional `priority: Priority | None = None` and `flags: frozenset[str] = frozenset()`. This is additive with defaults, and `ActUseCase` fills them; it is the one touch to P4 code ([LD-25](../PLAN.md#ld-25)).
  2. Tests:
     - high or safety → whatsapp;
     - medium → email;
     - WhatsApp failure → email sent and outbox has both rows (`channel=whatsapp status=failed`, `channel=email status=sent`);
     - an unknown phone → email.
- Acceptance: `pytest services/ai/tests/unit/test_routing_notifier.py -q` → `≥ 5 passed`

<a id="s1-2"></a>
## S1.2 — Write the WhatsAppCloudNotifier adapter

- [ ] Done
- Depends on: S1.1
- Est: 1 h · Cut: yes (#0)
- Files:
  - services/ai/campuspulse_ai/adapters/notify/whatsapp_cloud.py (Files added)
  - services/ai/tests/unit/test_whatsapp_cloud.py
  - services/ai/tests/fixtures/whatsapp/*.json
  - supabase/migrations/0006_outbox_channel_whatsapp.sql (only if `outbox.channel` was not added in [P4.1](P4_product_backend.md#p4-1))
- Interfaces:
  ```python
  class WhatsAppCloudNotifier:  # Notifier
      def __init__(self, token: str, phone_number_id: str, api_version: str, template: str, template_lang: str,
                   http: "httpx.Client", *, timeout_s: float, max_retries: int) -> None: ...
      def send(self, msg: OutboxMessage) -> OutboxMessage: ...   # provider_id = wamid; NotificationError(retryable) on 5xx/timeout; non-retryable on 4xx
  ```
- Config keys: `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION` (default `v26.0`, the version current in Meta docs, verified), `WHATSAPP_TEMPLATE` (default `hello_world`; target `urgent_request_alert`), `WHATSAPP_TEMPLATE_LANG` (`en_US`), `DEMO_PHONE_ALLOWLIST` (comma-separated E.164 digits; **empty ⇒ reject all**).
- Steps:
  1. Send `POST https://graph.facebook.com/{version}/{PHONE_NUMBER_ID}/messages` with `Authorization: Bearer <token>` (verified) and the body `{"messaging_product":"whatsapp","to":"<E.164>","type":"template","template":{"name":…,"language":{"code":…},"components":[{"type":"body","parameters":[{"type":"text","text":"<category>"},{"type":"text","text":"<building>"},{"type":"text","text":"<ticket_id>"}]}]}}`. The template body shape is UNVERIFIED; check it against the Meta template docs during S1.3.
  2. **Business-initiated messages outside the 24 h window must use an approved template** (verified). A free-text `type:"text"` message is never used.
  3. Error mapping by `error.code`:
     - `190` (token expired, verified) → non-retryable;
     - `131047` (24 h window, verified) → non-retryable;
     - recipient not in the test allowed list → non-retryable (code UNVERIFIED);
     - 5xx/timeout → retryable.
  4. Phone allow-list: `RecipientPolicy` is reused with digits-only normalisation.
- Acceptance: `pytest services/ai/tests/unit/test_whatsapp_cloud.py -q` → `≥ 5 passed` (respx)

<a id="s1-3"></a>
## S1.3 — Set up the account and send one live message

- [ ] Done
- Depends on: S1.2; [Appendix D](appendix_D_accounts.md) (Meta)
- Est: 0.5 h + template approval wait (approval time UNVERIFIED) · Cut: yes (#0)
- Steps:
  1. Register up to **5** developer-owned recipient numbers on the test number (the 5-recipient limit is from Meta docs search snippets; partly verified).
  2. Submit a **utility** template `urgent_request_alert` ("CampusPulse demo: urgent {{1}} request in building {{2}}, ticket {{3}}"). Until it is approved, use `hello_world`.
  3. Create a **System User token** with `whatsapp_business_messaging`, `whatsapp_business_management` and `business_management` (verified). The dashboard temporary token "expires quickly" (verified; about 24 h is UNVERIFIED).
  4. Set the env on Render and redeploy.
- Acceptance: `python scripts/smoke_whatsapp.py --to <allow-listed E.164>` (Files added) → `WhatsApp OK wamid=…`. A safety request on the hosted app → outbox shows `channel=whatsapp status=sent`.
- Notes:
  - Pricing is per message since 1 Jul 2025, and utility messages are charged again from 1 Oct 2026 (verified). Test-number messages are believed free (UNVERIFIED).
  - Never message a non-allow-listed number.
  - Disclose "Meta WhatsApp Cloud API" in README if shipped.

## S1 decisions logged during this phase
- [ ] WhatsApp built or cut (#0)
- [ ] Meta app, phone number ID and template approval date
- [ ] `DEMO_PHONE_ALLOWLIST` contents (developer-owned numbers only)
