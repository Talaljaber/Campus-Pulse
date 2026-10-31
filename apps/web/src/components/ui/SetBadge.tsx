"use client";

import { labelOf, useLang, useT } from "@/i18n";
import { Badge } from "./Badge";
import { cn } from "./cn";
import { CATEGORY_TONE, PRIORITY_TONE, type Tone } from "./tone";

/** Props for {@link SetBadge}. */
export interface SetBadgeProps {
  /** The conformal prediction set: every label the model could not rule out. */
  set: readonly string[];
  /** Whether `set` holds categories or priorities (picks the tones and the translated labels). */
  kind: "category" | "priority";
  /** The label that was chosen. It is left out of the list. */
  chosen: string;
  className?: string;
}

/**
 * "Could also be: IT Support". Renders nothing when the set holds only the chosen
 * label, so a confident result stays quiet.
 */
export function SetBadge({ set, kind, chosen, className }: SetBadgeProps) {
  const t = useT();
  const { lang } = useLang();
  const others = set.filter((v) => v !== chosen);
  if (others.length === 0) return null;
  const toneOf = (v: string): Tone => (kind === "category" ? CATEGORY_TONE[v] : PRIORITY_TONE[v]) ?? "neutral";
  return (
    <div
      role="group"
      aria-label={`${t("explain.set.couldAlsoBe")} (${t(kind === "category" ? "explain.set.category" : "explain.set.priority")})`}
      className={cn("flex flex-wrap items-center gap-2 text-sm text-fg-2", className)}
    >
      <span>{t("explain.set.couldAlsoBe")}:</span>
      <ul className="flex flex-wrap gap-1.5">
        {others.map((v) => (
          <li key={v}>
            <Badge tone={toneOf(v)}>{labelOf(kind, v, lang)}</Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}
