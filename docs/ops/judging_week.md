# Judging week runbook (11 to 13 Nov 2026)

Submission is **by email** to `nadia.alrousan@gju.edu.jo`, subject `AI Quest 2026 – Track C – <team name>`, with the
team members' names and student IDs. Remote judges evaluate 11 to 13 Nov, so the hosted app must be awake and
working for those three days, and a local fallback must start in 3 commands. Deadline for the submission: 10 Nov
2026, 23:59 Amman.

## Status of what could be checked from the repo

| Item | Status | Evidence / what the user must confirm |
| --- | --- | --- |
| Render plan | Blueprint says `plan: starter` (paid, no spin-down; `render.yaml`) | **Needs the dashboard**: Render, service `campuspulse-ai`, Settings, Instance Type = Starter (not Free, which sleeps after 15 min). If a bigger model needs more than 512 MB, move to Standard and edit `render.yaml` |
| Render health check | `healthCheckPath: /health` in the blueprint | Dashboard: Settings, Health Check Path = `/health`. Note `/health` does not query the database (it reports wiring only) |
| Supabase tier | Unknown from the repo | **Needs the dashboard**: Project settings, Billing. A Free project is paused after about a week of inactivity and its data is unreachable until restored. Either upgrade to Pro for the week (about 25 USD, removes the risk) or rely on the keep-alive below. If it is already paused, press Restore now |
| Netlify | `netlify.toml` builds `apps/web` | Dashboard: latest production deploy is green; env vars `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `AI_SERVICE_URL`, `AI_SERVICE_TOKEN` set |
| Keep-alive | `.github/workflows/keepalive.yml` (every 6 h) | Needs the repo variables and secrets below, then run it once by hand (Actions, keepalive, Run workflow) |
| Local fallback | `scripts/demo_local.py`, tested once on the dev laptop (2026-11-01) | Re-test on the laptop you will use, with Docker Desktop running |

## The checklist (in order)

Times are estimates for the user. Do items 1 to 6 by 8 Nov so a failure still leaves two days.

1. **Confirm plans** (10 min). Render = Starter, Supabase tier known (upgrade or restore), Netlify deploy green.
2. **Keep-alive** (10 min). GitHub repo, Settings, Secrets and variables, Actions.
   - Variables: `API_URL` (the `https://...onrender.com` URL), `WEB_URL` (the Netlify URL), `SUPABASE_URL`, `DEMO_STUDENT_EMAIL` (`talal@demo.local`).
   - Secrets: `SUPABASE_ANON_KEY`, `DEMO_STUDENT_PASSWORD`.
   - Run the workflow once and check the three steps are green. The workflow is on `main` only, so merge first.
3. **Uptime ping** (10 min). Create a free monitor (UptimeRobot or Better Stack) on `<API_URL>/health` and on `<WEB_URL>/login`, 5-minute interval, email alert to the team. This is the early warning; the GitHub cron is the database keep-alive.
4. **LLM cost cap** (10 min). The default scored path is offline and needs no key. If `ENABLE_LLM` or `LLM_ARABIZI_TRANSLATE` is on in the hosted app: OpenRouter, Keys, set a credit limit on the key (the docs say 10 USD) and keep `LLM_DAILY_BUDGET_USD` set on Render. Decide now whether the hosted app runs with the LLM off during judging (safest: the demo then costs nothing and cannot hit a rate limit).
5. **Allow-list** (5 min). Render env: `DEMO_EMAIL_ALLOWLIST` lists only your own demo inboxes (and `DEMO_STUDENT_INBOX`, `DEMO_OFFICE_INBOX` are in it). No GJU address, no judge address. Enforced in code; empty means no email at all, which is also fine.
6. **Judge logins** (15 min).
   - Run `python scripts/seed_demo_users.py` against the hosted project (needs `DEMO_USER_PASSWORD`) so the four logins exist with a password you know: `talal@demo.local` (student), `it@demo.local` (IT staff), `advisor@demo.local` (advisor), `admin@demo.local` (admin).
   - Put the logins and one shared password in the submission email (these are demo accounts on the reserved `demo.local` domain; no mail goes to them). Optionally set `NEXT_PUBLIC_DEMO_LOGIN_HINT` on Netlify so `/login` shows a hint line.
   - Log in as each of the four once on the hosted site.
7. **Contacts** (5 min). Put two team phone numbers or WhatsApp contacts in the submission email so judges can reach you if the site is down.
8. **Dry run on the hosted app** (20 min). Walk `docs/ops/demo_script.md` end to end on the hosted URL, on a phone as well as the laptop. Check the first request after idle is not slow (a cold API takes under a minute to load the model).
9. **Local fallback rehearsal** (30 min, once, on the laptop you will carry). See below. Close it again afterwards.
10. **Freeze** (2 min). From the evening of 10 Nov nothing is merged to `main` except a rollback: every push to `main` redeploys Render (`autoDeployTrigger: commit`) and Netlify, and a bad deploy is the most likely way to lose the demo. Optionally pause auto-deploy in both dashboards for 11 to 13 Nov.
11. **Send the submission email** (10 min), before 10 Nov 23:59. Template below. Send it from your own mailbox yourself; nothing in the repo sends it.
12. **During 11 to 13 Nov**: check the monitor emails each morning and evening; open the site once a day.

### Visible demo note (required)

The tool must never claim to contact a real department. Make sure a demo note is visible to judges:

- The submission email and the first page of any slide or write-up say: "CampusPulse is a demo. No real GJU department, advisor or security office is contacted. Messages go only to team-owned demo inboxes."
- The web app already carries "Demo content, not an official GJU answer." on FAQ answers and a "Demo accounts only ... Nothing is sent to real people." banner on the outbox page. Student-facing copy that could read as real contact is listed in `docs/plan/p7/P8.8_report.md` for the UI owner.
- Say it aloud in the first 20 seconds of any live demo.

### Rollback (a deploy broke the demo)

1. `git log --oneline -5` on `main`, pick the last good commit `<good>`.
2. `git revert --no-edit <bad>..HEAD` (or `git revert <bad>` for one commit), `git push origin main`. Do not force-push.
3. Render and Netlify redeploy from `main` (about 5 to 10 minutes; Render builds the image and verifies the model against its manifest). Or, faster, in each dashboard use Deploys, pick the last good deploy, Rollback.
4. Check `/health` returns `"status":"ok"`, then log in and run one request.
5. If the hosted app cannot be fixed in 15 minutes, tell the judges in a reply email and run the local fallback on a screen share.

## Local fallback

Works with no hosted service. It needs, installed once beforehand: Docker Desktop (running), the Supabase CLI, Node 22 with pnpm, and the Python venv from `docs/ops/README.md` with the encoder fetched (`python scripts/fetch_models.py`; judges do not need this, only you). It sends nothing anywhere: the LLM, Linear and email are forced off and the allow-list is empty.

```bash
python scripts/demo_local.py setup   # 1: starts local Supabase, applies migrations and seeds, creates the logins
python scripts/demo_local.py api     # 2 (terminal 1): the API on http://localhost:8000
python scripts/demo_local.py web     # 3 (terminal 2): the web app on http://localhost:3000
```

Log in with the `@demo.local` accounts above; the password is `campuspulse-demo` unless `DEMO_LOCAL_PASSWORD` was set before `setup`. The first `web` run installs the web dependencies (needs the network once; do it at home). Stop with Ctrl+C in each terminal and `supabase stop`.

Notes from the one test run:

- `setup` writes `.env.demo.local` (gitignored, local-stack keys only). Re-running `setup` is safe.
- If Supabase says a port is already allocated (another local Supabase project on the laptop), stop that project (`supabase stop --project-id <id>`) or copy `supabase/` to another folder, change the ports in its `config.toml` and set `DEMO_SUPABASE_WORKDIR` to that folder's parent before `setup`. That is how the test run was done, since the dev laptop already runs two other Supabase projects.
- The API needs about 480 MB of RAM and loads the model in 10 to 40 seconds. Close other heavy apps.
- A fresh local database does not give `service_role` table grants by default; `setup` adds them (local database only). The hosted project is unaffected, but a **newly created** hosted Supabase project would hit the same `permission denied` unless its migrations add the grants. Do not recreate the hosted project during judging.
- Last resort that needs no Docker and no network: `python services/ai/predict.py` on a CSV (the scored offline path), to show category, priority and uncertainty in a terminal.

## Submission email template

```
To: nadia.alrousan@gju.edu.jo
Subject: AI Quest 2026 – Track C – <team name>

Dear Dr. Nadia,

Please find our Track C submission, CampusPulse.

Team: <team name>
Members: <Full name 1> (<student ID 1>), <Full name 2> (<student ID 2>), ...

Hosted demo:  <WEB_URL>
Demo logins (demo accounts, password <password>):
  student  talal@demo.local
  IT staff it@demo.local
  advisor  advisor@demo.local
  admin    admin@demo.local
Repository:   <repo URL or attached archive>
Demo video / script: <link or attachment>   (3-minute walkthrough: docs/ops/demo_script.md)

Please note: CampusPulse is a demo. No real GJU department, advisor or security office is contacted, and no
message is sent to any real person. Notifications go only to team-owned demo inboxes. The FAQ content is
demo content, not an official GJU answer.

If the hosted demo is unreachable during 11 to 13 November, please contact <name> on <phone / WhatsApp> and we
will respond immediately or run the demo live.

Kind regards,
<name>
```
