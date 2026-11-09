"use client";

import Link from "next/link";
import { labelOf, useLang, useT, type DictKey } from "@/i18n";
import type { BuildingRequest } from "@/lib/pulse/view";
import { ticketNumber } from "@/lib/tickets/number";
import { useNow } from "../explain/useNow";
import { Badge } from "../ui/Badge";
import { EmptyState } from "../ui/EmptyState";
import { useDuration } from "../ui/useDuration";

const STATUSES = new Set(["new", "in_progress", "solved", "closed", "merged"]);

/** What the list needs of a ticket. */
export interface BuildingTicket {
  id: string;
  status: string;
}

/** Props for {@link BuildingRequests}. */
export interface BuildingRequestsProps {
  /** The chosen building's requests, newest first. */
  requests: readonly BuildingRequest[];
  /** The ticket of each request the caller may open (RLS: staff their office's, admin all). */
  tickets: ReadonlyMap<string, BuildingTicket>;
  /** Epoch ms to pin the clock (tests). */
  now?: number;
}

/**
 * The requests of the building chosen on the Pulse map: category, priority, room, age, and the ticket
 * with its status as a link to the staff ticket page. A request whose ticket belongs to another office
 * (or that got an FAQ answer instead of a ticket) says so instead of linking.
 */
export function BuildingRequests({ requests, tickets, now }: BuildingRequestsProps) {
  const t = useT();
  const { lang } = useLang();
  const span = useDuration();
  const clock = useNow(now);

  if (requests.length === 0) return <EmptyState title={t("pulse.building.empty")} hint={t("pulse.building.emptyHint")} />;

  return (
    <ul className="flex flex-col gap-2">
      {requests.map((r) => {
        const ticket = tickets.get(r.id);
        const what = [r.category && labelOf("category", r.category, lang), r.priority && t("pulse.building.priority", { priority: labelOf("priority", r.priority, lang) })]
          .filter(Boolean)
          .join(" · ");
        return (
          <li key={r.id} className="flex flex-col gap-1 rounded-md border border-line bg-surface-1 px-3 py-2 text-sm">
            <p className="font-medium text-fg-1">{what || t("pulse.building.unlabelled")}</p>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-3">
              {r.room && <span>{t("pulse.building.room", { room: r.room })}</span>}
              {clock !== null && <span>{t("pulse.event.ago", { span: span(clock - new Date(r.createdAt).getTime()) })}</span>}
              {r.simulated && (
                <Badge tone="info" icon={null}>
                  {t("pulse.simulated")}
                </Badge>
              )}
            </div>
            {ticket ? (
              <Link href={`/staff/tickets/${ticket.id}`} className="inline-flex min-h-9 w-fit items-center gap-2 font-medium text-accent underline-offset-2 hover:underline">
                {t("pulse.building.open", { number: ticketNumber(ticket.id) })}
                {STATUSES.has(ticket.status) && (
                  <Badge tone="neutral" icon={null}>
                    {t(`staff.status.${ticket.status}` as DictKey)}
                  </Badge>
                )}
              </Link>
            ) : (
              <p className="text-xs text-fg-3">{t("pulse.building.noTicket")}</p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
