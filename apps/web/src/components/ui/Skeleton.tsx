"use client";

import { useT } from "@/i18n";
import { cn } from "./cn";

/** Props for {@link Skeleton}. */
export interface SkeletonProps {
  /** Number of text-line placeholders. Default 3. */
  lines?: number;
  className?: string;
}

/** Loading placeholder. Announced once as a status ("Loading content"); the bars are hidden from AT. */
export function Skeleton({ lines = 3, className }: SkeletonProps) {
  const t = useT();
  return (
    <div role="status" aria-busy="true" className={cn("flex flex-col gap-2", className)}>
      <span className="sr-only">{t("ui.skeleton.label")}</span>
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          aria-hidden="true"
          className={cn("h-4 rounded-sm bg-surface-2 motion-safe:animate-pulse", i === lines - 1 && lines > 1 ? "w-2/3" : "w-full")}
        />
      ))}
    </div>
  );
}
