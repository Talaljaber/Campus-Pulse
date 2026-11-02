"use client";

import type { FormEvent, ReactNode } from "react";
import { useT } from "@/i18n";
import { Button } from "./Button";
import { cn } from "./cn";

/** Props for {@link FilterGroup}. */
export interface FilterGroupProps {
  /** Legend text. Default: the translated "Filtering criteria". */
  legend?: string;
  /** The filter controls; they are laid out in two columns (one on phones). */
  children: ReactNode;
  /** Called when the form is submitted (the Search button or Enter in a field). */
  onSubmit: () => void;
  /** When set, a secondary "Reset" button is shown. */
  onReset?: () => void;
  className?: string;
}

/** Bordered "Filtering criteria" box: a fieldset with a bold blue legend, a 2-column grid and one solid Search button. */
export function FilterGroup({ legend, children, onSubmit, onReset, className }: FilterGroupProps) {
  const t = useT();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit();
  };
  return (
    <form onSubmit={submit} onReset={(e) => { e.preventDefault(); onReset?.(); }}>
      <fieldset className={cn("min-w-0 border border-line-strong bg-surface-0 px-4 pb-4 pt-1", className)}>
        <legend className="px-2 text-base font-bold text-accent">{legend ?? t("filters.legend")}</legend>
        <div className="grid gap-x-6 gap-y-3 pt-2 sm:grid-cols-2">{children}</div>
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3">
          <Button type="submit">{t("filters.search")}</Button>
          {onReset && (
            <Button type="reset" variant="secondary">
              {t("filters.reset")}
            </Button>
          )}
        </div>
      </fieldset>
    </form>
  );
}
