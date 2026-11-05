"use client";

import { Fragment, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { useMediaQuery } from "@/hooks/useMediaQuery";
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
  /** Shown on the collapsed card on a phone. With none marked, the first two columns are. The rest sit behind "Show details". */
  primary?: boolean;
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

/** True when the event came from a control inside the row (button, link, field): those keep their own behaviour. */
function fromControl(e: { target: EventTarget; currentTarget: HTMLElement }): boolean {
  const hit = (e.target as HTMLElement).closest("button, a, input, select, textarea, label");
  return hit !== null && e.currentTarget.contains(hit);
}

/** One row as a card: the primary columns always, the other columns behind a "Show details" button. */
function RowCard<T>({ row, primary, rest, onRowClick }: { row: T; primary: Column<T>[]; rest: Column<T>[]; onRowClick?: (row: T) => void }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const lead = primary.length > 1 ? primary[0] : null;
  const title = primary.length > 1 ? primary[1] : primary[0];
  const tail = primary.slice(2);
  return (
    <li className="overflow-hidden rounded-lg border border-line-strong bg-surface-0 shadow-1">
      <div
        tabIndex={onRowClick ? 0 : undefined}
        onClick={onRowClick ? (e) => !fromControl(e) && onRowClick(row) : undefined}
        onKeyDown={onRowClick ? (e) => e.key === "Enter" && e.target === e.currentTarget && onRowClick(row) : undefined}
        className={cn("flex flex-col gap-1.5 p-3", onRowClick && "cursor-pointer hover:bg-surface-1")}
      >
        <div className="flex items-baseline gap-2">
          {lead && <span className="shrink-0 text-xs text-fg-3">{lead.cell(row)}</span>}
          {title && <span className="min-w-0 flex-1 break-words font-medium text-fg-1">{title.cell(row)}</span>}
        </div>
        {tail.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-fg-1">
            {tail.map((c) => (
              <span key={c.id}>{c.cell(row)}</span>
            ))}
          </div>
        )}
      </div>
      {rest.length > 0 && (
        <>
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="flex min-h-10 w-full items-center justify-between border-t border-line px-3 text-sm font-semibold text-accent hover:bg-surface-1"
          >
            {open ? t("ui.table.hideDetails") : t("ui.table.showDetails")}
            <Icon name="chevron-down" size={16} className={cn("transition-transform", open && "rotate-180")} />
          </button>
          {open && (
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5 border-t border-line bg-surface-1 p-3 text-sm">
              {rest.map((c) => (
                <Fragment key={c.id}>
                  <dt className="text-fg-3">{c.header}</dt>
                  <dd className="break-words text-fg-1">{c.cell(row)}</dd>
                </Fragment>
              ))}
            </dl>
          )}
        </>
      )}
    </li>
  );
}

/** The phone layout of a {@link DataTable}: a sort control and a list of {@link RowCard}s. */
function CardList<T>({ columns, shown, rowKey, sort, onSortChange, onRowClick, caption, empty, className }: DataTableProps<T> & { shown: T[] }) {
  const t = useT();
  const flagged = columns.filter((c) => c.primary);
  const primary = flagged.length > 0 ? flagged : columns.slice(0, 2);
  const rest = columns.filter((c) => !primary.includes(c));
  const sortable = columns.filter((c) => c.sortValue);
  return (
    <section aria-label={caption} className={cn("flex flex-col gap-2", className)}>
      {sortable.length > 0 && (
        <div className="flex items-center gap-2">
          <select
            aria-label={t("ui.table.sortBy")}
            value={sort?.columnId ?? ""}
            onChange={(e) => onSortChange(e.target.value === "" ? null : { columnId: e.target.value, dir: sort?.dir ?? "asc" })}
            className="min-h-10 min-w-0 flex-1 rounded-md border border-line-strong bg-surface-0 px-2 text-sm text-fg-1"
          >
            <option value="">{t("ui.table.sortBy")}</option>
            {sortable.map((c) => (
              <option key={c.id} value={c.id}>
                {c.header}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!sort}
            aria-label={sort?.dir === "desc" ? t("ui.table.sortDescending") : t("ui.table.sortAscending")}
            onClick={() => sort && onSortChange({ columnId: sort.columnId, dir: sort.dir === "asc" ? "desc" : "asc" })}
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-md border border-line-strong bg-surface-0 text-accent disabled:opacity-50"
          >
            <Icon name="arrow-down" size={16} className={cn(sort?.dir === "asc" && "rotate-180")} />
          </button>
        </div>
      )}
      {shown.length === 0 ? (
        <p className="rounded-lg border border-line-strong bg-surface-0 px-3 py-6 text-center text-fg-3">{empty ?? t("ui.table.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {shown.map((row) => (
            <RowCard key={rowKey(row)} row={row} primary={primary} rest={rest} onRowClick={onRowClick} />
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * Dense, bordered data table with zebra rows. Sortable headers are buttons that toggle asc/desc and
 * set `aria-sort` on the active column. With `onRowClick`, each row is focusable and Enter or a click
 * opens it (a click or Enter on a nested button, link or field does not, so inline controls keep working).
 * On a phone (under 768 px) the same rows become cards that fit the width: the `primary` columns
 * stay visible, the others are behind a "Show details" button, and a select sorts instead of the headers.
 */
export function DataTable<T>(props: DataTableProps<T>) {
  const { columns, rows, rowKey, sort, onSortChange, onRowClick, caption, empty, className } = props;
  const t = useT();
  const phone = useMediaQuery("(max-width: 767px)");
  const shown = sortRows(rows, columns, sort);
  const align = (a?: "start" | "end") => (a === "end" ? "text-end" : "text-start");

  const toggle = (id: string) =>
    onSortChange(sort?.columnId === id && sort.dir === "asc" ? { columnId: id, dir: "desc" } : { columnId: id, dir: "asc" });

  const onKey = (e: KeyboardEvent<HTMLTableRowElement>, row: T) => {
    if (e.key === "Enter" && e.target === e.currentTarget) onRowClick?.(row);
  };
  const onClick = (e: MouseEvent<HTMLTableRowElement>, row: T) => {
    if (!fromControl(e)) onRowClick?.(row);
  };

  if (phone) return <CardList {...props} shown={shown} />;

  return (
    <div
      className={cn("relative overflow-x-auto overscroll-x-contain rounded-lg border border-line-strong bg-surface-0 shadow-1", className)}
      tabIndex={0}
      role="region"
      aria-label={caption}
    >
      <table className={cn("w-full border-collapse text-sm", columns.length > 3 && "min-w-[42rem]")}>
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
