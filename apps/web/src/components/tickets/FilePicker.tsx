"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { useT } from "@/i18n";
import { checkFile, extOf, kb, type FileProblem } from "@/lib/files/limits";
import { ACCEPT, type FileRow } from "@/lib/files/types";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";

/** Props for {@link FilePicker}. */
export interface FilePickerProps {
  /** Files chosen so far (they are uploaded when the message is sent). */
  picked: readonly File[];
  onChange: (files: File[]) => void;
  /** Files the ticket already holds, for the count and size limits. */
  existing: readonly Pick<FileRow, "size_bytes">[];
  /** True while the message is an internal note: the files will be staff-only. */
  internal?: boolean;
  disabled?: boolean;
}

/**
 * The upload control of a message box: a button, the demo notice, the chosen files with a remove
 * button each, and a clear sentence for a refused file (type, size, count). The server checks the
 * real bytes again; this only gives a fast answer.
 */
export function FilePicker({ picked, onChange, existing, internal = false, disabled = false }: FilePickerProps) {
  const t = useT();
  const input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState<FileProblem | null>(null);

  const choose = (e: ChangeEvent<HTMLInputElement>) => {
    const next = [...picked];
    let first: FileProblem | null = null;
    for (const file of Array.from(e.target.files ?? [])) {
      const p = checkFile(file, existing, next);
      if (p) first ??= p;
      else next.push(file);
    }
    setProblem(first);
    if (next.length !== picked.length) onChange(next);
    e.target.value = ""; // the same file may be chosen again after removing it
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" size="sm" disabled={disabled} onClick={() => input.current?.click()}>
          {t("files.attach")}
        </Button>
        <input ref={input} type="file" multiple accept={ACCEPT} tabIndex={-1} aria-label={t("files.attach")} onChange={choose} disabled={disabled} className="sr-only" />
        <p className="text-sm text-fg-2">{t("files.notice")}</p>
      </div>
      <p className="text-sm text-fg-3">{t("files.hint")}</p>
      {internal && <p className="text-sm text-fg-2">{t("files.staffOnlyHint")}</p>}
      {problem && (
        <p role="alert" className="text-sm font-medium text-danger">
          {t(`files.error.${problem}`)}
        </p>
      )}
      {picked.length > 0 && (
        <ul aria-label={t("files.picked")} className="flex flex-wrap gap-2">
          {picked.map((f, i) => (
            <li key={`${f.name}-${i}`} className="flex items-center gap-2 rounded-md border border-line bg-surface-0 px-2.5 py-1 text-sm text-fg-1">
              <span dir="auto" className="max-w-48 truncate">
                {f.name}
              </span>
              <span className="text-fg-3">
                {extOf(f.name).toUpperCase()} · {kb(f.size)}
              </span>
              <button
                type="button"
                disabled={disabled}
                aria-label={t("files.remove", { name: f.name })}
                onClick={() => {
                  setProblem(null);
                  onChange(picked.filter((_, j) => j !== i));
                }}
                className="inline-flex size-6 items-center justify-center rounded-sm text-fg-2 hover:bg-surface-2"
              >
                <Icon name="close" className="size-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
