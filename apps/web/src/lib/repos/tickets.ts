import type { Sb, Tables } from "../supabase/types";
import { eqFilter, subscribeTable, unwrap } from "./realtime";

import type { ActivityRow } from "../tickets/types";

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

/** The tickets a requester opened themselves, newest first (RLS decides what the caller may read; the filter picks "mine"). */
export async function listMyTickets(sb: Sb, alias: string): Promise<TicketRow[]> {
  return unwrap(await sb.from("tickets").select("*").eq("requester_alias", alias).order("created_at", { ascending: false }));
}

/** The time of the latest visible thread row per ticket (internal rows are hidden from a requester by RLS). */
export async function listLastActivity(sb: Sb, ticketIds: string[]): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  if (ticketIds.length === 0) return out;
  const rows = unwrap(await sb.from("ticket_activity").select("ticket_id, created_at").in("ticket_id", ticketIds).order("created_at", { ascending: false }));
  for (const r of rows as { ticket_id: string; created_at: string }[]) if (!out.has(r.ticket_id)) out.set(r.ticket_id, r.created_at);
  return out;
}

/** The tickets opened for one request (a student sees their own by RLS). */
export async function listTicketsForRequest(sb: Sb, requestId: string): Promise<TicketRow[]> {
  return unwrap(await sb.from("tickets").select("*").eq("request_id", requestId).order("created_at", { ascending: true }));
}

/** The tickets of several requests (the Pulse building list). RLS decides which the caller may read. */
export async function listTicketsForRequests(sb: Sb, requestIds: readonly string[]): Promise<TicketRow[]> {
  if (requestIds.length === 0) return [];
  return unwrap(await sb.from("tickets").select("*").in("request_id", [...requestIds]).order("created_at", { ascending: true }));
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

/** One ticket by id. `null` when it does not exist or RLS hides it. */
export async function getTicket(sb: Sb, id: string): Promise<TicketRow | null> {
  const res = await sb.from("tickets").select("*").eq("id", id).maybeSingle();
  if (res.error) throw new Error(res.error.message);
  return res.data;
}

/** The thread of a ticket, oldest first. RLS hides internal rows from the requester. */
export async function listActivity(sb: Sb, ticketId: string): Promise<ActivityRow[]> {
  const rows = unwrap(await sb.from("ticket_activity").select("*").eq("ticket_id", ticketId).order("created_at", { ascending: true }));
  return rows as ActivityRow[];
}

/** New thread rows of one ticket. Returns an unsubscribe function. */
export function subscribeActivity(sb: Sb, ticketId: string, onRow: (row: ActivityRow) => void): () => void {
  return subscribeTable<ActivityRow>(sb, "ticket_activity", (c) => onRow(c.row), { filter: eqFilter("ticket_id", ticketId) });
}

/** Updates of one ticket (status, clock, office). Returns an unsubscribe function. */
export function subscribeTicket(sb: Sb, ticketId: string, onChange: (t: TicketRow) => void): () => void {
  return subscribeTable<TicketRow>(sb, "tickets", (c) => onChange(c.row), { filter: eqFilter("id", ticketId) });
}
