import type { DictKey } from "@/i18n";
import type { AnnouncementKind, AnnouncementOut } from "@/lib/ai/types";
import type { AnnouncementRow } from "@/lib/repos/announcements";

export type { AnnouncementRow };

/** Dictionary key of a kind's label (Outage, Maintenance, Info). An unknown kind reads as Info. */
export function kindKey(kind: string): DictKey {
  return kind === "outage" || kind === "maintenance" ? `announcements.kind.${kind}` : "announcements.kind.info";
}

/** Badge tone of a kind: outages are urgent, maintenance a warning, info neutral. */
export function kindTone(kind: AnnouncementKind | string): "danger" | "warn" | "info" {
  return kind === "outage" ? "danger" : kind === "maintenance" ? "warn" : "info";
}

/** Is the row visible on Home at `now`? Mirrors the SQL and the repo filter (archive, start, end). */
export function isLive(a: Pick<AnnouncementRow, "archived_at" | "starts_at" | "ends_at">, now: Date): boolean {
  if (a.archived_at !== null) return false;
  if (new Date(a.starts_at).getTime() > now.getTime()) return false;
  return a.ends_at === null || new Date(a.ends_at).getTime() > now.getTime();
}

/** Newest `starts_at` first. */
export function sortNewest<T extends Pick<AnnouncementRow, "starts_at">>(rows: readonly T[]): T[] {
  return [...rows].sort((a, b) => new Date(b.starts_at).getTime() - new Date(a.starts_at).getTime());
}

/**
 * Folds one Realtime change into the list: a live row is added or replaced by id, an archived, ended or
 * not-yet-started row is removed. Keeps the order and the Home limit.
 */
export function applyChange(rows: readonly AnnouncementRow[], change: AnnouncementRow, now: Date, limit = 20): AnnouncementRow[] {
  const rest = rows.filter((r) => r.id !== change.id);
  return sortNewest(isLive(change, now) ? [...rest, change] : rest).slice(0, limit);
}

/** First word of a name, for "Hello Lina". Falls back to the whole (trimmed) string. */
export function firstName(name: string | null): string {
  const clean = (name ?? "").trim();
  return clean.split(/\s+/)[0] ?? clean;
}

/** The table row for an API answer, so a post or an archive shows at once, before Realtime delivers the same row. */
export function rowOf(a: AnnouncementOut): AnnouncementRow {
  return { ...a, created_at: a.created_at ?? a.starts_at };
}
