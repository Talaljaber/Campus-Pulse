"use client";

import { useT } from "@/i18n";
import { cn } from "../ui/cn";
import { CampusPulseMark } from "./CampusPulseMark";

/** Props for {@link Brand}. */
export interface BrandProps {
  /** Hide the "for students" subtitle (used where space is tight). */
  compact?: boolean;
  className?: string;
}

/**
 * Mark, wordmark and subtitle. The wordmark "CampusPulse" is the product name in Latin letters in
 * every language (`lang="en"`, `dir="ltr"`); only the subtitle is translated. "for students"
 * says who it serves; it does not claim to be a university system (the footer says so in words).
 */
export function Brand({ compact = false, className }: BrandProps) {
  const t = useT();
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <CampusPulseMark size={compact ? 36 : 44} className="shrink-0" />
      <span className="flex min-w-0 flex-col leading-tight">
        <span lang="en" dir="ltr" className="text-start text-[1.35rem] font-extrabold tracking-tight">
          <span className="text-accent">Campus</span>
          <span className="text-orange-ink">Pulse</span>
        </span>
        {!compact && <span className="text-xs font-medium text-fg-2">{t("shell.subtitle")}</span>}
      </span>
    </span>
  );
}
