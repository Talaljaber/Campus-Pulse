/** Ticket files (P9.10): shapes and the limits the server enforces (the browser checks them first for a quick message). */

/** One row of `ticket_files` as clients may read it (never the storage path). Also what `POST tickets/{id}/files` returns. */
export type FileRow = {
  id: string;
  ticket_id: string;
  activity_id?: string | null;
  uploader_role?: "student" | "staff" | "admin";
  visibility: "public" | "internal";
  mime: string;
  size_bytes: number;
  ext: string;
  created_at: string;
};

/** `GET files/{id}/link`. */
export type FileLink = { url: string; expires_in: number };

export const MAX_FILE_BYTES = 5 * 1024 * 1024;
export const MAX_FILES_PER_TICKET = 5;
export const MAX_BYTES_PER_TICKET = 15 * 1024 * 1024;

/** Extensions the server accepts (it decides by the bytes; this list only gives a fast message). */
export const ALLOWED_EXT = ["png", "jpg", "jpeg", "webp", "pdf", "docx", "xlsx", "pptx", "txt"] as const;
export const ACCEPT = ALLOWED_EXT.map((e) => `.${e}`).join(",");
