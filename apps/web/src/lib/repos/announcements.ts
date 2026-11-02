import type { Sb, Tables } from "../supabase/types";
import { subscribeTable, unwrap } from "./realtime";

export type AnnouncementRow = Tables<"announcements">;

/** How many announcements Home shows at most. */
export const LIVE_ANNOUNCEMENT_LIMIT = 20;

/**
 * The announcements a student sees on Home: not archived, already started, not yet ended, newest
 * first. Read under RLS (`announcements_read`), so nothing here is access control.
 */
export async function listLiveAnnouncements(sb: Sb, now: Date): Promise<AnnouncementRow[]> {
  const iso = now.toISOString();
  return unwrap(
    await sb
      .from("announcements")
      .select("*")
      .is("archived_at", null)
      .lte("starts_at", iso)
      .or(`ends_at.is.null,ends_at.gt.${iso}`)
      .order("starts_at", { ascending: false })
      .limit(LIVE_ANNOUNCEMENT_LIMIT),
  );
}

/**
 * Every announcement staff may manage, archived ones included (RLS lets staff and admin read
 * archived rows). With an office the list is that office's only; with `null` (an admin) it is all of
 * them, campus-wide notices included. Newest first.
 */
export async function listOfficeAnnouncements(sb: Sb, office: string | null): Promise<AnnouncementRow[]> {
  const query = sb.from("announcements").select("*");
  const scoped = office === null ? query : query.eq("office", office);
  return unwrap(await scoped.order("starts_at", { ascending: false }));
}

/** Announcement inserts and updates (a new notice, an archive). Returns an unsubscribe function. */
export function subscribeAnnouncements(sb: Sb, onChange: (a: AnnouncementRow) => void): () => void {
  return subscribeTable<AnnouncementRow>(sb, "announcements", (c) => onChange(c.row));
}
