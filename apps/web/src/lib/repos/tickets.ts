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

/**
 * Every ticket RLS lets the caller see, soonest SLA first: staff get their office's, admin
 * gets all. Pass an office to narrow an admin's view; it is a convenience, not the access control.
 */
export async function listTickets(sb: Sb, office: string | null = null): Promise<TicketRow[]> {
  return office === null ? listVisibleTickets(sb) : listOfficeTickets(sb, office);
}

async function listVisibleTickets(sb: Sb): Promise<TicketRow[]> {
  return unwrap(await sb.from("tickets").select("*").order("sla_due_at", { ascending: true, nullsFirst: false }));
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

/**
 * Ticket inserts and updates. With an office the channel is filtered to it; with `null`
 * (an admin) it carries every ticket RLS allows. Returns an unsubscribe function.
 */
export function subscribeTickets(sb: Sb, office: string | null, onChange: (t: TicketRow) => void): () => void {
  return subscribeTable<TicketRow>(sb, "tickets", (c) => onChange(c.row), office === null ? {} : { filter: eqFilter("office", office) });
}
