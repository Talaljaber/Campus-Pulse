# UI (apps/web): as-built

Owner: UI stream. Covers what exists after P0.8, P5.1 to P5.12 and P5.15 (design system, data layer, auth, student chat, voice, staff dashboard, Pulse, model lab, outbox). Later pages are appended by their tasks.

## Run it

```powershell
corepack enable            # or: npm i -g pnpm@10.17.0
pnpm install               # repo root (pnpm-workspace.yaml -> apps/web)
pnpm --filter web dev      # http://localhost:3000 ; kitchen sink at /dev/ui
pnpm --filter web typecheck
pnpm --filter web lint
pnpm --filter web test -- --run          # vitest (jsdom, threads pool)
pnpm --filter web build
cd apps/web; pnpm exec playwright install chromium   # once
pnpm exec playwright test e2e/devui.spec.ts          # starts next dev on :3100 itself
```

### Local dev with the mock API (no backend needed)

Until the real service is deployed, point the web app at the fixture-backed mock API.

```powershell
# once, from the repo root (Python 3.11+)
python -m venv .venv
.venv\Scripts\python -m pip install -r services/ai/requirements-dev.txt -e services/ai

# terminal 1: the mock API on :8000 (every route answers from services/ai/tests/fixtures/api)
.venv\Scripts\python -m uvicorn campuspulse_ai.frameworks.mock_app:create_mock_app --factory --port 8000

# terminal 2: apps/web/.env.local (gitignored), then the app
#   NEXT_PUBLIC_SUPABASE_URL=https://<project>.supabase.co
#   NEXT_PUBLIC_SUPABASE_ANON_KEY=<publishable key>
#   AI_SERVICE_URL=http://localhost:8000
#   AI_SERVICE_TOKEN=local-dev-token          # any value; the mock only checks it is present
cd apps/web; pnpm dev
```

The mock chooses its answer by the exact request text (case and spacing ignored), so type a sentence from `services/ai/tests/fixtures/api/triage_*.json`, for example `where is the bus timetable for the Madaba route?`. Sign in with a demo login (below); the password is `DEMO_USER_PASSWORD` from the root `.env`, typed by hand.

Checks that must pass before a commit (all from `apps/web`):

```powershell
pnpm typecheck; pnpm lint; pnpm test -- --run
pnpm build; node scripts/check-bundle-secrets.mjs      # prints: bundle clean (0 matches)
$env:PW_PYTHON = "<path to the venv python>"; pnpm exec playwright test   # starts fake Supabase, mock API and next dev itself
```

Playwright runs with one worker (two workers left the first sign-in of a spec hanging) and a 150 s test timeout, because `next dev` compiles each route on first visit. If another checkout already runs the e2e servers on the default ports (3100, 8765, 54399), set `PW_PORT`, `PW_API_PORT` and `PW_SUPABASE_PORT` to free ones so the config does not reuse the other checkout's servers.

Notes: the package manager is pnpm 10.17.0 (`packageManager` in `apps/web/package.json`), not npm as the P0.8 text says. Every dependency is an exact pin from Appendix A. No service-role key exists in `apps/web`.

## Design tokens

Source: `src/design/tokens.css`. Light is the default; dark applies under `prefers-color-scheme: dark` unless `<html data-theme="light">`, and is forced by `<html data-theme="dark">` (set by `ThemeSwitch`). Tailwind 4 maps them in `@theme inline` (no `tailwind.config.ts`).

**Look (UI batch 6).** A modern, accessible take on the GJU web identity: a blue top band and a darker icon bar, a white nav row with uppercase bold blue links, the MyGJU portal pattern (rounded-top tabs, icon tiles, fieldset-style info panels, a white card with a soft shadow on a grey page) and a dark footer. The palette is blue + orange-yellow + warm grey. Nothing here is the university's artwork: the mark, the wordmark and every colour value are our own (see [Branding rules](#branding-rules)).

**Contrast is enforced** by `src/design/__tests__/tokens.test.ts`, in both themes: text tokens on every surface >= 4.5:1; tone colours (categories, priorities, semantic) on every surface >= 3:1; primary text on a 16% tint of every tone >= 4.5:1; and a table of **named shell pairs** (below) at their AA minimum. Orange on white is about 2:1, so `--cp-orange` is for borders, bars, icons and fills behind dark text only. Text in orange uses `--cp-orange-ink` (>= 3:1, large bold text only: the wordmark and big headings).

### Brand and shell tokens

| Token | Meaning | Light | Dark | Tailwind | Checked pair (light / dark) |
| --- | --- | --- | --- | --- | --- |
| `--cp-page` | grey page behind the white card | `#eef2f6` | `#0b0f14` | `bg-page` | body text 1 on it >= 4.5 |
| `--cp-band` / `--cp-on-band` | top blue band / its white text | `#1f78c4` / `#ffffff` | `#14507f` / `#ffffff` | `bg-band`, `text-on-band` | 4.62 / 8.46 |
| `--cp-band-2` | darker icon bar under the band | `#155a99` | `#0e3a5e` | `bg-band-2` | white on it 7.11 / 11.76 |
| `--cp-accent` / `--cp-on-accent` | links, nav links, active tab text, primary button / its text | `#1a68ac` / `#ffffff` | `#8cc3f2` / `#0e1218` | `text-accent`, `bg-accent` | on card 5.80 / 9.78; on grey tab 4.80 / 7.81; button text 5.80 / 10.02 |
| `--cp-brand` | decorative blue (mark, map buildings, icons) | `#1b84c9` | `#4ea6e6` | `text-brand`, `bg-brand` | graphics on card 4.05 / 6.91 (>= 3) |
| `--cp-orange` / `--cp-on-orange` | orange-yellow fill (accent button, bars, tab top edge) / dark text on it | `#f0a81f` / `#1c2025` | `#f0a81f` / `#1c2025` | `bg-orange`, `border-orange` | text on it 8.05 / 8.05; **orange alone on white is 2.03, never used for text** |
| `--cp-orange-ink` | orange for large bold text and icons | `#b86e00` | `#f0b84a` | `text-orange-ink` | on card 3.99 / 10.17 (>= 3) |
| `--cp-heading` | warm grey for h1 and h2 | `#5b5d60` | `#c9ced6` | `text-heading` | on card 6.60 / 11.59; on grey tab 5.46 / 9.26 |
| `--cp-panel` / `--cp-on-panel` | grey-blue badge-panel band / white caption | `#52769a` / `#ffffff` | `#3d5f80` / `#ffffff` | `bg-panel`, `text-on-panel` | 4.75 / 6.67 |
| `--cp-footer` / `--cp-on-footer` / `--cp-footer-link` | dark footer / text / links | `#3a3a3a` / `#e8e8e8` / `#9dcdf5` | `#07090d` / `#d5d9df` / `#9dcdf5` | `bg-footer`, `text-on-footer` | 9.28 and 6.76 / 14.06 and 11.85 |

The official-site blues (about `#2A86D5`, `#1F6DB5`) and the `#8AA6BF` panel grey do not reach AA with white text, so the band, the icon bar and the panel are the nearest values that do. The values above are what ships.

### Surfaces, text, lines, semantic

| Token | Meaning | Light | Dark | Tailwind utility |
| --- | --- | --- | --- | --- |
| `--cp-surface-0` | card and control background | `#ffffff` | `#10151c` | `bg-surface-0` |
| `--cp-surface-1` | panels, zebra rows | `#f4f6f8` | `#171d26` | `bg-surface-1` |
| `--cp-surface-2` | inactive tab, table header, hover, skeleton | `#e6eaee` | `#212936` | `bg-surface-2` |
| `--cp-text-1` | primary text | `#1c2025` | `#eef1f5` | `text-fg-1` |
| `--cp-text-2` | secondary text | `#3e444c` | `#c5ccd7` | `text-fg-2` |
| `--cp-text-3` | tertiary, hints | `#545b65` | `#9aa4b3` | `text-fg-3` |
| `--cp-border` | decorative divider | `#ccd3db` | `#2e3744` | `border-line` |
| `--cp-border-strong` | control outline (>= 3:1) | `#76808f` | `#7f8a9b` | `border-line-strong` |
| `--cp-focus` | focus ring (white on the blue bands) | `#1a68ac` | `#8cc3f2` | `outline-focus` |
| `--cp-ok` `--cp-warn` `--cp-danger` `--cp-info` | semantic states | `#17713a` `#8f5900` `#c4161c` `#1a68ac` | `#55d08a` `#f0b040` `#ff8585` `#8cc3f2` | `text-ok` ... |
| `--cp-cat-registration` | category Registration | `#0066b3` | `#5fadff` | `bg-cat-registration` |
| `--cp-cat-it` | category IT Support | `#7a3ea1` | `#c996f2` | `bg-cat-it` |
| `--cp-cat-finance` | category Finance | `#a84e00` | `#f2a65a` | `bg-cat-finance` |
| `--cp-cat-transport` | category Transportation | `#00735a` | `#3fd1a2` | `bg-cat-transport` |
| `--cp-cat-facilities` | category Facilities | `#7d6200` | `#e8cd52` | `bg-cat-facilities` |
| `--cp-cat-academic` | category Academic Support | `#b0307a` | `#f58cbf` | `bg-cat-academic` |
| `--cp-pri-low` | priority low (arrow-down icon) | `#566a80` | `#9db0c6` | `bg-pri-low` |
| `--cp-pri-medium` | priority medium (equal icon) | `#9a5a00` | `#f0b040` | `bg-pri-medium` |
| `--cp-pri-high` | priority high (double-chevron-up icon) | `#c4161c` | `#ff8585` | `bg-pri-high` |
| `--cp-space-1..8` | 4px scale: 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4 rem | same | same | Tailwind `p-*`, `gap-*` |
| `--cp-radius-sm/md/lg` | 0.375 / 0.625 / 1 rem | same | same | `rounded-sm/md/lg` |
| `--cp-font-sans` | Inter, then IBM Plex Sans Arabic (Arabic glyphs), then system | same | same | `font-sans` |
| `--cp-font-mono` | system monospace | same | same | `font-mono` |
| `--cp-text-xs..2xl` | 0.75, 0.875, 1, 1.125, 1.375, 1.75 rem | same | same | `text-xs` ... `text-2xl` |
| `--cp-shadow-1/2/card`, `--cp-overlay` | elevation, the portal card's soft outer shadow, modal backdrop | rgb alpha | stronger alpha | `shadow-1/2/card` |
| `--cp-motion-fast/slow` | 120 ms / 280 ms | same | same | `duration-(--cp-motion-fast)` |

Colour is never the only cue: category colours always sit next to a text label **and a shape** on the map (square, plus, diamond, triangle, cross, bar; see the Pulse map), priority is lightness plus an icon (and a ring weight on the map), the current nav link has an underline and a bar, the selected tab has a white fill and a top edge, toasts carry an icon. Reduced motion disables animation globally (`globals.css`). The category palette is the Okabe-Ito-derived set used since P5.1 (colour-blind safe), retuned only where needed for the contrast tests.

RTL rule (ESLint `no-restricted-syntax`, `src/components/**` and `src/app/**`): no `ml- mr- pl- pr- left- right- border-l/r rounded-l/r text-left text-right`. Use `ms- me- ps- pe- start- end- border-s/e text-start text-end`. Another rule (type-only imports from `@/lib/ai/*` are allowed) bans `@/lib/supabase/*`, `@/lib/ai/*`, `@/lib/repos/*` imports from components.

### Typography

- **Latin:** Inter (`next/font/google`, `--font-inter`). **Arabic:** IBM Plex Sans Arabic (400 to 700, arabic + latin subsets, `--font-plex-arabic`), listed second in `--cp-font-sans`, so Arabic text gets the Arabic face and Latin runs inside Arabic text keep Inter. Both `display: swap`.
- h1 and h2 take `--cp-heading` (warm grey) from the base layer; component titles that need more weight use `text-fg-1` or `text-accent`. Nav links are uppercase through CSS only (`uppercase tracking-wide`), so accessible names are unchanged and Arabic is unaffected.
- Arabic gets 1.8 line height and no negative letter-spacing.
- The wordmark "CampusPulse" is Latin in every language (`lang="en"`, `dir="ltr"`): "Campus" in `--cp-accent`, "Pulse" in `--cp-orange-ink`, 21.6px extra-bold (large text, so the 3:1 pair applies).

### Branding rules

- **No GJU artwork and no claim to be a GJU system.** The mark (`components/brand/CampusPulseMark.tsx`) is original: one tilted blue square with a white heartbeat line through it and a small tilted orange square. It is deliberately not the university's two-square logo. The wordmark is "CampusPulse" with the subtitle "for GJU students" (`shell.subtitle`; Arabic "لطلبة الجامعة الألمانية الأردنية"). The name "GJU" appears only as the audience and in the disclaimer.
- **The footer, on every page** (root layout, `SiteFooter`): "Prototype for GJU AI Quest 2026, not an official GJU service", always in English **and** Arabic whatever the UI language, plus "All data shown is fictional." and the stack line. The chat page keeps its own "Integration-ready prototype on synthetic data" line.
- **No real people:** the header greets the demo alias (`talal`, `staff-it`, `admin`); every name, building and record is fictional.

## Shell

| Piece | File | What it does |
| --- | --- | --- |
| `SiteFooter` | `components/shell/SiteFooter.tsx` | dark footer with the bilingual prototype disclaimer; mounted once in `app/layout.tsx` under the page content (the layout is a `min-h-dvh` flex column, so the footer sits at the bottom of short pages) |
| `AppShell` | `components/shell/AppShell.tsx` | `{ role, current, alias, width }`: the header, then the single `<main id="main">` holding a white card (`shadow-card`) on the grey page. `width`: `narrow` (chat, login), `default`, `wide` (Pulse). `role={null}` is the login page |
| `SiteHeader` | `components/shell/SiteHeader.tsx` | blue top band with the logo card (white, rounded, soft shadow, straddling the band and the icon bar) and "Hello <alias>"; darker icon bar with Help (opens a role-specific dialog) and Sign out (icons only under 640 px, the text stays for assistive technology); white nav row with `RoleNav` and the `LanguageSwitch` at the end; a skip link. The only language switch on a page |
| `RoleNav` | `components/shell/RoleNav.tsx` | uppercase bold blue links with thin vertical separators; student: New request; staff: Staff desk, Pulse map, Outbox; admin: Model lab first, then those. The current link has `aria-current="page"`, an underline and an orange bar |
| `PageHeader` | `components/shell/PageHeader.tsx` | the page's `<h1>`, an optional subtitle and badges, with an orange bar at the start |

Every screen now renders `<AppShell role current alias width>` instead of its own header. `StaffScreen`, `PulseScreen`, `OutboxScreen` and `LabScreen` gained an optional `alias` prop, which their pages pass from the profile.

## Component catalog (`src/components/ui`, all in `index.ts`)

All are presentational: no fetching, no business logic, no keys. Every one exports its props type with TSDoc. Live demo of every state in EN and AR side by side, with the palette and a theme switch: `/dev/ui` (404 in production). Smoke test: `e2e/devui.spec.ts`.

| Component | Purpose | Props type | Accessibility |
| --- | --- | --- | --- |
| `Button` | action; variants primary (blue), **accent (orange, one per view)**, secondary (blue outline), ghost, danger; sizes sm, md | `ButtonProps` | native button, `type=button` default, `loading` sets `aria-busy` and disables, 44px target at md, focus ring |
| `Chip`, `ChipGroup` | single choice (clarification options, outbox filters) | `ChipProps`, `ChipGroupProps` | `role=radio` in a labelled `radiogroup`, roving tabindex, arrows (mirrored in RTL), Home/End, check icon on selected |
| `Badge` | category, priority, state label | `BadgeProps` | text always present; priority/semantic tones add an `aria-hidden` icon |
| `Card` | grey panel with a title (orange bar) and actions | `CardProps` | titled card is a region labelled by its `h3` |
| `Tabs`, `TabPanel` | **portal tabs**: rounded-top grey tabs, the selected one white with blue text and an orange top edge, merging into the panel; scrolls sideways on narrow screens | `TabsProps`, `TabPanelProps` | WAI-ARIA tabs, `aria-selected`/`aria-controls`, roving tabindex, RTL-aware arrows; the focus ring is drawn inside the tab |
| `IconTile` | **portal tile**: white card, thin grey border, a grey, orange or blue illustrative icon at the start and a blue label; a link (`href`), a button (`onClick`) or a static card; `hint`, `selected`, `disabled` | `IconTileProps` | the label is the name; `aria-pressed` / `aria-current` for `selected`; native disabled |
| `InfoPanel`, `InfoGrid` | **fieldset-style panel** (thin grey border, legend title in blue) and a two-column label/value grid (bold label, normal value; stacks under 640 px). `InfoPanel` has an `actions` slot: the action-button pattern | `InfoPanelProps`, `InfoGridProps`, `InfoRow` | a real `<fieldset>` + `<legend>` (role `group`, named by the legend); the grid is a `<dl>` |
| `Table<T>` | data table; bold header with a heavier rule, zebra rows | `TableProps<T>`, `TableColumn<T>` | `th scope=col`, visually hidden caption, focusable scroll region, `text-start/end` alignment, translated empty row |
| `ToastProvider`, `useToast()` | transient messages; an icon per tone beside the thick start edge | `ToastProviderProps`, `ToastApi` | polite live region, dismiss button, auto-dismiss (timers cleaned up); no-op outside the provider |
| `Dialog` | modal with an orange top edge | `DialogProps` | `role=dialog aria-modal`, named by title, focus moves in, Tab trapped, Esc and backdrop close, focus restored, scroll locked |
| `Skeleton` | loading placeholder | `SkeletonProps` | one `role=status` with sr-only text, bars `aria-hidden` |
| `EmptyState` | nothing-here message | `EmptyStateProps` | plain text, optional action |
| `Icon` | built-in decorative line icons (check, alert, info, close, help, logout, globe, user, graduation, briefcase, shield, chat, ticket, map, mail, flask, mic, chevrons, ...) | `IconProps`, `IconName` | `aria-hidden` |
| `LanguageSwitch` | EN/AR toggle (blue outline pill) | `LanguageSwitchProps` | labelled group, `aria-pressed`, each name in its own language |
| `ThemeSwitch` | system/light/dark | `ThemeSwitchProps` | labelled radiogroup; persisted in localStorage `cp_theme` (guarded) |
| `RtlProvider` | owns language, syncs `<html lang dir>`, cookie `cp_lang` | `RtlProviderProps` | direction set server-side first, so there is no flash |
| `TextField`, `TextArea` (P5.7/P5.8) | labelled input and textarea (bold label, blue border on hover and focus) | `TextFieldProps`, `TextAreaProps` | visible `<label>` (textarea can hide it visually), `aria-describedby` for helper text, 44px target, `dir="auto"` on the textarea |
| `Select` (P5.10) | labelled native select | `SelectProps` (`label`, `options`, `hideLabel`, `description`) | real `<label>`, 44px target, native keyboard and screen-reader behaviour |
| `Loadable` (P5.10) | the three list states: skeleton while loading, an alert with Retry on failure, the children when ready | `LoadableProps` (`state`, `onRetry`, `lines`) | skeleton is one `role=status`; the failure is `role=alert` |
| `ServiceBanner` (P5.7) | "AI waking up" / "unavailable" strip | `ServiceBannerProps` | polite `role="status"` region always in the DOM; empty when `state="ok"` |

Brand: `Brand` and `CampusPulseMark` in `components/brand/` (mark + wordmark + subtitle; the mark is `aria-hidden`).

Building a page on the design system (this is the pattern the later advisor-routing and student-journey pages should follow):

```tsx
<AppShell role="staff" current="staff" alias={alias}>
  <PageHeader title={t("…")} subtitle={t("…")} />
  <Tabs … />                                   {/* portal tabs */}
  <TabPanel …>
    <div className="grid gap-2 sm:grid-cols-3"> <IconTile icon="chat" label="…" href="…" /> … </div>
    <InfoPanel title="Assignment" actions={<><Button>Forward</Button><Button variant="secondary">Cancel</Button></>}>
      <InfoGrid rows={[{ label: "Office", value: "IT" }, …]} />
    </InfoPanel>
  </TabPanel>
</AppShell>
```

Helpers: `useDuration()` (ms to a short translated span, "5 min", "3 h", "2 d", using the `explain.ago.*` units; P5.10), `tone.ts` (`Tone`, `CATEGORY_TONE`, `PRIORITY_TONE`: exact backend label to tone), `cn.ts`.

`ProbBar` and `SetBadge` (P5.4) live in the same folder and are exported from `index.ts`; they are listed in the next section because they render API data.

## Generated API types

The HTTP contract is `services/ai/openapi.json` (Backend stream). The UI never hand-writes DTO types.

| File | What |
| --- | --- |
| `src/lib/ai/types.gen.ts` | generated by `openapi-typescript` 7.13.0 (exact pin, Appendix A). **Do not edit.** Committed. Excluded from ESLint. |
| `src/lib/ai/types.ts` | hand-written, type-only aliases: `TriageResponse`, `TriageStatus`, `TriageFlag`, `Category`, `Priority`, `Tier`, `CategoryResult`, `PriorityResult`, `Evidence`, `TopToken`, `Explanation`, `Neighbor`, `Trace`, `CounterfactualHint` (the hint inside a triage response), `CounterfactualView` (the answer of the counterfactual endpoint), `Action`, `Booking`, `FaqAnswer`, `ExternalRef`, `Clarification`, `Understanding`, `Entities`, `Incident`, `ErrorResponse`, `InputLang` (the service's `en`/`ar`/`arabizi`; the UI language type is `Lang` from `@/i18n`). Field names stay snake_case, exactly as generated (LD-36). |

Regenerate after any change to `openapi.json` (from `apps/web`, or `pnpm --filter web gen:types` from the repo root):

```powershell
pnpm gen:types        # openapi-typescript ../../services/ai/openapi.json -o src/lib/ai/types.gen.ts
```

`src/lib/ai/__tests__/types.gen.test.ts` regenerates into a temp file and fails if it differs from the committed one, so a stale file breaks `pnpm test`. Components may `import type` from `@/lib/ai/*` (the ESLint rule `@typescript-eslint/no-restricted-imports` allows type-only imports there); runtime imports from `@/lib/ai/*`, `@/lib/supabase/*` and `@/lib/repos/*` are still errors.

Fixtures for stories and tests: `src/lib/fixtures/api.ts` imports the backend's example responses (`services/ai/tests/fixtures/api/*.json`, via the `@fixtures/*` alias in `tsconfig.json` and `vitest.config.mts`) as `TRIAGE_FIXTURES` (10 triage examples: EN, AR, Arabizi, all five statuses), `COUNTERFACTUAL_FIXTURE` and `INCIDENT_FIXTURES`. `src/lib/fixtures/map.ts` adds 20 deterministic map dots and the incident ring.

## Triage display components (P5.4)

All render DTO slices only (prop types come from `types.gen.ts` through `types.ts`). No fetching, no thresholds, no routing logic; every sentence comes from the dictionaries (`explain.*`, `result.*`, `action.*`, `flags.*`). The language comes from `useLang()`, so there is no `lang` prop. A word click is reported with a callback; the parent fetches the counterfactual and passes the answer back. Live demo with every fixture and an audience switch: `/dev/ui` > "Triage components".

| Component | Where | Purpose | Props type | Renders |
| --- | --- | --- | --- | --- |
| `ProbBar` | `ui/` | label, rounded percent and bar | `ProbBarProps` (`label`, `prob` 0-1, `tone`) | `CategoryOut.prob`, `PriorityOut.prob`, token weights. `role="meter"`, `aria-valuenow` in percent, clamped |
| `SetBadge` | `ui/` | "Could also be: ..." (the conformal set minus the chosen label); renders nothing for a singleton | `SetBadgeProps` (`set`, `kind`, `chosen`) | `CategoryOut.set`, `PriorityOut.set` |
| `EvidenceText` | `explain/` | the request text with top words highlighted (opacity follows weight, capped so text keeps 4.5:1) and evidence spans underlined; highlighted words are `<button aria-pressed>` when `onTokenClick` is set; direction follows the script of the text, not the page | `EvidenceTextProps` (`text`, `tokens`, `evidence`, `onTokenClick`, `activeToken`) | `ExplanationOut.top_tokens`, `PriorityOut.evidence` |
| `CounterfactualHint` | `explain/` | "What if..." sentence, a "Try without X" button, and the live answer in a polite `role="status"` region | `CounterfactualHintProps` (`hint`, `view`, `onCounterfactual`) | `CounterfactualOut` and `CounterfactualResponse` |
| `ExplanationPanel` | `explain/` | top words (inline when `text` is given, else keyboard chips with weights), urgency signals with translated evidence types, similar requests (memory neighbours say "Learned from a staff correction N s ago"), the counterfactual, and a trace line (tier, set sizes, cost, latency, artifact, clarified) | `ExplanationPanelProps` (`explanation`, `text`, `evidence`, `tier`, `onCounterfactual`, `counterfactual`, `now`) | `ExplanationOut` + `PriorityOut.evidence` + `TriageResponse.tier` |
| `ActionSummary` | `chat/` | "What happens next": ticket with Linear link and SLA (Asia/Amman time), advisor booking, FAQ answer with source link and `[demo]` marker, safety alert (`role="alert"`), incident merge, and the "waits for staff" note on `human_review`. Only `http(s)` URLs become links | `ActionSummaryProps` (`action`, `status`) | `ActionOut` |
| `FlagBadges` | `chat/` | badges for the flags the audience may see. `urgency_unsupported` needs staff, `priority_gaming_suspected` needs admin, `empty_input` is never shown (docs/api/README.md > Flags). `isFlagVisible()` is exported | `FlagBadgesProps` (`flags`, `audience`) | `TriageResponse.flags` |
| `UnderstandingView` | `chat/` | the UD-10 summary in the UI language, entities found, the student reply, a note when `source` is `rules`, and optionally the ticket draft | `UnderstandingViewProps` (`understanding`, `showTicketDraft`) | `UnderstandingOut` |
| `ResultCard` | `chat/` | one whole triage result for any of the five statuses: status badge, "understood as" (Arabizi), two meters with sets, flags, status message, understanding, action and explanation | `ResultCardProps` (`result`, `audience`, `text`, `onCounterfactual`, `counterfactual`, `now`) | `TriageResponse` |

Notes:
- The counterfactual callback is `onCounterfactual(token)` on `ExplanationPanel`, `CounterfactualHint` and `ResultCard`. The lower-level `EvidenceText` keeps the name `onTokenClick(token)`. The token is the canonical string from `top_tokens` (what the API expects as `drop`).
- `now` (epoch ms) pins the clock for "N s ago". Without it the time is read after hydration, so server and client HTML match.
- `ResultCard` needs the request `text` to highlight inside it (the API response does not echo it); without it the panel lists the words as chips.
- Server prose in `action.message` is English only, so `ActionSummary` builds its sentences from structured fields and does not print `action.message`. `result.message` is printed for `out_of_scope` and `distress` (the wording matters there); `human_review` uses a localised sentence.

## Map primitives (P5.5)

`src/components/pulse/map/*`, exported from `index.ts`. Live demo: `/dev/ui` > "Campus map" (20 fixture dots, one incident ring, selectable buildings).

| Component | Purpose | Props type |
| --- | --- | --- |
| `CampusMap` | the SVG (`viewBox 0 0 1000 600`), ground, buildings, and an overlay slot for dots and rings | `CampusMapProps` (`buildings`, `children`, `onBuildingClick`, `selected`) |
| `BuildingShape` | one footprint with its letter and name in the UI language; a button when `onSelect` is given | `BuildingShapeProps` (`b`, `selected`, `onSelect`) |
| `RequestDot` | a request: fill = category token, radius 4 / 6 / 9 for low / medium / high, heavier red outline for high, hollow dashed when `simulated` | `RequestDotProps` (`x`, `y`, `category`, `priority`, `simulated`) |
| `IncidentRing` | ring around an incident; radius grows with `reportCount` (18 + 2 per report, capped at 10), count printed inside; pulses with CSS `cp-ring-pulse` unless reduced motion is on | `IncidentRingProps` (`x`, `y`, `priority`, `reportCount`) |
| `MapLegend` | HTML legend (category colours, size = priority, simulated, incident); mirrors in RTL | `MapLegendProps` |

Helpers in `campus.ts`: `Building` (a `buildings` row: `id, code, name_en, name_ar, map_x, map_y`), `FOOTPRINTS`/`footprintOf(code)`, `dotPosition(building, requestId)` (deterministic spot inside the footprint, from an FNV-1a hash of the request id), `FIXTURE_BUILDINGS`, `DOT_RADIUS`, `hash32`.

Conventions:
- **Coordinates:** 1000 x 600 user units, origin top-left, x to the right, y down. `buildings.map_x/map_y` is the **centre** of a footprint (DB seed, docs/db/schema.md); size comes from `campus.ts` by `code` (unknown codes get 120 x 80). A building with a null coordinate is skipped. Dots and rings take absolute map coordinates; use `dotPosition` to place a dot in its building.
- **Fictional campus, no map library** (react-leaflet is Hippocratic-licensed, rejected in Appendix A). Buildings are A to M without I and J (11 letters).
- **RTL:** the `<svg>` is pinned to `dir="ltr"`, so geometry never mirrors. Only building names (set to `direction: rtl` in Arabic) and the HTML legend follow the language.
- **Accessibility:** the map is `role="img"` with `<title>` and `<desc>` when static. With `onBuildingClick` it becomes `role="group"` (an image role would hide the buttons from assistive technology) and each building is `role="button"`, `aria-pressed`, focusable, Enter and Space, with a dashed focus ring. Every dot and ring has `role="img"` and a translated name (`map.*`). Colour is never the only cue: category is explained by the legend, priority by size and outline, simulated by a dashed outline.
- **Motion:** `IncidentRing` reads `prefers-reduced-motion` (`usePrefersReducedMotion`), draws only the static ring and count when reduced, and the keyframes exist only under `no-preference` in `globals.css`.

## i18n

Files: `src/i18n/{en.ts, ar.ts, core.ts, context.tsx, index.ts}`. No i18n library.

- `en.ts` is the key source; `ar.ts` is typed `Dict`, so a missing or extra key fails `typecheck`. `dict.test.ts` also checks key parity, non-empty values and matching `{placeholders}`.
- Keys are dotted camelCase, `<area>.<name>`: areas `app`, `common`, `lang`, `theme`, `category`, `priority`, `ui.<component>`, `explain`, `result`, `action`, `flags` (keys are the API flag names), `map`, `chat`, `staff`, `pulse`, `lab`, `devui`, plus top-level `disclaimer`. Placeholders are `{name}`.
- Backend labels ("IT Support", "high", ...) are never translated in data; display them with `labelOf(kind, value, lang)`. Unknown labels pass through unchanged.
- Language choice: cookie `cp_lang`, then `Accept-Language` (q-values honoured), then `en` (`resolveLang`). The root layout does this on the server and passes `lang` to `RtlProvider`.
- Hooks: `useT()` returns `t(key, vars?)`; `useLang()` returns `{ lang, dir, setLang }`. Without a provider they default to English, which keeps component tests simple. `LangScope` renders a subtree in a fixed language (used by `/dev/ui`).

Add a string:
1. Add the key to `en.ts` (right area, camelCase).
2. Add the same key to `ar.ts` (TypeScript will not compile until you do).
3. Use `t("area.key")` in the component. Never hard-code visible text, including `aria-label`s.
4. Run `pnpm --filter web typecheck` and the `src/i18n` tests.

## Data layer (P5.6)

Components never import it (ESLint enforces this); hooks in `src/hooks/*` and pages do.

| File | What |
| --- | --- |
| `src/lib/supabase/types.ts` | type-only re-export of `Database` from `supabase/types/database.types.ts` through the `@db/*` alias (tsconfig and vitest). The file is DB-owned and is never copied. Also `Sb = SupabaseClient<Database>`, the client type every repo takes. |
| `src/lib/supabase/browser.ts` | `createBrowserSupabase()`: one `@supabase/ssr` browser client per tab (anon key + the user's cookie session). |
| `src/lib/supabase/server.ts` | `createServerSupabase()` (`server-only`): the same client bound to request cookies, for Server Components and route handlers. |
| `src/lib/supabase/env.ts` | reads `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`. No service-role key exists in `apps/web`. |

### Repos (`src/lib/repos/*`, read-only, RLS decides the rows)

Every function takes the client first. `subscribe*` returns an unsubscribe function. Realtime delivers only rows the table's SELECT policy allows; `eqFilter` refuses filter values that are not plain slugs. Errors throw `Error(<PostgREST message>)`.

| Function | Reads | Notes |
| --- | --- | --- |
| `listMyRequests(sb, limit=20)` | table `requests` | student: own rows (RLS by alias) |
| `listMyPredictions(sb, requestId)` | **view `predictions_student_v`** | students have no policy on `predictions`; the view hides staff-only flags, `per_model` and cost |
| `listRequestsWithLocation(sb, limit=200)` / `subscribeRequestsWithLocation(sb, cb)` | table `requests` where `building_id` is set | staff and admin; the subscription drops rows without a building |
| `listReviewQueue(sb)` | table `review_queue`, `status = open`, oldest first | staff and admin |
| `listBuildings(sb)` | table `buildings` | any signed-in user |
| `listTickets(sb, office \| null)` / `listOfficeTickets(sb, office)` / `subscribeTickets(sb, office \| null, cb)` | table `tickets` | sorted by `sla_due_at`; with an office the read and the channel are filtered (`office=eq.<office>`), with `null` (an admin) they carry every row RLS allows (P5.10) |
| `listPredictionsByIds`, `listPredictionsForRequest`, `listLatestPredictions(sb, requestIds)`, `listFlaggedPredictions(sb, flags, limit)` / `subscribePredictions(sb, cb)` | table `predictions` (`repos/predictions.ts`, P5.10-P5.11) | staff and admin only. `listLatestPredictions` keeps the newest row per request (map dot colours); `listFlaggedPredictions` uses an array overlap on `flags`; the subscription reports inserts only |
| `listRequestsByIds(sb, ids)` | table `requests` | staff and admin; RLS drops what the caller may not see (P5.10) |
| `listTicketsForRequest(sb, requestId)`, `listTicketLinks(sb, ticketIds)` | `tickets`, `ticket_links` | link rows carry the Linear URL |
| `listOpenIncidents(sb)` / `subscribeIncidents(sb, cb)` | table `incidents`, `status = open` | staff of the office, admin all |
| `listOutbox(sb, {kind?, limit?})` / `subscribeOutbox(sb, cb)` | table `outbox` | student: rows for their alias; staff and admin all |
| `listNotifications(sb, alias)` / `subscribeNotifications(sb, alias, cb)` | table `notifications` | the only table a student subscribes to; the callback gets inserts only |
| `listRedteamRuns(sb)`, `listRecentEvents(sb)` | `redteam_runs`, `events` | staff and admin. Live model numbers come from `GET /v1/metrics` through the proxy, not the database |

Plan differences: `listReviewQueue` lives in `requests.ts` (it reads the review items of predictions), and `ReviewRow` is the `review_queue` row type.

### AI client and proxy

| File | What |
| --- | --- |
| `src/lib/ai/client.ts` | `import "server-only"`. `aiFetch<T>(path, { method, body?, userJwt, timeoutMs? })` calls `${AI_SERVICE_URL}/v1/<path>` with `Authorization: Bearer AI_SERVICE_TOKEN` and `X-CP-User-JWT`, 20 s timeout. It never throws: the result is `AiResult<T>`. The only module that reads `AI_SERVICE_URL` and `AI_SERVICE_TOKEN`. |
| `src/lib/ai/result.ts` | `AiResult<T> = {ok:true,data} \| AiFail`. `AiFail = {ok:false, status, code, error, details, waking}`. `code` is an API error code (`docs/api/README.md > Errors`) or a web-layer one: `ai_waking`, `ai_not_configured`, `bad_gateway`, `network`. `waking` is true for a timeout, a network error, or an empty 502/503/504 (Render booting). A 503 that carries the API body (`artifact_unavailable`, `store_unavailable`) is a real error, not waking. |
| `src/lib/ai/allowlist.ts` | `matchAllowed(method, segments)`. Allowed: `POST triage`, `POST triage/{id}/clarify`, `GET explain/{id}/counterfactual`, `POST feedback`, `POST tickets/{id}/status`, `GET incidents`, `POST incidents/{id}/resolve`, `GET insights/recurring`, `POST redteam/run`, `GET metrics`, `POST batch`, `GET health` (public), `POST admin/simulate`, `POST admin/reindex`. Ids match `[A-Za-z0-9_-]{1,64}`. Everything else (including the Linear webhook) is 404. |
| `src/app/api/ai/[...path]/route.ts` | the proxy (`GET`, `POST`). Allow-list, then `getUser()` (401 without a session; only `health` is public), then `aiFetch` with the verified session token. It drops any client `Authorization` and `X-CP-*` header (headers are built from scratch), and for `triage` sets `student_alias` from the profile. Errors keep the API status and body and add `waking`. |
| `src/lib/ai/browser.ts` | `callAi<T>(path, { method?, body?, timeoutMs?, signal? })`: the browser's way to call `/api/ai/<path>`; maps the proxy answer to `AiResult<T>`. Holds no secret. |

The browser calls `/api/ai/...` only. The leak check (`scripts/check-bundle-secrets.mjs`, `pnpm check:secrets`) scans `.next/static` and the prerendered HTML for `AI_SERVICE_TOKEN`, `service_role`, `sk-or-`, `GMAIL_APP_PASSWORD`, `WHATSAPP_TOKEN` and the literal values of `AI_SERVICE_TOKEN` / `SUPABASE_SERVICE_ROLE_KEY` when set; it exits 1 on a match. The scanner itself is covered by `src/lib/__tests__/bundle-secrets.test.ts`.

Env vars the web app reads: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `AI_SERVICE_URL`, `AI_SERVICE_TOKEN` (server runtime only), and the optional `NEXT_PUBLIC_DEMO_LOGIN_HINT` (a reminder shown on the login page, never the password).

## Auth and roles (P5.7)

- **Sign-in:** Supabase email and password, `signIn()` in `src/lib/auth/signin.ts`, driven by `useSignIn` and the `LoginForm` on `/login`. After sign-in the role comes from the user's own `profiles` row (`fetchProfile`); an account with no profile is signed out again with a message.
- **Demo logins (D-008):** three "Sign in as" buttons (`src/lib/auth/demo.ts`): `talal@demo.local` (student), `it@demo.local` (staff, office `it`), `admin@demo.local`. A button only fills the email and moves focus to the password field. The shared password is typed by hand; nothing secret is in code or `NEXT_PUBLIC_*`.
- **Role routing, `src/proxy.ts`** (Next 16 renamed `middleware` to `proxy`; the plan text still says `middleware.ts`). It refreshes the session (`@supabase/ssr`), verifies it with `getUser()`, reads the role, and applies `decideRoute` (`src/lib/auth/routing.ts`, a pure function with a tested matrix):

  | Path | signed out | student | staff | admin |
  | --- | --- | --- | --- | --- |
  | `/login` | passes | `/` | `/staff` | `/lab` |
  | `/` | `/login` | passes | passes | passes |
  | `/staff`, `/pulse`, `/outbox` | `/login?next=...` | `/` | passes | passes |
  | `/lab` | `/login?next=...` | `/` | `/staff` | passes |
  | `/dev/*` | passes (404s itself in production) | | | |

  `/api/*` and static assets are outside the matcher: route handlers authenticate themselves. A user whose profile is missing or has an unknown role is treated as signed out. `?next=` is accepted only as a same-origin path (`safeNext`).
- **"AI waking up" banner:** `ServiceBanner({ state: 'ok'|'waking'|'down' })` (`components/ui`), mounted once in the root layout by `components/shell/ServiceStatus` and driven by `useServiceHealth`: it polls `GET /api/ai/health` every 30 s while healthy and every 5 s otherwise; a probe slower than 3 s or an unreachable service is `waking`; 12 failed probes (about a minute) or a degraded/misconfigured service is `down`. The state machine is `src/lib/ai/health.ts`. The banner is a polite live region and shows nothing when ok.

## Student chat `/` (P5.8)

`src/app/(student)/page.tsx` (server) checks the session and profile, then renders `ChatScreen` with the alias. Composition: `ChatThread` (a `role="log"` list) renders, per item, a student bubble, a `ResultCard` (which already contains `ExplanationPanel`, `ActionSummary`, `FlagBadges`, `UnderstandingView` and the Arabizi "understood as" line), the `DistressCard`, a `ClarificationBubble`, a live notice or an error line.

| Piece | Where | Behaviour |
| --- | --- | --- |
| `Composer({ onSubmit(text, mode), busy, micSlot? })` | `components/chat` | Enter sends, Shift+Enter adds a line, IME composition does not send; blank text is not sent; cleared after sending. `micSlot` takes a node or a function of `{ begin, apply }` (see "Voice input"); a dictated transcript only fills the box and the request is sent as `voice`. |
| `ClarificationBubble({ q, onPick, disabled, answered? })` | `components/chat` | the question in its own script's direction; options are buttons in a labelled group, not a radiogroup (an arrow key would otherwise send an answer on every move). Answered chip shows a check and `aria-pressed`. |
| `BuildingPicker({ buildings, value, onChange, disabled })` | `components/chat` | native select, names in the UI language; `value` is the building id, which equals its code in the seed and is sent as `location.building`. |
| `DistressCard({ message })` | `components/chat` | the service's supportive text as written (counselling placeholder and 911), no labels or ticket UI. |
| `Disclaimer` | `components/chat` | "Integration-ready prototype on synthetic data". |
| `TextField`, `TextArea` | `components/ui` | new primitives (none existed): a real visible label, 44 px target, `dir="auto"` on the textarea. |
| `ArabiziHint` | not built | `ResultCard` already prints "Understood as: ..." from `understood_as`; a second component would duplicate it. |

Logic, outside components:
- `src/lib/chat/reducer.ts` is a pure reducer. `needs_clarification` adds only the question; `out_of_scope` adds the rephrase card and the topic chips; everything else adds one card.
- `src/lib/chat/service.ts` has `submitTriage`, `answerClarification`, `fetchCounterfactual` (all through `callAi`), `chatErrorKind` (the service's English prose is never shown: a status or code maps to `chat.error*`) and `noticeFromNotification`.
- Hooks (`src/hooks`): `useChat` (state, send, pick, counterfactual, notice; locks against double sends), `useNotifications(alias, cb)` (Realtime on `notifications`, unsubscribes on unmount), `useBuildings`, `useServiceHealth`, `useSignIn` and `useSignOut`. The plan's `useTriage`, `useClarify` and `useCounterfactual` are one hook because they share the thread.
- Clarification: the chip answer goes to `POST triage/{id}/clarify` with `question_id` and `option_id`; the result is appended and the chip stays selected. A failed answer re-opens the question. Counterfactual: clicking a highlighted word calls `GET explain/{id}/counterfactual?drop=<token>` and the answer appears inside the same `ResultCard`.
- Live updates: `noticeFromNotification` follows the contract in docs/api/README.md ("Notifications payload"). A `message` is shown as written and wins (kinds `message` and `incident` carry only `message`; `ticket_status` may carry one too). Without a message, a `status` becomes "Your ticket <title> is now <status>" (`ticket_status` rows carry `ticket_id`, `status`, `title`). Anything else is "You have a new update". The old `body` key is not read.
- Clarify errors: 409 (no question pending), 422 (the answer names a question that is not the pending one) and 404 all become `chat.errorNothingToAnswer`; the question is re-opened by the reducer only for a failed call, so the student can send the request again.

Tests: `src/components/chat/__tests__/flow.test.tsx` runs the real hook against the API fixtures (clarify, counterfactual, distress, waking, re-open, double send); `e2e/student-basic.spec.ts` runs the real app against the mock API and `e2e/support/fake-supabase.mjs` (a test double that accepts `E2E_PASSWORD`, default `e2e-password`).

## Voice input (P5.9)

Dictation for the student chat, through the browser's Web Speech API. It is offered only where the API exists (Chrome, Edge, Safari); on Firefox the mic button is not rendered and typing is the only path. The browser's own speech service hears the audio; the web app never receives it.

| Piece | Where | Behaviour |
| --- | --- | --- |
| `useSpeech(lang: 'ar-JO' \| 'en-US'): { supported, listening, transcript, start, stop, error? }` | `src/hooks/useSpeech.ts` | `supported` is false on the server and in Firefox (so there is no hydration mismatch). `start()` creates one recogniser (`continuous=false`, `interimResults=true`), clears the transcript and error, and must come from a click. `transcript` joins every result, interim words included. `error` is the browser's code (`not-allowed`, `no-speech`, ...). The recogniser is aborted on unmount. |
| `MicButton({ lang, onTranscript, onStart?, disabled? })` | `components/chat` | Toggle button (`aria-pressed`, label "Dictate in English/Arabic" or "Stop listening", 44 px, danger variant while listening) plus a polite sr-only "Listening" status. A failure becomes a toast (`chat.voice.error*`); an `aborted` session is silent. Renders nothing when unsupported. |
| `Composer({ micSlot })` | `components/chat` | `micSlot` is a node **or** a function receiving `{ begin, apply }`. `begin()` remembers the text already typed; `apply(transcript)` sets the box to typed text plus the transcript and marks the message as voice. The transcript is only put in the box: the student edits it and presses send (SPEC 5.1 [1]). The request goes out with `input_mode: "voice"`; emptying the box, or a send, resets the mode to `text`. |
| `src/lib/voice/speech.ts` | pure | `speechLangFor(lang)` (the UI language picks the dictation language), `getRecognitionCtor`, `transcriptOf`, `speechErrorKind`, `joinTranscript`. |

`ChatScreen` wires it: `micSlot={(mic) => <MicButton lang={speechLangFor(lang)} onStart={mic.begin} onTranscript={mic.apply} />}`. The dictation language follows the page language (Arabic page, `ar-JO`). A `ToastProvider` now lives in the root layout. Tests: `src/hooks/__tests__/useSpeech.test.tsx` (mocked `webkitSpeechRecognition`), `src/lib/voice/__tests__`, `src/components/chat/__tests__/voice.test.tsx`. Manual: in Chrome press the mic, say the moment-1 sentence, see it in the box, edit, send.

## Staff dashboard `/staff` (P5.10)

- **Route and roles:** `/staff`, staff and admin (the proxy sends students to `/`, signed-out visitors to `/login`; the page re-checks). Staff see only their office, an admin sees every office; **row-level security decides the rows**, the page never filters for access. The `office` argument only narrows an admin's query.
- **Run it locally:** sign in as `it@demo.local` (staff, office `it`) or `admin@demo.local` with the mock API and the real Supabase project (see "Local dev with the mock API"). Ticket status, confirm/correct and resolve go through the proxy to the API; the mock answers them from fixtures.
- **Composition:** `app/staff/page.tsx` (server: session, profile, office) renders `StaffScreen` (wires the hooks, not in the barrel). Four tabs (`Tabs`/`TabPanel`): Tickets, Needs review (N), Incidents (N), Flags. Counts are in the tab names.

| Area | Component (`components/staff`) | Data | Notes |
| --- | --- | --- | --- |
| Queue | `TicketQueue({ tickets, now, onStatus, onSelect, selectedId, pendingIds, showOffice })`, `TicketRow`, `StatusSelect` | `listTickets(sb, office)` + `listTicketLinks`; Realtime `subscribeTickets`; `POST tickets/{id}/status` | Active tickets by `sla_due_at`, finished last. SLA is a badge in words ("Overdue by 3 h", "Due in 2 d") plus a danger edge when overdue, so colour is never the only cue. Filter: Active / Finished / All. A live ticket gets its Linear link read once. `merged` is shown but cannot be picked. A failed change toasts `staff.error.*`. |
| Detail | `RequestDetail({ ticket, detail, load, audience, counterfactual, onCounterfactual, onClose })` | `listRequestsByIds` + `listPredictionsForRequest` (hook `useTicketDetail`); `GET explain/{id}/counterfactual` | The request text in its own direction, voice/simulated markers, building and room, the current decision, flags the viewer may see, and the `ExplanationPanel` inside a collapsed `<details>`. Without a readable prediction it says so. |
| Review | `ReviewQueue({ items, pendingIds, onConfirm, onCorrect })`, `CorrectionForm({ categories, priorities, initial, busy, onSubmit, onCancel })` | `listReviewQueue` + `listPredictionsByIds` + `listRequestsByIds`; `POST feedback` | Each item: text, best guess, why it was unsure (set sizes, or a distress note), collapsed explanation, Confirm and Correct. Correct opens the form (native selects, labels in the page language, values are the exact backend strings, optional note). Success shows `staff.memoryToast` and drops the item. A **distress** item has no Correct button (nothing to classify). `review_queue` is not in the Realtime publication, so a new `predictions` insert flagged `needs_review` or `distress` triggers a debounced re-read. |
| Incidents | `IncidentsPanel({ incidents, buildings, onResolve })` around `pulse/IncidentList` | `listOpenIncidents` + `subscribeIncidents`; `POST incidents/{id}/resolve` | Resolve opens a confirmation dialog with an optional note to the reporters; the toast says how many were notified. |
| Flags | `FlagsPanel({ events, audience, now })` | `listFlaggedPredictions(sb, ['injection_attempt','urgency_unsupported','priority_gaming_suspected'])` + `listRequestsByIds` | Reads `predictions.flags`, not the `events` log (flag names are documented, audit action names are not). Gaming is admin only (`isFlagVisible`); an event with no visible flag is hidden. Informational: a flag never changes a label. |

- **States:** every list uses `Loadable` (skeleton while loading, an alert with a Retry button when the read fails, then the content), each list has an `EmptyState`, and a failed action toasts a translated sentence (`session`, `forbidden`, `notFound`, `waking`, `generic`). The global "AI waking up" banner still covers the service.
- **Logic outside components:** `src/lib/staff/{tickets,review,detail,flags,explanation,service}.ts` and `src/lib/incidents` (pure: sort, SLA state, merge live rows, build views; thin API calls). Hooks: `useTicketQueue(office)`, `useReviewQueue()`, `useIncidents()`, `useFlagEvents()`, `useTicketDetail(requestId)`, `useMapBuildings()`.
- **Explanation adapter:** the stored `predictions.explanation` is the backend's domain object, not the API's `ExplanationOut` (neighbours say `category` not `label`, the trace is a free dictionary). `explanationFromPrediction(row)` maps it defensively (the trace is rebuilt from the row's `set_*`, `cost_usd`, `latency_ms`, `artifact_version`; `models_agree` is a placeholder `true`) and `evidenceFromPrediction` reads `core.evidence.spans`.
- **Office names:** `profiles.office`/`tickets.office` are codes (D-005); `useOfficeLabel()` shows `staff.offices.<code>`. `applyTicketOut` keeps the database's `office` and `category` when the API answers a status change, because the API may name an office in words.
- **Tests:** `src/lib/staff/__tests__`, `src/components/staff/__tests__`, `src/hooks/__tests__/staffHooks.test.tsx`, `src/lib/__tests__/repos-staff.test.ts`; `e2e/staff-basic.spec.ts` (queue for the office only, overdue marker, status change, detail with a collapsed explanation, correct once with the memory toast, resolve an incident, Arabic RTL with no overflow, admin sees every office). The fake Supabase gained fixture rows and a stand-in for office-level RLS on tickets; Realtime is still not faked.

## Pulse `/pulse` (P5.11)

- **Route and roles:** `/pulse`, staff and admin (same guard as `/staff`). Staff see their office's rows, an admin sees all (RLS).
- **Run it locally:** as for `/staff`; with the simulator (`python scripts/simulate_pulse.py --scenario config/simulation/wifi_m.yaml`, DB stream) dots and a ring appear live.
- **Composition:** `app/pulse/page.tsx` renders `PulseScreen` (not in the barrel): header (live badge, link back to `/staff`, language switch, sign out), the `CampusMap` with `RequestDot`s and `IncidentRing`s plus `MapLegend`, a card with `IncidentList`, a card with `EventFeed`. Clicking a building toggles a filter on the incident list ("Building M, ... / Show all buildings").

| Piece | Where | Data / behaviour |
| --- | --- | --- |
| `usePulse()` | `src/hooks` | One snapshot (`listRequestsWithLocation`, `listOpenIncidents`, `listOutbox({kind:'broadcast', limit: 20})`, then `listLatestPredictions` for the dot labels), then Realtime on `requests` (with a building), `predictions` inserts, `incidents` and `outbox` (broadcast). `resolve(id, note)` calls `POST incidents/{id}/resolve` and applies the answer. |
| `pulseReducer`, `INITIAL_PULSE` | `src/lib/pulse/state.ts` | Pure. A dot needs the request **and** its labels, in either arrival order. An incident is new (not seen), a bump (higher `report_count`) or resolved (status not open; removed). The feed is deduplicated by event id (`req:`, `inc:<id>:new`, `inc:<id>:bump:<n>`, `inc:<id>:resolved`, `b:`) and capped at 50, newest first. SIMULATED = a simulated request, an outbox row with status `simulated`, or an incident whose building only has simulated requests. |
| `dotsOf`, `ringsOf`, `openIncidents` | `src/lib/pulse/view.ts` | Dots inside the footprint via `dotPosition`; rings above the building centre, several in one building spread sideways; incidents newest first, optionally one building. |
| `IncidentList({ incidents, buildings, onResolve, now })` | `components/pulse` | Title, category and priority badges, report count, age, building name; Resolve (when `onResolve` is given) opens a `Dialog` with an optional note and stays open until the promise settles. Used by `/staff` as well. |
| `EventFeed({ events, now })` | `components/pulse` | A polite `role="log"`. Each line is a sentence in the page language from structured fields (`pulse.event.*`); free text (an incident title) is shown as written. A SIMULATED badge marks demo traffic. `FeedEvent = { id, at, kind: 'request'\|'incident_new'\|'incident_bump'\|'broadcast'\|'resolved', simulated, buildingId, category, priority, count, title }` (structured instead of the plan's single `text`, so the sentence can be translated). |

- **States:** loading skeleton, a retry alert on a failed snapshot, empty states for incidents and the feed. The map stays `dir="ltr"` in Arabic; everything else mirrors.
- **Tests:** `src/lib/pulse/__tests__` (reducer and view), `src/components/pulse/__tests__`, `src/hooks/__tests__/usePulse.test.tsx` (fake channels: live request, prediction, bump, resolve), `e2e/pulse-basic.spec.ts` (dots, ring, feed, SIMULATED, building filter, resolve, RTL, student blocked). The live half of moment 2 is covered by the reducer and hook tests because the e2e Supabase double does not speak Realtime.

## Model lab `/lab` (P5.12)

- **Route and roles:** `/lab`, admin only (the proxy sends staff to `/staff`, students to `/`; the page re-checks; the API checks the role again). The admin login lands here.
- **Data:** `GET /v1/metrics` (`MetricsResponse`) and `POST /v1/redteam/run` through the proxy (`src/lib/lab/service.ts`; hooks `useLabMetrics`, `useRedTeam` in `src/hooks/useLab.ts`). `refresh()` re-reads quietly after a run.
- **Composition:** `LabScreen` (not in the barrel) with four tabs. Charts are numbers in tables with a thin repeat bar; no chart library was added.

| Tab | Components (`components/lab`, typed slices of `MetricsResponse`) |
| --- | --- |
| Benchmark | `BenchmarkTable` (one table per target; model rows by dataset column: CV official, CV all, Set 1 to Set 4, Pooled, Probes; every cell has macro-F1, accuracy, rows and groups, "Small sample" under 30 groups, Cut and Not available as words; a legend of the columns and how to read them), `AblationTable`, `ConfusionMatrix` (counts and row shares, diagonal bold and outlined, tint is a repeat only) |
| Calibration and fairness | `CoverageChart` (coverage, mean set size, single-label rate per dataset and language, counts, the "approximate, about 30 groups" caveat), `CalibrationTable` (ECE and bins), `FairnessChart` (macro-F1 per language, gap to the best in points, counts) |
| Live system | `RouterStats` (requests, tier 0 share, cost, cost per 1,000, cached, tier table), `MemoryStats` |
| Red team | `RedTeamRunner` (ten styles, n 1 to 200, seed; validates itself; all styles are sent as `styles: null`), `ScorecardHistory` (newest first; pass rate by style and language weakest first; failures folded in a `<details>`) |

- **Per-set columns:** the contract's `dataset` enum has only `oof_official`, `oof_all`, `our_test` (pooled) and `probes`. The page also reads `our_test:set1`, `our_test_set1`, `our_test/set1` or `set1` (same for set2 to set4) into their own columns (`datasetKeyOf`, `src/lib/lab/metrics.ts`). Until the report has such rows only Pooled shows, with a note saying so.
- **Empty report:** with no `model_lab.json` (`generated_at` null and every offline section empty) the Benchmark and Calibration tabs show "No model metrics yet"; the live system and the red team still work. A failed read shows the shared retry alert.
- **Red-team history:** `MetricsResponse.redteam` merged with this session's runs by `run_id` (the service's copy wins). While the backend leaves `redteam` empty, only runs started on this page show, and they are lost on reload.
- **Tests:** `src/lib/lab/__tests__`, `src/components/lab/__tests__` (components, and `LabScreen` with the service mocked), `e2e/admin-basic.spec.ts`.

## Outbox `/outbox` (P5.15)

- **Route and roles:** `/outbox`, staff and admin (as `/staff`). Row-level security decides the rows (staff and admin read all).
- **Composition:** `OutboxScreen` (not in the barrel) wires `useOutbox` (`listOutbox` limit 200 plus `subscribeOutbox`, merged by id so a status change updates in place) to `OutboxTable`. A "Demo accounts only" banner, status chips with counts (`ChipGroup`; All, Sent, SIMULATED, Deferred, REJECTED, Failed, Queued, plus any unknown status present), a folded "What the statuses mean", and the table: when (Amman time), kind, channel, to, subject, status badge, reason or error. Rejected and failed rows also get a heavier edge, so colour is never the only cue.
- **Logic:** `src/lib/outbox/view.ts` (tones, merge, counts, filters; pure, tested).

## Navigation between the staff-side pages

`components/shell/RoleNav({ role, current })` is in the header of `/lab`, `/staff`, `/pulse` and `/outbox`: staff get Staff desk, Pulse map, Outbox; an admin gets Model lab first, then the same three. The current page has `aria-current="page"` and a bold underline. It replaced the single ad hoc links (`staff.pulseLink`, `pulse.back`, now removed). `PulseScreen` takes a `role` prop.

## Routes

| Route | Roles | Status |
| --- | --- | --- |
| `/login` | public | email and password, demo buttons (P5.7) |
| `/` | any signed-in role | student chat (P5.8) |
| `/api/ai/[...path]` | session (health is public) | allow-listed proxy to the AI service (P5.6) |
| `/dev/ui` | dev only | kitchen sink; `notFound()` when `NODE_ENV === "production"` |
| `/staff` | staff, admin | staff dashboard (P5.10) |
| `/pulse` | staff, admin | live map, incidents and feed (P5.11) |
| `/outbox` | staff, admin | outbox list with status filters (P5.15) |
| `/admin` | admin | Overview (P10.17): backlog, SLA, offices, request volume, AI handling, AI cost, delivery; the admin login lands here. The model lab (`/lab`, P5.12) was removed. |
