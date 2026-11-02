"use client";

import { useState } from "react";
import { labelOf, useLang, useT, type DictKey } from "@/i18n";
import type { HintRow } from "@/lib/tickets/types";
import { formatDateTime } from "@/lib/time";
import { textDir } from "../explain/text";
import { Card } from "../ui/Card";
import { DataTable, type Column, type SortState } from "../ui/DataTable";

/** Props for {@link PastCorrections}. */
export interface PastCorrectionsProps {
  hints: readonly HintRow[];
}

const PRIORITY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 };

/** The corrections staff made on tickets (forward or priority change), newest first, sortable by every column. */
export function PastCorrections({ hints }: PastCorrectionsProps) {
  const t = useT();
  const { lang } = useLang();
  const [sort, setSort] = useState<SortState>(null);

  const cat = (c: string | null) => (c ? labelOf("category", c, lang) : "-");
  const pri = (p: string | null) => (p ? labelOf("priority", p, lang) : "-");

  const columns: Column<HintRow>[] = [
    {
      id: "text",
      header: t("corrections.col.text"),
      cell: (r) => (
        <span dir={textDir(r.request_text)} className="line-clamp-2">
          {r.request_text}
        </span>
      ),
      sortValue: (r) => r.request_text,
    },
    { id: "modelCategory", header: t("corrections.col.modelCategory"), cell: (r) => cat(r.model_category), sortValue: (r) => cat(r.model_category) },
    { id: "modelPriority", header: t("corrections.col.modelPriority"), cell: (r) => pri(r.model_priority), sortValue: (r) => PRIORITY_RANK[r.model_priority ?? ""] ?? 3 },
    { id: "category", header: t("corrections.col.category"), cell: (r) => cat(r.corrected_category), sortValue: (r) => cat(r.corrected_category) },
    { id: "priority", header: t("corrections.col.priority"), cell: (r) => pri(r.corrected_priority), sortValue: (r) => PRIORITY_RANK[r.corrected_priority] ?? 3 },
    {
      id: "kind",
      header: t("corrections.col.kind"),
      cell: (r) => (r.kind === "forward" || r.kind === "priority" ? t(`corrections.kind.${r.kind}` as DictKey) : r.kind),
      sortValue: (r) => r.kind,
    },
    { id: "when", header: t("corrections.col.when"), cell: (r) => formatDateTime(r.created_at, lang), sortValue: (r) => new Date(r.created_at).getTime() },
  ];

  return (
    <Card title={t("corrections.title")}>
      <p className="mb-3 text-sm text-fg-2">{t("corrections.hint")}</p>
      <DataTable
        caption={t("corrections.title")}
        columns={columns}
        rows={[...hints]}
        rowKey={(r) => r.id}
        sort={sort}
        onSortChange={setSort}
        empty={t("corrections.empty")}
      />
    </Card>
  );
}
