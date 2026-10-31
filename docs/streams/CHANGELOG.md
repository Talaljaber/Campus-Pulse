# Stream changelog: append-only, one entry per finished task, newest last; never edit earlier entries.

### P0.2 — Python package skeleton with exact pins  (foundation, 2026-10-31, commit pending)
- **What now exists:** the installable `campuspulse_ai` package (`services/ai/`, version `0.1.0`) with an empty `__init__.py` in every directory of the ARCHITECTURE §1.2 tree, the four exact-pinned requirement sets, the root ruff config (with the random-split ban) and `tests/{unit,contracts,invariants,e2e,fixtures}/` packages.
- **Public interfaces added or changed:** `campuspulse_ai.__version__`; `services/ai/requirements{,-api,-dev,-train}.txt` (see [docs/ops/README.md](../ops/README.md#local-python-setup)); pytest markers `slow`, `network`, `e2e`.
- **How to use it:** `python -m venv .venv && .venv/Scripts/python -m pip install -r services/ai/requirements-dev.txt -e services/ai`
- **Config / env added:** none.
- **Acceptance:** pip install exit 0; `pip check` -> `No broken requirements found.`; version -> `0.1.0`; `pytest ...test_requirements_pinned.py -q` -> `1 passed`; `inference set clean`. `ruff check .` -> `All checks passed!` after the lead review.
- **Limitations / TODO / known issues:** Lead review: the legacy data scripts are excluded from ruff (`extend-exclude`), and the pytest markers were set to the plan conventions (`train`, `artifacts`, `supabase`, `slow`, `offline`, with `--strict-markers`). `requirements-train.txt` was not installed here (ML stream does that).
- **Affects streams:** all (dev install and lint/test commands); ML (train set, ruff findings in `scripts/`).

### P0.4 — Domain layer: labels, values, entities, errors, ports  (Lead, 2026-10-31)
- **What now exists:** `services/ai/campuspulse_ai/domain/` — the frozen contract every stream codes against. Stdlib only, `mypy --strict` clean.
- **Public interfaces added:** see `domain/ports.py` (`ALL_PORTS` lists all 29 ports: the ARCHITECTURE §1.4 set plus `RequestUnderstander` (UD-10) and `ProblemClusterer` (UD-6)). Labels: `Category`, `Priority` (StrEnum; `str(x) == x.value`), `CATEGORY_ORDER`/`PRIORITY_ORDER` (fixed prob-vector column order), `CATEGORY_LABELS`/`PRIORITY_LABELS`.
- **Types the brief only named, now fixed (values.py unless noted):** `ProbabilityTarget`, `MetaValue`, `ActionType` (faq_answer, ticket, booking, safety_alert, incident_merge), `RequestStatus`/`TicketStatus` (moved to values.py; entities import them), `ClarificationBudget(max_questions, asked).remaining`, `ClarificationOption(id, text, constraint)`, `ClarificationQuestion(id, target, text, lang, options, expected_info_gain)`, `MemoryStats`, `ActionPlan(kind, office, sla_hours, tags, also_ticket)`, `FAQHit`, `TicketLink(ticket_id, sink, external_id, url)`, `InboundEvent(sink, external_id, status, occurred_at, payload)`, `OfficeHours(tz, weekdays, start, end)`, `Slot`, `Booking`, `Advisor`, `RouterStats`, `StudentSignals`, `Counterfactual(drop, category, priority)`, `Entities`, `Understanding` (UD-10), `ProblemCluster` (UD-6). In entities.py: `IncidentDecision`, `OracleAnswer`, `OracleContext(lang, neighbors, prompt_version)`, `Case`, `Explanation`; `Ticket` gained `title`/`body` (filled from `Understanding`); `OutboxMessage` gained optional `priority`/`flags` (LD-25) and `kind` includes `"whatsapp"` (future).
- **Flags:** `values.FLAGS` = ARCHITECTURE §5 list + `understanding_fallback` (UD-10) + debug-only `empty_input`.
- **Implemented now:** `ProbVector` (validated; `argmax` ties → label order; `top`, `as_dict`, `prob`), `PredictionSet`, `Manifest.sha`, `Priority.rank/bump`, `policy.RecipientPolicy` (empty allow-list rejects all; case/space-insensitive).
- **How to use:** `from campuspulse_ai.domain.ports import TicketSink` — implement the Protocol structurally; no inheritance needed. Raise only `domain/errors.py` exceptions (`SinkError(msg, retryable=...)`).
- **Acceptance:** `pytest services/ai/tests/unit/test_domain_values.py -q` → `7 passed`; `mypy --strict services/ai/campuspulse_ai/domain` → `Success: no issues found in 9 source files`; `ruff check .` → `All checks passed!`.
- **Limitations:** `policy.DefaultDecisionPolicy` (P3.1), `priority_rules.EVIDENCE_FEATURES` (P1.12), `routing` planner (P3.8/P4.8) are docstring placeholders. **Domain changes go through the lead only** (EXECUTION rule 3).
- **Affects streams:** all.

### P0.8 — Scaffold the Next.js app (`apps/web`)  (ui, 2026-10-31, commit see git log)
- **What now exists:** strict-TypeScript Next 16.4.2 app (Tailwind 4 CSS-first, ESLint 10 flat config, vitest 4 + Testing Library + jsdom) with a placeholder `/` and a dev-only `/dev/ui` (`notFound()` in production). Every dependency is an exact pin from Appendix A.
- **Public interfaces added or changed:** scripts `dev`, `build`, `typecheck`, `lint`, `test` in `apps/web/package.json`; root `pnpm-workspace.yaml` (so `pnpm --filter web <script>` works); `netlify.toml` (`base = apps/web`, `pnpm run build`, `NODE_VERSION=22`).
- **How to use it:** `pnpm install` (repo root), then `pnpm --filter web dev`.
- **Config / env added:** none.
- **Acceptance:** `pnpm --filter web typecheck` and `lint` exit 0; `build` prints `Compiled successfully` and lists `/dev/ui`; pin check prints `pinned`.
- **Limitations / TODO / known issues:** the plan says npm + `package-lock.json`; the lead's instruction (pnpm 10.17.0, `pnpm-lock.yaml`) was followed, so the Foundation CI job (P0.9) must use pnpm, not `npm ci`. ESLint 10 has unmet-peer warnings from eslint-config-next plugins (lint still passes). Extra devDeps beyond Appendix A: `@types/*`, `@testing-library/{dom,user-event,jest-dom}`, `@vitejs/plugin-react`.
- **Affects streams:** Foundation (CI must use pnpm; Netlify build command).

### P5.1 — Design tokens, Tailwind v4 theme and fonts  (ui, 2026-10-31, commit see git log)
- **What now exists:** `apps/web/src/design/tokens.css` with the `--cp-*` variables (surfaces, text, 6 category and 3 priority colours, semantic colours, spacing, radius, type scale, shadow, motion) in light, `prefers-color-scheme: dark` and forced `[data-theme]` variants, mapped into Tailwind 4 through `@theme inline` (no `tailwind.config.ts`). Inter and IBM Plex Sans Arabic load via `next/font/google`. An ESLint rule bans physical `ml-/mr-/pl-/pr-/left-/right-/text-left/text-right` in `src/components/**` and `src/app/**`, and another bans data-layer imports in components.
- **Public interfaces added or changed:** CSS variables (see [docs/ui/README.md](../ui/README.md#design-tokens)); Tailwind colour utilities `bg-surface-0|1|2`, `text-fg-1|2|3`, `border-line`, `bg-cat-*`, `bg-pri-*`, `text-ok|warn|danger|info`, `bg-accent`.
- **How to use it:** `<div className="bg-surface-1 text-fg-2 ps-4 rounded-md">`.
- **Config / env added:** none.
- **Acceptance:** `vitest run src/design` -> `11 passed` (WCAG contrast for both themes); lint 0 errors; typecheck and build pass.
- **Limitations / TODO / known issues:** dark-mode polish is P5.17 (cut-flagged); category colours were chosen for colour-blind separation but are always paired with a text label.
- **Affects streams:** none outside UI.

### P5.2 — i18n dictionaries, `useT()`, RtlProvider and the language switch  (ui, 2026-10-31, commit see git log)
- **What now exists:** in-repo EN/AR dictionaries (`src/i18n/{en,ar}.ts`; `ar: Dict` makes a missing key a type error), `useT()`, `useLang()`, `labelOf()`, `resolveLang()`, `RtlProvider` (sets `<html lang dir>`, cookie `cp_lang`), `LangScope` (fixed-language subtree for side-by-side demos) and `LanguageSwitch`. The root layout resolves the language server-side (cookie, then `Accept-Language`, then `en`), so the first paint already has the right direction.
- **Public interfaces added or changed:** `useT(): (key: DictKey, vars?) => string`, `labelOf(kind, value, lang)`, `RtlProvider({ lang })`, `LanguageSwitch()`; see [docs/ui/README.md](../ui/README.md#i18n).
- **How to use it:** `const t = useT(); t("common.close")`; `labelOf("category", "IT Support", lang)`.
- **Config / env added:** cookie `cp_lang` (`en` | `ar`).
- **Acceptance:** `vitest run src/i18n src/components` -> `10 passed`; typecheck and lint exit 0.
- **Limitations / TODO / known issues:** the root layout reads cookies and headers, so every page renders dynamically. Chat, staff, pulse and lab strings are added by the tasks that build those pages. vitest is configured with `pool: "threads"` because forked workers timed out on this Windows machine.
- **Affects streams:** none outside UI.

### P5.3 — UI primitives and the `/dev/ui` kitchen sink  (ui, 2026-10-31, commit see git log)
- **What now exists:** `Button, Chip/ChipGroup, Badge, Card, Tabs/TabPanel, Table, ToastProvider/useToast, Dialog, Skeleton, EmptyState, Icon, ThemeSwitch, LanguageSwitch` in `src/components/ui` (exported from `index.ts`), each with a props type and TSDoc, keyboard support (arrows mirrored in RTL) and focus states. `/dev/ui` shows every primitive in English and Arabic side by side with a theme switch. A minimal `playwright.config.ts` and `e2e/devui.spec.ts` exist (P5.13 will extend the config).
- **Public interfaces added or changed:** see the catalog in [docs/ui/README.md](../ui/README.md#component-catalog-srccomponentsui-all-in-indexts). Tones are `cat-*`, `pri-*`, `ok|warn|danger|info|neutral` (`CATEGORY_TONE` / `PRIORITY_TONE` map exact backend labels).
- **How to use it:** `import { Button, Badge, CATEGORY_TONE } from "@/components/ui"`; `<Badge tone={CATEGORY_TONE["IT Support"]}>...</Badge>`.
- **Config / env added:** none.
- **Acceptance:** `vitest run` -> `4 files, 38 tests passed` (`src/components/ui`: 18, `src/i18n`+`src/design`: 20); `playwright test e2e/devui.spec.ts` -> `1 passed` (every Tab stop reachable, no horizontal overflow at 390px, theme forcing); typecheck, lint, build exit 0.
- **Limitations / TODO / known issues:** `ProbBar` and `SetBadge` (named in ARCHITECTURE 1.7) are P5.4. `ThemeSwitch` applies the saved theme after hydration (brief flash possible for a saved dark choice; an inline pre-paint script is a P5.17 polish item). `Dialog` is hand-rolled (not native `<dialog>`) because jsdom lacks `showModal`.
- **Affects streams:** none outside UI.
