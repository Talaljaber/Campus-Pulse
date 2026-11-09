import { callAi } from "@/lib/ai/browser";
import type { AiResult } from "@/lib/ai/result";
import type { components } from "@/lib/ai/types.gen";

/** A suggested announcement the backend drafted from an incident (generated API type). */
export type AnnouncementDraft = components["schemas"]["AnnouncementDraftOut"];

export const DRAFT_TITLE_MAX = 120;
export const DRAFT_BODY_MAX = 1000;

const base = (id: string) => `announcement-drafts/${encodeURIComponent(id)}`;

/** `GET /v1/announcement-drafts`: the caller's office (all offices for an admin). May include non-pending ones. */
export function listDrafts(): Promise<AiResult<AnnouncementDraft[]>> {
  return callAi<AnnouncementDraft[]>("announcement-drafts");
}

/** `PATCH /v1/announcement-drafts/{id}`: edit title and text. A 409 means the version is stale. */
export function editDraft(id: string, version: number, title: string, body: string): Promise<AiResult<AnnouncementDraft>> {
  return callAi<AnnouncementDraft>(base(id), { method: "PATCH", body: { version, title: title.trim(), body: body.trim() } });
}

/** `POST /v1/announcement-drafts/{id}/publish`: it becomes a normal announcement. */
export function publishDraft(id: string, version: number): Promise<AiResult<AnnouncementDraft>> {
  return callAi<AnnouncementDraft>(`${base(id)}/publish`, { method: "POST", body: { version } });
}

/** `POST /v1/announcement-drafts/{id}/dismiss`. */
export function dismissDraft(id: string, version: number): Promise<AiResult<AnnouncementDraft>> {
  return callAi<AnnouncementDraft>(`${base(id)}/dismiss`, { method: "POST", body: { version } });
}
