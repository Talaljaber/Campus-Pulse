"use client";

import type { ReactNode } from "react";
import { labelOf, useLang, useT, type DictKey } from "@/i18n";
import { formatDateTime } from "@/lib/time";
import type { ActivityRow } from "@/lib/tickets/types";
import { textDir } from "../explain/text";
import { useOfficeLabel } from "../staff/office";
import { Badge } from "../ui/Badge";
import { cn } from "../ui/cn";

/** Props for {@link TicketThread}. */
export interface TicketThreadProps {
  activity: readonly ActivityRow[];
  /** Who is looking. A requester never sees internal rows, even if one reaches the client. */
  viewer: "staff" | "requester";
}

const isInternal = (r: ActivityRow) => r.visibility === "internal" || r.kind === "note" || r.kind === "reminder";

/**
 * The history of a ticket, oldest first: comments, internal notes, status, forward and priority
 * changes, requester actions and reminders. Shared by the staff workspace and the requester's page
 * (viewer `requester` filters internal rows out defensively; the database already hides them).
 */
export function TicketThread({ activity, viewer }: TicketThreadProps) {
  const t = useT();
  const rows = viewer === "requester" ? activity.filter((r) => !isInternal(r)) : activity;
  if (rows.length === 0) return <p className="text-sm text-fg-2">{t("ticketThread.empty")}</p>;
  return (
    <ol aria-label={t("ticketThread.label")} className="flex flex-col gap-3">
      {rows.map((r) => (
        <ThreadItem key={r.id} row={r} />
      ))}
    </ol>
  );
}

function ThreadItem({ row }: { row: ActivityRow }) {
  const t = useT();
  const { lang } = useLang();
  const officeLabel = useOfficeLabel();
  const status = (s: string | null) => (s ? t(`staff.status.${s}` as DictKey) : "");
  const priority = (p: string | null) => (p ? labelOf("priority", p, lang) : "");
  const internal = isInternal(row);

  const who =
    row.actor_role === "system"
      ? t("ticketThread.actor.system")
      : row.actor_role === "student"
        ? (row.actor_alias ?? t("ticketThread.actor.requester"))
        : [row.actor_alias ?? t(`ticketThread.actor.${row.actor_role}` as DictKey), row.actor_office ? `(${officeLabel(row.actor_office)})` : ""]
            .filter(Boolean)
            .join(" ");

  let summary: ReactNode = null;
  switch (row.kind) {
    case "created":
      summary = t("ticketThread.created");
      break;
    case "status":
      summary = t("ticketThread.status", { from: status(row.from_status), to: status(row.to_status) });
      break;
    case "forward":
      summary = t("ticketThread.forward", { from: officeLabel(row.from_office ?? ""), to: officeLabel(row.to_office ?? "") });
      break;
    case "priority":
      summary = t("ticketThread.priority", { from: priority(row.from_priority), to: priority(row.to_priority) });
      break;
    case "student_action":
      summary = row.to_status ? t("ticketThread.studentActionTo", { to: status(row.to_status) }) : t("ticketThread.studentAction");
      break;
    case "reminder":
      summary = t("ticketThread.reminder");
      break;
    case "comment":
      // A comment can carry the status change it caused (rows 2 and 12 of the state machine).
      summary = row.from_status && row.to_status && row.from_status !== row.to_status ? t("ticketThread.status", { from: status(row.from_status), to: status(row.to_status) }) : null;
      break;
    default:
      summary = null;
  }

  return (
    <li
      data-kind={row.kind}
      className={cn(
        "flex flex-col gap-1.5 rounded-md border p-3",
        internal ? "border-dashed border-line-strong bg-surface-2" : "border-line bg-surface-0",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <span className="font-bold text-fg-1">{who}</span>
        <time dateTime={row.created_at} className="text-fg-3">
          {formatDateTime(row.created_at, lang)}
        </time>
        {internal && (
          <Badge tone="warn" icon="info">
            {t("ticketThread.internal")}
          </Badge>
        )}
      </div>
      {summary && <p className="text-sm font-medium text-fg-2">{summary}</p>}
      {row.body && (
        <p dir={textDir(row.body)} className="whitespace-pre-wrap text-base text-fg-1">
          {row.body}
        </p>
      )}
    </li>
  );
}
