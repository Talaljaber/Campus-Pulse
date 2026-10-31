"use client";

import { useT } from "@/i18n";
import { durationParts } from "@/lib/time";

/**
 * Returns a formatter from milliseconds to a short translated span ("5 min", "3 h", "2 d"),
 * using the units of the explanation panel's "N s ago" so the whole UI agrees.
 */
export function useDuration(): (ms: number) => string {
  const t = useT();
  return (ms) => {
    const { unit, n } = durationParts(ms);
    return t(`explain.ago.${unit}`, { n });
  };
}
