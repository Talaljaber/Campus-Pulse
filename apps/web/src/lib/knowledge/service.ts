import { callAi } from "@/lib/ai/browser";
import type { AiResult } from "@/lib/ai/result";
import type { components } from "@/lib/ai/types.gen";

type S = components["schemas"];

/** One knowledge-base document as the admin list shows it (generated API type). */
export type KnowledgeDoc = S["KnowledgeDocOut"];

/** Limits that mirror the API's (`docs/plan/p10/P10.19_knowledge_base.md`). The server checks them again. */
export const KNOWLEDGE_MAX_BYTES = 5 * 1024 * 1024;
export const KNOWLEDGE_MAX_CHARS = 200_000;
export const KNOWLEDGE_MAX_TITLE = 200;
export const KNOWLEDGE_ACCEPT = ".pdf,.txt,.md";

/** True for a file name with an accepted extension. */
export function isKnowledgeFile(name: string): boolean {
  return /\.(pdf|txt|md)$/i.test(name);
}

/** What the admin typed: a file or pasted text (never both). `office` is "" for the whole campus. */
export interface KnowledgeInput {
  title: string;
  office: string;
  file?: File | null;
  text?: string;
}

/** `POST /v1/admin/knowledge` (multipart, forwarded as is by the proxy). */
export function uploadKnowledge(input: KnowledgeInput): Promise<AiResult<KnowledgeDoc>> {
  const form = new FormData();
  form.append("title", input.title);
  if (input.office) form.append("office", input.office);
  if (input.file) form.append("file", input.file, input.file.name);
  else form.append("text", input.text ?? "");
  return callAi<KnowledgeDoc>("admin/knowledge", { method: "POST", body: form });
}

/** `GET /v1/admin/knowledge`: newest first. */
export function listKnowledge(): Promise<AiResult<S["KnowledgeListOut"]>> {
  return callAi<S["KnowledgeListOut"]>("admin/knowledge", { timeoutMs: 15_000 });
}

/** `DELETE /v1/admin/knowledge/{id}`. */
export function deleteKnowledge(id: string): Promise<AiResult<S["KnowledgeDeleteOut"]>> {
  return callAi<S["KnowledgeDeleteOut"]>(`admin/knowledge/${encodeURIComponent(id)}`, { method: "DELETE" });
}
