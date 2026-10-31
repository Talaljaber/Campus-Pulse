"use client";

import { useMemo, useState } from "react";
import { useOutbox } from "@/hooks/useOutbox";
import { useSignOut } from "@/hooks/useSignIn";
import { useT, type DictKey } from "@/i18n";
import { filterOutbox, filterStatuses, statusCounts } from "@/lib/outbox/view";
import { RoleNav } from "../shell/RoleNav";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { ChipGroup } from "../ui/Chip";
import { EmptyState } from "../ui/EmptyState";
import { LanguageSwitch } from "../ui/LanguageSwitch";
import { Loadable } from "../ui/Loadable";
import { OutboxTable } from "./OutboxTable";

/** Props for {@link OutboxScreen}. */
export interface OutboxScreenProps {
  role: "staff" | "admin";
}

const KNOWN = ["sent", "simulated", "deferred", "rejected", "failed", "queued"];

/**
 * The outbox page `/outbox` (staff and admin): every message the system tried to send, newest
 * first, kept live. A banner says that only demo inboxes receive anything, status chips filter
 * the list with counts, and a rejected message shows the reason it was blocked. It only wires
 * `useOutbox` to the table; which rows appear is decided by row-level security.
 */
export function OutboxScreen({ role }: OutboxScreenProps) {
  const t = useT();
  const signOut = useSignOut();
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
    <main className="mx-auto flex min-h-dvh max-w-6xl flex-col gap-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold">{t("outbox.title")}</h1>
            <Badge tone="ok">{t("pulse.live")}</Badge>
          </div>
          <p className="text-fg-2">{t("outbox.subtitle")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <RoleNav role={role} current="outbox" />
          <LanguageSwitch />
          <Button variant="ghost" size="sm" onClick={() => void signOut()}>
            {t("auth.signOut")}
          </Button>
        </div>
      </header>

      <aside aria-label={t("outbox.banner.title")} className="flex flex-col gap-1 rounded-lg border border-line-strong bg-surface-1 p-4">
        <p className="font-semibold">{t("outbox.banner.title")}</p>
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
    </main>
  );
}
