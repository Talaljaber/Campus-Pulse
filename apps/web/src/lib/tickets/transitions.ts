/** What staff may do to a ticket, mirroring the state machine of the API (staff rows: set in_progress, solved, closed, reopen). */
import type { TicketStatus } from "@/lib/ai/types";

export type StaffStatus = Exclude<TicketStatus, "merged">;

/**
 * The statuses staff may move a ticket to from `status`. `new` and `in_progress` can go to
 * in_progress (from new only), solved or closed; `solved` can be closed or reopened (in_progress);
 * `closed` can only be reopened. A `merged` ticket accepts no action. The server stays the judge:
 * this only keeps the picker from offering moves it would refuse.
 */
export function staffStatusOptions(status: string): StaffStatus[] {
  switch (status) {
    case "new":
      return ["in_progress", "solved", "closed"];
    case "in_progress":
      return ["solved", "closed"];
    case "solved":
      return ["in_progress", "closed"];
    case "closed":
      return ["in_progress"];
    default:
      return [];
  }
}
