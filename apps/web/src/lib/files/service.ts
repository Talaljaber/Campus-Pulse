import { callAi } from "@/lib/ai/browser";
import type { AiResult } from "@/lib/ai/result";
import type { FileLink, FileRow } from "./types";

/** `POST /v1/tickets/{id}/files` (multipart). The file's own name is sent only for the server's claim check; it is never stored. */
export function uploadFile(ticketId: string, file: File, internal: boolean): Promise<AiResult<FileRow>> {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("internal", internal ? "true" : "false");
  return callAi<FileRow>(`tickets/${encodeURIComponent(ticketId)}/files`, { method: "POST", body: form });
}

/** `GET /v1/files/{id}/link`: a link that works for 60 seconds. */
export function fileLink(fileId: string): Promise<AiResult<FileLink>> {
  return callAi<FileLink>(`files/${encodeURIComponent(fileId)}/link`);
}

/**
 * Opens a signed link in a new tab without giving the new page our window (`noopener noreferrer`).
 * A synthetic anchor click keeps the browser's user-gesture allowance after the `await`.
 */
export function openInNewTab(url: string): void {
  const a = document.createElement("a");
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** Asks for a signed link and opens it in a new tab; returns the result so the caller can show an error. */
export async function openFile(fileId: string): Promise<AiResult<FileLink>> {
  const res = await fileLink(fileId);
  if (res.ok) openInNewTab(res.data.url);
  return res;
}
