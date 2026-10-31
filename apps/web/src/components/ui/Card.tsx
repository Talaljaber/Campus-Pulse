import { useId, type ReactNode } from "react";
import { cn } from "./cn";

/** Props for {@link Card}. */
export interface CardProps {
  /** Heading content. When set, the card is a labelled region. */
  title?: ReactNode;
  /** Right-aligned (start-to-end flow) controls shown beside the title. */
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

/** Surface container with an optional heading row. Presentational only. */
export function Card({ title, actions, children, className }: CardProps) {
  const titleId = useId();
  return (
    <section
      aria-labelledby={title ? titleId : undefined}
      className={cn("rounded-lg border border-line bg-surface-1 p-4 shadow-1", className)}
    >
      {(title || actions) && (
        <header className="mb-3 flex items-center justify-between gap-3">
          {title && (
            <h3 id={titleId} className="border-s-4 border-orange ps-2.5 text-lg font-bold text-fg-1">
              {title}
            </h3>
          )}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}
