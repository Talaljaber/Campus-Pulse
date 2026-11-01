"use client";

import { useState, type FormEvent } from "react";
import { useT } from "@/i18n";
import { Button } from "../ui/Button";
import { Select } from "../ui/Select";
import { TextArea } from "../ui/TextField";
import { OFFICE_CODES, useOfficeLabel } from "./office";

/** Props for {@link ForwardForm}. */
export interface ForwardFormProps {
  /** The office the picker starts on (the model's guess for a review, the current office for a ticket). */
  initialOffice: string;
  /** Offices to leave out of the picker (a ticket cannot be forwarded to the office that holds it). */
  exclude?: readonly string[];
  busy?: boolean;
  /** A sentence for a failed attempt, shown inside the form so the reviewer keeps their note. */
  error?: string | null;
  onSubmit: (office: string, note: string) => void;
  onCancel: () => void;
}

/**
 * Forward an item to an office with an optional note. Used for review items (the advisor resolves
 * the review) and for tickets (staff move the ticket). The office codes are the D-005 ones;
 * their names come from the dictionary.
 */
export function ForwardForm({ initialOffice, exclude = [], busy = false, error = null, onSubmit, onCancel }: ForwardFormProps) {
  const t = useT();
  const officeLabel = useOfficeLabel();
  const offices = OFFICE_CODES.filter((o) => !exclude.includes(o));
  const [office, setOffice] = useState(offices.includes(initialOffice as never) ? initialOffice : (offices[0] ?? ""));
  const [note, setNote] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!busy && office) onSubmit(office, note);
  };

  return (
    <form onSubmit={submit} aria-label={t("forward.title")} className="flex flex-col gap-3 rounded-md border border-line bg-surface-0 p-3">
      <Select
        label={t("forward.office")}
        value={office}
        disabled={busy}
        onChange={(e) => setOffice(e.target.value)}
        options={offices.map((o) => ({ value: o, label: officeLabel(o) }))}
        className="max-w-72"
      />
      <TextArea label={t("forward.note")} value={note} disabled={busy} onChange={(e) => setNote(e.target.value)} rows={2} />
      {error && (
        <p role="alert" className="text-sm font-medium text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" loading={busy}>
          {t("forward.submit")}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          {t("forward.cancel")}
        </Button>
      </div>
    </form>
  );
}
