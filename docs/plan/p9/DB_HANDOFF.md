# P9 database hand-off

> **Nobody applies anything until the lead says so.**
> This document is read-only guidance. Nothing here has been applied to any database. The migrations are applied by the lead, as the `postgres` owner, in one short window together with the P9 deploy (see "When to apply").

## Test status (read this first)

- **None of the P9 migrations (0013, 0014) has been run against a real Postgres.** Not locally, not on the live project. Review so far is by reading only.
- What did pass: the Python unit tests and the web unit tests, which use in-memory stores (they never touch SQL).
- `supabase/tests/rls.sql` checks 14 to 19 (thread visibility, office staff vs own request, hints without `embedding`, anon, announcements, no client writes) exist but were **never executed**. Expect to run them on a scratch database first if one is available (`scripts/test_rls.py`), otherwise paste into the SQL editor: the script runs in one transaction and rolls back.
- Review result for 0013 and 0014 (by reading, against 0002/0003/0006/0009/0012): no defect found, no change made to either file. Details in each section.

## Live data and facts the migrations assume

Facts supplied by the DB owner (read-only look at the live project):

1. `tickets.status` has an inline CHECK from 0002 whose real name is `tickets_status_check`.
2. Live data is demo only: 8 tickets (open 6, in_progress 1, resolved 1, escalated 0), 9 requests, 12 notifications. Profiles: 1 student, 2 staff (office `it`, and the advisor login with office `academic`), 1 admin.
3. RLS policies and helpers in 0003, 0006, 0012 do not reference ticket status names. Old names lived only in backend code (now updated). Confirmed by grep: no `'open'`, `'resolved'`, `'escalated'` in 0003 to 0012 outside the `incidents` table (a different enum that is not changed).
4. `service_role` has SELECT/INSERT/UPDATE/DELETE on all existing public tables but cannot create objects. Migrations run as the `postgres` owner. New tables need explicit GRANTs.
5. `pg_cron` and `pg_net` are not installed and are not needed: SLA reminders come from the GitHub cron `.github/workflows/sla-ping.yml` calling `POST /v1/cron/sla`, plus the in-process scan and the post-response sweep. The `storage` schema exists with 0 buckets.

## Apply order

| # | File | Status |
|---|---|---|
| 1 | `supabase/migrations/0013_student_journey.sql` | ready, never executed |
| 2 | `supabase/migrations/0014_reminder_count.sql` | ready, never executed |
| 3 | `supabase/migrations/0015_ticket_files.sql` | placeholder: pending, will be added when P9.10 lands |

Apply 0013 then 0014, each as one transaction (Supabase `apply_migration` / SQL editor wraps in a transaction; if you use `psql`, pass `-1`/`--single-transaction`). 0014 depends on the `tickets` table only, but keep the order.

---

## 0013_student_journey.sql

Path: `supabase/migrations/0013_student_journey.sql`

### Plain summary

- `profiles` gains five nullable directory columns: `display_name`, `student_number` (unique), `faculty`, `university_email` (unique), `demo_inbox`. All fictional, none mailed.
- `tickets.status` is renamed to the new vocabulary and the CHECK is replaced. The clock moves into the ticket: `clock_started_at`, `reminder_sent_at`, `awaiting_student`, `requester_alias` (copied from `requests.alias`, filled by a trigger on insert).
- Two new `private` helpers: `cp_owns_ticket(uuid)`, `cp_ticket_office_staff(uuid)`; one trigger function `private.cp_fill_ticket_requester()`.
- New tables, all with RLS on: `ticket_activity` (thread), `announcements`, `ticket_hints` (+ RPC `public.match_ticket_hints`).
- `ticket_activity` and `announcements` are added to the `supabase_realtime` publication.

### Destructive, renaming and constraint-changing statements

| Statement | Effect |
|---|---|
| `alter table tickets drop constraint tickets_status_check` | Drops the old CHECK BY NAME (as 0009 did for `outbox_status_check`). The name matches the Postgres auto-name for the inline column CHECK in 0002 (`tickets_status_check`) and the DB owner confirmed it. |
| `update tickets set status = case ... ` | `open` -> `new`, `resolved` -> `solved`, `escalated` -> `in_progress`; `in_progress`, `closed`, `merged` unchanged. Runs strictly between the DROP and the ADD, which is the only order that works (the old CHECK would reject `new`, the new CHECK would reject leftover `open`). |
| `add constraint tickets_status_check check (status in ('new','in_progress','solved','closed','merged'))` | Values `open`, `resolved`, `escalated` are no longer allowed. |
| `alter column status set default 'new'` | Default changes from `'open'`. |
| `add column clock_started_at` then `update ... = created_at` then `set not null, set default now()` | Backfill: every existing ticket's clock starts at its creation time. Then NOT NULL. |
| `add column awaiting_student boolean not null default false` | NOT NULL with default, existing rows get `false`. |
| `add column requester_alias` + `update ... from requests` | Backfill from `requests.alias`. Nullable. |
| `create index tickets_requester_alias_idx`, `tickets_open_due_idx` (partial on `new`/`in_progress`) | New indexes (brief lock on an 8-row table). |

Not touched: `tickets.escalated_at`, `tickets.resolved_at` (columns stay, now legacy), the `incidents` table and its `open`/`resolved` status.

### Expected effect on the live demo data

| Before | After |
|---|---|
| open 6 | new 6 |
| in_progress 1 | in_progress 1 + the 0 former escalated = 1 |
| resolved 1 | solved 1 |
| escalated 0 | (none) |

So expect: `new 6, in_progress 1, solved 1` (8 tickets). All 8 get `clock_started_at = created_at` and a `requester_alias`. Existing tickets with `sla_due_at` in the past and status `new`/`in_progress` will be treated as overdue by the first SLA scan and get one reminder email each (only to allow-listed demo inboxes). Consider that when choosing the window.

Old advisor staff row (the profile of office `academic` behind `advisor@demo.local`): nothing is deleted or altered. It stays a valid staff profile of office `academic`, so routing by office still works and `advisors.profile_id` and `review_queue.assignee` links keep working. It is simply no longer seeded (`scripts/seed_demo_users.py` leaves `advisor@demo.local` untouched and prints a note) and no longer offered on the login page. The lead may delete that auth user by hand later; deleting the auth user cascades per the `profiles` FK, so check `advisors.profile_id` and `review_queue.assignee` first.

### Grants and RLS the migration relies on

Verified by reading 0013 (all present, no fix needed):

- Global default privileges from 0003 already revoke all from `anon` and revoke write privileges from `authenticated` on new public tables; 0013 repeats this explicitly for the three new tables.
- `ticket_activity`, `announcements`: `grant select to authenticated`; `grant select, insert, update, delete to service_role`.
- `ticket_hints`: `select` revoked from `authenticated`, then column-level `grant select (id, ticket_id, kind, request_text, lang, model_category, model_priority, corrected_category, corrected_priority, note, author_alias, author_role, created_at)` which **excludes `embedding`**; `service_role` gets select/insert/update/delete.
- `match_ticket_hints(vector, int, float8)`: EXECUTE revoked from `public, anon, authenticated`, granted to `service_role` only. It is `security definer`, `search_path = public, extensions`.
- `private.cp_owns_ticket(uuid)`, `private.cp_ticket_office_staff(uuid)`: EXECUTE revoked from `public, anon`, granted to `authenticated, service_role`. `grant usage on schema private to authenticated, service_role` already exists from 0006.
- `private.cp_fill_ticket_requester()`: EXECUTE revoked from `public, anon, authenticated`; it is only used by the BEFORE INSERT trigger `tickets_fill_requester`.
- RLS policies created: `ticket_activity_read` (admin, or office staff who are not the requester, or the requester for `public` rows), `announcements_read` (live rows to any authenticated user, archived ones to staff too), `ticket_hints_read` (staff only). No INSERT/UPDATE/DELETE policies: all writes go through the API with the service role.
- Existing policies (`tickets_read` etc.) are not changed and do not mention status names.

### Does the currently deployed app (main) break after this is applied? Yes.

- `main`'s backend writes tickets with status `open`, `resolved`, `escalated`. The new CHECK rejects all three: ticket creation (triage), resolve and the old SLA escalation fail with a constraint error (surfaced as 503/500).
- `main`'s web shows and filters on the old status names, so lists would show `new`/`solved` rows under unknown labels or in no filter.
- Conversely, the p9 backend and web do not work before 0013 (they write `new` and read the new columns/tables).

### When to apply

**Together with the p9 deploy, in one short window. Do not apply it ahead of time.**

Order:

1. Announce the window; make sure the p9 API and web builds are ready to go (merged `p9` branch deployed from a green CI, Render and Netlify previews ready). Set the new env vars first (see below), they are harmless on main.
2. Apply `0013`, then `0014`.
3. Run the verification SQL below (about two minutes).
4. Deploy the API (Render, from the p9 commit). Wait for `/health` to be ok.
5. Deploy the web (Netlify).
6. Run `python scripts/seed_demo_users.py` and `supabase/seed/05_announcements.sql` (Seeds section), then smoke test: login, ask, ticket appears as `new`, staff reply, announcement on Home.

Between steps 2 and 5 the site is partly broken for new tickets; keep that gap to minutes.

If something fails:

- **A migration fails**: it is one transaction, so nothing is partly applied. Do not deploy. Read the error, forward-fix in a new commit, retry. Main keeps working because nothing changed.
- **0013 and 0014 applied, API or web deploy fails**: prefer fixing forward and redeploying. If that cannot be done quickly, roll the migrations back (section "Rollback") and redeploy main's previous build, in that order; the app and the schema must be on the same side.
- **Deployed OK but smoke test fails**: forward-fix; rollback only if the failure is data-destroying.

### Verification SQL (read-only)

```sql
-- 1. status counts: expect new 6, in_progress 1, solved 1 on the demo data; no open/resolved/escalated
select status, count(*) from public.tickets group by status order by 1;

-- 2. the new constraint and default
select conname, pg_get_constraintdef(oid) from pg_constraint
 where conrelid = 'public.tickets'::regclass and contype = 'c' and conname = 'tickets_status_check';
select column_default from information_schema.columns
 where table_schema = 'public' and table_name = 'tickets' and column_name = 'status';

-- 3. new columns on tickets and profiles
select table_name, column_name, data_type, is_nullable, column_default
  from information_schema.columns
 where table_schema = 'public'
   and ((table_name = 'tickets'  and column_name in ('clock_started_at','reminder_sent_at','awaiting_student','requester_alias','reminder_count'))
     or (table_name = 'profiles' and column_name in ('display_name','student_number','faculty','university_email','demo_inbox')))
 order by table_name, column_name;
-- backfill check: both should be 0
select count(*) from public.tickets where clock_started_at is null;
select count(*) from public.tickets t join public.requests r on r.id = t.request_id
 where t.requester_alias is distinct from r.alias;

-- 4. the new tables exist with RLS on, and their policies
select relname, relrowsecurity from pg_class
 where relnamespace = 'public'::regnamespace and relname in ('ticket_activity','announcements','ticket_hints');
select tablename, policyname, cmd, roles, qual from pg_policies
 where schemaname = 'public' and tablename in ('ticket_activity','announcements','ticket_hints')
 order by tablename, policyname;       -- expect 3 policies, all SELECT, no write policies

-- 5. table grants: authenticated = SELECT only on activity/announcements; none on hints (column grants instead);
--    service_role = SELECT, INSERT, UPDATE, DELETE; anon = nothing
select table_name, grantee, privilege_type from information_schema.role_table_grants
 where table_schema = 'public' and table_name in ('ticket_activity','announcements','ticket_hints')
   and grantee in ('anon','authenticated','service_role')
 order by table_name, grantee, privilege_type;

-- 6. column grants on ticket_hints: authenticated must not include 'embedding'
select column_name, grantee, privilege_type from information_schema.column_privileges
 where table_schema = 'public' and table_name = 'ticket_hints' and grantee in ('anon','authenticated')
 order by grantee, column_name;
select has_column_privilege('authenticated', 'public.ticket_hints', 'embedding', 'select') as authenticated_reads_embedding; -- expect false

-- 7. function privileges
select p.oid::regprocedure as fn,
       has_function_privilege('anon',          p.oid, 'execute') as anon,
       has_function_privilege('authenticated', p.oid, 'execute') as authenticated,
       has_function_privilege('service_role',  p.oid, 'execute') as service_role
  from pg_proc p
 where (p.pronamespace = 'private'::regnamespace and p.proname in ('cp_owns_ticket','cp_ticket_office_staff','cp_fill_ticket_requester'))
    or (p.pronamespace = 'public'::regnamespace  and p.proname = 'match_ticket_hints');
-- expect: cp_owns_ticket / cp_ticket_office_staff: false,true,true ; cp_fill_ticket_requester: false,false,false ;
--         match_ticket_hints: false,false,true

-- 8. the trigger and the realtime publication
select tgname from pg_trigger where tgrelid = 'public.tickets'::regclass and tgname = 'tickets_fill_requester';
select schemaname, tablename from pg_publication_tables where pubname = 'supabase_realtime' order by 2;
-- expect, in addition to the 0004 tables: ticket_activity, announcements
```

---

## 0014_reminder_count.sql

Path: `supabase/migrations/0014_reminder_count.sql`

### Plain summary

Adds `tickets.reminder_count smallint not null default 0 check (reminder_count between 0 and 2)`: at most two SLA reminders per clock period. 0 = none, 1 = first (office), 2 = second and last (office + admin). Application code resets it to 0 on a clock restart.

### Destructive statements

None. One additive column, NOT NULL with a default (existing rows get 0), plus an unnamed CHECK (Postgres names it `tickets_reminder_count_check`). Note for the first scan after deploy: existing overdue tickets have `reminder_count = 0` and will get reminder 1.

### Grants and RLS

No new objects, so no new grants. `tickets` already has table-level SELECT for `authenticated` (0003, policy `tickets_read` unchanged) and full DML for `service_role`; the new column is covered by both.

### Deployed-app impact and timing

Additive, so by itself it would not break main. It must still go in the same window as 0013 (the p9 API reads and writes this column and 0013's columns together). Apply right after 0013.

### Verification SQL (read-only)

```sql
select column_name, data_type, is_nullable, column_default
  from information_schema.columns
 where table_schema = 'public' and table_name = 'tickets' and column_name = 'reminder_count';
select conname, pg_get_constraintdef(oid) from pg_constraint
 where conrelid = 'public.tickets'::regclass and contype = 'c' and pg_get_constraintdef(oid) like '%reminder_count%';
select reminder_count, count(*) from public.tickets group by 1;   -- expect all 0
```

---

## 0015_ticket_files.sql (placeholder)

Pending: this file will be added when P9.10 lands (last package, only if P9.0 to P9.9 are merged and green). It is not in the repo yet. Nothing to apply now.

Expected content, from PLAN (h) P9.10: a `ticket_files` table (RLS read like `ticket_activity`, grants like 0013: SELECT to `authenticated`, full DML to `service_role`, nothing for `anon`) and the private storage bucket:

```sql
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('ticket-files', 'ticket-files', false, 5242880, array[...]) on conflict (id) do nothing;
```

with no `storage.objects` policies for client roles (service role only). The `storage` schema exists with 0 buckets today.

Manual alternative if the lead wants the bucket before the migration exists: Dashboard > Storage > New bucket, name `ticket-files`, **Private**, file size limit 5 MB, allowed MIME types as listed in PLAN (h) P9.10 (`image/png`, `image/jpeg`, `image/webp`, `application/pdf`, `text/plain`, and the docx, xlsx, pptx `application/vnd.openxmlformats-officedocument.*` types). Do not add storage policies. The later `insert ... on conflict do nothing` then leaves it as is. Add a verification block (`select id, public, file_size_limit from storage.buckets;`, `ticket_files` grants and policies) to this document when the file lands. Its timing is separate from the 0013/0014 window.

---

## Rollback

Forward-fix is preferred: the migrations are small, the data is demo only, and a rollback leaves the new app unusable anyway. If a rollback is unavoidable (and you are redeploying main's previous build), do it in this order, as `postgres`, in one transaction:

```sql
-- 0014 reverse
alter table public.tickets drop column reminder_count;

-- 0013 status reverse: restore the old CHECK first, then re-map, in the order that works
alter table public.tickets drop constraint tickets_status_check;
update public.tickets set status = case status when 'new' then 'open' when 'solved' then 'resolved' else status end;
alter table public.tickets add constraint tickets_status_check
  check (status in ('open', 'in_progress', 'resolved', 'closed', 'escalated', 'merged'));
alter table public.tickets alter column status set default 'open';
```

Notes:

- The old CHECK is restored BEFORE the app is redeployed, and the re-map runs between drop and add (same logic as the forward migration). `escalated` cannot be recovered: tickets that were `escalated` before 0013 are now `in_progress` (there were 0 on the live project).
- The additive parts of 0013 can simply stay: the new tickets columns, the three new tables, the helpers, the trigger and the profiles columns are ignored by main's code. Leaving them is safer than dropping them. If you do want them gone: `drop trigger tickets_fill_requester on public.tickets; drop function private.cp_fill_ticket_requester(), private.cp_owns_ticket(uuid), private.cp_ticket_office_staff(uuid), public.match_ticket_hints(extensions.vector, int, float8); drop table public.ticket_activity, public.announcements, public.ticket_hints; alter publication supabase_realtime drop table ...` (publication membership goes with the tables) and drop the added columns and indexes. Do this only on request.
- Data written by the new app between apply and rollback is orphaned: thread rows in `ticket_activity`, `ticket_hints` (staff corrections), `announcements`, `clock_started_at`, `awaiting_student`, `reminder_count` values, and tickets that were created as `new`, `solved` are re-mapped but their thread is invisible to main. Tickets in `in_progress` that were reopened keep that status. Any emails already sent cannot be recalled.

---

## Seeds (after the migrations, during the window)

### Demo users: `scripts/seed_demo_users.py`

- Creates or refreshes 10 fictional demo logins and upserts their `profiles` (including the 0013 directory columns, so run it only **after 0013**): students `talal`, `lina`, `omar`; staff `registrar`, `it`, `finance`, `transport`, `facilities`, `academic`; admin `admin`. All addresses are `<name>@demo.local` (login names only, nothing is mailed; users are created already confirmed).
- Password: taken from the env var `DEMO_USER_PASSWORD` (or the repo `.env`); it is never written in the file and never in this document. All demo users share it.
- Needs `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the environment (or `.env`) of the machine that runs it. Dev machine only.
- Idempotent: an existing user gets its password reset and its profile upserted; a user on an earlier login name is renamed in place (same id, rows stay linked). `advisor@demo.local` is no longer managed: an existing account is left untouched.
- Run: `python scripts/seed_demo_users.py` -> expect "10 users ready".

### Announcements: `supabase/seed/05_announcements.sql`

- Two fictional rows (library wifi outage, Outlook maintenance, office `it`, EN + AR text) for the Home page. Requires 0013 (`public.announcements`).
- Idempotent: fixed ids, `on conflict (id) do update` (and un-archives them). `created_by` stays null. `starts_at = now()` and `ends_at` 7 and 2 days ahead each time it runs, so re-running refreshes them for a demo.
- Run in the SQL editor as `postgres`, once, after 0013.

## Environment variables added by P9 (names only)

On the API (Render, `render.yaml` / `.env.example`):

- `DEMO_OFFICE_INBOXES` (per-office demo inboxes, e.g. `it=...,finance=...`; others use `DEMO_OFFICE_INBOX`)
- `DEMO_ADMIN_INBOX` (admin copy of ticket emails)
- `PUBLIC_WEB_URL` (base URL for links in emails)
- `SLA_SWEEP_MIN_INTERVAL_S` (value `60` already in `render.yaml`; `0` disables the sweep)
- `SLA_SCAN_MINUTES` (existed; semantics now "SLA reminder scanner interval")

Already required and unchanged: `AI_SERVICE_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DEMO_EMAIL_ALLOWLIST` (every demo inbox above must be on it, otherwise sends are rejected), `GMAIL_SMTP_USER`, `GMAIL_APP_PASSWORD`. `.env.example` and `render.yaml` list the values as placeholders only; real values are set in the Render and Netlify dashboards.

For the seed script (local shell): `DEMO_USER_PASSWORD`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`.

GitHub, for `.github/workflows/sla-ping.yml` (calls `POST /v1/cron/sla` every 10 minutes):

- repository **variable** `API_URL` (`https://<service>.onrender.com`, also used by `keepalive.yml`)
- repository **secret** `AI_SERVICE_TOKEN` (same value as on Render and Netlify)

If either is missing the workflow skips with a warning; the in-process scan and sweep still run while the service is awake.
