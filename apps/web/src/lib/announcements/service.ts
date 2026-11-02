import { callAi } from "@/lib/ai/browser";
import type { AiFail, AiResult } from "@/lib/ai/result";
import type { AnnouncementKind, AnnouncementOut } from "@/lib/ai/types";

/** Why an announcement call failed, as the UI says it (dictionary key `announcements.error.<kind>`). */
export type AnnouncementErrorKind = "generic" | "waking" | "session" | "forbidden" | "notFound" | "invalid";

/** What the staff form sends. `office` null = campus-wide (admin only); staff leave it null and the server forces theirs. */
export interface NewAnnouncement {
  title: string;
  body: string;
  kind: AnnouncementKind;
  office: string | null;
  /** ISO timestamp with an offset, or null for "until archived". */
  endsAt: string | null;
}

/** `POST /v1/announcements`: staff post for their own office, an admin for any office or campus-wide. */
export function createAnnouncement(a: NewAnnouncement): Promise<AiResult<AnnouncementOut>> {
  return callAi<AnnouncementOut>("announcements", {
    method: "POST",
    body: { title: a.title.trim(), body: a.body.trim(), kind: a.kind, office: a.office, ends_at: a.endsAt },
  });
}

/** `POST /v1/announcements/{id}/archive`: take an announcement off Home. */
export function archiveAnnouncement(id: string): Promise<AiResult<AnnouncementOut>> {
  return callAi<AnnouncementOut>(`announcements/${encodeURIComponent(id)}/archive`, { method: "POST" });
}

/** Maps a failed call to a dictionary entry; the API's own prose is English and technical, so it is not shown. */
export function announcementErrorKind(fail: AiFail): AnnouncementErrorKind {
  if (fail.status === 401 || fail.code === "unauthenticated") return "session";
  if (fail.status === 403 || fail.code === "forbidden") return "forbidden";
  if (fail.status === 404 || fail.code === "not_found") return "notFound";
  if (fail.status === 422 || fail.code === "invalid_input") return "invalid";
  if (fail.waking) return "waking";
  return "generic";
}
