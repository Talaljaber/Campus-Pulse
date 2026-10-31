import { callAi } from "@/lib/ai/browser";
import type { AiFail, AiResult } from "@/lib/ai/result";
import type { Category, FeedbackResponse, Priority, TicketOut, TicketStatus } from "@/lib/ai/types";

/** Why a staff action failed, as the UI needs to say it (the dictionary key is `staff.error.<kind>`). */
export type StaffErrorKind = "generic" | "waking" | "session" | "forbidden" | "notFound";

/** What the staff member decided about a prediction. Both `null` means "confirm as it is". */
export interface Correction {
  category: Category | null;
  priority: Priority | null;
  note: string;
}

/**
 * `POST /v1/feedback`: confirm (both labels `null`) or correct a prediction. The prediction
 * becomes final, deferred actions run, and the example enters live memory at once.
 */
export function sendFeedback(predictionId: string, c: Correction): Promise<AiResult<FeedbackResponse>> {
  return callAi<FeedbackResponse>("feedback", {
    method: "POST",
    body: {
      prediction_id: predictionId,
      corrected_category: c.category,
      corrected_priority: c.priority,
      note: c.note.trim(),
    },
  });
}

/** `POST /v1/tickets/{id}/status`: the dashboard status change. */
export function setTicketStatus(ticketId: string, status: TicketStatus): Promise<AiResult<TicketOut>> {
  return callAi<TicketOut>(`tickets/${encodeURIComponent(ticketId)}/status`, { method: "POST", body: { status } });
}

/**
 * Maps a failed call to a dictionary entry. The API's own prose is English and technical,
 * so staff see our sentence, not the server's.
 */
export function staffErrorKind(fail: AiFail): StaffErrorKind {
  if (fail.status === 401 || fail.code === "unauthenticated") return "session";
  if (fail.status === 403 || fail.code === "forbidden") return "forbidden";
  if (fail.status === 404 || fail.code === "not_found") return "notFound";
  if (fail.waking) return "waking";
  return "generic";
}
