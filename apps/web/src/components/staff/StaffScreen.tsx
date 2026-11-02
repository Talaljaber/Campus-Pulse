"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useNotifications } from "@/hooks/useNotifications";
import { useTicketQueue } from "@/hooks/useTicketQueue";
import { labelOf, useLang, useT, type DictKey } from "@/i18n";
import type { NoticeData } from "@/lib/chat/types";
import { DEFAULT_CRITERIA, applyCriteria, sortTickets, type QueueCriteria, type TicketView } from "@/lib/staff/tickets";
import { timeLeft } from "@/lib/tickets/clock";
import { ticketNumber } from "@/lib/tickets/number";
import { formatDateTime } from "@/lib/time";
import { useNoticeText } from "../chat/ChatThread";
import { useNow } from "../explain/useNow";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { ClockLabel } from "../tickets/ClockLabel";
import { PriorityBadge } from "../tickets/PriorityBadge";
import { Badge } from "../ui/Badge";
import { DataTable, type Column, type SortState } from "../ui/DataTable";
import { FilterGroup } from "../ui/FilterGroup";
import { Loadable } from "../ui/Loadable";
import { Select } from "../ui/Select";
import { TextField } from "../ui/TextField";
import { useToast } from "../ui/Toast";
import { OFFICE_CODES, useOfficeLabel } from "./office";

/** Props for {@link StaffScreen}. */
export interface StaffScreenProps {
  role: "staff" | "admin";
  /** The signed-in user's alias: the greeting, and the requests that are hidden from this queue. */
  alias?: string | null;
  /** The name for the header greeting: the display name, else the alias. */
  name?: string | null;
  /** The staff member's office code (D-005). Null for an admin, who sees every office. */
  office: string | null;
}

const PRIORITY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 };
/** Sort value for "no clock" (finished tickets sort after every running one when ascending). */
const NO_CLOCK = 8.64e15;

/**
 * The staff queue `/staff`: a filter box and a sortable table of the office's tickets (all offices for
 * an admin). A row opens the ticket workspace. Which rows appear is decided by row-level security; the
 * only filter applied here is hiding the viewer's own requests.
 */
export function StaffScreen({ role, alias = null, name = null, office }: StaffScreenProps) {
  const t = useT();
  const { lang } = useLang();
  const router = useRouter();
  const toast = useToast();
  const officeLabel = useOfficeLabel();
  const noticeText = useNoticeText();
  const clock = useNow();

  const queue = useTicketQueue(office, alias);

  // UD-13: a ticket forwarded to this office.
  const onNotice = (n: NoticeData) => {
    if (n.type === "ticket_forwarded") toast.show(noticeText(n), "info");
  };
  useNotifications(alias, onNotice);
  useNotifications(office ? `office:${office}` : null, onNotice);

  const [draft, setDraft] = useState<QueueCriteria>(DEFAULT_CRITERIA);
  const [applied, setApplied] = useState<QueueCriteria>(DEFAULT_CRITERIA);
  const [sort, setSort] = useState<SortState>(null);

  const rows = useMemo(() => sortTickets(applyCriteria(queue.tickets, applied, ticketNumber)), [queue.tickets, applied]);

  const left = (r: TicketView) => (clock === null ? null : timeLeft(r.sla_due_at, r.status, clock));
  const statusText = (r: TicketView) => t(`staff.status.${r.status}` as DictKey);

  const columns: Column<TicketView>[] = [
    { id: "number", header: t("queue.col.number"), cell: (r) => <span className="font-mono">{ticketNumber(r.id)}</span>, sortValue: (r) => ticketNumber(r.id) },
    {
      id: "title",
      header: t("queue.col.title"),
      cell: (r) => (
        <span dir="auto" className="font-medium">
          {r.title}
        </span>
      ),
      sortValue: (r) => r.title,
    },
    { id: "category", header: t("queue.col.category"), cell: (r) => labelOf("category", r.category, lang), sortValue: (r) => labelOf("category", r.category, lang) },
    { id: "priority", header: t("queue.col.priority"), cell: (r) => <PriorityBadge priority={r.priority} />, sortValue: (r) => PRIORITY_RANK[r.priority] ?? 3 },
    { id: "status", header: t("queue.col.status"), cell: statusText, sortValue: statusText },
    ...(office === null
      ? [{ id: "office", header: t("queue.col.office"), cell: (r: TicketView) => officeLabel(r.office), sortValue: (r: TicketView) => officeLabel(r.office) } satisfies Column<TicketView>]
      : []),
    { id: "deadline", header: t("queue.col.deadline"), cell: (r) => formatDateTime(r.sla_due_at, lang), sortValue: (r) => new Date(r.sla_due_at).getTime() },
    {
      id: "left",
      header: t("queue.col.left"),
      cell: (r) => <ClockLabel dueIso={r.sla_due_at} status={r.status} now={clock} />,
      sortValue: (r) => {
        const l = left(r);
        return l && l.state !== "stopped" ? l.ms : NO_CLOCK;
      },
    },
    {
      id: "overdue",
      header: t("queue.col.overdue"),
      cell: (r) => (left(r)?.state === "overdue" ? <Badge tone="danger">{t("queue.overdue")}</Badge> : null),
      sortValue: (r) => (left(r)?.state === "overdue" ? 0 : 1),
    },
  ];

  return (
    <AppShell role={role} current="queue" name={name} alias={alias}>
      <PageHeader
        title={t("staff.title")}
        badges={
          <Badge tone="info" icon={null}>
            {office ? t("staff.office", { office: officeLabel(office) }) : t("staff.allOffices")}
          </Badge>
        }
      />

      <FilterGroup
        onSubmit={() => {
          setApplied(draft);
          setSort(null);
        }}
        onReset={() => {
          setDraft(DEFAULT_CRITERIA);
          setApplied(DEFAULT_CRITERIA);
          setSort(null);
        }}
      >
        <Select
          label={t("queue.filter.status")}
          value={draft.status}
          onChange={(e) => setDraft({ ...draft, status: e.target.value as QueueCriteria["status"] })}
          options={[
            { value: "active", label: t("staff.queue.filterActive") },
            { value: "done", label: t("staff.queue.filterDone") },
            { value: "all", label: t("staff.queue.filterAll") },
          ]}
        />
        <Select
          label={t("queue.filter.priority")}
          value={draft.priority}
          onChange={(e) => setDraft({ ...draft, priority: e.target.value as QueueCriteria["priority"] })}
          options={[
            { value: "all", label: t("queue.filter.any") },
            { value: "high", label: t("queue.urgent") },
            { value: "medium", label: labelOf("priority", "medium", lang) },
            { value: "low", label: labelOf("priority", "low", lang) },
          ]}
        />
        {office === null && (
          <Select
            label={t("queue.filter.office")}
            value={draft.office}
            onChange={(e) => setDraft({ ...draft, office: e.target.value })}
            options={[{ value: "all", label: t("queue.filter.any") }, ...OFFICE_CODES.map((o) => ({ value: o, label: officeLabel(o) }))]}
          />
        )}
        <TextField label={t("queue.filter.search")} value={draft.search} onChange={(e) => setDraft({ ...draft, search: e.target.value })} />
      </FilterGroup>

      <section aria-label={t("staff.queue.title")} className="flex flex-col gap-2">
        <Loadable state={queue.load} onRetry={queue.reload}>
          <DataTable
            caption={t("staff.queue.title")}
            columns={columns}
            rows={rows}
            rowKey={(r) => r.id}
            sort={sort}
            onSortChange={setSort}
            onRowClick={(r) => router.push(`/staff/tickets/${r.id}`)}
            empty={
              <>
                <strong className="block text-fg-1">{t("staff.queue.empty")}</strong>
                {t("staff.queue.emptyHint")}
              </>
            }
          />
        </Loadable>
      </section>
    </AppShell>
  );
}
