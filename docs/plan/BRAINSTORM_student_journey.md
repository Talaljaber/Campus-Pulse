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
