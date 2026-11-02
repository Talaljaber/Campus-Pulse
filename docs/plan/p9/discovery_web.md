# Discovery: apps/web (what exists today)

Read-only inventory, written from source reads on the current `main` working tree. All paths are relative to `apps/web/` unless shown otherwise. Nothing was run (no build, typecheck, test or e2e), so anything about runtime behaviour is "not verified". Env var values were never read; only names.

## 0. Stack at a glance

| Item | Fact | Source |
|---|---|---|
| Framework | Next.js 16.4.2, React 19.3.1, App Router | `package.json` |
| Language | TypeScript 5.9.3, alias `@/` = `src/` | `package.json` |
| Styling | Tailwind 4.3.3 via `@tailwindcss/postcss`; no `tailwind.config` file | `postcss.config.mjs`, `src/app/globals.css` |
| Auth/data client | `@supabase/supabase-js` 2.118.0, `@supabase/ssr` 0.12.7 | `package.json` |
| UI library | None (no shadcn, Radix, Headless UI, lucide or MUI in `package.json`) | `package.json` |

## 1. Routes (`src/app/**`) and who sees them

| File | URL | Who can open it (proxy + page guard) | What it renders |
|---|---|---|---|
| `src/app/(student)/page.tsx` | `/` | any signed-in role (proxy lets every role through; page redirects to `/login` if no profile). Students use it; staff/admin also pass. | `ChatScreen` (student chat) |
| `src/app/login/page.tsx` | `/login` | public. Signed-in users are redirected to their home. | `LoginHeading` + `LoginForm` (demo sign-in buttons) |
| `src/app/staff/page.tsx` | `/staff` | staff, admin (student redirected to `homeFor`) | `StaffScreen`: tabs Tickets / Review / Incidents / Flags |
| `src/app/staff/reviews/page.tsx` | `/staff/reviews` | staff, admin | `AdvisorScreen` (advisor review queue) |
| `src/app/pulse/page.tsx` | `/pulse` | staff, admin | `PulseScreen` (live map, incidents, feed) |
| `src/app/outbox/page.tsx` | `/outbox` | staff, admin | `OutboxScreen` (sent/failed messages) |
| `src/app/lab/page.tsx` | `/lab` | admin only | `LabScreen` (tabs benchmark, calibration, live, redteam) |
| `src/app/dev/ui/page.tsx` | `/dev/ui` | public route in the proxy; returns 404 when `NODE_ENV=production` | `KitchenSink` component gallery |
| `src/app/api/ai/[...path]/route.ts` | `/api/ai/*` | GET and POST handler; see section 5 | JSON or CSV proxy to the AI service |
| `src/app/layout.tsx` | (root layout) | all | `<html lang dir>`, fonts, `RtlProvider`, `ToastProvider`, `ServiceStatus`, `SiteFooter` |

Not present as routes: welcome/home for students, announcements, "My requests", notifications page, student ticket status page, settings, profile, sign-up, password reset, staff comments or notes pages.

### Proxy rules (`src/lib/auth/routing.ts`, used by `src/proxy.ts`)

- No session: only `/login` and `/dev` pass; everything else goes to `/login?next=<path>`. `/` goes to plain `/login`.
- Signed in on `/login`: redirect to `homeFor(role)`.
- `/lab` needs admin. `/staff`, `/pulse`, `/outbox` need staff or admin.
- `homeFor`: admin to `/lab`; staff with office `academic` to `/staff/reviews`; other staff to `/staff`; student to `/`.
- Proxy matcher skips `api/`, `_next/static`, `_next/image`, favicon and image files.
- Tests: `src/lib/auth/__tests__/proxy.test.ts`, `routing.test.ts`, `src/lib/__tests__/proxy.test.ts`.

### Layout and navigation components

- `src/components/shell/AppShell.tsx`: wraps pages; props `role`, `current`, `alias`, `width`.
- `src/components/shell/SiteHeader.tsx`: brand link to `/`, "Hello {alias}", help dialog, sign-out button (only when role is set), skip-to-content link.
- `src/components/shell/RoleNav.tsx`: nav links per role, rendered by `SiteHeader.tsx` when a role is set (`AppShell` only passes the type). `NavPage` values: `request`, `staff`, `reviews`, `pulse`, `outbox`, `lab`.
  - Student: `request` ("New request") only. Staff: `staff`, `reviews`, `pulse`, `outbox`. Admin: those plus `lab`.
- `src/components/shell/PageHeader.tsx`, `SiteFooter.tsx` (fictional-prototype disclaimer text), `ServiceStatus.tsx` (AI health banner).

## 2. Login and roles

- Auth is Supabase email and password: `src/lib/auth/signin.ts` calls `signInWithPassword`, then loads the profile. A missing profile signs the user out (`no_profile`).
- Roles: `profiles` table with `role` (`student|staff|admin`), `office` (for staff) and `alias` (pseudonym used by the AI service and Realtime filters). Read by `src/lib/auth/profile.ts` (`fetchProfile`) under RLS (you can read your own row).
- Session checks: `src/lib/auth/session.ts` (`readSession`, used by proxy) calls `getUser()` and refreshes cookies; `src/lib/supabase/server.ts` (`createServerSupabase`) for server components and the API route.
- Every page repeats the check: `getUser()`, then `fetchProfile`, then a role redirect (second lock).
- Seeded demo accounts: `src/lib/auth/demo.ts` (`DEMO_ACCOUNTS`), emails only, shared password typed by the presenter:

| Id | Role | Email (from code) | Lands on |
|---|---|---|---|
| student | student | `talal@demo.local` | `/` |
| staff | staff (office from profile) | `it@demo.local` | `/staff` |
| advisor | staff, office `academic` | `advisor@demo.local` (fictional Dr. Rana Haddad) | `/staff/reviews` |
| admin | admin | `admin@demo.local` | `/lab` |

- `src/components/auth/LoginForm.tsx`: email and password form plus "Sign in as" buttons that only fill the email and focus the password. Optional hint text from `NEXT_PUBLIC_DEMO_LOGIN_HINT`.
- `src/hooks/useSignIn.ts` and `src/lib/auth/signin.ts` (`signIn`, `signOut`).
- Office codes (D-005): `registrar`, `it`, `finance`, `transport`, `facilities`, `academic` (`src/components/staff/office.ts`). Category to office map is in the same file (Registration, IT Support, Finance, Transportation, Facilities, Academic Support).
- Not present: self sign-up, student onboarding, role-admin UI, staff account creation UI.

## 3. Student chat (`/`)

### Page and components

- `src/components/chat/ChatScreen.tsx`: header, `ChatThread`, `BuildingPicker` (when buildings exist), `Composer` (text), `MicButton` (voice), `Disclaimer`. Uses `useChat`, `useNotifications(alias, chat.notice)`, `useBuildings`.
- `src/components/chat/ChatThread.tsx`: renders the items: student bubble, `ResultCard` (or `DistressCard`), `ClarificationBubble`, live notice, error.
- `src/components/chat/ResultCard.tsx` shows: status badge (`decided`, `needs_clarification`, `human_review`, `out_of_scope`, `distress`), "understood as", category and priority as `ProbBar` (probability) plus `SetBadge` (the conformal "could also be" set), `FlagBadges` (student audience hides staff-only flags), clarification text, out-of-scope or distress message, `UnderstandingView`, `ActionSummary`, and `ExplanationPanel`.
- Confidence: shown as a probability bar per label (`result.prob`) and a set badge (`result.set`). No separate "confidence %" text was found beyond that; `ProbBar` label is `Category: <label>`.
- Similar questions: `ExplanationPanel` shows "Similar requests" from `explanation.neighbors` with "N% similar" and a "learned from a staff correction" note. This is inside the result card, not a separate page.
- Clarifying question: `ClarificationBubble` renders answer chips; `pick` calls `POST triage/{id}/clarify`.
- Counterfactual: user picks a word; `GET explain/{id}/counterfactual?drop=<token>` (`CounterfactualHint.tsx`).
- Voice: `src/lib/voice/speech.ts`, `useSpeech.ts`, `MicButton.tsx` (browser speech; not verified across browsers).

### How it calls the AI service

- Browser calls `callAi` in `src/lib/ai/browser.ts`, which does `fetch("/api/ai/<path>")` (same origin). It never calls the AI service directly.
- Calls: `POST /api/ai/triage`, `POST /api/ai/triage/{id}/clarify`, `GET /api/ai/explain/{id}/counterfactual` via `src/lib/chat/service.ts` (`submitTriage`, `answerClarification`, `fetchCounterfactual`, `chatErrorKind`). Reducer: `src/lib/chat/reducer.ts`.
- Types: `src/lib/ai/types.gen.ts` generated from `services/ai/openapi.json` (`pnpm gen:types`).
- Student alias is set server-side from the profile (`aliasOf`), never from the browser.

### LLM chat

- No free-form LLM chat exists in apps/web. The student flow is a one-shot triage call plus a fixed clarification (chips). Grep for `openrouter|llm|chatbot|anthropic` found only lab and i18n strings (`llm_out_of_set`, "Tier 1, LLM"). The chat does not call a model-as-tool loop.

## 4. Staff and admin console

### `/staff` (`src/components/staff/StaffScreen.tsx`)

Tabs (`TAB_IDS`): `tickets`, `review`, `incidents`, `flags`. Header badge shows the office name or "all offices" (admin).

**Tickets tab**

- Filter `Select` with `active` (default), `done`, `all` (`src/lib/staff/tickets.ts`, `filterTickets`). `ACTIVE_STATUSES` = open, in_progress, escalated.
- Layout: a card list (`<ul>` in `TicketQueue.tsx`), not a table. Rows: `TicketRow.tsx`.
- Columns (per card, in order): title (button, opens detail), SLA badge ("due in X" / "overdue by X" / finished; overdue gets a red edge), category badge, priority badge, provisional badge, office name (admin only), Linear link badge (`ticket_links`, only if the URL is http(s)), status `StatusSelect`.
- Sorting: active by SLA due ascending, then finished newest first (`sortTickets`). Sort is by SLA; there is no column header sorting.
- Status values staff may set: `open`, `in_progress`, `escalated`, `resolved`, `closed` (`SETTABLE_STATUSES`). `merged` is set by the system. Calls `POST tickets/{id}/status`.
- Live updates: `useTicketQueue` subscribes to `tickets` (`subscribeTickets`) and merges rows.
- Detail pane (`RequestDetail.tsx`): request info (simulated, voice, building, room), decision (category, priority, flags), explanation (collapsed), counterfactual, and a **forward** form (`ForwardForm.tsx`: office select + note) calling `POST tickets/{id}/forward`. Read-only otherwise.

**Review tab** (`ReviewQueue.tsx`, `useReviewQueue`)

- Lists open `review_queue` items, oldest first.
- Per item: text, best guess, reasons, explanation (collapsed), and buttons **Confirm** (`onConfirm`) and **Correct** (opens `CorrectionForm.tsx`: category select, priority select, note). Correction goes to `POST feedback` (`sendFeedback` in `src/lib/staff/service.ts`).
- The correction UI is only here, in the review queue. There is no correction control in the ticket detail pane.

**Incidents tab** (`IncidentsPanel.tsx`, `useIncidents`): open incidents with a resolve action and optional note to reporters. Calls `POST incidents/{id}/resolve`.

**Flags tab** (`FlagsPanel.tsx`, `useFlagEvents`): flagged predictions list (flags only, read-only).

### `/staff/reviews` (advisor, `AdvisorScreen.tsx`, `AdvisorReviews.tsx`)

- Tabs by status (`advisor.tabs.*`), list of review items (`AdvisorReviewList`) with "mine" and "distress" badges, detail pane (`AdvisorReviewDetail`) with student alias, reasoning, Confirm, and Forward (office + note). Calls `GET reviews`, `POST reviews/{id}/forward`.

### `/pulse` (`PulseScreen.tsx`)

- Live campus map (`components/pulse/map/*`: `CampusMap`, `BuildingShape`, `RequestDot`, `IncidentRing`, `MapLegend`; geometry in `map/campus.ts`), `IncidentList`, `EventFeed`. Incident resolve in the page (`pulse.toast.resolved`).
- Data: `usePulse`, `useIncidents`, `useMapBuildings`; realtime on `requests`.
- Student is redirected away.

### `/outbox` (`OutboxScreen.tsx`)

- Table of `outbox` rows (`OutboxTable.tsx`), chips to filter by status, and a help `<details>`. Shows why a message was rejected (`llm_out_of_set` etc.). Read-only.

### `/lab` (admin, `LabScreen.tsx`)

- Tabs: `benchmark`, `calibration`, `live`, `redteam`. Data: `GET metrics`, `POST redteam/run`, `GET insights/recurring` (`src/hooks/useLab.ts`).

Not in the staff console (grep-verified): comments, internal notes, file attachments. Free-text fields exist only for forward, correction, advisor-forward and incident-resolve notes.

## 5. Route handlers and server-side code

### Route handlers (`src/app/api/**`)

Only one file: `src/app/api/ai/[...path]/route.ts` exporting `GET` and `POST` (same `handle`). `dynamic = "force-dynamic"`, responses `Cache-Control: no-store`.

What it does: matches `method + path` against `src/lib/ai/allowlist.ts` (else 404); for non-public paths verifies the session with `getUser()` (401 otherwise); adds `student_alias` to `triage`; drops browser `Authorization` and `X-CP-*` headers; forwards via `aiFetch` (`src/lib/ai/client.ts`) and returns JSON or CSV.

Allow-listed (method, path below `/v1`): POST `triage`, POST `triage/{id}/clarify`, GET `explain/{id}/counterfactual`, POST `feedback`, POST `tickets/{id}/status`, POST `tickets/{id}/forward`, GET `reviews`, POST `reviews/{id}/forward`, GET `incidents`, POST `incidents/{id}/resolve`, GET `insights/recurring`, POST `redteam/run`, GET `metrics`, POST `batch` (CSV upload), GET `health` (public), POST `admin/simulate` and `admin/reindex` (optional, 501 if absent). Not proxied: `integrations/linear/webhook`.

Not proxied: `integrations/linear/webhook` (HMAC, server to server).

### Server actions

- `grep "use server"` in `src`, `e2e`: no matches. There are no server actions. All writes go through the AI proxy above; the browser client is read-only under RLS (`src/lib/supabase/browser.ts` comment).

### Other server code

- `src/lib/supabase/server.ts` (`import "server-only"`), `src/lib/ai/client.ts` (`import "server-only"`).
- `scripts/check-bundle-secrets.mjs` (`check:secrets`): after `pnpm build`, scans the client bundle for the token values and marker strings.

### Environment variable names read by code (names only)

| Name | Read in | Side |
|---|---|---|
| `AI_SERVICE_URL` | `src/lib/ai/client.ts` | server |
| `AI_SERVICE_TOKEN` | `src/lib/ai/client.ts` | server |
| `NEXT_PUBLIC_SUPABASE_URL` | `src/lib/supabase/env.ts` | public (client bundle) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `src/lib/supabase/env.ts` | public (client bundle) |
| `NEXT_PUBLIC_DEMO_LOGIN_HINT` | `src/components/auth/LoginForm.tsx` | public, optional |
| `NODE_ENV` | `src/app/dev/ui/page.tsx` | build |
| `E2E_PASSWORD` | `e2e/*` (fake Supabase password, default `e2e-password` per config comment) | test only |
| `PW_PORT`, `PW_BASE_URL`, `PW_API_PORT`, `PW_SUPABASE_PORT`, `PW_PYTHON`, `FAKE_SUPABASE_PORT` | `playwright.config.ts`, `e2e/support/fake-supabase.mjs` | test only |

Not verified: the contents of `apps/web/.env.local` (present on disk, deliberately not read). `.env.example` at apps/web was not seen in the file list (not present under apps/web).

## 6. Tests and scripts

### `package.json` scripts

| Script | Command |
|---|---|
| `dev` | `next dev` |
| `build` | `next build` |
| `start` | `next start` |
| `typecheck` | `tsc --noEmit` |
| `lint` | `eslint .` |
| `test` | `vitest` |
| `check:secrets` | `node scripts/check-bundle-secrets.mjs` (needs `pnpm build` first) |
| `e2e` | `playwright test` |
| `gen:types` | `openapi-typescript ../../services/ai/openapi.json -o src/lib/ai/types.gen.ts` |

Package manager pinned to `pnpm@10.17.0`; Node `>=22` (`.nvmrc`).

### Vitest (`vitest.config.mts`, `vitest.setup.ts`)

- jsdom, globals, threads pool (`maxWorkers: 2`), include `src/**/*.test.{ts,tsx}`, setup adds `@testing-library/jest-dom` and cleanup.
- 42 test files under `src/` (counted by `find`), spread across lib, hooks, components, i18n, design.
- Not verified: whether they pass today (not run).

### Playwright (`playwright.config.ts`, `e2e/`)

- 5 spec files, 14 tests (counted by `test(` lines): `student-basic` (1), `staff-basic` (3, includes Arabic/RTL), `admin-basic` (6), `pulse-basic` (3), `devui` (1).
- The e2e starts a fake Supabase (`e2e/support/fake-supabase.mjs`, port 54399), the mock AI API (`campuspulse_ai.frameworks.mock_app` via uvicorn, port 8765, from `services/ai`), and `next dev`. One worker. Chromium only.
- Not verified: whether the e2e suite passes today.

## 7. i18n (EN/AR, RTL)

- Dictionaries: `src/i18n/en.ts`, `src/i18n/ar.ts` (about 730 lines each). Typed keys: `DictKey` (`src/i18n/core.ts`).
- Engine: custom, no library. `src/i18n/core.ts`: `translate(lang, key, vars)` with `{name}` placeholders, falls back to English. `labelOf(kind, value, lang)` for category and priority labels (`CATEGORY_VALUES`, `PRIORITY_VALUES`).
- Language choice: cookie `cp_lang` (1 year), then `Accept-Language`, then English (`resolveLang`). Set by `LanguageSwitch` in `src/components/ui/LanguageSwitch.tsx`, persisted by `src/components/ui/RtlProvider.tsx`.
- Server render: `src/app/layout.tsx` sets `<html lang dir>` from the cookie and header.
- Hooks: `useT()`, `useLang()`, `LangScope` (`src/i18n/context.tsx`).
- Fonts: Inter and IBM Plex Sans Arabic via `next/font/google` in `layout.tsx`.
- Tests: `src/i18n/__tests__/dict.test.ts` (AR keys equal EN keys, placeholders match).

## 8. Design system

- Components: `src/components/` folders `ui` (25 files incl. Badge, Button, Card, Dialog, Select, Table, Tabs, Toast, ProbBar, SetBadge, Icon; barrel `index.ts`), `shell`, `brand`, `auth`, `chat`, `explain`, `staff`, `pulse` (+ `map`), `outbox`, `lab`.
- Hand-rolled SVG icons: `src/components/ui/Icon.tsx` with `IconName` union (mic, check, alert, info, close, help, logout, globe, user, graduation, briefcase, shield, chat, ticket, map, mail, flask, chevron-down, and more).
- Tokens: `src/design/tokens.css`, `--cp-*` on `:root` (surfaces, text, borders, accent `#1a68ac`, bands, orange `#f0a81f` for non-text, category and priority colours, semantic colours, spacing, radius, motion). Light theme only.
- Tailwind v4 maps tokens with `@theme inline` (`tokens.css` line 105): `bg-surface-1`, `text-fg-2`, `border-line`, `text-accent`.
- Contrast rules are unit-tested: `src/design/__tests__/tokens.test.ts`.

## 9. Realtime and data layer (for the gap list)

- Repos in `src/lib/repos/*.ts` (read only, RLS). **No caller found** (grep for usage) for `listMyRequests` and `listMyPredictions` (`requests.ts`) or `listNotifications` (`notifications.ts`). `subscribeNotifications` (live inserts for the student alias) is used by `useNotifications`.
- Tables referenced by `.from()` in apps/web: `buildings`, `events`, `incidents`, `notifications`, `outbox`, `predictions`, `predictions_student_v`, `profiles`, `redteam_runs`, `requests`, `review_queue`, `ticket_links`, `tickets`.
- DB types: `src/lib/supabase/types.ts` re-exports `Database` from `supabase/types/database.types.ts` (outside apps/web; not read).

## 10. Summary table: existing vs. target

| Target item | Status in apps/web today | Evidence |
|---|---|---|
| Welcome page with announcements | Missing. `/` opens the chat directly. No announcements table or UI. `loginTitle` "Welcome to CampusPulse" is the login heading only | `app/(student)/page.tsx`, `i18n/en.ts:51` |
| Normal chat agent (LLM talks, model as tool) | Missing. One-shot triage plus fixed clarification chips; no LLM chat | `components/chat/*`, `lib/chat/*` |
| My Requests with ticket status | Missing UI. `listMyRequests` and `listNotifications` exist as repo functions with no caller. Live notices only, not a list | `lib/repos/requests.ts`, `lib/repos/notifications.ts`, `hooks/useNotifications.ts` |
| Staff accounts per department | Partly. Role plus office on `profiles`, office-scoped queue via RLS, 4 demo accounts. No account admin UI | `lib/auth/demo.ts`, `components/staff/StaffScreen.tsx` |
| Comments | Missing (none in code) | grep |
| Internal notes | Missing (only forward, correction and resolve notes) | grep |
| File attachments | Missing in the web app (only CSV batch upload for admin, `batch`) | `lib/ai/allowlist.ts` |
| SLA deadline column | Partly. SLA badge per card ("due in / overdue"), sorted by `sla_due_at`; no column header or sort control | `TicketRow.tsx`, `lib/staff/tickets.ts` |
| Correction UI | Exists in review queue only | `components/staff/CorrectionForm.tsx` |

## Not verified

- Build, typecheck, lint, vitest and playwright results (none run).
- Whether `profiles`, `tickets`, `notifications` tables and RLS policies match these reads (the DB schema lives in `supabase/`, not read).
- Runtime behaviour of voice input and the Linear link.
- Whether `services/ai/openapi.json` matches `src/lib/ai/types.gen.ts`.
- Contents of `apps/web/.env.local` (deliberately not read).
