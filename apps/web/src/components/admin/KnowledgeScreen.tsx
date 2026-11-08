"use client";

import { useId, useRef, useState, type FormEvent } from "react";
import { useKnowledge } from "@/hooks/useKnowledge";
import { useLang, useT } from "@/i18n";
import {
  KNOWLEDGE_ACCEPT,
  KNOWLEDGE_MAX_BYTES,
  KNOWLEDGE_MAX_CHARS,
  KNOWLEDGE_MAX_TITLE,
  isKnowledgeFile,
  type KnowledgeDoc,
} from "@/lib/knowledge/service";
import { formatDateTime } from "@/lib/time";
import { AppShell } from "../shell/AppShell";
import { PageHeader } from "../shell/PageHeader";
import { OFFICE_CODES, useOfficeLabel } from "../staff/office";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { DataTable, type Column, type SortState } from "../ui/DataTable";
import { Dialog } from "../ui/Dialog";
import { EmptyState } from "../ui/EmptyState";
import { Icon } from "../ui/Icon";
import { Select } from "../ui/Select";
import { useToast } from "../ui/Toast";
import { TextArea, TextField } from "../ui/TextField";

/** Props for {@link KnowledgeScreen}. */
export interface KnowledgeScreenProps {
  alias: string | null;
  name?: string | null;
}

type Mode = "file" | "text";

/** The upload form: a title, an office, and either a file or pasted text. Reports back through `onAdded`. */
function UploadForm({ add, onAdded }: { add: ReturnType<typeof useKnowledge>["add"]; onAdded: (doc: KnowledgeDoc) => void }) {
  const t = useT();
  const officeLabel = useOfficeLabel();
  const toast = useToast();
  const modeName = useId();
  const fileInput = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [office, setOffice] = useState("");
  const [mode, setMode] = useState<Mode>("file");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const offices = [{ value: "", label: t("knowledge.form.wholeCampus") }, ...OFFICE_CODES.map((c) => ({ value: c, label: officeLabel(c) }))];

  const pick = (f: File | null) => {
    setError(null);
    if (f && !isKnowledgeFile(f.name)) {
      setError(t("knowledge.form.wrongType"));
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      return;
    }
    if (f && f.size > KNOWLEDGE_MAX_BYTES) {
      setError(t("knowledge.form.tooBig"));
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      return;
    }
    setFile(f);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    const cleanTitle = title.trim();
    if (!cleanTitle) return setError(t("knowledge.form.needTitle"));
    if (mode === "file" && !file) return setError(t("knowledge.form.needFile"));
    if (mode === "text" && !text.trim()) return setError(t("knowledge.form.needText"));
    setError(null);
    setBusy(true);
    const res = await add({ title: cleanTitle, office, ...(mode === "file" ? { file } : { text }) });
    setBusy(false);
    if (!res.ok) {
      // A 422 carries the server's own reason (empty file, scanned PDF, too long...). Anything else is generic.
      setError(res.message ?? t("knowledge.form.failed"));
      return;
    }
    toast.show(t("knowledge.form.added", { title: res.doc.title }), "ok");
    onAdded(res.doc);
    setTitle("");
    setText("");
    setFile(null);
    if (fileInput.current) fileInput.current.value = "";
  };

  return (
    <Card title={t("knowledge.form.heading")}>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3" noValidate>
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField
            label={t("knowledge.form.title")}
            value={title}
            maxLength={KNOWLEDGE_MAX_TITLE}
            onChange={(e) => setTitle(e.target.value)}
            dir="auto"
            required
          />
          <Select label={t("knowledge.form.office")} value={office} onChange={(e) => setOffice(e.target.value)} options={offices} />
        </div>

        <fieldset className="flex flex-wrap gap-x-5 gap-y-1">
          <legend className="mb-1 text-sm font-bold text-accent">{t("knowledge.form.source")}</legend>
          {(["file", "text"] as const).map((m) => (
            <label key={m} className="flex min-h-11 items-center gap-2 text-fg-1">
              <input type="radio" name={modeName} checked={mode === m} onChange={() => { setMode(m); setError(null); }} className="size-4 accent-(--cp-accent,currentColor)" />
              {m === "file" ? t("knowledge.form.modeFile") : t("knowledge.form.modeText")}
            </label>
          ))}
        </fieldset>

        {mode === "file" ? (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="knowledge-file" className="text-sm font-bold text-accent">
              {t("knowledge.form.file")}
            </label>
            <input
              ref={fileInput}
              id="knowledge-file"
              type="file"
              accept={KNOWLEDGE_ACCEPT}
              onChange={(e) => pick(e.target.files?.[0] ?? null)}
              className="min-h-11 w-full min-w-0 rounded-md border border-line-strong bg-input px-3 py-2 text-fg-1 file:me-3 file:rounded-sm file:border-0 file:bg-surface-2 file:px-3 file:py-1 file:font-semibold file:text-accent"
            />
          </div>
        ) : (
          <TextArea
            label={t("knowledge.form.text")}
            value={text}
            rows={8}
            maxLength={KNOWLEDGE_MAX_CHARS}
            onChange={(e) => setText(e.target.value)}
            description={t("knowledge.form.chars", { count: text.length.toLocaleString("en-US"), max: KNOWLEDGE_MAX_CHARS.toLocaleString("en-US") })}
          />
        )}

        {error && (
          <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm font-medium text-danger">
            {error}
          </p>
        )}
        <div>
          <Button type="submit" loading={busy}>
            {busy ? t("knowledge.form.adding") : t("knowledge.form.add")}
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** Admin Knowledge `/admin/knowledge` (P10.19): add documents the assistant may quote, and remove them. */
export function KnowledgeScreen({ alias, name = null }: KnowledgeScreenProps) {
  const t = useT();
  const { lang } = useLang();
  const officeLabel = useOfficeLabel();
  const toast = useToast();
  const { docs, load, add, remove } = useKnowledge();
  const [sort, setSort] = useState<SortState>(null);
  const [target, setTarget] = useState<KnowledgeDoc | null>(null);
  const [deleting, setDeleting] = useState(false);

  const confirmDelete = async () => {
    if (!target || deleting) return;
    setDeleting(true);
    const res = await remove(target.id);
    setDeleting(false);
    if (res.ok) toast.show(t("knowledge.delete.done", { title: target.title }), "ok");
    else toast.show(t("knowledge.delete.failed"), "danger");
    setTarget(null);
  };

  const dash = t("common.none");
  const columns: Column<KnowledgeDoc>[] = [
    { id: "title", primary: true, header: t("knowledge.list.title"), cell: (d) => <span dir="auto">{d.title}</span>, sortValue: (d) => d.title },
    { id: "office", header: t("knowledge.list.office"), cell: (d) => (d.office ? officeLabel(d.office) : t("knowledge.form.wholeCampus")), sortValue: (d) => d.office ?? "" },
    { id: "source", header: t("knowledge.list.source"), cell: (d) => (d.filename ? <span dir="auto">{d.filename}</span> : t("knowledge.list.pasted")), sortValue: (d) => d.filename ?? "" },
    { id: "passages", header: t("knowledge.list.passages"), align: "end", cell: (d) => d.chunk_count, sortValue: (d) => d.chunk_count },
    { id: "by", header: t("knowledge.list.by"), cell: (d) => d.uploaded_by || dash, sortValue: (d) => d.uploaded_by ?? "" },
    { id: "date", header: t("knowledge.list.date"), cell: (d) => formatDateTime(d.created_at, lang), sortValue: (d) => d.created_at },
    {
      id: "delete",
      primary: true,
      header: t("knowledge.delete.action"),
      cell: (d) => (
        <Button variant="secondary" size="sm" aria-label={t("knowledge.delete.label", { title: d.title })} onClick={() => setTarget(d)}>
          {t("knowledge.delete.action")}
        </Button>
      ),
    },
  ];

  return (
    <AppShell role="admin" current="knowledge" name={name} alias={alias}>
      <PageHeader title={t("knowledge.title")} subtitle={t("knowledge.subtitle")} />
      <p className="flex items-start gap-2 text-sm text-fg-2">
        <Icon name="book" size={18} className="mt-0.5 shrink-0 text-accent" />
        {t("knowledge.note")}
      </p>
      <UploadForm add={add} onAdded={() => setSort(null)} />
      {load === "loading" && <p role="status" className="text-fg-2">{t("common.loading")}</p>}
      {load === "error" && (
        <p role="alert" className="rounded-md border border-danger px-3 py-2 text-danger">
          {t("knowledge.list.loadFailed")}
        </p>
      )}
      {load === "ready" &&
        (docs.length === 0 ? (
          <EmptyState title={t("knowledge.empty")} />
        ) : (
          <DataTable caption={t("knowledge.list.caption")} columns={columns} rows={docs} rowKey={(d) => d.id} sort={sort} onSortChange={setSort} />
        ))}
      <Dialog open={target !== null} onClose={() => !deleting && setTarget(null)} title={t("knowledge.delete.title")}>
        <p>{target ? t("knowledge.delete.body", { title: target.title }) : null}</p>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button variant="secondary" onClick={() => setTarget(null)} disabled={deleting}>
            {t("common.cancel")}
          </Button>
          <Button variant="danger" loading={deleting} onClick={() => void confirmDelete()}>
            {t("knowledge.delete.confirm")}
          </Button>
        </div>
      </Dialog>
    </AppShell>
  );
}
