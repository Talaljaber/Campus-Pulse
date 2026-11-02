import type { ReactNode } from "react";
import { cn } from "./cn";

/** One label/value row of an {@link InfoGrid}. */
export interface InfoRow {
  label: ReactNode;
  value: ReactNode;
}

/** Props for {@link InfoGrid}. */
export interface InfoGridProps {
  rows: readonly InfoRow[];
  className?: string;
}

/**
 * Two-column label/value grid (bold label, normal value) as a description list; it stacks on
 * narrow screens. Use inside an {@link InfoPanel} or on its own.
 */
export function InfoGrid({ rows, className }: InfoGridProps) {
  return (
    <dl className={cn("grid gap-x-6 gap-y-2 sm:grid-cols-[minmax(7rem,max-content)_minmax(0,1fr)]", className)}>
      {rows.map((r, i) => (
        <div key={i} className="contents">
          <dt className="font-bold text-fg-1">{r.label}</dt>
          <dd className="min-w-0 break-words text-fg-1 max-sm:mb-1">{r.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Props for {@link InfoPanel}. */
export interface InfoPanelProps {
  /** The legend, which also names the group for assistive technology. */
  title: ReactNode;
  children: ReactNode;
  /**
   * The action-button pattern: the buttons that act on what the panel shows (confirm, forward,
   * book). They sit in a row under a divider, in reading order, with the main action first.
   */
  actions?: ReactNode;
  className?: string;
}

/**
 * Fieldset-style information panel: a thin grey border with the title in the legend, the way a portal
 * profile page frames "Personal information". A real `<fieldset>` and `<legend>`, so the
 * title is the group's accessible name. Put an {@link InfoGrid} inside for label/value pairs.
 */
export function InfoPanel({ title, children, actions, className }: InfoPanelProps) {
  return (
    <fieldset className={cn("min-w-0 rounded-md border border-line-strong bg-surface-0 px-4 pb-4 pt-1", className)}>
      <legend className="px-2 text-base font-bold text-accent">{title}</legend>
      <div className="flex flex-col gap-3 pt-2">{children}</div>
      {actions && <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3">{actions}</div>}
    </fieldset>
  );
}
