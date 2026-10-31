"use client";

import { useState, type FormEvent } from "react";
import { labelOf, useLang, useT } from "@/i18n";
import { Button } from "../ui/Button";
import { Select } from "../ui/Select";
import { TextArea } from "../ui/TextField";

/** What the form hands back. */
export interface CorrectionValues {
  category: string;
  priority: string;
  note: string;
}

/** Props for {@link CorrectionForm}. */
export interface CorrectionFormProps {
  /** Exact backend category labels to choose from. */
  categories: readonly string[];
  /** Exact backend priority labels to choose from. */
  priorities: readonly string[];
  /** The labels the model chose; the selects start there. */
  initial: { category: string; priority: string };
  /** Sending is in progress: the form is disabled. */
  busy?: boolean;
  onSubmit: (values: CorrectionValues) => void;
  onCancel?: () => void;
}

/**
 * Staff correct a prediction: category, priority and an optional note. Labels are shown in
 * the page language but the values stay the backend's exact strings. Native selects, so the
 * keyboard and screen readers behave as users expect.
 */
export function CorrectionForm({ categories, priorities, initial, busy = false, onSubmit, onCancel }: CorrectionFormProps) {
  const t = useT();
  const { lang } = useLang();
  const [category, setCategory] = useState(initial.category);
  const [priority, setPriority] = useState(initial.priority);
  const [note, setNote] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!busy) onSubmit({ category, priority, note });
  };

  return (
    <form onSubmit={submit} aria-label={t("staff.correction.title")} className="flex flex-col gap-3 rounded-md border border-line bg-surface-0 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Select
          label={t("staff.correction.category")}
          value={category}
          disabled={busy}
          onChange={(e) => setCategory(e.target.value)}
          options={categories.map((c) => ({ value: c, label: labelOf("category", c, lang) }))}
        />
        <Select
          label={t("staff.correction.priority")}
          value={priority}
          disabled={busy}
          onChange={(e) => setPriority(e.target.value)}
          options={priorities.map((p) => ({ value: p, label: labelOf("priority", p, lang) }))}
        />
      </div>
      <TextArea label={t("staff.correction.note")} value={note} disabled={busy} onChange={(e) => setNote(e.target.value)} rows={2} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" loading={busy}>
          {t("staff.correction.submit")}
        </Button>
        {onCancel && (
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            {t("staff.correction.cancel")}
          </Button>
        )}
      </div>
    </form>
  );
}
