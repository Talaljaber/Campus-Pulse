"use client";

import { useId, useState, type FormEvent, type ReactNode } from "react";
import { useT } from "@/i18n";
import { Button } from "./Button";
import { cn } from "./cn";
import { Icon } from "./Icon";

/** Props for {@link FilterGroup}. */
export interface FilterGroupProps {
  /** Legend text. Default: the translated "Filtering criteria". */
  legend?: string;
  /** The filter controls; they are laid out in a responsive grid (one column on phones). */
  children: ReactNode;
  /** Called when the form is submitted (the Search button or Enter in a field). */
  onSubmit: () => void;
  /** When set, a secondary "Reset" button is shown. */
  onReset?: () => void;
  /** Text of the solid submit button. Default: the translated "Search". */
  submitLabel?: string;
  className?: string;
}

/**
 * Bordered "Filtering criteria" box: a fieldset with a bold blue legend, a responsive grid and one
 * solid Search button. On a phone it starts collapsed behind a button with the legend's text, so the
 * results keep the screen; from `sm` up it is always open.
 */
export function FilterGroup({ legend, children, onSubmit, onReset, submitLabel, className }: FilterGroupProps) {
  const t = useT();
  const bodyId = useId();
  const [open, setOpen] = useState(false);
  const title = legend ?? t("filters.legend");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setOpen(false);
    onSubmit();
  };
  return (
    <form onSubmit={submit} onReset={(e) => { e.preventDefault(); onReset?.(); }} className="shrink-0">
      <fieldset className={cn("min-w-0 rounded-lg border border-line-strong bg-surface-0 px-3 py-1 shadow-1 sm:px-5 sm:pb-4", className)}>
        <legend className="px-2 text-base font-bold text-accent max-sm:sr-only">{title}</legend>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen((v) => !v)}
          className="flex min-h-10 w-full items-center justify-between text-base font-bold text-accent sm:hidden"
        >
          {title}
          <Icon name="chevron-down" size={18} className={cn("transition-transform", open && "rotate-180")} />
        </button>
        <div id={bodyId} className={cn(!open && "max-sm:hidden")}>
          <div className="grid gap-x-4 gap-y-3 pb-1 pt-2 sm:grid-cols-2 lg:grid-cols-4">{children}</div>
          <div className="mt-3 flex flex-col items-stretch gap-2 border-t border-line pt-3 sm:flex-row sm:flex-wrap sm:items-center">
            <Button type="submit">{submitLabel ?? t("filters.search")}</Button>
            {onReset && (
              <Button type="reset" variant="secondary">
                {t("filters.reset")}
              </Button>
            )}
          </div>
        </div>
      </fieldset>
    </form>
  );
}
