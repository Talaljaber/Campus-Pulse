"use client";

import { useState } from "react";
import { useT } from "@/i18n";
import { kb } from "@/lib/files/limits";
import type { FileRow } from "@/lib/files/types";
import { Icon } from "../ui/Icon";

/** Props for {@link FileChips}. */
export interface FileChipsProps {
  files: readonly FileRow[];
  /** Fetches a signed link and opens it; the chip shows a busy state until it settles. */
  onOpen?: (fileId: string) => Promise<void> | void;
}

/**
 * The files of one message as chips. A chip is a button: clicking it asks the server for a link that
 * works for 60 seconds (the page never holds a lasting address) and opens it in a new tab.
 */
export function FileChips({ files, onOpen }: FileChipsProps) {
  const t = useT();
  const [opening, setOpening] = useState<string | null>(null);
  if (files.length === 0) return null;

  const open = async (id: string) => {
    if (!onOpen || opening) return;
    setOpening(id);
    try {
      await onOpen(id);
    } finally {
      setOpening(null);
    }
  };

  return (
    <ul aria-label={t("files.label")} className="flex flex-wrap gap-2">
      {files.map((f) => {
        const kind = f.ext.toUpperCase();
        return (
          <li key={f.id}>
            <button
              type="button"
              data-file={f.id}
              disabled={!onOpen || opening !== null}
              aria-busy={opening === f.id}
              aria-label={t("files.open", { kind, size: kb(f.size_bytes) })}
              onClick={() => void open(f.id)}
              className="inline-flex min-h-9 items-center gap-2 rounded-md border border-line bg-surface-0 px-2.5 py-1 text-sm text-fg-1 hover:border-accent hover:bg-surface-1 disabled:opacity-60"
            >
              <Icon name={opening === f.id ? "spinner" : "ticket"} className="size-4" />
              <span>
                {kind} · {kb(f.size_bytes)}
              </span>
              {f.visibility === "internal" && <span className="text-fg-3">· {t("files.staffOnly")}</span>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
