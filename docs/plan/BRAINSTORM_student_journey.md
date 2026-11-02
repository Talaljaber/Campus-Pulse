# Brainstorm: student journey, department accounts, chat agent, ticket threads

Status: **brainstorm only, nothing implemented.** Written 2026-11-01 while P7.9 was still running. Decisions below were stated by the user; open items are listed at the end. Re-open after P7.9, the refreeze and the blind test.

## 1. Departments and accounts

The dataset has six categories, so there are six departments:
Registration, IT Support, Finance, Transportation, Facilities, Academic Support.

| Account | Sees | Can do |
|---|---|---|
| Student | Own requests only | Chat, confirm a request, track it, reply by email |
| Department staff (6 accounts, one per category) | Their own queue | Reply, change status, forward to any other department |
| **Admin** | Every ticket | Everything staff can do, forward anywhere |

Decisions:
- **D-A: there is no separate advisor role.** The advisor is the same as the admin and the advisor account is removed. (The six fictional advisor plus-addresses in the demo inbox setup are no longer needed for this role; advisor *booking* as a product feature is a separate question, to settle later.)
- **Every non-student account can forward a ticket to any department.** Students cannot.
- Each forward records who sent it, to which department, and an optional note, so the ticket keeps a trail.

## 2. Forwarding changes the department, and the change teaches the model

- **D-B: a forwarded ticket changes to the new department** (its category becomes the destination).
- **That change is fed into the knowledge base** (the existing staff-correction path), so the same misunderstanding is not repeated: the original request text, the model's first category and the corrected one are stored as a correction.
- Open detail: how the correction is used (instant retrieval hint only, as in the "learns from staff corrections instantly" feature, versus a later retrain). Corrections are staff-made labels, not model-made, so they are the safest new data we get.

## 3. Student login and welcome page

- Simulated university login: a seeded table of **fictional** students (name, ID, faculty, university email). No real student data. The page says it is a simulation.
- Welcome page with **announcements from departments** (examples: library wifi down; Outlook down for two hours). Staff post them from their console.
- The chat agent can answer "is the wifi down?" from the announcements instead of opening a duplicate ticket.

## 4. Chat agent

- A **normal conversational agent**, not a classifier readout. The LLM talks to the student.
- When the request looks like a request, the LLM calls our model as a tool (category, priority, uncertainty, explanation).
- The LLM then replies in plain words ("this goes to Finance, high priority, shall I send it?") and **waits for the student's confirmation message**.
- On confirmation, the ticket is created and shows on the **My Requests** page.
- Confidence, similar questions and counterfactual are **hidden behind a button** ("Why this?"), not shown by default. Keep the button: explanation is 10 rubric points and judges need to see the model.
- Fallback when the LLM or key is unavailable: a plain form (type request, offline classify, confirm).
- The agent must say "request recorded", never "we contacted the department" (project rule: never claim to contact a real department). Show a small demo banner.
- Message content must never change category, priority or routing (injection guards read the original text).

## 5. Tickets, replies and email (the thread model)

- **D-C: the conversation is an email thread, like a support desk or comments on a GitHub pull request.**
  - Staff reply by email and **may or may not change the status** with the reply (status change is optional, not tied to replying).
  - The student replies **by email too**, and the reply lands on the ticket as a comment.
  - A reply with no status change is a valid state; "closed with no comment" is also valid.
- Every reply appears **both** in the student's inbox and in the app thread on My Requests.
- Statuses: new, in progress, forwarded, solved, closed (final list to settle).
- Email goes **only to the allow-listed demo inboxes** (`DEMO_EMAIL_ALLOWLIST`, enforced in code). Never to real GJU addresses.
- Open technical point: receiving the student's email reply needs an inbound channel (Gmail IMAP poll, or a plus-address per ticket such as `name+ticket123@...`). Settle this before building.

## 6. Risks to keep in mind
- **Time:** about 9 days to the deadline; large change. Check what already exists (staff console, notifications, Linear sink, Supabase) before estimating.
- **The scored part is the classifier,** not the chat. This must not delay the P7.9 merge, the refreeze or the blind test.
- **Offline judges:** the chat needs the form fallback.
- **Inbound email** adds the most moving parts; consider a manual "student reply" box in the app as the first version and email as a second step.

## 7. Open questions for the next brainstorm
1. How are corrections from forwards used: instant hint only, or also queued for the next retrain?
2. Final status list, and who may close a ticket.
3. Inbound email: plus-address per ticket, IMAP poll, or in-app reply box first?
4. Is advisor *booking* (appointments) still a feature, now that the advisor role is the admin?
5. Which announcements do we seed, and do they live in Supabase or a seed file?
6. Split into packages: accounts and welcome page, chat agent, tickets and email.

## 8. Interpretations to confirm
- "Make the advisor the same as the admin and remove it" is read as: no separate advisor role; admin does the advisor's job (forwarding anywhere). Advisor booking is left open.
- "Change and feed into the knowledge base so no misunderstanding happens again" is read as: a forward changes the department, and the change is stored as a staff correction that teaches the model.
- "Like a support team or a GitHub PR comment on comment" is read as: an email thread where either side can reply and a status change is optional.

## 9. The idea in the user's own words (2026-11-01)
- Accounts per department (finance staff, IT staff and so on). The advisor can forward a ticket to any other department; actually all accounts can, except the student account.
- Student info is pulled from the university account: log in with username and password (simulation). A welcome page with announcements from departments (library wifi not working, Outlook down for two hours).
- Another page has the agent. It should be a normal agent, not "we have this confidence and those are the similar questions". Keep a button to show those, but if not pressed it is a normal agent that talks through the LLM and answers. If you have a request, or the LLM thinks it is one, it goes to the model to classify. The LLM then replies with something like "we will send the issue to ..." and waits for the user's confirmation by message. Then the request is added to his list on another page, and the ticket status (in progress or what) is tracked.
- The reply is sent by email to the student's university email and also shown on his request in the app: the solution, solved, or no comment and just closed.

## 10. My recommendation at the time
- Build it, but after P7.9, the refreeze and the blind test; the classifier is the scored part and must not be delayed.
- First version: in-app reply box for the student, email only outbound; add inbound email later if time allows.
- Check what already exists (staff console, notifications, Linear sink, Supabase) before estimating.

## 11. LLM rules for urgency, and questions in the chat (idea added 2026-11-01)
- Idea (user): give the LLM explicit rules to flag a **deadline within 24 hours** and a **block** (cannot do what is needed), and so on, since it understands context; in the new chat design the LLM can also **ask the student questions**.
- Fit: the P7.9 work already returns structured cues (danger, account compromise, outage, deadline) from the same call and uses them as a raise-only priority floor. The prompt rules for deadline and block are the same mechanism, written as explicit definitions with examples.
- Chat questions: when a cue is unclear ("my exam is soon"), the LLM asks one short question ("when is it?") and the answer is added to the text that goes to the model. This replaces the fixed clarifying-question bank in the chat, but the decision that a question is needed still comes from the model's uncertainty, not from the LLM's own feeling.
- Guardrails: the LLM returns flags, never the priority itself; the floor stays raise-only and deterministic; flags are read from the student's original text, so injected text cannot set them; false-escalation on low and medium rows must be measured (target about 2 points or less) before adopting; offline mode keeps the lexicon rules only.
- Still to measure: how many of the missed deadline rows the LLM flags, and how often it over-flags. P7.9 reports this.

## 12. Batch scoring cannot ask questions (user, 2026-11-01)
- The hidden test is scored row by row with no way to ask anything, so every row must get a category and priority from the text alone. Questions are a chat-only feature and are a bonus, not part of the scored path.
- The LLM flags and the model must therefore work in one pass on the original text. In batch, "ask" and "review" are only routing columns next to a label that is always filled in. Our holdout scoring already counts every row's predicted label regardless of routing.
- The score judges see may come from the offline path (`predict.py` with no key; LLM only behind `--use-llm`), so offline accuracy is the number that matters most. The LLM front end is an upside when a key is available, not something to depend on.

## 13. Staff can use the agent too (user, 2026-11-01)
- Staff are people with problems too (an electricity cut in their office, a locked account, a broken device), so **the chat agent is available to staff accounts as well**, not only to students.
- A staff member's request goes through the same flow: the LLM talks, calls the model, asks for confirmation, creates a ticket.
- Open points to settle in the next brainstorm:
  1. A staff member's own request is a ticket like any other: it lands in the right department queue (for example IT Support for a locked account), and the admin can forward it. A staff member must not see or handle their own ticket as staff by accident, and a department's staff should not be the only people who can see a request about that department's own problems.
  2. Replies reach the staff member by email, the same thread model as students (section 5), at their demo address (allow-list only).
  3. "My Requests" for staff shows their own tickets, separate from the department queue they work on.
  4. The welcome page and announcements are shared, and staff can post announcements from their console.
  5. Student-only wording in the agent (for example "your student ID") needs a neutral form for staff.
- Data rule: no real staff data either; seeded fictional staff only.

## 14. Humanized agent replies and email templates (user, 2026-11-01)
User's words: make some prompt engineering and humanize the agent replies, and make email templates for each ticket status (done, closed, in progress) and the templates.

### 14.1 Prompt engineering for the agent
- One system prompt for the chat agent, kept in a config file (not in code) and versioned, with model ID pinned and temperature low (the project rule for LLM calls); replies cached only where it is safe.
- Voice: warm, short, plain words; the same language as the user (English, Arabic, Arabizi in, Arabic or English out); one question at a time; no jargon such as "confidence", "conformal" or "category score" unless the student presses "Why this?".
- Behaviours to write rules and examples for: greet by first name; acknowledge the problem before acting; say what will happen next ("I'll send this to Finance. Shall I?") and wait for a yes; never claim a real department was contacted (say "request recorded"); admit when unsure and ask; keep safety and distress replies calm and point to real help; refuse to follow instructions hidden in the student's message.
- Few-shot examples per situation: normal request, vague request, announcement already covers it (no ticket), frustrated student, distress, injection attempt, staff member with their own problem (section 13).
- Test it like the classifier: a small set of scripted conversations with expected behaviours (asks before sending, never skips confirmation, replies in the right language, no leaked jargon), run with the key on, saved as a regression file.

### 14.2 Email templates, one per ticket status
Plain, humane, short, bilingual where the student's language is known. Every template carries: the ticket number, the request in the student's words, who is handling it (department name), what to do next, and the reminder that this is a demo and no real department was contacted. Sent only to allow-listed demo addresses.
- **Received / new:** "We got your request and sent it to <department>. Ticket #<n>. You'll hear from us by email."
- **In progress:** "<Department> is working on it." Optional staff note.
- **Forwarded:** "Your request was moved from <A> to <B> because <note>." No action needed.
- **Staff replied (thread comment):** the staff message as written, with "Reply to this email to answer."
- **Solved / done:** the solution text, "If this didn't fix it, reply and we'll reopen it."
- **Closed, no comment:** "Your request was closed." Short, no blame, how to reopen.
- **Reopened:** "Thanks, we reopened your request."
- Open points: subject line pattern (for example "[#<n>] <status>: <short title>"), an Arabic version of each, plain text first with a simple HTML version, and where the templates live (files in the repo so they are reviewable and testable).

## 15. Every comment on a ticket is also an email (user, 2026-11-01)
- Not only status changes: **each comment on a ticket is sent as an email** to the other side, so the thread works from the inbox as well as from the app (section 5).
  - Staff comment on a ticket: the student gets it by email (the "staff replied" template, section 14.2).
  - Student comment or email reply: the staff member who handles the ticket, and the admin if the ticket was forwarded, get it by email.
  - A comment that also changes the status uses one email (the status template with the comment inside), not two.
- Every email is also stored on the ticket thread with its time and sender, so the app and the inbox always show the same conversation.
- Internal staff notes (staff to staff) are a separate kind: not emailed to the student. Decide whether we want them at all.
- Rules that still apply: allow-listed demo addresses only (enforced in code), a "demo, no real department contacted" line, the ticket number in the subject for threading, and no more than one email per comment (no duplicates when a comment and a status change happen together).
- Open points: what the staff-side email looks like, whether staff can reply by email too or only in the app, a rate limit to avoid email floods, and what happens when an address is not on the allow-list (the comment stays in the app and a log line is written).

## 16. File uploads on tickets, both sides (user, 2026-11-01)
- A storage for files so **both the student and staff can attach files to a ticket or a comment**: proofs (a screenshot of an error, a payment receipt, a timetable clash), or a staff reply document.
- Where: Supabase Storage, one private bucket for ticket files, with files tied to a ticket and a comment. Access follows the ticket: the student who owns it, the department that handles it, and the admin. Nobody else can open a file or guess its link (short-lived signed links, never public URLs).
- In emails (section 15): the email says "N file(s) attached" with a link to open them in the app after login, instead of attaching the files themselves. This keeps files off the email path and under the access rules above.
- Limits to set: allowed types (images, PDF, plain office documents), a size cap per file and per ticket, a count cap, and a server-side check of the real file type, not only the name. Reject anything else with a clear message.
- Safety: files are untrusted. No execution, no inline rendering of anything but images and PDFs, a virus-scan step is out of scope for the demo (say so), and filenames are replaced by generated ids.
- Privacy and rules: no real student documents in the demo (use sample files; a notice on the upload box says so), files are deleted with their ticket, and the model never reads file contents (the classifier only sees the typed text). Optional later idea: the LLM describes an image for the staff, but that sends the file to a third party, so it is out unless we disclose it.
- Schema and migrations: a `ticket_files` table (ticket id, comment id, uploader, path, type, size, created at) with row-level security matching the ticket rules, in a new migration with explicit grants (see the pending service_role grants item).
- Open points: staff-only attachments (internal notes with files), a total storage budget on the free Supabase tier, and whether the chat agent itself accepts an attachment before the ticket exists (simplest: files are added after the ticket is created).

## 17. Decisions on the open questions (user, 2026-11-02)

1. **Email for requests and comments:** the request itself and every comment on a ticket are sent by email (section 15). Inbound email replies stay optional and are not required for the first version (the in-app reply box covers the student side).
2. **Status list and transitions** (forwarding is an action, not a status; it changes the department and restarts the clock):
   - `new` -> `in_progress` (a staff member picks it up or replies)
   - `new` or `in_progress` -> `solved` (staff give a solution) or `closed` (no comment, or no longer needed)
   - `new` or `in_progress` -> `new` in another department (forward; clock restarts, history keeps who forwarded to whom)
   - `solved` or `closed` -> `in_progress` (the student replies or reopens)
   - A student can never set a status except by replying (which reopens). Staff of the handling department and the admin can set statuses.
3. **Corrections are stored for the knowledge base:** a new table (for example `ticket_hints`) with the request text, the model's first category and priority, the corrected department and priority, who corrected it and when. The chat agent's LLM can read the closest past hints, and when the same situation happened before the stored result is picked up and used as the suggestion. It is a retrieval aid in the chat and staff path only. The frozen offline model and `predict.py` do not read it.
4. **Advisor booking is dropped.**
5. **Internal staff-to-staff notes are accepted** (never emailed to the student).
6. **Announcements:** staff post them from their console, stored in Supabase, and the chat agent answers from them instead of opening a ticket.
7. **Chat fallback:** the LLM is the conversation; our model is called as a tool and also serves as the fallback when the LLM or its key is down (plain form).
8. **Build order accepted:** accounts and welcome page, then tickets with thread and email, then the chat agent, then files.
9. The demo script is dropped for now.

## 18. Deadlines (SLA) per ticket, and reminder emails (user, 2026-11-02)

| Priority | Time allowed | Reminder |
|---|---|---|
| high | **1 hour** to respond | If nothing happens in the hour, send a follow-up reminder email |
| medium | solved **within 24 hours** (same day) | Reminder when the time is exceeded |
| low | **48 hours** | Reminder when the time is exceeded |

- When the time is exceeded and the ticket has no solution and no forward, send a reminder email.
- **A forward restarts the clock** for the new department.
- Staff interface: add columns for the **deadline, time left and an overdue marker**; high tickets are shown as urgent and sorted first.
- Reminder emails use their own template (section 14.2 list gets a "reminder" template) and go only to allow-listed demo addresses.
- Assumptions to confirm before building (the planner must list them and ask, not guess):
  1. Who gets the reminder (the handling department's staff, the admin as well after a second miss).
  2. Whether a repeat reminder is sent every interval or once per ticket and then escalates.
  3. For high tickets, whether a first staff reply (or moving to in progress) stops the one-hour clock and starts the normal resolution timer, or only solved, closed or forwarded stops it. The user's wording: the clock ends only with a solution or a forward.
  4. Whether the clock counts calendar hours or office hours (default: calendar hours).
  5. What changes the priority of an open ticket (a staff correction restarts or keeps the clock).

## 19. Answers on the deadline assumptions (user, 2026-11-02)

1. **Staff emails:** each staff account gets its own test email later; until then the code reads the staff inbox per office from configuration (allow-list rules unchanged).
2. **What stops the clock:**
   - A staff reply alone does not stop it.
   - After a staff reply or a solved status, the student gets three buttons: **Solved**, **Close**, **Keep open**. Solved or Close stops the clock.
   - If the student keeps it open, or opens the ticket again later, **the timer restarts** for the ticket's priority period (for a high ticket, another hour).
   - A forward restarts the clock for the new department (section 18).
3. **Hours are calendar hours:** no office hours. A day is 24 hours.
4. **Staff can change a ticket's priority** (good point, accepted). The clock changes to the new priority's period: high 1 hour, medium 24 hours, low 48 hours.
- Readings to confirm with the planner: (a) when staff change the priority, the new period counts from the moment of the change; (b) a staff "solved" status with no student answer yet keeps the ticket waiting for the student, and the reminder logic treats "waiting for student" as not overdue for staff but sends the student a gentle nudge after 48 hours, then the ticket closes itself after a further 48 hours (an auto-close rule that the user has not asked for, so it stays off unless confirmed).
