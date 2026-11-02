"use client";

import Link from "next/link";
import { Fragment } from "react";
import { useT } from "@/i18n";
import { cn } from "../ui/cn";

/** One step of the trail. The last one is the current page and has no link. */
export interface Crumb {
  label: string;
  href?: string;
}

/** Props for {@link Breadcrumb}. */
export interface BreadcrumbProps {
  crumbs: Crumb[];
  className?: string;
}

/** Grey breadcrumb line: `<nav aria-label="Breadcrumb">` with an ordered list. The separator mirrors in RTL. */
export function Breadcrumb({ crumbs, className }: BreadcrumbProps) {
  const t = useT();
  if (crumbs.length === 0) return null;
  return (
    <nav aria-label={t("shell.breadcrumb")} className={cn("px-4 pt-3 text-sm text-fg-3", className)}>
      <ol className="flex flex-wrap items-center gap-x-1.5">
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1;
          return (
            <Fragment key={`${i}-${c.label}`}>
              <li>
                {c.href && !last ? (
                  <Link href={c.href} className="text-fg-3 underline-offset-2 hover:text-accent hover:underline">
                    {c.label}
                  </Link>
                ) : (
                  <span aria-current={last ? "page" : undefined} className={last ? "font-semibold text-fg-2" : undefined}>
                    {c.label}
                  </span>
                )}
              </li>
              {!last && (
                <li aria-hidden="true" className="inline-block rtl:-scale-x-100">
                  ›
                </li>
              )}
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
