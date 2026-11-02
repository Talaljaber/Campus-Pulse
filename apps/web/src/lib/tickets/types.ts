/** Hand-written shapes for the ticket thread and the P9 ticket calls (until the generated types carry them). */
import type { TicketOut } from "@/lib/ai/types";

export type ActivityKind = "created" | "comment" | "note" | "status" | "forward" | "priority" | "student_action" | "reminder";
export type ActivityVisibility = "public" | "internal";
export type ActorRole = "student" | "staff" | "admin" | "system";

/** One row of `ticket_activity` (also what `POST tickets/{id}/comments` returns as `activity`). */
export type ActivityRow = {
  id: string;
  ticket_id: string;
  kind: ActivityKind;
  visibility: ActivityVisibility;
  actor_role: ActorRole;
  actor_alias: string | null;
  actor_office: string | null;
  body: string;
  from_status: string | null;
  to_status: string | null;
  from_office: string | null;
  to_office: string | null;
  from_priority: string | null;
  to_priority: string | null;
  created_at: string;
};

/** `POST tickets/{id}/comments` body. */
export interface CommentRequest {
  body: string;
  internal: boolean;
  status?: "in_progress" | "solved" | "closed" | null;
}

/** `POST tickets/{id}/student-action` body: the requester settles, closes or keeps their request open. */
export interface StudentActionRequest {
  action: "solved" | "close" | "keep_open";
}

/** `POST tickets/{id}/priority` body. */
export interface PriorityRequest {
  priority: "low" | "medium" | "high";
  note?: string | null;
}

/** `POST tickets/{id}/comments` response. */
export interface CommentResponse {
  ticket: TicketOut;
  activity: ActivityRow;
}

/** A past staff correction (a `ticket_hints` row without its embedding, which clients may not read). */
export type HintRow = {
  id: string;
  ticket_id: string | null;
  kind: string;
  request_text: string;
  lang: string | null;
  model_category: string | null;
  model_priority: string | null;
  corrected_category: string;
  corrected_priority: string;
  note: string | null;
  author_alias: string | null;
  author_role: string | null;
  created_at: string;
};
