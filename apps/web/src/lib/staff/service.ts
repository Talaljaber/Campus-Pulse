import { callAi } from "@/lib/ai/browser";
import type { AiFail, AiResult } from "@/lib/ai/result";
import type { Category, FeedbackResponse, Priority, ReviewItem, ReviewStatus, TicketOut, TicketStatus } from "@/lib/ai/types";

/** Why a staff action failed, as the UI needs to say it (the dictionary key is `staff.error.<kind>`). */
export type StaffErrorKind = "generic" | "waking" | "session" | "forbidden" | "notFound" | "notYours";

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

/** `GET /v1/reviews?status=`: the unsure requests the caller may resolve (an advisor's students first). */
export function fetchReviews(status: ReviewStatus): Promise<AiResult<ReviewItem[]>> {
  return callAi<ReviewItem[]>(`reviews?status=${status}`);
}

/** `POST /v1/reviews/{id}/forward`: resolve a review by sending it to an office (UD-13). */
export function forwardReview(reviewId: string, office: string, note: string): Promise<AiResult<FeedbackResponse>> {
  return callAi<FeedbackResponse>(`reviews/${encodeURIComponent(reviewId)}/forward`, {
    method: "POST",
    body: { office, note: note.trim() || null },
  });
}

/** `POST /v1/tickets/{id}/forward`: move a ticket to another office. */
export function forwardTicket(ticketId: string, office: string, note: string): Promise<AiResult<TicketOut>> {
  return callAi<TicketOut>(`tickets/${encodeURIComponent(ticketId)}/forward`, {
    method: "POST",
    body: { office, note: note.trim() || null },
  });
}

/** `POST /v1/tickets/{id}/status`: the dashboard status change. */
export function setTicketStatus(ticketId: string, status: TicketStatus): Promise<AiResult<TicketOut>> {
  return callAi<TicketOut>(`tickets/${encodeURIComponent(ticketId)}/status`, { method: "POST", body: { status } });
}

/** Like {@link staffErrorKind}, but a 403 on a forward means the item is in another queue ("not yours"). */
export function forwardErrorKind(fail: AiFail): StaffErrorKind {
  const kind = staffErrorKind(fail);
  return kind === "forbidden" ? "notYours" : kind;
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
