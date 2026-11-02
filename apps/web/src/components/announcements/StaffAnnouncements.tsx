"use client";

import { useState } from "react";
import { useManagedAnnouncements } from "@/hooks/useAnnouncements";
import { useLang, useT, type DictKey } from "@/i18n";
import type { AnnouncementKind } from "@/lib/ai/types";
import {
  BODY_MAX,
  EMPTY_DRAFT,
  KINDS,
  TITLE_MAX,
  ammanToIso,
  validateDraft,
  type AnnouncementDraft,
  type DraftErrors,
} from "@/lib/announcements/form";
import {
  announcementErrorKind,
  archiveAnnouncement,
  createAnnouncement,
  type AnnouncementErrorKind,
} from "@/lib/announcements/service";
import { kindKey, kindTone, rowOf, type AnnouncementRow } from "@/lib/announcements/view";
import { formatDateTime } from "@/lib/time";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { OFFICE_CODES, useOfficeLabel } from "../staff/office";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { DataTable, type Column, type SortState } from "../ui/DataTable";
import { FilterGroup } from "../ui/FilterGroup";
import { Loadable } from "../ui/Loadable";
import { Select } from "../ui/Select";
import { TextArea, TextField } from "../ui/TextField";

/** Props for {@link StaffAnnouncements}. */
export interface StaffAnnouncementsProps {
  role: "staff" | "admin";
  alias: string | null;
  name?: string | null;
  /** The staff member's office; null for an admin (who picks one, or campus-wide, in the form). */
  office: string | null;
}

type Notice = { tone: "ok" | "error"; text: DictKey } | null;

const errorKey = (kind: AnnouncementErrorKind): DictKey => `announcements.error.${kind}`;

/**
 * Staff and admin announcements `/staff/announcements`: a form (title, text, kind, office for admins,
 * end time) and the table of what the caller manages, with an archive button per row. Staff post for
 * their own office only: the form has no office field for them and the server forces it anyway.
 */
export function StaffAnnouncements({ role, alias, name = null, office }: StaffAnnouncementsProps) {
  const t = useT();
  const { lang } = useLang();
  const officeLabel = useOfficeLabel();
  const list = useManagedAnnouncements(office);
  const [draft, setDraft] = useState<AnnouncementDraft>(EMPTY_DRAFT);
  const [errors, setErrors] = useState<DraftErrors>({});
  const [busy, setBusy] = useState(false);
  const [archiving, setArchiving] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [sort, setSort] = useState<SortState>({ columnId: "starts", dir: "desc" });

  const set = <K extends keyof AnnouncementDraft>(key: K, value: AnnouncementDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));
  const reset = () => {
    setDraft(EMPTY_DRAFT);
    setErrors({});
  };

  const submit = async () => {
    const found = validateDraft(draft, new Date());
    setErrors(found);
    setNotice(null);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    const res = await createAnnouncement({
      title: draft.title,
      body: draft.body,
      kind: draft.kind,
      office: role === "admin" && draft.office ? draft.office : null,
      endsAt: draft.endsAt ? ammanToIso(draft.endsAt) : null,
    });
    setBusy(false);
    if (!res.ok) return setNotice({ tone: "error", text: errorKey(announcementErrorKind(res)) });
    list.put(rowOf(res.data));
    reset();
    setNotice({ tone: "ok", text: "announcements.posted" });
  };

  const archive = async (id: string) => {
    setArchiving(id);
    setNotice(null);
    const res = await archiveAnnouncement(id);
    setArchiving(null);
    if (!res.ok) return setNotice({ tone: "error", text: errorKey(announcementErrorKind(res)) });
    list.put(rowOf(res.data));
    setNotice({ tone: "ok", text: "announcements.archivedDone" });
  };

  const status = (a: AnnouncementRow): { key: DictKey; tone: "neutral" | "ok" } => {
    const now = Date.now();
    if (a.archived_at) return { key: "announcements.status.archived", tone: "neutral" };
    if (new Date(a.starts_at).getTime() > now) return { key: "announcements.status.scheduled", tone: "neutral" };
    if (a.ends_at && new Date(a.ends_at).getTime() <= now) return { key: "announcements.status.ended", tone: "neutral" };
    return { key: "announcements.status.live", tone: "ok" };
  };

  const columns: Column<AnnouncementRow>[] = [
    { id: "title", header: t("announcements.col.title"), cell: (a) => <span dir="auto">{a.title}</span>, sortValue: (a) => a.title },
    {
      id: "kind",
      header: t("announcements.col.kind"),
      cell: (a) => <Badge tone={kindTone(a.kind)}>{t(kindKey(a.kind))}</Badge>,
      sortValue: (a) => a.kind,
    },
    {
      id: "office",
      header: t("announcements.col.office"),
      cell: (a) => (a.office ? officeLabel(a.office) : t("announcements.campusWide")),
      sortValue: (a) => a.office ?? "",
    },
    {
      id: "starts",
      header: t("announcements.col.starts"),
      cell: (a) => formatDateTime(a.starts_at, lang),
      sortValue: (a) => new Date(a.starts_at).getTime(),
    },
    {
      id: "ends",
      header: t("announcements.col.ends"),
      cell: (a) => (a.ends_at ? formatDateTime(a.ends_at, lang) : t("common.none")),
      sortValue: (a) => (a.ends_at ? new Date(a.ends_at).getTime() : Number.MAX_SAFE_INTEGER),
    },
    {
      id: "status",
      header: t("announcements.col.status"),
      cell: (a) => {
        const s = status(a);
        return <Badge tone={s.tone}>{t(s.key)}</Badge>;
      },
    },
    {
      id: "actions",
      header: t("announcements.col.actions"),
      cell: (a) => (
        <Button
          variant="secondary"
          size="sm"
          disabled={a.archived_at !== null}
          loading={archiving === a.id}
          onClick={() => void archive(a.id)}
          aria-label={t("announcements.archiveFor", { title: a.title })}
        >
          {t("announcements.archive")}
        </Button>
      ),
    },
  ];

  const kindOptions = KINDS.map((k) => ({ value: k, label: t(kindKey(k)) }));
  const officeOptions = [
    { value: "", label: t("announcements.campusWide") },
    ...OFFICE_CODES.map((c) => ({ value: c, label: officeLabel(c) })),
  ];
  const fieldError = (field: keyof DraftErrors, max: number) => {
    const key = errors[field];
    return key ? t(key, { max }) : undefined;
  };

  return (
    <AppShell role={role} current="announcements" name={name} alias={alias}>
      <PageHeader title={t("nav.announcements")} subtitle={t("announcements.subtitle")} />
      <FilterGroup
        legend={t("announcements.form.legend")}
        submitLabel={t("announcements.form.submit")}
        onSubmit={() => void submit()}
        onReset={reset}
      >
        <TextField
          label={t("announcements.form.title")}
          value={draft.title}
          onChange={(e) => set("title", e.target.value)}
          aria-invalid={errors.title ? true : undefined}
          description={fieldError("title", TITLE_MAX)}
          dir="auto"
        />
        <Select
          label={t("announcements.form.kind")}
          options={kindOptions}
          value={draft.kind}
          onChange={(e) => set("kind", e.target.value as AnnouncementKind)}
        />
        <TextArea
          className="sm:col-span-2"
          label={t("announcements.form.body")}
          value={draft.body}
          onChange={(e) => set("body", e.target.value)}
          aria-invalid={errors.body ? true : undefined}
          description={fieldError("body", BODY_MAX)}
        />
        {role === "admin" ? (
          <Select
            label={t("announcements.form.office")}
            options={officeOptions}
            value={draft.office}
            onChange={(e) => set("office", e.target.value)}
          />
        ) : (
          <p className="self-end pb-2 text-fg-2">
            {t("announcements.form.ownOffice", { office: office ? officeLabel(office) : t("common.none") })}
          </p>
        )}
        <TextField
          type="datetime-local"
          label={t("announcements.form.endsAt")}
          value={draft.endsAt}
          onChange={(e) => set("endsAt", e.target.value)}
          aria-invalid={errors.endsAt ? true : undefined}
          description={fieldError("endsAt", 0) ?? t("announcements.form.endsHint")}
        />
      </FilterGroup>

      {busy && (
        <p role="status" className="text-fg-2">
          {t("common.loading")}
        </p>
      )}
      {notice && (
        <p role={notice.tone === "error" ? "alert" : "status"} className={notice.tone === "error" ? "font-bold text-danger" : "font-bold text-fg-1"}>
          {t(notice.text)}
        </p>
      )}

      <Loadable state={list.load} onRetry={list.reload} lines={4}>
        <DataTable
          caption={t("announcements.tableCaption")}
          columns={columns}
          rows={list.rows}
          rowKey={(a) => a.id}
          sort={sort}
          onSortChange={setSort}
          empty={t("announcements.empty")}
        />
      </Loadable>
    </AppShell>
  );
}
