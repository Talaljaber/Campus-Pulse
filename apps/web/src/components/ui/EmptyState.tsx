import type { ReactNode } from "react";
import { cn } from "./cn";

/** Props for {@link EmptyState}. */
export interface EmptyStateProps {
  title: string;
  hint?: string;
  /** Usually a {@link Button}. */
  action?: ReactNode;
  className?: string;
}

/** Centered "nothing here" message with an optional hint and call to action. */
export function EmptyState({ title, hint, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center gap-2 rounded-lg border border-dashed border-line-strong px-4 py-8 text-center", className)}>
      <p className="text-lg font-bold text-fg-1">{title}</p>
      {hint && <p className="text-sm text-fg-2">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
