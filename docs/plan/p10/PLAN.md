# P10: three follow-ups found while testing the P9 build (PAUSED, nothing implemented)

Written 2026-11-02 at the user's request: document, stop the agents, implement nothing now. Two agents (P10.1, P10.2) were started and stopped before any commit, so nothing from them is merged; any files left in their worktrees are unreviewed and should be discarded or re-done. P10.3 was never started.

## What was seen (facts from the local test run)
1. **Emails skipped:** the API log says "recipient not in DEMO allow-list: talal123542006@gmail.com" for forward, reply and reopen emails. Tickets work; no ticket email is sent to a non-allow-listed address.
2. **Chat invented advice:** the only announcement said "library wifi is down". For "wifi is down why" the agent added "our team is working on it" and "please use the lab network meanwhile", which no source says.
3. **LLM refused on the second turn:** `llm call failed (OpenRouter refused the call (429: credits or rate limit))`, so the chat fell back to the plain form (working as designed). Cause is credits or a rate limit; not known which.
4. **Clustering exists only in part** (SPEC 5.1 step 13): per-building incident detection, 30-minute window, embedding similarity, 3 or more reports merge into one incident and notify reporters. Not verified against the new P9 chat and ticket flow; needs a building; broadcast goes to reporters only.

## P10.1 Notification email with a consent tickbox (user decision)
- Profile page: a "Notification email" group with an input, a **required consent checkbox** ("This is my own email address and I agree to receive CampusPulse demo emails at it.") and Save. No verification code (user: demo app, one tester, the course doctor). CLAUDE.md email rule already updated to match.
- Rule in one place in the mailer: an address is allowed if it is in `DEMO_EMAIL_ALLOWLIST` or it is the `notify_email` of a profile with `notify_email_consent_at`. Everything else stays blocked and logged.
- Recipients: a student's requester emails go to that student's notify email; office emails go to the office inbox plus every staff profile of that office with a consented notify email (never the ticket's own requester).
- Guards kept: at most 5 changes per profile per hour, a kill switch env (`EMAIL_OPT_IN`), Remove on Profile, README disclosure. Known trade-off: no code means a mistyped or someone else's address would receive demo emails.
- Migration `0016_notify_email.sql` (new; 0013 to 0015 are frozen): `profiles.notify_email`, `profiles.notify_email_consent_at`, plus the two FK indexes the advisor asked for if 0015 lacks them (announcements.created_by, ticket_hints.ticket_id).
- Routes: `PUT /v1/profile/email` {email, consent: true}, `DELETE /v1/profile/email`. Web allow-list entries and tests.
- Tests: fake sender only; consent required, malformed email rejected, rate limit, kill switch, recipient resolution.
- Open: shared demo accounts (the last saved address wins); the doctor receives office emails only when logged in as, or saved on, a staff account of that office.

## P10.2 Chat answers only from what we know, plus one retry
- The agent may state facts, instructions, workarounds, ETAs or promises only if they are in the sources retrieved for that turn (live announcements, FAQ and knowledge base, past hints). Otherwise it says it has no information and asks one short question or offers to record a request. When an announcement is narrower than the student's message (library vs wifi in general) it says what the notice covers and asks where the problem is.
- Prompt rewrite with a grounding section and few-shot examples (EN, AR, Arabizi) including the library case; version bumped.
- A deterministic post-check without an extra LLM call that replaces a reply containing an unsupported promise or instruction ("working on it", "meanwhile", "please use", Arabic equivalents) with the safe "no information" template. It is a safety net with stated limits; the prompt is the main fix.
- One short retry (about 1 second) for 429, 5xx and timeouts only, never for 401, 402 or 400, in the chat adapter only.
- Tests with a fake LLM and fake transport; extend the scripted conversations with the library case and five more grounding cases; `scripts/run_chat_regression.py` documented for use with a real key, not run here.

## P10.3 Clustering similar shared-issue requests and announcing issues (user decisions; not started)
- Cluster similar **shared-issue** requests (electricity down, wifi down, bus late) even when worded differently and without any announcement. Embedding similarity, a longer window than 30 minutes, building optional.
- **Personal requests never cluster** (my account, my fee, my grade, my registration). Proposed rule: only Facilities, IT Support and Transportation requests with a shared-issue signal (outage or fault wording, group cues; the existing outage lexicon family, and the LLM group-outage cue when available); everything else is personal.
- **No duplicates:** a new request that matches an open cluster or announcement gets "this is already known", is added as another report, and creates no new ticket; the student can still choose to record a separate request.
- **More than three** similar requests: suggest the department (the majority office) and propose a draft announcement for that office's staff to edit and publish in one click. Nothing is announced automatically.
- On publish: **students and staff both receive an email** (allow-listed or consented addresses only), throttled.
- Needs first: a read-only check of how the P9 chat proposal flow and ticket creation interact with the existing incident detector and `merged` status; the threshold, window and similarity values to be set from tests on synthetic probes; the email audience depends on P10.1.

## Order when work resumes
P10.1 and P10.2 in parallel (different files); P10.3 after P10.1 merges (its broadcast uses the recipient resolution). Each is a Sonnet package with the usual gates (ruff, mypy, pytest default, web lint, typecheck, vitest), no push, ready-to-paste report in `docs/plan/p10/`. DB: migration 0016 (and any later) applied by the user in the SQL editor, then recorded in the migration history by the DB session.
