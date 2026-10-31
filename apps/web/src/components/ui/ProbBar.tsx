import type { CSSProperties } from "react";
import { cn } from "./cn";
import { toneColor, type Tone } from "./tone";

/** Props for {@link ProbBar}. */
export interface ProbBarProps {
  /** Visible label and accessible name of the meter, e.g. "Category: IT Support". */
  label: string;
  /** A probability in [0, 1]. Values outside the range are clamped for display. */
  prob: number;
  /** Fill colour family. The percentage is always printed, so colour is never the only cue. */
  tone?: Tone;
  className?: string;
}

/**
 * Confidence meter: a label, the rounded percentage and a filled bar.
 * Uses `role="meter"` with `aria-valuenow` in percent (0 to 100).
 */
export function ProbBar({ label, prob, tone = "neutral", className }: ProbBarProps) {
  const pct = Math.round(Math.min(1, Math.max(0, Number.isFinite(prob) ? prob : 0)) * 100);
  return (
    <div className={cn("flex flex-col gap-1", className)} style={{ "--tone": toneColor(tone) } as CSSProperties}>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium text-fg-1">{label}</span>
        {/* Digits stay left-to-right even in an Arabic sentence, so "78%" never reads "%78". */}
        <span dir="ltr" className="tabular-nums text-fg-2">
          {pct}%
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-valuetext={`${pct}%`}
        className="h-2 overflow-hidden rounded-full bg-surface-2"
      >
        <div
          className="h-full rounded-full bg-(--tone) transition-[inline-size] duration-(--cp-motion-slow)"
          style={{ inlineSize: `${pct}%` }}
        />
      </div>
    </div>
  );
}
