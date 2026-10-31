"use client";

import type { ReactNode } from "react";
import { useT } from "@/i18n";
import { cn } from "./cn";

/** One column of a {@link Table}. */
export interface TableColumn<T> {
  key: keyof T | string;
  header: string;
  /** Custom cell renderer; defaults to `String(row[key])`. */
  render?: (row: T) => ReactNode;
  /** Text alignment in the writing direction (never left/right). */
  align?: "start" | "end";
}

/** Props for {@link Table}. */
export interface TableProps<T> {
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /** Shown when `rows` is empty; defaults to a translated "No rows" message. */
  empty?: ReactNode;
  /** Accessible name (rendered as a visually hidden caption). */
  caption?: string;
  className?: string;
}

/**
 * Semantic data table (`<th scope="col">`). The scroll wrapper is focusable so keyboard
 * users can scroll wide tables.
 */
export function Table<T>({ columns, rows, rowKey, empty, caption, className }: TableProps<T>) {
  const t = useT();
  const alignClass = (a?: "start" | "end") => (a === "end" ? "text-end" : "text-start");
  return (
    <div
      className={cn("overflow-x-auto rounded-lg border border-line", className)}
      tabIndex={0}
      role="region"
      aria-label={caption}
    >
      <table className="w-full border-collapse text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="bg-surface-2 text-fg-2">
          <tr>
            {columns.map((c) => (
              <th key={String(c.key)} scope="col" className={cn("px-3 py-2 font-semibold", alignClass(c.align))}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-6 text-center text-fg-3">
                {empty ?? t("ui.table.empty")}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={rowKey(row)} className="border-t border-line">
                {columns.map((c) => (
                  <td key={String(c.key)} className={cn("px-3 py-2 text-fg-1", alignClass(c.align))}>
                    {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key as string] ?? "")}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
