import type { Sb } from "../supabase/types";

/** Reporting windows the admin can pick, in days. */
export const PERIODS = [7, 30, 90] as const;
export type Period = (typeof PERIODS)[number];
export const DEFAULT_PERIOD: Period = 30;

/** `?days=` to a supported period; anything else falls back to 30. */
export function periodOf(raw: string | string[] | undefined): Period {
  const n = Number(Array.isArray(raw) ? raw[0] : raw);
  return (PERIODS as readonly number[]).includes(n) ? (n as Period) : DEFAULT_PERIOD;
}

export interface OfficeStats {
  office: string;
  open: number;
  overdue: number;
  high_open: number;
  received: number;
  resolved: number;
  median_hours: number | null;
  sla_met_pct: number | null;
}

export interface DayCount {
  day: string;
  requests: number;
  high: number;
}

/** What `cp_admin_overview(p_days)` returns (supabase/migrations/0019_admin_overview.sql). */
export interface Overview {
  days: number;
  generated_at: string;
  requests: {
    total: number;
    by_lang: { en: number; ar: number; arabizi: number };
    voice: number;
    distress: number;
    out_of_scope: number;
    students: number;
  };
  tickets: {
    open: number;
    overdue: number;
    high_open: number;
    received: number;
    resolved: number;
    median_hours: number | null;
    sla_met_pct: number | null;
  };
  offices: OfficeStats[];
  daily: DayCount[];
  ai: {
    classified: number;
    automatic: number;
    to_human: number;
    asked_question: number;
    reviews: number;
    reviews_open: number;
    corrected: number;
    confirmed: number;
  };
  incidents: { open: number; opened: number };
  delivery: { sent: number; failed: number; rejected: number; queued: number; sync_errors: number; synced: number };
  people: { students: number; staff: number; admins: number };
}

/** The admin overview for the last `days` days. The database refuses anyone who is not an admin. */
export async function fetchOverview(sb: Sb, days: Period): Promise<Overview> {
  const { data, error } = await sb.rpc("cp_admin_overview", { p_days: days });
  if (error) throw new Error(error.message);
  return data as unknown as Overview;
}

/** Whole-number percentage of `part` in `whole`, or null when there is nothing to divide. */
export function share(part: number, whole: number): number | null {
  return whole > 0 ? Math.round((100 * part) / whole) : null;
}

/** Hours as a short duration: minutes under an hour, hours under two days, else days. */
export function duration(hours: number | null): { unit: "min" | "h" | "d"; value: number } | null {
  if (hours === null || !Number.isFinite(hours)) return null;
  if (hours < 1) return { unit: "min", value: Math.max(1, Math.round(hours * 60)) };
  if (hours < 48) return { unit: "h", value: Math.round(hours * 10) / 10 };
  return { unit: "d", value: Math.round((hours / 24) * 10) / 10 };
}

/** Money with cents, or four decimals under a cent so a quiet day does not read as zero. */
export function usd(value: number | null): string | null {
  if (value === null) return null;
  return value > 0 && value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`;
}

/** Whole days from now until `iso` (negative once passed), or null. */
export function daysUntil(iso: string | null, now: Date = new Date()): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : Math.floor((t - now.getTime()) / 86_400_000);
}

/** What `GET /v1/admin/usage` returns (services/ai: LlmUsageResponse). */
export interface LlmUsage {
  available: boolean;
  provider: string;
  spent_today_usd: number | null;
  spent_week_usd: number | null;
  spent_month_usd: number | null;
  spent_total_usd: number | null;
  limit_usd: number | null;
  limit_remaining_usd: number | null;
  limit_reset: string | null;
  key_expires_at: string | null;
  models: string[];
  checked_at: string;
}

export type AlertKind =
  | "overdue"
  | "highOpen"
  | "deliveryFailed"
  | "syncErrors"
  | "reviewsOpen"
  | "keyExpiring"
  | "keyExpired"
  | "spendNearLimit";

export interface Alert {
  kind: AlertKind;
  count: number;
  href?: string;
}

/** Things that need an administrator's attention now, most serious first. Empty when all is well. */
export function alertsOf(o: Overview, usage: LlmUsage | null, now: Date = new Date()): Alert[] {
  const out: Alert[] = [];
  const expires = usage?.available ? daysUntil(usage.key_expires_at, now) : null;
  if (expires !== null && expires < 0) out.push({ kind: "keyExpired", count: 0 });
  if (o.tickets.high_open > 0) out.push({ kind: "highOpen", count: o.tickets.high_open, href: "/staff" });
  if (o.tickets.overdue > 0) out.push({ kind: "overdue", count: o.tickets.overdue, href: "/staff" });
  if (o.delivery.failed > 0) out.push({ kind: "deliveryFailed", count: o.delivery.failed, href: "/outbox" });
  if (o.delivery.sync_errors > 0) out.push({ kind: "syncErrors", count: o.delivery.sync_errors });
  if (usage?.available && usage.limit_usd && usage.limit_remaining_usd !== null) {
    if (usage.limit_remaining_usd < usage.limit_usd * 0.2) {
      out.push({ kind: "spendNearLimit", count: share(usage.limit_usd - usage.limit_remaining_usd, usage.limit_usd) ?? 0 });
    }
  }
  if (expires !== null && expires >= 0 && expires <= 14) out.push({ kind: "keyExpiring", count: expires });
  if (o.ai.reviews_open > 0) out.push({ kind: "reviewsOpen", count: o.ai.reviews_open, href: "/staff/reviews" });
  return out;
}
