"use client";

import { useLang, useT, type DictKey } from "@/i18n";
import { outboxTone, type OutboxMessage } from "@/lib/outbox/view";
import { formatDateTime } from "@/lib/time";
import { Badge } from "../ui/Badge";
import { cn } from "../ui/cn";

/** Props for {@link OutboxTable}. */
export interface OutboxTableProps {
  /** Rows to show, already filtered and sorted newest first. */
  rows: readonly OutboxMessage[];
}

const STATUSES = ["sent", "simulated", "deferred", "rejected", "failed", "queued"];
const KINDS = ["email", "ticket", "booking", "alert", "broadcast", "in_app", "whatsapp"];
const CHANNELS = ["email", "in_app", "whatsapp"];

/** Status badge: the word is always there (SIMULATED, REJECTED, ...); the tone only backs it up. */
export function StatusBadge({ status }: { status: string }) {
  const t = useT();
  return (
    <Badge tone={outboxTone(status)} icon={status === "simulated" ? "info" : undefined}>
      {STATUSES.includes(status) ? t(`outbox.status.${status}` as DictKey) : status}
    </Badge>
  );
}

/**
 * The outbox as a table: when, kind, channel, recipient, subject, status and the reason or error.
 * A rejected or failed row also gets a heavier edge, so the rows that need a look stand out
 * without relying on the badge colour. Recipients are shown as stored; they are demo inboxes.
 */
export function OutboxTable({ rows }: OutboxTableProps) {
  const t = useT();
  const { lang } = useLang();
  const cols = ["when", "kind", "channel", "to", "subject", "status", "error"] as const;
  return (
    <div className="overflow-x-auto rounded-lg border border-line" role="region" aria-label={t("outbox.caption")} tabIndex={0}>
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{t("outbox.caption")}</caption>
        <thead className="bg-surface-2 text-fg-2">
          <tr>
            {cols.map((c) => (
              <th key={c} scope="col" className="px-3 py-2 text-start font-semibold">
                {t(`outbox.cols.${c}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const attention = r.status === "rejected" || r.status === "failed";
            return (
              <tr key={r.id} className="border-t border-line align-top" data-status={r.status}>
                <td className={cn("px-3 py-2 whitespace-nowrap", attention && "border-s-4 border-danger")}>{formatDateTime(r.created_at, lang)}</td>
                <td className="px-3 py-2">{KINDS.includes(r.kind) ? t(`outbox.kind.${r.kind}` as DictKey) : r.kind}</td>
                <td className="px-3 py-2">{CHANNELS.includes(r.channel) ? t(`outbox.channel.${r.channel}` as DictKey) : r.channel}</td>
                <td className="min-w-48 px-3 py-2 break-words" dir="ltr">
                  {r.to_address ? r.to_address : <span dir="auto" className="text-fg-3">{t("outbox.noRecipient")}</span>}
                </td>
                <td className="min-w-40 px-3 py-2 break-words" dir="auto">
                  {r.subject || <span className="text-fg-3">{t("outbox.noSubject")}</span>}
                </td>
                <td className="px-3 py-2">
                  <StatusBadge status={r.status} />
                </td>
                <td className="min-w-40 px-3 py-2 break-words" dir="auto">
                  {r.error ? r.error : <span className="text-fg-3">{t("outbox.noError")}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
