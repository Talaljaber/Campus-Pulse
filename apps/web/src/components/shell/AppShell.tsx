"use client";

import type { ReactNode } from "react";
import { useT } from "@/i18n";
import { homeFor, type Role } from "@/lib/auth/routing";
import { labelKeyOf, type PageId } from "@/lib/nav";
import { cn } from "../ui/cn";
import { Breadcrumb, type Crumb } from "./Breadcrumb";
import { SiteHeader } from "./SiteHeader";
import { TabBar } from "./TabBar";
import { TileRow, type TileSpec } from "./TileRow";

export type { Crumb, TileSpec };

/** Props for {@link AppShell}. */
export interface AppShellProps {
  /** The signed-in role, or null on the login page (no tabs, no breadcrumb). */
  role: Role | null;
  /** The page being shown: marks the tab as current. */
  current?: PageId;
  /** No longer shown (the greeting was removed from the header); accepted so callers need not change. */
  name?: string | null;
  /** No longer shown; see `name`. */
  alias?: string | null;
  /** Breadcrumb steps. Default: the role's home, then the current page, shown from `sm` up. Pass `[]` for none; custom steps show on phones too. */
  crumbs?: Crumb[];
  /** Optional tile row above the page. None by default. */
  tiles?: TileSpec[];
  /** `narrow` keeps reading content (forms, chat) to a readable column; the others use the full width. */
  width?: "narrow" | "default" | "wide";
  /** A bounded work area, such as chat, that owns the remaining viewport height and scrolls inside itself. */
  workspace?: boolean;
  children: ReactNode;
}

const NARROW = "max-w-[1080px]";

/**
 * Page chrome for every screen. The shell fills the whole viewport (width and height): the header and
 * the tab bar stay put and `<main id="content">` takes the rest, so the page itself never scrolls. The
 * content area scrolls only when its content is taller than the space left (or, for a `workspace`,
 * the work area scrolls inside itself).
 */
export function AppShell({ role, current, crumbs, tiles, width = "default", workspace = false, children }: AppShellProps) {
  const t = useT();

  const trail: Crumb[] =
    crumbs ??
    (role
      ? current && current !== "home"
        ? [{ label: t("app.name"), href: homeFor(role) }, { label: t(labelKeyOf(current)) }]
        : [{ label: t("app.name") }]
      : []);

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col bg-surface-0">
      <SiteHeader role={role} />
      {role && <TabBar role={role} current={current} />}
      <TileRow tiles={tiles ?? []} label={t("shell.shortcuts")} className="shrink-0 px-3 pt-3 sm:px-4 sm:pt-4" />
      <Breadcrumb crumbs={trail} className={cn("shrink-0", crumbs === undefined && "max-sm:hidden")} />
      <main
        id="content"
        tabIndex={-1}
        className={cn("flex min-h-0 flex-1 flex-col outline-none", workspace ? "overflow-hidden" : "overflow-y-auto overscroll-contain")}
      >
        <div
          className={cn(
            "mx-auto flex w-full flex-1 flex-col",
            workspace ? "min-h-0 p-2 sm:p-4" : "gap-3 p-3 sm:gap-4 sm:p-6",
            width === "narrow" && NARROW,
          )}
        >
          {children}
        </div>
      </main>
    </div>
  );
}
