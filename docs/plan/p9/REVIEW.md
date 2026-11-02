# P9 review (architect, 2026-11-02)

Branch `p9-integration`, reviewed at `48437b9`. All eleven packages (P9.0 to P9.10) plus the DB hand-off are merged. Gates at that commit (integrator runs, exit codes read directly): ruff 0, mypy --strict 0 (215 files), pytest default 0 (1506 passed, 1 skipped), mock openapi export identical, `gen_api_docs.py --check` 0, web lint 0, typecheck 0, vitest 0 (709), Playwright e2e 0 (17, mock API + fake Supabase), `pnpm build` 0 and `check:secrets` 0 (at `71d01aa`). `predict.py` and `models/` unchanged since the plan commit; migrations 0013/0014 unchanged since they were applied.

## What works (verified by tests only)
- Portal shell, login card with role check, per-role tabs, demo line on every page, EN/AR RTL (vitest + e2e text/overflow checks).
- Status model new/in_progress/solved/closed (+ merged), clock columns, SLA 1/24/48 h; every row of the state machine (PLAN d) has a unit test in `test_ticket_lifecycle.py`.
- Comments, internal notes (RLS + defensive filter in the requester view), forward with history and clock restart, priority change, requester Solved/Close/Keep open, hints written on forward/priority.
- Emails: 10 events EN/AR, demo line always appended, HTML escaped; mailer goes through the existing `AllowlistedNotifier` (composition/online.py), tests use fake notifiers only.
- Two-reminder rule with `claim_reminder` conditional update; in-process loop + throttled sweep on every API hit + `POST /v1/cron/sla` (service token) + `sla-ping.yml`.
- Chat agent: LLM returns only reply + intent; routing from the classifier on the requester's own words; HMAC proposal token bound to the alias, expiring, now single-use; distress first with no LLM call; banned-phrase and department post-checks; fallback form without a key.
- Files: private bucket, no client storage policies, magic-byte sniff, caps, generated paths, 60 s signed links, `noopener noreferrer`, internal files hidden from the requester.

## Security checks done by reading
- Allow-list: every ticket email goes through `AllowlistedNotifier`; recipients come from env/profile `demo_inbox` only.
- RLS: new tables have SELECT-only client policies; `ticket_hints.embedding` and `ticket_files.storage_path` are not granted to `authenticated`; `match_ticket_hints` is service-role only.
- Injection: no path lets message content set category, priority or office; the token is server-signed and verified with `hmac.compare_digest`.
- Keys: `check:secrets` clean; no key in client code.

## Deviations from the plan (accepted)
- Two-reminder rule (user change, brainstorm 21) replaces the plan's single reminder; `reminder_count` added in 0014.
- `TicketEmailTemplates` loads through an adapter (application layer may not import yaml).
- In a chat turn a clarifying question is plain reply text; the structured question only comes from `chat/preview`. `mode` is `agent|fallback`.
- Staff cannot post a public reply on a solved/closed ticket (they reopen through the status form).
- Announcements have their own store (to run P9.5 in parallel).

## Fixed during review
1. Proposal tokens could be confirmed twice (duplicate tickets) -> single-use claim (`7376abc`).
2. Header showed the alias on most pages -> display name everywhere (`48437b9`).

## Remaining issues (non-blocking, numbered feedback)
1. NOT verified against real services: Supabase (journey/announcement/file stores, RLS checks 14-19 in `supabase/tests/rls.sql`, the `match_ticket_hints` vector argument, Storage REST), the real LLM (prompt quality, JSON mode; `scripts/run_chat_regression.py` not run, no key), real SMTP, the GitHub cron. Do one live smoke test after deploy: login as each role, chat -> confirm -> staff reply -> Solved, forward, overdue reminder via `POST /v1/cron/sla`.
2. Single-use tokens are in-process (one uvicorn worker); a restart within 30 min allows one re-confirm.
3. Storage objects are not deleted with their ticket; a failed comment can leave unattached files (they count against the caps).
4. Office-side and reminder emails are English only (by plan A7).
5. Unused code left in the tree: old ChatThread/ResultCard pieces still used by staff views, `BuildingPicker`/`useBuildings`, advisor tabs on the Corrections page, booking code (unrouted), `tickets.escalated_at` (no longer written).
6. Arabic email and UI wording has had no native-speaker review.
7. No Playwright coverage for `/requests`, file upload, or the review-queue confirm/correct flow (unit tests only).
8. On the first scan after deploy, each existing overdue demo ticket gets one reminder email (allow-listed inboxes only).

Verdict: no blocking issue found. Ready for the lead to merge after applying `0015_ticket_files.sql`, seeding accounts and announcements, and a live smoke test (DB_HANDOFF.md).
