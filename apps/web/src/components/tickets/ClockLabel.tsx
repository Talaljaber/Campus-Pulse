"use client";

import { useT } from "@/i18n";
import { formatDuration, timeLeft } from "@/lib/tickets/clock";

/** Props for {@link ClockLabel}. */
export interface ClockLabelProps {
  dueIso: string;
  status: string;
  /** Epoch ms, or null before hydration (shows a dash). */
  now: number | null;
}

/** Time left on a ticket as text: "1 h 05 min", "overdue by 20 min", or "Stopped" once the clock is not running. */
export function ClockLabel({ dueIso, status, now }: ClockLabelProps) {
  const t = useT();
  if (now === null) return <span>-</span>;
  const left = timeLeft(dueIso, status, now);
  if (left.state === "stopped") return <span className="text-fg-2">{t("ticketClock.stopped")}</span>;
  return <span>{formatDuration(left.ms, t)}</span>;
}
