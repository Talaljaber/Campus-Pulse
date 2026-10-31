"use client";

import type { CSSProperties } from "react";
import { labelOf, useLang, useT } from "@/i18n";
import type { TicketStatus } from "@/lib/ai/types";
import { slaState, type TicketView } from "@/lib/staff/tickets";
import { Badge } from "../ui/Badge";
import { cn } from "../ui/cn";
import { CATEGORY_TONE, PRIORITY_TONE, toneColor, type Tone } from "../ui/tone";
import { useDuration } from "../ui/useDuration";
import { useOfficeLabel } from "./office";
import { StatusSelect } from "./StatusSelect";

/** Props for {@link TicketRow}. */
export interface TicketRowProps {
  ticket: TicketView;
  /** The clock for the SLA state. Pass it in so server and tests agree. */
  now: Date;
  /** This ticket's details are open on the page. */
  selected?: boolean;
  /** A status change is being saved. */
  pending?: boolean;
  /** Show the office (an admin sees every office). */
  showOffice?: boolean;
  /** The title was chosen: open the request details. */
  onSelect?: (id: string) => void;
  onStatus: (id: string, status: TicketStatus) => void;
}

const SLA_TONE: Record<"overdue" | "soon" | "ok" | "done", Tone> = { overdue: "danger", soon: "warn", ok: "neutral", done: "neutral" };

/**
 * One ticket of the queue. The SLA is a badge with words and an icon, and an overdue ticket
 * also gets a danger-coloured edge, so urgency never depends on colour alone. The title is a
 * real button that opens the details; the status picker is a labelled select.
 */
export function TicketRow({ ticket, now, selected = false, pending = false, showOffice = false, onSelect, onStatus }: TicketRowProps) {
  const t = useT();
  const { lang } = useLang();
  const span = useDuration();
  const officeLabel = useOfficeLabel();
  const sla = slaState(ticket, now);
  const slaText =
    sla.kind === "done"
      ? t("staff.ticket.finished")
      : sla.kind === "overdue"
        ? t("staff.ticket.overdue", { span: span(sla.ms) })
        : t("staff.ticket.dueIn", { span: span(sla.ms) });

  return (
    <article
      data-sla={sla.kind}
      data-selected={selected || undefined}
      style={{ "--edge": sla.kind === "overdue" ? toneColor("danger") : "var(--cp-border)" } as CSSProperties}
      className={cn(
        "flex flex-col gap-2 rounded-lg border border-line border-s-4 border-s-(--edge) bg-surface-1 p-3",
        selected && "outline-2 outline-offset-0 outline-accent",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <button
          type="button"
          aria-label={t("staff.ticket.open", { title: ticket.title })}
          aria-current={selected || undefined}
          onClick={() => onSelect?.(ticket.id)}
          disabled={!onSelect}
          dir="auto"
          className="min-h-9 flex-1 rounded-sm text-start text-base font-semibold text-fg-1 hover:underline disabled:no-underline"
        >
          {ticket.title}
        </button>
        <Badge tone={SLA_TONE[sla.kind]} icon={sla.kind === "overdue" ? "alert" : sla.kind === "soon" ? "alert" : null}>
          {slaText}
        </Badge>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={CATEGORY_TONE[ticket.category] ?? "neutral"}>{labelOf("category", ticket.category, lang)}</Badge>
        <Badge tone={PRIORITY_TONE[ticket.priority] ?? "neutral"}>{labelOf("priority", ticket.priority, lang)}</Badge>
        {ticket.provisional && <Badge tone="info">{t("staff.ticket.provisional")}</Badge>}
        {showOffice && <span className="text-sm text-fg-2">{officeLabel(ticket.office)}</span>}
        {ticket.link && /^https?:\/\//i.test(ticket.link.url ?? "") ? (
          <a
            href={ticket.link.url ?? undefined}
            target="_blank"
            rel="noreferrer noopener"
            className="text-sm text-accent underline"
          >
            {t("staff.ticket.linear", { id: ticket.link.id })}
          </a>
        ) : null}
      </div>

      <StatusSelect
        value={ticket.status}
        label={t("staff.ticket.statusLabel", { title: ticket.title })}
        pending={pending}
        onChange={(s) => onStatus(ticket.id, s)}
        className="max-w-56"
      />
    </article>
  );
}
