import { ALLOWED_EXT, MAX_BYTES_PER_TICKET, MAX_FILE_BYTES, MAX_FILES_PER_TICKET, type FileRow } from "./types";

/** Why a file was refused before upload. Each maps to an `files.error.*` sentence. */
export type FileProblem = "type" | "size" | "empty" | "count" | "total";

export const extOf = (name: string): string => (name.includes(".") ? name.slice(name.lastIndexOf(".") + 1).toLowerCase() : "");

/**
 * Quick browser-side check of one more file against the ticket's current files and the files already
 * picked. The server repeats every check on the real bytes; this only saves a round trip.
 */
export function checkFile(file: File, existing: readonly Pick<FileRow, "size_bytes">[], picked: readonly File[]): FileProblem | null {
  if (!(ALLOWED_EXT as readonly string[]).includes(extOf(file.name))) return "type";
  if (file.size === 0) return "empty";
  if (file.size > MAX_FILE_BYTES) return "size";
  if (existing.length + picked.length >= MAX_FILES_PER_TICKET) return "count";
  const total = existing.reduce((n, f) => n + f.size_bytes, 0) + picked.reduce((n, f) => n + f.size, 0) + file.size;
  if (total > MAX_BYTES_PER_TICKET) return "total";
  return null;
}

/** What the server's message points to, so a refusal from it also shows a translated sentence. */
export function problemFromServer(message: string): FileProblem | null {
  const m = message.toLowerCase();
  if (m.includes("file type is not allowed") || m.includes("does not match its")) return "type";
  if (m.includes("larger")) return "size";
  if (m.includes("empty")) return "empty";
  if (m.includes("15 mb")) return "total";
  if (m.includes("at most 5 files")) return "count";
  return null;
}

export const kb = (bytes: number): string => (bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);
