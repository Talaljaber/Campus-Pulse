# Appendix D — External accounts

> Part of the CampusPulse plan ([PLAN.md](../PLAN.md)). `§n` refers to [ARCHITECTURE.md](../ARCHITECTURE.md).

Status legend: V = verified from an official page on 2026-10-31 · U = UNVERIFIED.

**Supabase**
- **Plan/tier:**
  - Free: 2 projects, 500 MB DB, Realtime included.
  - **Pauses after 7 days of inactivity** (V, search summary).
  - pgvector HNSW is supported (V).
- **Env vars (where):**
  - Render: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (secret / legacy service_role).
  - Netlify: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (publishable / legacy anon).
  - Dev only: `SUPABASE_DB_URL`, `SUPABASE_TEST_URL`/`_SERVICE_ROLE_KEY`, `DEMO_USER_PASSWORD`.
- **Setup:**
  1. Create a project (region nearest Amman, e.g. Frankfurt; U).
  2. `supabase login`, then `supabase link --project-ref <ref>` (V), then `supabase db push` (V).
  3. Confirm `vector` ≥ 0.7.
  4. Copy the keys.
  5. Docker Desktop is needed for `supabase start` (local RLS tests).
- **First needed:** P0 (`0001_init.sql`). In this half: [P4.1](P4_product_backend.md#p4-1).
- **Top gotcha:** the pause after 7 idle days. `keep_warm.ps1` hits `/health?deep=1` daily until judging ends. The service-role key never goes to Netlify.

**Render**
- **Plan/tier:**
  - Starter `0.5c-512mb`: 0.5 CPU, **512 MB** (V); ≈ $7/mo (U), approved by the user.
  - Free: 0.1 CPU / 512 MB and spins down after 15 min (V).
  - Standard: 1 CPU / 2 GB (V), ≈ $25/mo (U), needs approval.
  - `PORT` defaults to 10000 (V).
  - **Free instances block SMTP ports 25/465/587** (V, since 26 Sep 2025). Port 25 is blocked on all plans (V); 465/587 on paid plans are believed open (U).
- **Env vars (where):** Render secrets (`sync: false`):
  - `AI_SERVICE_TOKEN`, `SUPABASE_*`, `OPENROUTER_*`, `ENABLE_LLM`, `LLM_DAILY_BUDGET_USD`;
  - `GMAIL_SMTP_USER`, `GMAIL_APP_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`, `DEMO_EMAIL_ALLOWLIST`;
  - `LINEAR_API_KEY`, `LINEAR_WEBHOOK_SECRET`, `ENABLE_SINKS`, `AUTH_MODE`, `ORT_INTRA_OP_THREADS=1`, `TZ`;
  - (S1) `WHATSAPP_*`, `DEMO_PHONE_ALLOWLIST`.
- **Setup:**
  1. Create the account and add a card.
  2. New → Blueprint from the repo-root `render.yaml`, or New Web Service → Docker with Dockerfile path `services/ai/Dockerfile` and context `.`.
  3. Set the plan to Starter and the health check to `/health`.
  4. Use the dashboard Shell for the [P4.0](P4_product_backend.md#p4-0) SMTP smoke test.
- **First needed:** P0 skeleton. In this half: [P4.0](P4_product_backend.md#p4-0), [P4.13](P4_product_backend.md#p4-13).
- **Top gotcha:** 512 MB RAM. Measure under `docker run -m 512m --cpus 0.5` before deploying. Also check SMTP egress on day one. Docker build memory and size limits are not documented (U), so keep the image lean (no torch).

**Netlify**
- **Plan/tier:**
  - Free: 300 credits/month (U on reset).
  - Next.js through the OpenNext adapter, all versions ≥ 13.5, with full route-handler support (V).
- **Env vars (where):** Netlify UI:
  - `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`;
  - `AI_SERVICE_URL` and `AI_SERVICE_TOKEN`, **scoped to Functions/runtime as well as Builds**;
  - `NODE_VERSION=22`.
- **Setup:**
  1. Connect the GitHub repo.
  2. Root `netlify.toml` with `[build] base = "apps/web"` (V).
  3. `NODE_VERSION=22`, required by supabase-js 2.118 (V; the Netlify docs use 22 as an example).
- **First needed:** P0. In this half: [P5.6](P5_frontend.md#p5-6), [P6.5](P6_ship.md#p6-5).
- **Top gotcha:** variables scoped only to Builds are not readable by route handlers at runtime. Never add the service-role key.

**GitHub** (repo + Release)
- **Plan/tier:** a free **public** repo.
- **Env vars (where):** `gh auth login` on the dev machine.
- **Setup:**
  1. Make `campuspulse/` its own repo (§7.1).
  2. Push it as public.
  3. Publish `models-v1-rc1` at [P1.19](P1_scored_core.md#p1-19), `models-v1-rc2` at [P2.13](P2_data_rigor.md#p2-13) and `models-v1` in [P6.2](P6_ship.md#p6-2).
- **First needed:** P0. In this half: [P4.13](P4_product_backend.md#p4-13) (RC asset), [P6.2](P6_ship.md#p6-2).
- **Top gotcha:** a private repo breaks judge cloning and Render's unauthenticated asset fetch.

**Hugging Face** (mirror, optional)
- **Plan/tier:** a free model repo. **Docker Spaces need a paid plan, so they are dropped** (V).
- **Env vars (where):** `HF_TOKEN` on the dev machine only.
- **Setup:** `huggingface-cli upload <dev>/campuspulse-models …`.
- **First needed:** [P6.2](P6_ship.md#p6-2) (optional).
- **Top gotcha:** keep it the backup. `--source hf` is not the default.

**OpenRouter**
- **Plan/tier:**
  - Pay-as-you-go: buy $10 credits. This also lifts `:free` limits to 1,000/day, though we don't use `:free`.
  - Without credits, `:free` models allow 50 requests/day, shared across keys (V).
- **Env vars (where):** Render and dev: `OPENROUTER_API_KEY`, `OPENROUTER_TIER1_MODEL`, `OPENROUTER_TIER2_MODEL`, `ENABLE_LLM`, `LLM_DAILY_BUDGET_USD`.
- **Setup:**
  1. Create the account and buy $10.
  2. Create a key with a **$10 spending limit** (U on the menu path).
  3. Check with `GET /api/v1/key`.
- **First needed:** P2 augmentation drafting. In this half: [P3.3](P3_intelligence.md#p3-3).
- **Top gotcha:** 402/429 kills the router mid-demo. `NullOracle` fallback plus a pre-demo key check.

**Gmail SMTP** (user decision)
- **Plan/tier:**
  - The consumer account `campuspulse.support@gmail.com`.
  - **App passwords require 2-Step Verification** (V).
  - Limits: 500 recipients/email and 500 emails/day (V). Our code cap is 100/day.
  - `smtp.gmail.com` 587 STARTTLS / 465 SSL (U, general knowledge).
- **Env vars (where):** Render and dev, never committed: `GMAIL_SMTP_USER`, `GMAIL_APP_PASSWORD`, `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `DEMO_EMAIL_ALLOWLIST`.
- **Setup:**
  1. Turn on 2SV.
  2. Account → Security → App passwords → create "CampusPulse Render".
  3. Store the password in a password manager.
  4. Build the allow-list from plus-addresses of this inbox (`campuspulse.support+student17@gmail.com`, `+adv-reg`, `+adv-acad`, …) **plus one second developer-owned inbox** for the visible "student inbox" ([OQ-6](../PLAN.md#oq-6)).
- **First needed:** [P4.0](P4_product_backend.md#p4-0) / [P4.4](P4_product_backend.md#p4-4).
- **Top gotcha:**
  - SMTP egress from Render (see Render).
  - App passwords disappear if 2SV is turned off.
  - Mail sent to the same account may show only in Sent (U).

**Linear** (demo workspace)
- **Plan/tier:**
  - Free: believed 250 issues and 2 teams, API and webhooks included (U; the pricing page does not render).
  - **Only workspace admins can create webhooks** (V).
  - Personal keys use `Authorization: <key>` with no Bearer (V).
  - Webhook: `Linear-Signature` = hex HMAC-SHA256 of the raw body; `webhookTimestamp` within 60 s; retries at 1 min, 1 h and 6 h; respond within 5 s (V).
- **Env vars (where):** Render: `LINEAR_API_KEY`, `LINEAR_WEBHOOK_SECRET`. The team, label and state IDs go in `config/integrations.yaml` (not secrets).
- **Setup:**
  1. Create a **new workspace** "CampusPulse Demo" (you are admin).
  2. Create one team "CPD", with **office as a label**, which stays within the 2-team cap.
  3. Create a personal API key.
  4. Create a webhook → `https://<render>/v1/integrations/linear/webhook` for Issue events.
  5. Run `scripts/smoke_linear.py`.
- **First needed:** [P4.0](P4_product_backend.md#p4-0) / [P4.6](P4_product_backend.md#p4-6).
- **Top gotcha:**
  - The issue cap: archive demo issues after rehearsals.
  - If webhooks are not on Free, inbound sync is demonstrated via the dashboard route.

**Google service account** (cut #5, stretch)
- **Plan/tier:** Calendar API is free (1 M requests/day).
- **Env vars (where):** Render: `GOOGLE_SERVICE_ACCOUNT_JSON`, `DEMO_CALENDAR_IDS`.
- **Setup:**
  1. Create a GCP project, enable the Calendar API, create a service account and a JSON key.
  2. Create 2 demo calendars and share them with the service-account email ("Make changes to events").
- **First needed:** P4.16 (only if early).
- **Top gotcha:** **service accounts cannot invite attendees without domain-wide delegation** (U, community sources). We create events on shared demo calendars only, with no attendees; invites go through the allow-listed email. **SlotsTable is the default.**

**Meta WhatsApp Cloud API** (S1, cut #0)
- **Plan/tier:**
  - The test number allows sends to ≤ 5 registered recipients (partly V).
  - Business-initiated messages outside 24 h need an **approved template**; `hello_world` is preinstalled (V).
  - Per-message pricing since 1 Jul 2025; utility charges resume 1 Oct 2026 (V).
  - Graph `v26.0` (V).
- **Env vars (where):** Render: `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION=v26.0`, `WHATSAPP_TEMPLATE`, `WHATSAPP_TEMPLATE_LANG`, `DEMO_PHONE_ALLOWLIST`.
- **Setup:**
  1. Create a Meta developer account and a Business app with the WhatsApp product.
  2. Register ≤ 5 developer-owned recipient numbers (each gets a confirmation code).
  3. Submit the utility template `urgent_request_alert`.
  4. Create a System User token with `whatsapp_business_messaging`, `whatsapp_business_management` and `business_management` (V).
- **First needed:** [S1.3](S1_whatsapp.md#s1-3).
- **Top gotcha:** the dashboard's temporary token "expires quickly" (V; ≈ 24 h is U), so use the System User token. Template approval time is U, so submit the template on the day S1 starts, or demo with `hello_world`.

**Master env-var list** (`.env.example`, kept current in [P6.6](P6_ship.md#p6-6)):
- **Brief/SPEC §11:**
  - `OPENROUTER_API_KEY`, `OPENROUTER_TIER1_MODEL`, `OPENROUTER_TIER2_MODEL`;
  - `SUPABASE_URL`, `SUPABASE_ANON_KEY` (web, as `NEXT_PUBLIC_*`), `SUPABASE_SERVICE_ROLE_KEY` (AI only);
  - `AI_SERVICE_URL`, `AI_SERVICE_TOKEN`;
  - `DEMO_EMAIL_ALLOWLIST`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `DEMO_CALENDAR_IDS`;
  - `LINEAR_API_KEY`, `LINEAR_WEBHOOK_SECRET`, `OUTBOUND_WEBHOOK_URL`, `OUTBOUND_WEBHOOK_SECRET`;
  - `ENABLE_LLM`, `ENABLE_SINKS`, `SLA_SCAN_MINUTES`, `ARTIFACT_DIR`.
- **Email env vars:** `GMAIL_SMTP_USER`, `GMAIL_APP_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_TIMEOUT_S`, `SMTP_MAX_RETRIES`, `SMTP_BACKOFF_S` and `SMTP_DAILY_CAP`.
- **Added in this half:**
  - `LLM_DAILY_BUDGET_USD`, `LLM_TIMEOUT_S`, `LLM_CACHE_PATH`;
  - `INJECTION_GUARD_MODE`, `EXPLAIN_MAX_OCCLUSIONS`;
  - `GAMING_MIN_REQUESTS`, `GAMING_CLAIM_RATIO`, `GAMING_HIGH_RATIO_MAX`;
  - `AUTH_MODE`, `SINK_RETRY_MAX`, `SINK_RETRY_BASE_S`, `INCIDENT_WINDOW_MIN`, `REDTEAM_MAX_N`, `REPORTS_DIR`, `ORT_INTRA_OP_THREADS`, `TZ`;
  - dev only: `SUPABASE_DB_URL`, `SUPABASE_TEST_URL`, `SUPABASE_TEST_SERVICE_ROLE_KEY`, `DEMO_USER_PASSWORD`, `PW_BASE_URL`, `PW_API_URL`, `RENDER_URL`;
  - S1: `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION`, `WHATSAPP_TEMPLATE`, `WHATSAPP_TEMPLATE_LANG`, `WHATSAPP_MIN_PRIORITY`, `WHATSAPP_ON_SAFETY`, `WHATSAPP_KINDS`, `DEMO_PHONE_ALLOWLIST`.

## Day-one account checklist (31 Oct – 1 Nov, before P0 deploys)

- [ ] **Today:** email the organiser about the solo vs "2–3 students" eligibility, before the 3 Nov track lock (§6.2 #1).
- [ ] Make `campuspulse/` its own **public** GitHub repo (§7.1, [OQ-7](../PLAN.md#oq-7)); `gh auth login`.
- [ ] Supabase project created, `vector` extension on, keys in a password manager; `supabase login` + `link`.
- [ ] Render account + card; Starter Docker service created (P0 `/health`); confirm 0.5 CPU / 512 MB on the instance page.
- [ ] Netlify site linked, base `apps/web`, `NODE_VERSION=22`.
- [ ] OpenRouter: $10 credits, key with a $10 limit, `GET /api/v1/key` OK.
- [ ] Gmail `campuspulse.support@gmail.com`: 2SV on, app password created. A second developer-owned inbox is chosen. `DEMO_EMAIL_ALLOWLIST` is drafted, containing only developer-owned addresses.
- [ ] Linear: new demo workspace (admin), one team, labels per office, personal API key. Webhook creation tested (records Free-plan availability, U).
- [ ] Docker Desktop installed (Supabase local stack, Render memory simulation, Linux clean-machine check).
- [ ] Optional: HF account (mirror). Not now: Google service account (cut #5), Meta WhatsApp (S1).
