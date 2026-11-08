"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useMyRequests, type MyTicket } from "@/hooks/useMyRequests";
import { useT, useLang, type DictKey } from "@/i18n";
import type { Role } from "@/lib/auth/routing";
import { matchesMyFilter, type MyFilter } from "@/lib/tickets/requester";
import { ticketNumber } from "@/lib/tickets/number";
import { formatDateTime } from "@/lib/time";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { useOfficeLabel } from "../staff/office";
import { DataTable, type Column, type SortState } from "../ui/DataTable";
import { FilterGroup } from "../ui/FilterGroup";
import { Loadable } from "../ui/Loadable";
import { Select } from "../ui/Select";

/** Props for {@link MyRequestsScreen}. */
export interface MyRequestsScreenProps {
  role: Role;
  alias: string | null;
  /** The name for the header greeting: the display name, else the alias. */
  name?: string | null;
}

/** `/requests`: the tickets the signed-in person opened, for students and for staff. A row opens `/requests/[id]`. */
export function MyRequestsScreen({ role, alias, name }: MyRequestsScreenProps) {
  const t = useT();
  const { lang } = useLang();
  const router = useRouter();
  const officeLabel = useOfficeLabel();
  const mine = useMyRequests(alias);
  const [draft, setDraft] = useState<MyFilter>("active");
  const [applied, setApplied] = useState<MyFilter>("active");
  const [sort, setSort] = useState<SortState>(null);

  const rows = useMemo(
    () =>
      mine.tickets
        .filter((r) => matchesMyFilter(r.status, applied))
        .sort((a, b) => b.lastUpdate.localeCompare(a.lastUpdate) || a.id.localeCompare(b.id)),
    [mine.tickets, applied],
  );

  const statusText = (r: MyTicket) => t(`staff.status.${r.status}` as DictKey);
  const columns: Column<MyTicket>[] = [
    { id: "number", primary: true, header: t("queue.col.number"), cell: (r) => <span className="font-mono">{ticketNumber(r.id)}</span>, sortValue: (r) => ticketNumber(r.id) },
    {
      id: "title",
      primary: true,
      header: t("queue.col.title"),
      cell: (r) => (
        <span dir="auto" className="font-medium">
          {r.title}
        </span>
      ),
      sortValue: (r) => r.title,
    },
    { id: "office", header: t("myRequests.col.department"), cell: (r) => officeLabel(r.office), sortValue: (r) => officeLabel(r.office) },
    { id: "status", primary: true, header: t("queue.col.status"), cell: statusText, sortValue: statusText },
    { id: "updated", header: t("myRequests.col.updated"), cell: (r) => formatDateTime(r.lastUpdate, lang), sortValue: (r) => new Date(r.lastUpdate).getTime() },
    {
      id: "deadline",
      header: t("myRequests.col.deadline"),
      cell: (r) => (r.status === "new" || r.status === "in_progress" ? formatDateTime(r.sla_due_at, lang) : "-"),
      sortValue: (r) => new Date(r.sla_due_at).getTime(),
    },
  ];

  return (
    <AppShell role={role} current="requests" name={name} alias={alias}>
      <PageHeader title={t("nav.requests")} />
      <FilterGroup
        onSubmit={() => {
          setApplied(draft);
          setSort(null);
        }}
        onReset={() => {
          setDraft("active");
          setApplied("active");
          setSort(null);
        }}
      >
        <Select
          label={t("queue.filter.status")}
          value={draft}
          onChange={(e) => setDraft(e.target.value as MyFilter)}
          options={[
            { value: "active", label: t("staff.queue.filterActive") },
            { value: "done", label: t("staff.queue.filterDone") },
            { value: "all", label: t("staff.queue.filterAll") },
          ]}
        />
      </FilterGroup>
      <section aria-label={t("nav.requests")}>
        <Loadable state={mine.load} onRetry={mine.reload}>
          <DataTable
            caption={t("nav.requests")}
            columns={columns}
            rows={rows}
            rowKey={(r) => r.id}
            sort={sort}
            onSortChange={setSort}
            onRowClick={(r) => router.push(`/requests/${r.id}`)}
            empty={
              <>
                <strong className="block text-fg-1">{t("myRequests.empty")}</strong>
                {t("myRequests.emptyHint")}
              </>
            }
          />
        </Loadable>
      </section>
    </AppShell>
  );
}
