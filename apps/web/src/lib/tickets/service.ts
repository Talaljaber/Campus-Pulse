import { callAi } from "@/lib/ai/browser";
import type { AiFail, AiResult } from "@/lib/ai/result";
import type { TicketOut } from "@/lib/ai/types";
import { problemFromServer, type FileProblem } from "@/lib/files/limits";
import type { CommentRequest, CommentResponse, PriorityRequest, StudentActionRequest } from "./types";

const base = (id: string) => `tickets/${encodeURIComponent(id)}`;

/** `POST /v1/tickets/{id}/comments`: a public reply or an internal note, optionally with a status change. */
export function postComment(ticketId: string, req: CommentRequest): Promise<AiResult<CommentResponse>> {
  return callAi<CommentResponse>(`${base(ticketId)}/comments`, {
    method: "POST",
    body: { body: req.body.trim(), internal: req.internal, status: req.status ?? null, ...(req.file_ids?.length ? { file_ids: req.file_ids } : {}) },
  });
}

/** `POST /v1/tickets/{id}/status` with an optional note. */
export function postStatus(ticketId: string, status: "new" | "in_progress" | "solved" | "closed", note?: string): Promise<AiResult<TicketOut>> {
  return callAi<TicketOut>(`${base(ticketId)}/status`, { method: "POST", body: { status, note: note?.trim() || null } });
}

/** `POST /v1/tickets/{id}/priority`: change the priority; the clock restarts with the new priority's hours. */
export function postPriority(ticketId: string, req: PriorityRequest): Promise<AiResult<TicketOut>> {
  return callAi<TicketOut>(`${base(ticketId)}/priority`, {
    method: "POST",
    body: { priority: req.priority, note: req.note?.trim() || null },
  });
}

/** `POST /v1/tickets/{id}/student-action`: the requester answers "solved", "close" or "keep open". */
export function postStudentAction(ticketId: string, req: StudentActionRequest): Promise<AiResult<TicketOut>> {
  return callAi<TicketOut>(`${base(ticketId)}/student-action`, { method: "POST", body: { action: req.action } });
}

/**
 * The sentence for a failed call. A refused transition (422) carries the server's own message
 * ("transition solved -> new not allowed"), which is what staff need; other failures use our dictionary.
 */
export function failMessage(fail: AiFail): { kind: "server"; text: string } | { kind: "dict"; key: "staff.error.generic" | "staff.error.waking" | "staff.error.session" | "staff.error.forbidden" | "staff.error.notFound" | `files.error.${FileProblem}` } {
  if ((fail.status === 422 || fail.code === "invalid_input") && fail.error) {
    // A refused file has its own translated sentence (type, size, count); other 422s show the server's words.
    const problem = problemFromServer(fail.error);
    if (problem) return { kind: "dict", key: `files.error.${problem}` };
    return { kind: "server", text: fail.error };
  }
  if (fail.status === 401 || fail.code === "unauthenticated") return { kind: "dict", key: "staff.error.session" };
  if (fail.status === 403 || fail.code === "forbidden") return { kind: "dict", key: "staff.error.forbidden" };
  if (fail.status === 404 || fail.code === "not_found") return { kind: "dict", key: "staff.error.notFound" };
  if (fail.waking) return { kind: "dict", key: "staff.error.waking" };
  return { kind: "dict", key: "staff.error.generic" };
}
