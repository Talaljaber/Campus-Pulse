import type { AiFail } from "@/lib/ai/result";
import { uploadFile } from "./service";
import type { FileRow } from "./types";

/** Files already uploaded for a message that has not been sent yet, so a retry does not upload them twice. */
export type UploadedCache = Map<File, { row: FileRow; internal: boolean }>;

/**
 * Uploads the picked files one by one (visibility follows the message: internal note = staff-only files)
 * and returns their ids and rows. Stops at the first failure and returns it; files uploaded before it stay
 * in `cache`, so sending again continues where it stopped.
 */
export async function uploadAll(ticketId: string, picked: readonly File[], internal: boolean, cache: UploadedCache): Promise<{ ok: true; rows: FileRow[] } | AiFail> {
  const rows: FileRow[] = [];
  for (const file of picked) {
    const hit = cache.get(file);
    if (hit && hit.internal === internal) {
      rows.push(hit.row);
      continue;
    }
    const res = await uploadFile(ticketId, file, internal);
    if (!res.ok) return res;
    cache.set(file, { row: res.data, internal });
    rows.push(res.data);
  }
  return { ok: true, rows };
}
