"use client";

import { useMemo, useState } from "react";
import { useOutbox } from "@/hooks/useOutbox";
import { useT, type DictKey } from "@/i18n";
import { filterOutbox, filterStatuses, statusCounts } from "@/lib/outbox/view";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { ChipGroup } from "../ui/Chip";
import { EmptyState } from "../ui/EmptyState";
import { Loadable } from "../ui/Loadable";
import { OutboxTable } from "./OutboxTable";

/** Props for {@link OutboxScreen}. */
export interface OutboxScreenProps {
  role: "staff" | "admin";
  /** The signed-in user's alias, for the header greeting. */
  alias?: string | null;
}

const KNOWN = ["sent", "simulated", "deferred", "rejected", "failed", "queued"];

/**
 * The outbox page `/outbox` (staff and admin): every message the system tried to send, newest
 * first, kept live. A banner says that only demo inboxes receive anything, status chips filter
 * the list with counts, and a rejected message shows the reason it was blocked. It only wires
 * `useOutbox` to the table; which rows appear is decided by row-level security.
 */
export function OutboxScreen({ role, alias = null }: OutboxScreenProps) {
  const t = useT();
  const outbox = useOutbox();
  const [status, setStatus] = useState("all");

  const counts = useMemo(() => statusCounts(outbox.rows), [outbox.rows]);
  const visible = useMemo(() => filterOutbox(outbox.rows, status), [outbox.rows, status]);
  const label = (s: string) => (KNOWN.includes(s) ? t(`outbox.status.${s}` as DictKey) : s);
  const chips = [
    { id: "all", label: t("outbox.filter.all", { count: counts.all ?? 0 }) },
    ...filterStatuses(outbox.rows).map((s) => ({ id: s, label: t("outbox.filter.status", { status: label(s), count: counts[s] ?? 0 }) })),
  ];

  return (
    <AppShell role={role} current="outbox" alias={alias}>
      <PageHeader title={t("outbox.title")} subtitle={t("outbox.subtitle")} badges={<Badge tone="ok">{t("pulse.live")}</Badge>} />

      <aside
        aria-label={t("outbox.banner.title")}
        className="flex flex-col gap-1 rounded-md border border-line-strong border-s-[6px] border-s-orange bg-surface-1 p-4"
      >
        <p className="font-bold">{t("outbox.banner.title")}</p>
        <p className="text-fg-2">{t("outbox.banner.body")}</p>
      </aside>

      <Loadable state={outbox.load} onRetry={outbox.reload} lines={6}>
        <div className="flex flex-col gap-4">
          <ChipGroup label={t("outbox.filter.label")} items={chips} value={status} onChange={setStatus} />
          <details className="rounded-md border border-line bg-surface-1 p-3">
            <summary className="cursor-pointer font-medium">{t("outbox.help.title")}</summary>
            <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
              {KNOWN.map((s) => (
                <div key={s} className="contents">
                  <dt className="font-medium">{label(s)}</dt>
                  <dd className="text-fg-2">{t(`outbox.help.${s}` as DictKey)}</dd>
                </div>
              ))}
            </dl>
          </details>
          {outbox.rows.length === 0 ? (
            <EmptyState title={t("outbox.empty")} hint={t("outbox.emptyHint")} />
          ) : visible.length === 0 ? (
            <EmptyState
              title={t("outbox.emptyFiltered")}
              hint={t("outbox.emptyFilteredHint")}
              action={
                <Button variant="secondary" size="sm" onClick={() => setStatus("all")}>
                  {t("outbox.filter.all", { count: counts.all ?? 0 })}
                </Button>
              }
            />
          ) : (
            <OutboxTable rows={visible} />
          )}
        </div>
      </Loadable>
    </AppShell>
  );
}
