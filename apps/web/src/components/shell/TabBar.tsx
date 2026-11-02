"use client";

import Link from "next/link";
import { useT } from "@/i18n";
import type { Role } from "@/lib/auth/routing";
import { tabsFor, type PageId } from "@/lib/nav";
import { cn } from "../ui/cn";

/** Props for {@link TabBar}. */
export interface TabBarProps {
  role: Role;
  /** The page being shown. The matching tab gets `aria-current="page"`; a page without a tab (the outbox) marks none. */
  current?: PageId;
  className?: string;
}

/**
 * The portal's top-level tab row: plain links in a `<nav>`, in the same order on every page, listing
 * only what the role may open. The active tab has blue text and a 3 px brand-blue bar (not colour
 * alone), and `aria-current="page"`. Focus uses the global visible focus ring.
 */
export function TabBar({ role, current, className }: TabBarProps) {
  const t = useT();
  return (
    <nav aria-label={t("nav.label")} className={cn("border-b border-line", className)}>
      <ul className="flex flex-wrap items-stretch px-2">
        {tabsFor(role).map((tab) => {
          const active = tab.id === current;
          return (
            <li key={tab.id}>
              <Link
                href={tab.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "-mb-px inline-flex min-h-12 items-center border-b-[3px] px-4 text-sm font-bold",
                  "transition-colors duration-(--cp-motion-fast) hover:bg-surface-1",
                  active ? "border-brand text-accent" : "border-transparent text-fg-2 hover:text-accent",
                )}
              >
                {t(tab.labelKey)}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
