"use client";

import Link from "next/link";
import { useT, type DictKey } from "@/i18n";
import type { ChatTicketOut } from "@/lib/chat/agentTypes";
import { textDir } from "../explain/text";
import { useOfficeLabel } from "../staff/office";
import { PriorityBadge } from "../tickets/PriorityBadge";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";

type Status = ChatTicketOut["status"];

const LABEL: Record<Status, DictKey> = {
  new: "chat.card.received",
  in_progress: "chat.card.inProgress",
  solved: "chat.card.solved",
  closed: "chat.card.closed",
  merged: "chat.card.merged",
};

/** Text colour of the indicator, one design token per status (never the only cue: the word is always shown). */
const TONE: Record<Status, string> = {
  new: "text-info",
  in_progress: "text-info",
  solved: "text-ok",
  closed: "text-fg-3",
  merged: "text-fg-3",
};

/**
 * The small animated mark in front of the status word. Each status has one soft CSS animation (defined
 * in `globals.css` under `prefers-reduced-motion: no-preference`, so reduced motion shows only the
 * final state): new = a dot with one ripple, in progress = three breathing dots, solved = a check that
 * draws itself with a fading glow, closed = a lock that settles, merged = two dots joining.
 */
function StatusMark({ status }: { status: Status }) {
  const cls = cn("cp-st", `cp-st-${status.replace("_", "-")}`, TONE[status]);
  switch (status) {
    case "new":
      return (
        <span className={cls} aria-hidden="true">
          <span className="cp-st-ring" />
          <span className="cp-st-core size-2.5 rounded-full bg-current" />
        </span>
      );
    case "in_progress":
      return (
        <span className={cls} aria-hidden="true">
          <i className="size-1.5 rounded-full bg-current" />
          <i className="size-1.5 rounded-full bg-current" />
          <i className="size-1.5 rounded-full bg-current" />
        </span>
      );
    case "solved":
      return (
        <span className={cls} aria-hidden="true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" focusable="false">
            <path className="cp-st-check" d="M5 12.5l4.5 4.5L19 7.5" pathLength={1} />
          </svg>
        </span>
      );
    case "closed":
      return (
        <span className={cls} aria-hidden="true">
          <Icon name="lock" size={14} />
        </span>
      );
    case "merged":
      return (
        <span className={cls} aria-hidden="true">
          <i className="size-2 rounded-full bg-current" />
          <i className="size-2 rounded-full bg-current" />
        </span>
      );
  }
}

/** Props for {@link StatusCard}. */
export interface StatusCardProps {
  ticket: ChatTicketOut;
}

/**
 * One of the person's requests as a card: number, title (a link to the request), office, priority and
 * a status pill with its animation. When the office replied and waits, an extra line says so.
 */
export function StatusCard({ ticket }: StatusCardProps) {
  const t = useT();
  const officeLabel = useOfficeLabel();
  const status = t(LABEL[ticket.status]);
  return (
    <article
      data-status={ticket.status}
      aria-label={t("chat.card.cardLabel", { number: ticket.number, title: ticket.title, status })}
      className="flex w-full max-w-prose flex-col gap-2 rounded-lg border border-line bg-surface-raised p-3 shadow-1"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-fg-2">#{ticket.number}</span>
        <span
          role="status"
          className={cn("cp-st-pill inline-flex items-center gap-2 rounded-full border border-line bg-surface-1 px-2.5 py-0.5 text-sm font-semibold text-fg-1", ticket.status === "closed" && "cp-st-pill-closed")}
        >
          <StatusMark status={ticket.status} />
          {status}
        </span>
      </div>
      <Link
        href={`/requests/${encodeURIComponent(ticket.ticket_id)}`}
        dir={textDir(ticket.title)}
        aria-label={t("chat.card.open", { number: ticket.number })}
        className="font-semibold text-accent underline underline-offset-2"
      >
        {ticket.title}
      </Link>
      <div className="flex flex-wrap items-center gap-2 text-sm text-fg-2">
        <span>{officeLabel(ticket.office)}</span>
        <PriorityBadge priority={ticket.priority} />
      </div>
      {ticket.awaiting_student && <p className="text-sm font-semibold text-fg-1">{t("chat.card.awaiting")}</p>}
    </article>
  );
}

/** A list of status cards, one per request. */
export function StatusCards({ tickets }: { tickets: readonly ChatTicketOut[] }) {
  return (
    <ul className="flex w-full flex-col gap-2">
      {tickets.map((ticket) => (
        <li key={ticket.ticket_id}>
          <StatusCard ticket={ticket} />
        </li>
      ))}
    </ul>
  );
}
