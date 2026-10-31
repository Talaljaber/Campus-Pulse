"use client";

import Link from "next/link";
import { useT, type DictKey } from "@/i18n";
import { cn } from "../ui/cn";

/** The pages a signed-in user moves between. `request` is the student's chat at `/`. */
export type NavPage = "request" | "staff" | "pulse" | "outbox" | "lab";

/** Props for {@link RoleNav}. */
export interface RoleNavProps {
  /** A student sees only the request page; staff the desk, the map and the outbox; an admin also the model lab. */
  role: "student" | "staff" | "admin";
  /** The page being shown, marked with `aria-current="page"`. */
  current: NavPage;
  className?: string;
}

const HREF: Record<NavPage, string> = { request: "/", staff: "/staff", pulse: "/pulse", outbox: "/outbox", lab: "/lab" };
const STUDENT_PAGES: readonly NavPage[] = ["request"];
const STAFF_PAGES: readonly NavPage[] = ["staff", "pulse", "outbox"];
const ADMIN_PAGES: readonly NavPage[] = ["lab", "staff", "pulse", "outbox"];

/**
 * The portal nav row: uppercase bold blue links separated by thin vertical bars, in the same order
 * on every page. It lists only what the role may open (the proxy would bounce a staff member from
 * `/lab` anyway), so nobody is offered a link that does not work. The current page has an underline
 * and a thick orange bar, so it is not marked by colour alone. Uppercase is CSS only: the accessible
 * names are unchanged.
 */
export function RoleNav({ role, current, className }: RoleNavProps) {
  const t = useT();
  const pages = role === "admin" ? ADMIN_PAGES : role === "staff" ? STAFF_PAGES : STUDENT_PAGES;
  return (
    <nav aria-label={t(role === "student" ? "nav.studentLabel" : "nav.label")} className={className}>
      <ul className="flex flex-wrap items-center">
        {pages.map((page) => (
          <li key={page} className="not-first:border-s not-first:border-[color-mix(in_srgb,var(--cp-accent)_45%,transparent)]">
            <Link
              href={HREF[page]}
              aria-current={page === current ? "page" : undefined}
              className={cn(
                "inline-flex min-h-12 items-center border-b-[3px] px-3.5 text-sm font-bold uppercase tracking-wide text-accent sm:px-5",
                "transition-colors duration-(--cp-motion-fast) hover:bg-surface-1",
                page === current
                  ? "border-orange underline decoration-2 underline-offset-8"
                  : "border-transparent hover:underline hover:underline-offset-8",
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
