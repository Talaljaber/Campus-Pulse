import type { ReactNode } from "react";
import { cn } from "../ui/cn";

/** Props for {@link PageHeader}. */
export interface PageHeaderProps {
  /** The page's one `<h1>`. */
  title: ReactNode;
  /** One muted sentence under the title. */
  subtitle?: ReactNode;
  /** Badges or status chips shown beside the title. */
  badges?: ReactNode;
  className?: string;
}

/**
 * Title block at the top of a page's card: the h1 in warm grey with an orange bar at the start
 * (the bar is decoration, the heading is the structure). Every page uses it so the titles line up.
 */
export function PageHeader({ title, subtitle, badges, className }: PageHeaderProps) {
  return (
    <header className={cn("flex flex-col gap-1 border-s-4 border-orange ps-3", className)}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h1 className="text-2xl font-bold">{title}</h1>
        {badges}
      </div>
      {subtitle && <p className="text-fg-2">{subtitle}</p>}
    </header>
  );
}
