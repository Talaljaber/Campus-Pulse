# UI (apps/web): as-built

Owner: UI stream. Covers what exists after P0.8, P5.1, P5.2 and P5.3. Pages, data layer and feature components are added by later tasks and will be appended here.

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

Notes: the package manager is pnpm 10.17.0 (`packageManager` in `apps/web/package.json`), not npm as the P0.8 text says. Every dependency is an exact pin from Appendix A. No service-role key exists in `apps/web`.

## Design tokens

Source: `src/design/tokens.css`. Light is the default; dark applies under `prefers-color-scheme: dark` unless `<html data-theme="light">`, and is forced by `<html data-theme="dark">` (set by `ThemeSwitch`). Tailwind 4 maps them in `@theme inline` (no `tailwind.config.ts`). Contrast is enforced by `src/design/__tests__/tokens.test.ts`: text on every surface >= 4.5:1, tone colours on every surface >= 3:1, primary text on a 16% tint of every tone >= 4.5:1.

| Token | Meaning | Light | Dark | Tailwind utility |
| --- | --- | --- | --- | --- |
| `--cp-surface-0` | page background | `#ffffff` | `#0e1218` | `bg-surface-0` |
| `--cp-surface-1` | cards, panels | `#f5f7fa` | `#161b23` | `bg-surface-1` |
| `--cp-surface-2` | table header, hover, skeleton | `#e9edf2` | `#1f2631` | `bg-surface-2` |
| `--cp-text-1` | primary text | `#12161d` | `#eef1f5` | `text-fg-1` |
| `--cp-text-2` | secondary text | `#3a4351` | `#c5ccd7` | `text-fg-2` |
| `--cp-text-3` | tertiary, hints | `#566070` | `#9aa4b3` | `text-fg-3` |
| `--cp-border` | decorative divider | `#d2d8e0` | `#2e3744` | `border-line` |
| `--cp-border-strong` | control outline (>= 3:1) | `#76808f` | `#7f8a9b` | `border-line-strong` |
| `--cp-focus` | focus ring | `#0b5cd5` | `#86b7ff` | `outline-focus` |
| `--cp-accent` / `--cp-on-accent` | primary button fill / its text | `#0b5cd5` / `#ffffff` | `#86b7ff` / `#0e1218` | `bg-accent`, `text-on-accent` |
| `--cp-cat-registration` | category Registration | `#0066b3` | `#5fadff` | `bg-cat-registration` |
| `--cp-cat-it` | category IT Support | `#7a3ea1` | `#c996f2` | `bg-cat-it` |
| `--cp-cat-finance` | category Finance | `#a84e00` | `#f2a65a` | `bg-cat-finance` |
| `--cp-cat-transport` | category Transportation | `#00735a` | `#3fd1a2` | `bg-cat-transport` |
| `--cp-cat-facilities` | category Facilities | `#7d6200` | `#e8cd52` | `bg-cat-facilities` |
| `--cp-cat-academic` | category Academic Support | `#b0307a` | `#f58cbf` | `bg-cat-academic` |
| `--cp-pri-low` | priority low (arrow-down icon) | `#566a80` | `#9db0c6` | `bg-pri-low` |
| `--cp-pri-medium` | priority medium (equal icon) | `#9a5a00` | `#f0b040` | `bg-pri-medium` |
| `--cp-pri-high` | priority high (double-chevron-up icon) | `#c4161c` | `#ff8585` | `bg-pri-high` |
| `--cp-ok` `--cp-warn` `--cp-danger` `--cp-info` | semantic states | `#17713a` `#8f5900` `#c4161c` `#0b5cd5` | `#55d08a` `#f0b040` `#ff8585` `#86b7ff` | `text-ok` ... |
| `--cp-space-1..8` | 4px scale: 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4 rem | same | same | Tailwind `p-*`, `gap-*` |
| `--cp-radius-sm/md/lg` | 0.375 / 0.625 / 1 rem | same | same | `rounded-sm/md/lg` |
| `--cp-font-sans` | Inter, then IBM Plex Sans Arabic (Arabic glyphs), then system | same | same | `font-sans` |
| `--cp-font-mono` | system monospace | same | same | `font-mono` |
| `--cp-text-xs..2xl` | 0.75, 0.875, 1, 1.125, 1.375, 1.75 rem | same | same | `text-xs` ... `text-2xl` |
| `--cp-shadow-1/2`, `--cp-overlay` | elevation, modal backdrop | rgb black alpha | stronger alpha | `shadow-1/2` |
| `--cp-motion-fast/slow` | 120 ms / 280 ms | same | same | `duration-(--cp-motion-fast)` |

Rules: category colours are always shown next to a text label; priority is lightness plus an icon, never colour alone; reduced-motion disables animation globally (`globals.css`).

RTL rule (ESLint `no-restricted-syntax`, `src/components/**` and `src/app/**`): no `ml- mr- pl- pr- left- right- border-l/r rounded-l/r text-left text-right`. Use `ms- me- ps- pe- start- end- border-s/e text-start text-end`. Another rule bans `@/lib/supabase/*`, `@/lib/ai/*`, `@/lib/repos/*` imports from components.

Fonts: Inter (latin) and IBM Plex Sans Arabic (arabic + latin, 400-700) through `next/font/google`, `display: swap`.

## Component catalog (`src/components/ui`, all in `index.ts`)

All are presentational: no fetching, no business logic, no keys. Every one exports its props type with TSDoc. Live demo of every state in EN and AR side by side, with a theme switch: `/dev/ui` (404 in production). Smoke test: `e2e/devui.spec.ts`.

| Component | Purpose | Props type | Accessibility |
| --- | --- | --- | --- |
| `Button` | action; variants primary, secondary, ghost, danger; sizes sm, md | `ButtonProps` | native button, `type=button` default, `loading` sets `aria-busy` and disables, 44px target at md, focus ring |
| `Chip`, `ChipGroup` | single choice (clarification options) | `ChipProps`, `ChipGroupProps` | `role=radio` in a labelled `radiogroup`, roving tabindex, arrows (mirrored in RTL), Home/End, check icon on selected |
| `Badge` | category, priority, state label | `BadgeProps` | text always present; priority/semantic tones add an `aria-hidden` icon |
| `Card` | surface with title and actions | `CardProps` | titled card is a region labelled by its `h3` |
| `Tabs`, `TabPanel` | tab list and linked panel | `TabsProps`, `TabPanelProps` | WAI-ARIA tabs, `aria-selected`/`aria-controls`, roving tabindex, RTL-aware arrows |
| `Table<T>` | data table | `TableProps<T>`, `TableColumn<T>` | `th scope=col`, visually hidden caption, focusable scroll region, `text-start/end` alignment, translated empty row |
| `ToastProvider`, `useToast()` | transient messages | `ToastProviderProps`, `ToastApi` | polite live region, dismiss button, auto-dismiss (timers cleaned up); no-op outside the provider |
| `Dialog` | modal | `DialogProps` | `role=dialog aria-modal`, named by title, focus moves in, Tab trapped, Esc and backdrop close, focus restored, scroll locked |
| `Skeleton` | loading placeholder | `SkeletonProps` | one `role=status` with sr-only text, bars `aria-hidden` |
| `EmptyState` | nothing-here message | `EmptyStateProps` | plain text, optional action |
| `Icon` | built-in decorative icons | `IconProps`, `IconName` | `aria-hidden` |
| `LanguageSwitch` | EN/AR toggle | `LanguageSwitchProps` | labelled group, `aria-pressed`, each name in its own language |
| `ThemeSwitch` | system/light/dark | `ThemeSwitchProps` | labelled radiogroup; persisted in localStorage `cp_theme` (guarded) |
| `RtlProvider` | owns language, syncs `<html lang dir>`, cookie `cp_lang` | `RtlProviderProps` | direction set server-side first, so there is no flash |

Helpers: `tone.ts` (`Tone`, `CATEGORY_TONE`, `PRIORITY_TONE`: exact backend label to tone), `cn.ts`.

DTO rendering components (`ProbBar`, `SetBadge`, `ResultCard`, ...) arrive with P5.4 and will be listed here with the DTO each renders.

## i18n

Files: `src/i18n/{en.ts, ar.ts, core.ts, context.tsx, index.ts}`. No i18n library.

- `en.ts` is the key source; `ar.ts` is typed `Dict`, so a missing or extra key fails `typecheck`. `dict.test.ts` also checks key parity, non-empty values and matching `{placeholders}`.
- Keys are dotted camelCase, `<area>.<name>`: areas `app`, `common`, `lang`, `theme`, `category`, `priority`, `ui.<component>`, `chat`, `staff`, `pulse`, `lab`, `devui`, plus top-level `disclaimer`. Placeholders are `{name}`.
- Backend labels ("IT Support", "high", ...) are never translated in data; display them with `labelOf(kind, value, lang)`. Unknown labels pass through unchanged.
- Language choice: cookie `cp_lang`, then `Accept-Language` (q-values honoured), then `en` (`resolveLang`). The root layout does this on the server and passes `lang` to `RtlProvider`.
- Hooks: `useT()` returns `t(key, vars?)`; `useLang()` returns `{ lang, dir, setLang }`. Without a provider they default to English, which keeps component tests simple. `LangScope` renders a subtree in a fixed language (used by `/dev/ui`).

Add a string:
1. Add the key to `en.ts` (right area, camelCase).
2. Add the same key to `ar.ts` (TypeScript will not compile until you do).
3. Use `t("area.key")` in the component. Never hard-code visible text, including `aria-label`s.
4. Run `pnpm --filter web typecheck` and the `src/i18n` tests.

## Routes

| Route | Roles | Status |
| --- | --- | --- |
| `/` | any | placeholder (language switch, tagline, disclaimer); chat arrives in P5.8 |
| `/dev/ui` | dev only | kitchen sink; `notFound()` when `NODE_ENV === "production"` |

Data-layer functions (`src/lib/repos/*`, `src/lib/ai/*`) do not exist yet (P5.6).
