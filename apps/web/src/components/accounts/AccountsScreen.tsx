"use client";

import { useState } from "react";
import { useT } from "@/i18n";
import type { ProfileRow } from "@/lib/profiles/types";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { useOfficeLabel } from "../staff/office";
import { DataTable, type Column, type SortState } from "../ui/DataTable";

/** Props for {@link AccountsScreen}. */
export interface AccountsScreenProps {
  alias: string | null;
  name?: string | null;
  rows: readonly ProfileRow[];
}

/** Admin Accounts `/admin/accounts`: a read-only, sortable table of the (fictional) accounts. */
export function AccountsScreen({ alias, name = null, rows }: AccountsScreenProps) {
  const t = useT();
  const officeLabel = useOfficeLabel();
  const [sort, setSort] = useState<SortState>({ columnId: "role", dir: "asc" });
  const dash = t("common.none");
  const roleLabel = (r: string) => (r === "student" || r === "staff" || r === "admin" ? t(`profile.roles.${r}`) : r);
  const columns: Column<ProfileRow>[] = [
    { id: "name", primary: true, header: t("profile.name"), cell: (r) => r.display_name ?? dash, sortValue: (r) => r.display_name ?? "" },
    { id: "role", primary: true, header: t("profile.role"), cell: (r) => roleLabel(r.role), sortValue: (r) => r.role },
    { id: "office", header: t("profile.office"), cell: (r) => (r.office ? officeLabel(r.office) : dash), sortValue: (r) => r.office ?? "" },
    { id: "alias", header: t("accounts.alias"), cell: (r) => r.alias ?? dash, sortValue: (r) => r.alias ?? "" },
    {
      id: "studentNumber",
      header: t("profile.studentNumber"),
      cell: (r) => r.student_number ?? dash,
      sortValue: (r) => r.student_number ?? "",
    },
  ];
  return (
    <AppShell role="admin" current="accounts" name={name} alias={alias}>
      <PageHeader title={t("nav.accounts")} subtitle={t("accounts.subtitle")} />
      <DataTable
        caption={t("nav.accounts")}
        columns={columns}
        rows={[...rows]}
        rowKey={(r) => r.id}
        sort={sort}
        onSortChange={setSort}
        empty={t("accounts.empty")}
      />
      <p className="text-sm text-fg-2">{t("profile.simulated")}</p>
    </AppShell>
  );
}
