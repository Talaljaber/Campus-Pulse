"use client";

import Link from "next/link";
import { useT } from "@/i18n";
import type { Role } from "@/lib/auth/routing";
import { tabsFor, type PageId } from "@/lib/nav";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";

/** Props for {@link TabBar}. */
export interface TabBarProps {
  role: Role;
  /** The page being shown. The matching tab gets `aria-current="page"`; a page without a tab (the outbox) marks none. */
  current?: PageId;
  className?: string;
}

/** With more tabs than this, a phone shows the label of the current tab only (the others are icons). */
const MAX_LABELLED_ON_PHONE = 4;

/**
 * The portal's top-level tab row: plain links in a `<nav>`, in the same order on every page, listing
 * only what the role may open. It never scrolls: on a phone every tab shares the width equally (icon
 * above a small label), from `sm` up it is a row of text tabs. The active tab has blue text and a
 * 3 px brand-blue bar (not colour alone), and `aria-current="page"`. Focus uses the global ring.
 */
export function TabBar({ role, current, className }: TabBarProps) {
  const t = useT();
  const tabs = tabsFor(role);
  const labelAll = tabs.length <= MAX_LABELLED_ON_PHONE;
  return (
    <nav aria-label={t("nav.label")} className={cn("shrink-0 border-b border-line", className)}>
      <ul className="flex items-stretch sm:px-2">
        {tabs.map((tab) => {
          const active = tab.id === current;
          const showLabel = labelAll || active;
          return (
            <li key={tab.id} className={cn("min-w-0 sm:flex-none", active && !labelAll ? "flex-[2.4]" : "flex-1")}>
              <Link
                href={tab.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "-mb-px flex h-full min-h-12 min-w-0 flex-col items-center justify-center gap-0.5 border-b-[3px] px-1 text-[11px] font-bold leading-tight",
                  "sm:flex-row sm:gap-2 sm:px-4 sm:text-sm",
                  "transition-colors duration-(--cp-motion-fast) hover:bg-surface-1",
                  active ? "border-brand text-accent" : "border-transparent text-fg-2 hover:text-accent",
                )}
              >
                <Icon name={tab.icon} size={20} strokeWidth={1.8} className="shrink-0 sm:hidden" aria-hidden="true" />
                <span className={cn("max-w-full truncate whitespace-nowrap", !showLabel && "max-sm:sr-only")}>{t(tab.labelKey)}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
