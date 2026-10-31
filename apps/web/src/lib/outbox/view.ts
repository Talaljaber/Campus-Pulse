/**
 * Pure helpers for the outbox page: status tones, filters and the live merge. The statuses are the
 * database's (`outbox_status_check`, docs/db/schema.md): `queued`, `sent`, `failed`, `rejected`,
 * `simulated` and `deferred`. A status we do not know is shown as written with a neutral tone.
 */
import type { Tone } from "@/components/ui/tone";
import type { OutboxRow } from "@/lib/repos/outbox";

/** One row of the `outbox` table, as the page shows it. Components import this name, not the repo. */
export type OutboxMessage = OutboxRow;

/** Filter order on the page: what happened for real first, then the cases that need a look. */
export const OUTBOX_STATUSES = ["sent", "simulated", "deferred", "rejected", "failed", "queued"] as const;

/** How many rows the page keeps; older ones fall off as new ones arrive. */
export const OUTBOX_LIMIT = 200;

/** Badge tone per status. Text is always printed next to it, so the tone is a second cue only. */
export function outboxTone(status: string): Tone {
  switch (status) {
    case "sent":
      return "ok";
    case "simulated":
      return "info";
    case "deferred":
      return "warn";
    case "rejected":
    case "failed":
      return "danger";
    default:
      return "neutral";
  }
}

const time = (iso: string): number => {
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? 0 : ms;
};

/** Newest first. */
export function sortOutbox(rows: readonly OutboxRow[]): OutboxRow[] {
  return [...rows].sort((a, b) => time(b.created_at) - time(a.created_at));
}

/** Applies one live insert or update: the row replaces the one with its id, or joins the list. Capped at {@link OUTBOX_LIMIT}. */
export function mergeOutbox(rows: readonly OutboxRow[], incoming: OutboxRow): OutboxRow[] {
  const rest = rows.filter((r) => r.id !== incoming.id);
  return sortOutbox([incoming, ...rest]).slice(0, OUTBOX_LIMIT);
}

/** Rows per status, plus the total under `all`. */
export function statusCounts(rows: readonly OutboxRow[]): Record<string, number> {
  const out: Record<string, number> = { all: rows.length };
  for (const r of rows) out[r.status] = (out[r.status] ?? 0) + 1;
  return out;
}

/** The statuses to offer as filters: the known ones in order, then any other status that is present. */
export function filterStatuses(rows: readonly OutboxRow[]): string[] {
  const present = new Set(rows.map((r) => r.status));
  const extra = [...present].filter((s) => !(OUTBOX_STATUSES as readonly string[]).includes(s)).sort();
  return [...OUTBOX_STATUSES, ...extra];
}

/** Rows with the chosen status (`all` keeps every row). */
export function filterOutbox(rows: readonly OutboxRow[], status: string): OutboxRow[] {
  return status === "all" ? [...rows] : rows.filter((r) => r.status === status);
}
