import { callAi } from "@/lib/ai/browser";
import type { AiFail, AiResult } from "@/lib/ai/result";
import type { CounterfactualView, TriageResponse } from "@/lib/ai/types";
import type { NotificationRow } from "@/lib/repos/notifications";
import type { ChatErrorKind, NoticeData } from "./types";

/** Whether the text came from the keyboard or the (P5.9) voice transcript the student confirmed. */
export type InputMode = "text" | "voice";

/**
 * `POST /v1/triage`. The student alias is not sent: the proxy sets it from the signed-in
 * profile. `buildingId` is the picked building's code (ids equal codes in the seed).
 */
export function submitTriage(text: string, mode: InputMode, buildingId: string | null): Promise<AiResult<TriageResponse>> {
  return callAi<TriageResponse>("triage", {
    method: "POST",
    body: { text, input_mode: mode, ...(buildingId ? { location: { building: buildingId } } : {}) },
  });
}

/** `POST /v1/triage/{id}/clarify` with the chosen chip. */
export function answerClarification(requestId: string, questionId: string, optionId: string): Promise<AiResult<TriageResponse>> {
  return callAi<TriageResponse>(`triage/${encodeURIComponent(requestId)}/clarify`, {
    method: "POST",
    body: { question_id: questionId, option_id: optionId },
  });
}

/** `GET /v1/explain/{id}/counterfactual?drop=<token>`: the labels with that word removed. */
export function fetchCounterfactual(requestId: string, token: string): Promise<AiResult<CounterfactualView>> {
  return callAi<CounterfactualView>(
    `explain/${encodeURIComponent(requestId)}/counterfactual?drop=${encodeURIComponent(token)}`,
  );
}

/**
 * Picks the message to show for a failed call. The API's own prose is English-only and
 * technical, so the student never sees it: we map the status and code to a dictionary entry.
 */
export function chatErrorKind(fail: AiFail, during: "triage" | "clarify" | "other" = "other"): ChatErrorKind {
  if (fail.status === 401 || fail.code === "unauthenticated") return "session";
  if (fail.waking) return "waking";
  // 409: no question is pending. 422: the answer names a question that is not the pending one. 404: unknown request or option.
  if (during === "clarify" && (fail.status === 404 || fail.status === 409 || fail.status === 422)) return "nothingToAnswer";
  return "generic";
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : null);

/**
 * Reduces a `notifications` row to what the thread prints, following the payload contract in
 * docs/api/README.md ("Notifications payload"):
 * - `message` rows carry `message` and never `status`; incident rows carry `message` too;
 * - `ticket_status` rows carry `ticket_id`, `status`, `title` and optionally `message`.
 * A `message`, when present, is shown as written (it wins over the status sentence). Without
 * one, a `status` becomes "Your ticket <title> is now <status>". Anything else is a generic
 * "new update". Values are only ever rendered as text.
 */
export function noticeFromNotification(row: Pick<NotificationRow, "kind" | "payload">): NoticeData {
  const p = isRecord(row.payload) ? row.payload : {};
  // Staff notices carry server prose in English only, so they are rebuilt from their fields in the page language.
  if (row.kind === "review_assigned") return { type: "review_assigned", assigned: p.assigned === true };
  if (row.kind === "ticket_forwarded") {
    return { type: "ticket_forwarded", title: str(p.title) ?? "", fromOffice: str(p.from_office) ?? "" };
  }
  const message = str(p.message);
  if (message) return { type: "message", message };
  const status = str(p.status);
  if (status) return { type: "ticket_status", title: str(p.title) ?? str(p.ticket_title) ?? "", status };
  return { type: "generic" };
}
