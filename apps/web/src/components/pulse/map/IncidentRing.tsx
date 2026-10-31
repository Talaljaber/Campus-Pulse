"use client";

import { useSyncExternalStore } from "react";
import { labelOf, useLang, useT } from "@/i18n";
import { PRIORITY_TONE, toneColor } from "../../ui/tone";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined" || !window.matchMedia) return () => {};
  const mq = window.matchMedia(QUERY);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

function getSnapshot(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia && window.matchMedia(QUERY).matches;
}

/** `true` when the user asked the OS for reduced motion. Server render assumes `true` (static). */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, () => true);
}

/** Props for {@link IncidentRing}. */
export interface IncidentRingProps {
  x: number;
  y: number;
  /** `low`, `medium` or `high`. Picks the ring colour. */
  priority: string;
  /** Number of reports in the incident. A bigger incident gets a bigger ring and shows the count. */
  reportCount: number;
}

/**
 * A ring around an open incident. It pulses with a CSS animation (`cp-ring-pulse` in
 * `globals.css`) unless the user prefers reduced motion; the static ring and the count
 * are always drawn, so the incident is visible without any animation.
 */
export function IncidentRing({ x, y, priority, reportCount }: IncidentRingProps) {
  const t = useT();
  const { lang } = useLang();
  const reduced = usePrefersReducedMotion();
  const color = toneColor(PRIORITY_TONE[priority] ?? "neutral");
  const r = 18 + Math.min(Math.max(reportCount, 1), 10) * 2;
  // A second cue next to colour: a high incident has a heavy solid ring, a low one a thin dashed ring.
  const strokeWidth = priority === "high" ? 4.5 : priority === "low" ? 2.5 : 3.5;
  const dash = priority === "low" ? "7 5" : undefined;
  const label = t("map.ring", { count: reportCount, priority: labelOf("priority", priority, lang) });
  return (
    <g role="img" aria-label={label} data-animated={reduced ? "false" : "true"} data-priority={priority}>
      <title>{label}</title>
      {!reduced && (
        <circle className="cp-ring-pulse" cx={x} cy={y} r={r} fill="none" stroke={color} strokeWidth={strokeWidth} />
      )}
      <circle
        cx={x}
        cy={y}
        r={r}
        fill={`color-mix(in srgb, ${color} 14%, transparent)`}
        stroke={color}
        strokeWidth={strokeWidth}
        strokeDasharray={dash}
      />
      <text
        x={x}
        y={y}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={14}
        fontWeight={700}
        aria-hidden="true"
        className="fill-fg-1"
      >
        {reportCount}
      </text>
    </g>
  );
}
