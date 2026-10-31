"use client";

import type { ReactNode } from "react";
import type { Role } from "@/lib/auth/routing";
import { cn } from "../ui/cn";
import type { NavPage } from "./RoleNav";
import { SiteHeader } from "./SiteHeader";

/** Props for {@link AppShell}. */
export interface AppShellProps {
  /** The signed-in role, or null on the login page. */
  role: Role | null;
  /** The page being shown, for the nav row. */
  current?: NavPage;
  /** The signed-in user's alias ("Hello <alias>"). */
  alias?: string | null;
  /** `narrow` for the chat and login, `default` for tables, `wide` for the Pulse map. */
  width?: "narrow" | "default" | "wide";
  children: ReactNode;
}

const WIDTH = { narrow: "max-w-3xl", default: "max-w-6xl", wide: "max-w-7xl" } as const;

/**
 * Page chrome for every screen: the portal header, then the content in a white card with a soft
 * outer shadow on the grey page. It renders the one `<main>` landmark (the skip link targets it).
 * The dark footer lives in the root layout so it also covers pages that do not use the shell.
 */
export function AppShell({ role, current, alias, width = "default", children }: AppShellProps) {
  return (
    <>
      <SiteHeader role={role} current={current} alias={alias} />
      <main id="main" tabIndex={-1} className={cn("mx-auto w-full flex-1 px-3 py-5 outline-none sm:px-4 sm:py-8", WIDTH[width])}>
        <div className="flex flex-col gap-4 rounded-xl border border-line bg-surface-0 p-4 shadow-card sm:p-6">{children}</div>
      </main>
    </>
  );
}
