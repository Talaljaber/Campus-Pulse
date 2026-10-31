"use client";

import { useT } from "@/i18n";
import type { TicketStatus } from "@/lib/ai/types";
import { sortTickets, type TicketView } from "@/lib/staff/tickets";
import { EmptyState } from "../ui/EmptyState";
import { TicketRow } from "./TicketRow";

/** Props for {@link TicketQueue}. */
export interface TicketQueueProps {
  tickets: readonly TicketView[];
  /** The clock for SLA states. */
  now: Date;
  onStatus: (id: string, status: TicketStatus) => void;
  /** A ticket title was chosen. */
  onSelect?: (id: string) => void;
  /** The ticket whose details are open. */
  selectedId?: string | null;
  /** Tickets whose status change is being saved. */
  pendingIds?: ReadonlySet<string>;
  /** Show each ticket's office (an admin sees every office). */
  showOffice?: boolean;
}

/**
 * The ticket queue: soonest SLA first, finished tickets last. An overdue ticket gets a
 * danger badge and edge. The component only orders and lays out what it is given; the page
 * decides which tickets are shown (the office filter is row-level security, not this list).
 */
export function TicketQueue({ tickets, now, onStatus, onSelect, selectedId = null, pendingIds, showOffice = false }: TicketQueueProps) {
  const t = useT();
  if (tickets.length === 0) return <EmptyState title={t("staff.queue.empty")} hint={t("staff.queue.emptyHint")} />;
  return (
    <ul aria-label={t("staff.queue.title")} className="flex flex-col gap-2">
      {sortTickets(tickets).map((ticket) => (
        <li key={ticket.id}>
          <TicketRow
            ticket={ticket}
            now={now}
            selected={ticket.id === selectedId}
            pending={pendingIds?.has(ticket.id)}
            showOffice={showOffice}
            onSelect={onSelect}
            onStatus={onStatus}
          />
        </li>
      ))}
    </ul>
  );
}
