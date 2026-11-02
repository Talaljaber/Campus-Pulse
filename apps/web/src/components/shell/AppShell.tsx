"use client";

import type { ReactNode } from "react";
import { useT } from "@/i18n";
import { homeFor, type Role } from "@/lib/auth/routing";
import { labelKeyOf, tilesFor, type PageId } from "@/lib/nav";
import { cn } from "../ui/cn";
import { Breadcrumb, type Crumb } from "./Breadcrumb";
import { SiteHeader } from "./SiteHeader";
import { TabBar } from "./TabBar";
import { TileRow, type TileSpec } from "./TileRow";

export type { Crumb, TileSpec };

/** Props for {@link AppShell}. */
export interface AppShellProps {
  /** The signed-in role, or null on the login page (no tabs, no tiles, no breadcrumb). */
  role: Role | null;
  /** The page being shown: marks the tab (or the outbox tile) as current. */
  current?: PageId;
  /** The name for "Hello <name>": the display name, falling back to the alias. */
  name?: string | null;
  /** The signed-in alias. Used as the name until profiles carry a display name. */
  alias?: string | null;
  /** Breadcrumb steps. Default: the role's home, then the current page. Pass `[]` for none. */
  crumbs?: Crumb[];
  /** Tile row under the tabs. Default: the role's shortcuts (none for students). Pass `[]` for none. */
  tiles?: TileSpec[];
  /** `narrow` and `default` use the 1000 px portal container; `wide` (the Pulse map) 1200 px. */
  width?: "narrow" | "default" | "wide";
  children: ReactNode;
}

const WIDTH = { narrow: "max-w-[1000px]", default: "max-w-[1000px]", wide: "max-w-[1200px]" } as const;

/**
 * Page chrome for every screen: the grey page with one centred white container holding the header
 * band, the tab bar, the tile row, the breadcrumb and `<main id="content">`. The dark footer with the
 * "Demo: simulated portal" line is rendered by the root layout, so it also covers pages that do not
 * use the shell.
 */
export function AppShell({ role, current, name, alias, crumbs, tiles, width = "default", children }: AppShellProps) {
  const t = useT();

  const tileList: TileSpec[] =
    tiles ??
    (role
      ? tilesFor(role).map((d) => ({ id: d.id, icon: d.icon, href: d.href, label: t(d.labelKey), selected: d.id === current }))
      : []);

  const trail: Crumb[] =
    crumbs ??
    (role
      ? current && current !== "home"
        ? [{ label: t("app.name"), href: homeFor(role) }, { label: t(labelKeyOf(current)) }]
        : [{ label: t("app.name") }]
      : []);

  return (
    <div className={cn("mx-auto my-0 flex w-full flex-1 flex-col bg-surface-0 shadow-container sm:my-6", WIDTH[width])}>
      <SiteHeader role={role} name={name ?? alias} />
      {role && <TabBar role={role} current={current} />}
      <TileRow tiles={tileList} label={t("shell.shortcuts")} />
      <Breadcrumb crumbs={trail} />
      <main id="content" tabIndex={-1} className="flex flex-col gap-4 p-4 outline-none sm:p-6">
        {children}
      </main>
    </div>
  );
}
