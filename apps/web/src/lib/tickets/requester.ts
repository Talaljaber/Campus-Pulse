/** What a requester may do on their own ticket. Pure, so the visibility matrix is unit-tested on its own. */
import type { TicketRow } from "@/lib/repos/tickets";
import type { StudentActionRequest } from "./types";

export type StudentAction = StudentActionRequest["action"];

/** Statuses a requester's answer can still change; a closed or merged ticket offers nothing. */
const ANSWERABLE: ReadonlySet<string> = new Set(["new", "in_progress", "solved"]);

/** The three answer buttons appear when staff are waiting for the requester, or the ticket is marked solved. */
export function showStudentActions(t: Pick<TicketRow, "status" | "awaiting_student">): boolean {
  return ANSWERABLE.has(t.status) && (t.awaiting_student || t.status === "solved");
}

/** A message on a solved or closed ticket reopens it (done server-side). */
export function messageReopens(status: string): boolean {
  return status === "solved" || status === "closed";
}

/** Filter for "My requests": running tickets are active, solved / closed / merged are done. */
export type MyFilter = "active" | "done" | "all";

export function matchesMyFilter(status: string, filter: MyFilter): boolean {
  if (filter === "all") return true;
  const active = status === "new" || status === "in_progress";
  return filter === "active" ? active : !active;
}
