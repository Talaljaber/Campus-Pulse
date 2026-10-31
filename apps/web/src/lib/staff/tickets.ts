/**
 * Pure logic for the ticket queue: merging live updates, ordering, SLA state. No React,
 * no fetching, so it is unit-tested on its own.
 */
import type { TicketStatus } from "@/lib/ai/types";
import type { TicketLinkRow, TicketRow } from "@/lib/repos/tickets";
export { durationParts } from "@/lib/time";

/** A ticket row plus its external link (the Linear issue), when it has one. */
export interface TicketView extends TicketRow {
  link: { id: string; url: string | null } | null;
}

/** Statuses staff may choose. `merged` is set by the system when a ticket joins an incident. */
export const SETTABLE_STATUSES = ["open", "in_progress", "escalated", "resolved", "closed"] as const satisfies readonly TicketStatus[];

/** Statuses that still need work. The queue shows these by default. */
export const ACTIVE_STATUSES: ReadonlySet<string> = new Set(["open", "in_progress", "escalated"]);

export const isActive = (t: Pick<TicketRow, "status">): boolean => ACTIVE_STATUSES.has(t.status);

/** Which tickets a queue filter shows. */
export type QueueFilter = "active" | "done" | "all";

export function filterTickets<T extends Pick<TicketRow, "status">>(tickets: readonly T[], filter: QueueFilter): T[] {
  if (filter === "all") return [...tickets];
  return tickets.filter((t) => (filter === "active") === isActive(t));
}

const time = (iso: string | null): number => (iso ? new Date(iso).getTime() : Number.POSITIVE_INFINITY);

/**
 * Soonest SLA first among active tickets, then the finished ones (newest first). The sort
 * is stable and does not mutate its input.
 */
export function sortTickets<T extends Pick<TicketRow, "status" | "sla_due_at" | "created_at" | "id">>(tickets: readonly T[]): T[] {
  return [...tickets].sort((a, b) => {
    const aa = isActive(a);
    const bb = isActive(b);
    if (aa !== bb) return aa ? -1 : 1;
    const bySla = aa ? time(a.sla_due_at) - time(b.sla_due_at) : time(b.created_at) - time(a.created_at);
    return bySla !== 0 && Number.isFinite(bySla) ? bySla : a.id.localeCompare(b.id);
  });
}

/** Inserts or replaces a ticket by id. Returns a new array. */
export function upsertTicket<T extends { id: string }>(list: readonly T[], row: T): T[] {
  const at = list.findIndex((t) => t.id === row.id);
  if (at === -1) return [...list, row];
  const next = [...list];
  next[at] = row;
  return next;
}

/** Attaches the Linear (or other) link to each ticket. A ticket without a link keeps `link: null`. */
export function withLinks(tickets: readonly TicketRow[], links: readonly TicketLinkRow[]): TicketView[] {
  const byTicket = new Map<string, TicketLinkRow>();
  for (const l of links) if (!byTicket.has(l.ticket_id) || l.sink === "linear") byTicket.set(l.ticket_id, l);
  return tickets.map((t) => {
    const l = byTicket.get(t.id);
    return { ...t, link: l ? { id: l.external_id, url: l.external_url } : null };
  });
}

/** Applies a live row to a view, keeping the link it already had. */
export function mergeLive(list: readonly TicketView[], row: TicketRow): TicketView[] {
  const known = list.find((t) => t.id === row.id);
  return upsertTicket(list, { ...row, link: known?.link ?? null });
}

export type SlaKind = "done" | "overdue" | "soon" | "ok";

/** How close a ticket is to its SLA. `soon` means less than four hours left. */
export const SOON_MS = 4 * 3_600_000;

export interface SlaState {
  kind: SlaKind;
  /** Milliseconds until the deadline (negative when overdue). */
  ms: number;
}

export function slaState(t: Pick<TicketRow, "status" | "sla_due_at">, now: Date): SlaState {
  const ms = new Date(t.sla_due_at).getTime() - now.getTime();
  if (!isActive(t)) return { kind: "done", ms };
  if (ms < 0) return { kind: "overdue", ms };
  return { kind: ms < SOON_MS ? "soon" : "ok", ms };
}

/**
 * Merges the fields a status change returns (the API's `TicketOut`) into the local row.
 * `office` and `category` are kept from the database row on purpose: the API may name an
 * office in words ("Registrar") where the database stores its code (`registrar`).
 */
export function applyTicketOut<T extends TicketRow>(
  row: T,
  out: Pick<TicketRow, "status" | "resolved_at" | "escalated_at" | "provisional" | "priority" | "sla_due_at">,
): T {
  return {
    ...row,
    status: out.status,
    resolved_at: out.resolved_at,
    escalated_at: out.escalated_at,
    provisional: out.provisional,
    priority: out.priority,
    sla_due_at: out.sla_due_at,
  };
}
