"use client";

import { useT, type DictKey } from "@/i18n";
import type { TriageFlag } from "@/lib/ai/types";
import { Badge } from "../ui/Badge";
import { cn } from "../ui/cn";
import type { Tone } from "../ui/tone";

/** Who is looking at the result. Decides which flags are shown. */
export type Audience = "student" | "staff" | "admin";

/** Props for {@link FlagBadges}. */
export interface FlagBadgesProps {
  /** `result.flags`. */
  flags: readonly TriageFlag[];
  audience: Audience;
  className?: string;
}

/**
 * Flags the API documents as staff-only or admin-only (docs/api/README.md, "Flags").
 * The service already strips them from the student view; hiding them again here is
 * defence in depth, not the source of truth. `empty_input` is never returned by the API.
 */
const MIN_AUDIENCE: Partial<Record<TriageFlag, Audience>> = {
  urgency_unsupported: "staff",
  priority_gaming_suspected: "admin",
};
const NEVER: readonly TriageFlag[] = ["empty_input"];
const RANK: Record<Audience, number> = { student: 0, staff: 1, admin: 2 };

const TONE: Partial<Record<TriageFlag, Tone>> = {
  safety: "danger",
  distress: "danger",
  injection_attempt: "warn",
  needs_review: "info",
  staff_confirmed: "ok",
};

/** Whether `flag` may be shown to `audience`. Exported for tests and for pages that filter lists. */
export function isFlagVisible(flag: TriageFlag, audience: Audience): boolean {
  if (NEVER.includes(flag)) return false;
  return RANK[audience] >= RANK[MIN_AUDIENCE[flag] ?? "student"];
}

/** A row of badges for the flags the audience may see. Renders nothing when none apply. */
export function FlagBadges({ flags, audience, className }: FlagBadgesProps) {
  const t = useT();
  const visible = flags.filter((f) => isFlagVisible(f, audience));
  if (visible.length === 0) return null;
  return (
    <ul aria-label={t("flags.label")} className={cn("flex flex-wrap gap-2", className)}>
      {visible.map((f) => (
        <li key={f} data-flag={f}>
          <Badge tone={TONE[f] ?? "neutral"}>{t(`flags.${f}` satisfies DictKey)}</Badge>
        </li>
      ))}
    </ul>
  );
}
