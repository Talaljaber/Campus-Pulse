import type { Sb } from "../supabase/types";
import type { FileRow } from "../files/types";
import { unwrap } from "./realtime";

/** Only the granted columns (migration 0015 never lets a client read the storage path). */
const FILE_COLUMNS = "id, ticket_id, activity_id, uploader_role, visibility, mime, size_bytes, ext, created_at";

/** The files of a ticket the caller may see (RLS: the requester gets public ones only), oldest first. */
export async function listFiles(sb: Sb, ticketId: string): Promise<FileRow[]> {
  // `ticket_files` is not in the generated database types until the migration is applied and they are regenerated.
  const db = sb as unknown as {
    from(t: string): { select(c: string): { eq(c: string, v: string): { order(c: string, o: { ascending: boolean }): PromiseLike<{ data: FileRow[] | null; error: { message: string } | null }> } } };
  };
  return unwrap(await db.from("ticket_files").select(FILE_COLUMNS).eq("ticket_id", ticketId).order("created_at", { ascending: true }));
}

/** Like {@link listFiles} but never throws: a ticket page must still open if files cannot be read (e.g. migration not applied). */
export async function listFilesSafe(sb: Sb, ticketId: string): Promise<FileRow[]> {
  try {
    return await listFiles(sb, ticketId);
  } catch {
    return [];
  }
}
