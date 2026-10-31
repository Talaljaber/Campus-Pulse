"use client";

import Link from "next/link";
import { useT, type DictKey } from "@/i18n";
import { cn } from "../ui/cn";

/** The pages a signed-in staff member or admin moves between. */
export type NavPage = "staff" | "pulse" | "outbox" | "lab";

/** Props for {@link RoleNav}. */
export interface RoleNavProps {
  /** Staff see the desk, the map and the outbox; an admin also sees the model lab. */
  role: "staff" | "admin";
  /** The page being shown, marked with `aria-current="page"`. */
  current: NavPage;
  className?: string;
}

const HREF: Record<NavPage, string> = { staff: "/staff", pulse: "/pulse", outbox: "/outbox", lab: "/lab" };
const STAFF_PAGES: readonly NavPage[] = ["staff", "pulse", "outbox"];
const ADMIN_PAGES: readonly NavPage[] = ["lab", "staff", "pulse", "outbox"];

/**
 * The links between the staff-side pages, in the same order on every page. It lists only what the
 * role may open (the proxy would bounce a staff member from `/lab` anyway), so nobody is offered
 * a link that does not work. The current page is marked in text weight and an underline, not colour.
 */
export function RoleNav({ role, current, className }: RoleNavProps) {
  const t = useT();
  const pages = role === "admin" ? ADMIN_PAGES : STAFF_PAGES;
  return (
    <nav aria-label={t("nav.label")} className={className}>
      <ul className="flex flex-wrap items-center gap-1">
        {pages.map((page) => (
          <li key={page}>
            <Link
              href={HREF[page]}
              aria-current={page === current ? "page" : undefined}
              className={cn(
                "inline-flex min-h-9 items-center rounded-md border-b-2 px-3 text-sm",
                page === current
                  ? "border-accent font-bold text-fg-1"
                  : "border-transparent font-medium text-accent underline hover:bg-surface-2",
              )}
            >
              {t(`nav.${page}` as DictKey)}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
