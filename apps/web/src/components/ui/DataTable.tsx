"use client";

import type { KeyboardEvent, MouseEvent, ReactNode } from "react";
import { useT } from "@/i18n";
import { cn } from "./cn";
import { Icon } from "./Icon";

/** One column of a {@link DataTable}. A column with a `sortValue` can be sorted by its header. */
export interface Column<T> {
  id: string;
  header: string;
  cell: (row: T) => ReactNode;
  /** Value to sort by. Omit for a column that is not sortable. */
  sortValue?: (row: T) => string | number;
  align?: "start" | "end";
  /** Any CSS width (`"8rem"`, `"20%"`). */
  width?: string;
}

/** Sort state: which column and which way. `null` = the rows' own order. */
export type SortState = { columnId: string; dir: "asc" | "desc" } | null;

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

function compare(a: string | number, b: string | number): number {
  return typeof a === "number" && typeof b === "number" ? a - b : collator.compare(String(a), String(b));
}

/**
 * Returns a sorted copy of `rows` (stable; the input is never mutated). With no sort, an unknown
 * column or a column without `sortValue`, the rows come back in their original order.
 */
export function sortRows<T>(rows: readonly T[], columns: readonly Column<T>[], sort: SortState): T[] {
  const col = sort ? columns.find((c) => c.id === sort.columnId) : undefined;
  if (!sort || !col?.sortValue) return [...rows];
  const value = col.sortValue;
  const sign = sort.dir === "asc" ? 1 : -1;
  return rows
    .map((row, index) => ({ row, index, v: value(row) }))
    .sort((x, y) => sign * compare(x.v, y.v) || x.index - y.index)
    .map((x) => x.row);
}

/** Props for {@link DataTable}. */
export interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /** Current sort (controlled). The table sorts `rows` itself with {@link sortRows}. */
  sort: SortState;
  onSortChange: (next: SortState) => void;
  /** Makes rows focusable; click and Enter on a focused row call it. */
  onRowClick?: (row: T) => void;
  /** Accessible name (visually hidden caption). */
  caption: string;
  /** Shown when there are no rows. */
  empty?: ReactNode;
  className?: string;
}

/**
 * Dense, bordered data table with zebra rows. Sortable headers are buttons that toggle asc/desc and
 * set `aria-sort` on the active column. With `onRowClick`, each row is focusable and Enter or a click
 * opens it (a click or Enter on a nested button, link or field does not, so inline controls keep working).
 */
export function DataTable<T>({ columns, rows, rowKey, sort, onSortChange, onRowClick, caption, empty, className }: DataTableProps<T>) {
  const t = useT();
  const shown = sortRows(rows, columns, sort);
  const align = (a?: "start" | "end") => (a === "end" ? "text-end" : "text-start");

  const toggle = (id: string) =>
    onSortChange(sort?.columnId === id && sort.dir === "asc" ? { columnId: id, dir: "desc" } : { columnId: id, dir: "asc" });

  /** True when the event came from a control inside the row (button, link, field): those keep their own behaviour. */
  const fromControl = (e: { target: EventTarget; currentTarget: HTMLElement }) => {
    const hit = (e.target as HTMLElement).closest("button, a, input, select, textarea, label");
    return hit !== null && e.currentTarget.contains(hit);
  };
  const onKey = (e: KeyboardEvent<HTMLTableRowElement>, row: T) => {
    if (e.key === "Enter" && e.target === e.currentTarget) onRowClick?.(row);
  };
  const onClick = (e: MouseEvent<HTMLTableRowElement>, row: T) => {
    if (!fromControl(e)) onRowClick?.(row);
  };

  return (
    <div className={cn("overflow-x-auto border border-line-strong bg-surface-0", className)} tabIndex={0} role="region" aria-label={caption}>
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b-2 border-line-strong bg-surface-2 text-fg-1">
          <tr>
            {columns.map((c) => {
              const active = sort?.columnId === c.id ? sort : null;
              return (
                <th
                  key={c.id}
                  scope="col"
                  style={c.width ? { width: c.width } : undefined}
                  aria-sort={active ? (active.dir === "asc" ? "ascending" : "descending") : undefined}
                  className={cn("px-2 py-2 font-bold", align(c.align))}
                >
                  {c.sortValue ? (
                    <button
                      type="button"
                      onClick={() => toggle(c.id)}
                      className="inline-flex min-h-8 items-center gap-1 rounded-sm font-bold text-fg-1 hover:text-accent"
                    >
                      {c.header}
                      <Icon name="arrow-down" size={14} className={cn(active ? "text-accent" : "opacity-40", active?.dir === "asc" && "rotate-180")} />
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {shown.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-2 py-6 text-center text-fg-3">
                {empty ?? t("ui.table.empty")}
              </td>
            </tr>
          ) : (
            shown.map((row) => (
              <tr
                key={rowKey(row)}
                tabIndex={onRowClick ? 0 : undefined}
                onClick={onRowClick ? (e) => onClick(e, row) : undefined}
                onKeyDown={onRowClick ? (e) => onKey(e, row) : undefined}
                className={cn("border-t border-line even:bg-surface-1", onRowClick && "cursor-pointer hover:bg-surface-2")}
              >
                {columns.map((c) => (
                  <td key={c.id} className={cn("px-2 py-1.5 align-middle text-fg-1", align(c.align))}>
                    {c.cell(row)}
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
