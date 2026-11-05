"use client";

import { useState } from "react";
import { useLang, useT } from "@/i18n";
import { kindKey, kindTone, type AnnouncementRow } from "@/lib/announcements/view";
import { formatDateTime } from "@/lib/time";
import { useOfficeLabel } from "../staff/office";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { EmptyState } from "../ui/EmptyState";

/** Props for {@link AnnouncementList}. */
export interface AnnouncementListProps {
  rows: readonly AnnouncementRow[];
  /** Home stays calm: expose only the newest title, with the full notice in a dialog. */
  compact?: boolean;
}

/**
 * Bordered list of announcements: kind badge (Outage, Maintenance, Info), the office or "Campus-wide",
 * the start time (Amman), the title and the text. The text follows its own direction, so an Arabic
 * sentence inside an English notice still reads correctly.
 */
export function AnnouncementList({ rows, compact = false }: AnnouncementListProps) {
  const t = useT();
  const { lang } = useLang();
  const officeLabel = useOfficeLabel();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  if (rows.length === 0) return <EmptyState title={t("home.announcementsEmpty")} />;
  const shown = compact ? rows.slice(0, 1) : rows;
  const selected = rows.find((row) => row.id === selectedId) ?? null;
  return (
    <>
      <ul aria-label={t("home.announcements")} className="flex flex-col gap-3">
      {shown.map((a) => (
        <li key={a.id} className="flex flex-col gap-1.5 border border-line-strong border-s-[6px] border-s-orange bg-surface-0 p-4">
          <h3 className="text-lg font-bold text-fg-1" dir="auto">
            {a.title}
          </h3>
          {compact ? (
            <div><Button variant="secondary" size="sm" onClick={() => setSelectedId(a.id)}>{t("announcements.showDetails")}</Button></div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-fg-2">
                <Badge tone={kindTone(a.kind)}>{t(kindKey(a.kind))}</Badge>
                <span>{a.office ? officeLabel(a.office) : t("announcements.campusWide")}</span>
                <time dateTime={a.starts_at}>{formatDateTime(a.starts_at, lang)}</time>
              </div>
              <p className="whitespace-pre-line text-fg-1" dir="auto">
                {a.body}
              </p>
            </>
          )}
        </li>
      ))}
      </ul>
      {selected && (
        <Dialog open onClose={() => setSelectedId(null)} title={selected.title}>
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-fg-2">
              <Badge tone={kindTone(selected.kind)}>{t(kindKey(selected.kind))}</Badge>
              <span>{selected.office ? officeLabel(selected.office) : t("announcements.campusWide")}</span>
              <time dateTime={selected.starts_at}>{formatDateTime(selected.starts_at, lang)}</time>
            </div>
            <p className="whitespace-pre-line text-fg-1" dir="auto">{selected.body}</p>
          </div>
        </Dialog>
      )}
    </>
  );
}
