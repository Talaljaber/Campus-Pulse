"use client";

import { useLang, useT } from "@/i18n";
import { kindKey, kindTone, type AnnouncementRow } from "@/lib/announcements/view";
import { formatDateTime } from "@/lib/time";
import { useOfficeLabel } from "../staff/office";
import { Badge } from "../ui/Badge";
import { EmptyState } from "../ui/EmptyState";

/** Props for {@link AnnouncementList}. */
export interface AnnouncementListProps {
  rows: readonly AnnouncementRow[];
}

/**
 * Bordered list of announcements: kind badge (Outage, Maintenance, Info), the office or "Campus-wide",
 * the start time (Amman), the title and the text. The text follows its own direction, so an Arabic
 * sentence inside an English notice still reads correctly.
 */
export function AnnouncementList({ rows }: AnnouncementListProps) {
  const t = useT();
  const { lang } = useLang();
  const officeLabel = useOfficeLabel();
  if (rows.length === 0) return <EmptyState title={t("home.announcementsEmpty")} />;
  return (
    <ul aria-label={t("home.announcements")} className="flex flex-col gap-3">
      {rows.map((a) => (
        <li key={a.id} className="flex flex-col gap-1.5 border border-line-strong border-s-[6px] border-s-orange bg-surface-0 p-4">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-fg-2">
            <Badge tone={kindTone(a.kind)}>{t(kindKey(a.kind))}</Badge>
            <span>{a.office ? officeLabel(a.office) : t("announcements.campusWide")}</span>
            <time dateTime={a.starts_at}>{formatDateTime(a.starts_at, lang)}</time>
          </div>
          <h3 className="text-lg font-bold text-fg-1" dir="auto">
            {a.title}
          </h3>
          <p className="whitespace-pre-line text-fg-1" dir="auto">
            {a.body}
          </p>
        </li>
      ))}
    </ul>
  );
}
