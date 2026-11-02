import type { DictKey } from "@/i18n";
import type { AnnouncementKind } from "@/lib/ai/types";

export const TITLE_MAX = 120;
export const BODY_MAX = 1000;
export const KINDS: readonly AnnouncementKind[] = ["info", "outage", "maintenance"];

/** The staff form's raw field values. `endsAt` is a `datetime-local` string (`YYYY-MM-DDTHH:mm`) or empty. */
export interface AnnouncementDraft {
  title: string;
  body: string;
  kind: AnnouncementKind;
  /** Office code, `""` for campus-wide (admin) or for "my office" (staff). */
  office: string;
  endsAt: string;
}

export type DraftField = "title" | "body" | "endsAt";
export type DraftErrors = Partial<Record<DraftField, DictKey>>;

/** Jordan has kept UTC+3 all year since 2022, so a typed local time is read as +03:00. */
export function ammanToIso(local: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local)) return null;
  const date = new Date(`${local}:00+03:00`);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/**
 * Checks the form the way the API will (title 1 to 120, body 1 to 1000 characters, end in the future),
 * so a mistake is shown at the field before any request. Returns no entries when the draft is fine.
 */
export function validateDraft(d: AnnouncementDraft, now: Date): DraftErrors {
  const errors: DraftErrors = {};
  const title = d.title.trim();
  const body = d.body.trim();
  if (title.length === 0) errors.title = "announcements.form.errTitleRequired";
  else if (title.length > TITLE_MAX) errors.title = "announcements.form.errTitleLong";
  if (body.length === 0) errors.body = "announcements.form.errBodyRequired";
  else if (body.length > BODY_MAX) errors.body = "announcements.form.errBodyLong";
  if (d.endsAt) {
    const iso = ammanToIso(d.endsAt);
    if (iso === null || new Date(iso).getTime() <= now.getTime()) errors.endsAt = "announcements.form.errEnds";
  }
  return errors;
}

export const EMPTY_DRAFT: AnnouncementDraft = { title: "", body: "", kind: "info", office: "", endsAt: "" };
