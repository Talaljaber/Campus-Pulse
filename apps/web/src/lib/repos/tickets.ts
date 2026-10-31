import type { Sb, Tables } from "../supabase/types";
import { eqFilter, subscribeTable, unwrap } from "./realtime";

export type TicketRow = Tables<"tickets">;
export type TicketLinkRow = Tables<"ticket_links">;

/**
 * Tickets of one office, soonest SLA first. RLS already restricts staff to their own
 * office; the explicit filter keeps an admin's view to the office they asked for.
 */
export async function listOfficeTickets(sb: Sb, office: string): Promise<TicketRow[]> {
  return unwrap(
    await sb.from("tickets").select("*").eq("office", office).order("sla_due_at", { ascending: true, nullsFirst: false }),
  );
}

/** The tickets opened for one request (a student sees their own by RLS). */
export async function listTicketsForRequest(sb: Sb, requestId: string): Promise<TicketRow[]> {
  return unwrap(await sb.from("tickets").select("*").eq("request_id", requestId).order("created_at", { ascending: true }));
}

/** External links (Linear, ...) of the given tickets. */
export async function listTicketLinks(sb: Sb, ticketIds: string[]): Promise<TicketLinkRow[]> {
  if (ticketIds.length === 0) return [];
  return unwrap(await sb.from("ticket_links").select("*").in("ticket_id", ticketIds));
}

/** Ticket inserts and updates for one office. Returns an unsubscribe function. */
export function subscribeTickets(sb: Sb, office: string, onChange: (t: TicketRow) => void): () => void {
  return subscribeTable<TicketRow>(sb, "tickets", (c) => onChange(c.row), { filter: eqFilter("office", office) });
}
