/** The SLA clock of a ticket, as the UI shows it. Pure: no React, no timers. */
import type { DictKey } from "@/i18n";

export type ClockState = "running" | "overdue" | "stopped";

export interface TimeLeft {
  state: ClockState;
  /** Milliseconds until the deadline; negative once overdue; 0 for a stopped clock. */
  ms: number;
}

/** The clock runs while a ticket is `new` or `in_progress`. `solved`, `closed` and `merged` stop it. */
export function isRunning(status: string): boolean {
  return status === "new" || status === "in_progress";
}

/**
 * Time left on a ticket. Exactly at the deadline it is still running with 0 ms left; it is overdue
 * only after it (`now > due`). A stopped clock reports `stopped` whatever the deadline says.
 */
export function timeLeft(dueIso: string, status: string, nowMs: number): TimeLeft {
  const due = new Date(dueIso).getTime();
  if (!isRunning(status) || Number.isNaN(due)) return { state: "stopped", ms: 0 };
  const ms = due - nowMs;
  return { state: ms < 0 ? "overdue" : "running", ms };
}

type Translate = (key: DictKey, vars?: Record<string, string | number>) => string;

/** A span as "5 min", "1 h 05 min" or "2 d 3 h" (sign ignored, minutes rounded up so it never reads "0 min"). */
export function formatSpan(ms: number, t: Translate): string {
  const totalMin = Math.max(1, Math.ceil(Math.abs(ms) / 60_000));
  if (totalMin < 60) return t("ticketClock.min", { m: totalMin });
  const hours = Math.floor(totalMin / 60);
  if (hours < 24) return t("ticketClock.hmin", { h: hours, mm: String(totalMin % 60).padStart(2, "0") });
  return t("ticketClock.dh", { d: Math.floor(hours / 24), h: hours % 24 });
}

/** "1 h 05 min" while time is left, "overdue by 20 min" afterwards. */
export function formatDuration(ms: number, t: Translate): string {
  const span = formatSpan(ms, t);
  return ms < 0 ? t("ticketClock.overdueBy", { span }) : span;
}
