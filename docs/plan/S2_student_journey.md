# S2 — Student journey after "send" (future, after stability)

> **Status:** planned, not started (user decision [UD-14](../PLAN.md#ud-14)). **Start gate:** the core is stable: the P2 exit gate passed (v1-rc2 frozen), UD-13 advisor routing is live on the web, and the Render and Netlify deploys are green. Nothing here blocks P6.
>
> Conventions: [PLAN.md › Conventions](../PLAN.md#conventions). Tick `- [ ] Done` under each task as you finish it.

**Why.** Today a student gets one smart answer (category, priority, reasons, actions) and live status bubbles in the chat, and then nothing they can browse or act on. These features let a student **follow, confirm, correct and talk about** a request, so the system closes the loop from the student's side. Most backend pieces already exist (tickets, Linear status sync, `ticket_status` notifications, incidents, slots/bookings), so the work is mostly new reads, a few endpoints and new screens.

**Order.** Build in this order; each item is shippable alone.

<a id="s2-1"></a>
## S2.1 — Resolved? Rate it, or reopen it
- [ ] Done
- When a ticket becomes `resolved`, the student is asked in the timeline and as a notification: **"Did this fix it?"**
  - **Yes:** the ticket closes, and the student gives a 1–5 rating. Ratings appear in the model lab as student satisfaction per office.
  - **No:** the ticket reopens to the same office, with the student's note, its SLA restarted and the office notified. It mirrors to Linear as a state change plus a comment.
- **FAQ answers:** add "Helpful / Not helpful". "Not helpful" creates a ticket from the same request (the FAQ fallback), and both outcomes are logged so `tau_faq` can be re-measured.
- **DB:** `tickets.rating smallint null`, `tickets.reopened_count int default 0`, and a `faq_feedback` record (or an event). Students may update only these fields on their own tickets (RLS or a definer RPC).
- **Backend:** `POST /v1/tickets/{id}/confirm` with `{fixed: bool, rating?, note?}`, plus `POST /v1/faq/{request_id}/feedback`. The reopen goes through SyncTicketUseCase rules: a reopen by the owner is the only allowed backwards move.
- **UI:** a confirm card in the timeline, and a rating control.

<a id="s2-2"></a>
## S2.2 — Known-issue matching and campus status
- [ ] Done
- On triage, if the request matches an **open incident** (same building, cosine to the centroid ≥ `tau_inc`, per D-015/D-017), the student sees: **"Known issue: Wi-Fi in building M, 6 reports, IT is on it."** They can then:
  - **follow** it: they're notified on updates and resolution;
  - or **report anyway**: a normal ticket, kept as `merged` under the incident as today.
- A small **campus-status banner** on the student page lists current open incidents by building, with a short label.
- **Backend:** triage returns `known_issue: {incident_id, title, reports, office}` (additive DTO field), and `POST /v1/incidents/{id}/follow`.
- **DB:** `incident_followers(incident_id, alias)` with RLS (students see only their own follows). Incident broadcast notifies the followers.
- **UI:** a known-issue card in the chat and the status banner.

<a id="s2-3"></a>
## S2.3 — My requests and a live timeline
- [ ] Done
- A **"My requests"** page lists every request with:
  - its status (open, in progress, resolved, closed);
  - its office and ticket number;
  - an **expected-by** time from the SLA (`sla_due_at`).
  - It has filters for active, finished and all.
- **Request detail:** a live **timeline** from the request's events: submitted → understood as (category × priority, with "why") → clarified → sent to the office or to the advisor (UD-13) → forwarded → in progress → resolved → rated. It updates in real time.
- **Backend:** `GET /v1/me/requests` and `GET /v1/me/requests/{id}` (the timeline is assembled server-side from requests, predictions, tickets, ticket_links and events), student-scoped.
- **UI:** `/requests` and `/requests/[id]`, linked from the chat result card ("Track this request").

<a id="s2-4"></a>
## S2.4 — Follow-up messages
- [ ] Done
- The student can add details to an open request ("only on the 2nd floor"), and staff can reply. Messages appear in the timeline and as notifications, and mirror to Linear as comments (inbound Linear comments come back if the webhook carries them).
- **DB:** `ticket_messages(id, ticket_id, author_alias, author_role, body, created_at)`, with RLS: the owning student plus the ticket's office staff plus admin.
- **Backend:** `POST /v1/tickets/{id}/messages` and `GET /v1/tickets/{id}/messages`. Injection guard and length cap on student text; never re-triage on a follow-up.
- **UI:** a thread in the request detail and in the staff ticket detail.

<a id="s2-5"></a>
## S2.5 — My appointments
- [ ] Done
- Shows the student's advisor bookings (time in Amman, the fictional advisor, room), with **cancel** and **reschedule** (pick another free slot, with the same race-safe claim as booking).
- **Backend:** `GET /v1/me/appointments`, `POST /v1/appointments/{id}/cancel`, `POST /v1/appointments/{id}/reschedule`. Emails go only to allow-listed inboxes.
- **UI:** an appointments section on "My requests".

<a id="s2-6"></a>
## S2.6 — Cancel a request
- [ ] Done
- "Never mind, it's fixed": the student withdraws an open request. The ticket closes with reason `withdrawn_by_student`, mirrors to Linear and is audited. Safety tickets can't be withdrawn by the student (staff close them).
- **Backend:** `POST /v1/tickets/{id}/withdraw` with `{note?}`. **UI:** a button in the request detail.

<a id="s2-7"></a>
## S2.7 — Notification centre
- [ ] Done
- A bell with every past update (not only the live bubbles in the chat), an unread count, mark-as-read, and tap-to-open the related request.
- **DB:** `notifications.read_at timestamptz null`, so a student can mark their own as read.
- **UI:** a bell in the header for every role (staff see their office notes, per 0010).

## Notes
- **i18n:** every new string is in EN and AR (native review), and RTL-safe.
- **Privacy:** students only ever see their own requests, messages and follows (RLS). Staff see their office (0010/0012). Distress stays admin-only (0011).
- **Video:** S2.1–S2.3 make a strong "student follow-up" demo moment if built before the recording.
