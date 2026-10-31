"use client";

import type { ReactNode } from "react";
import { useT, type DictKey } from "@/i18n";
import { DATASET_ORDER, isSmallSample, type Target } from "@/lib/lab/metrics";
import { Badge } from "../ui/Badge";
import { cn } from "../ui/cn";

/**
 * Small pieces the lab sections share. Nothing here fetches or decides: they only lay out numbers
 * that `lib/lab/metrics.ts` already shaped.
 */

/** A thin bar for a value from 0 to 1. Decorative: the number is always printed next to it. */
export function MiniBar({ value, className }: { value: number; className?: string }) {
  const pct = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0)) * 100;
  return (
    <span aria-hidden="true" className={cn("block h-1.5 w-full min-w-16 overflow-hidden rounded-full bg-surface-2", className)}>
      <span className="block h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
    </span>
  );
}

/** The wrapper every lab table sits in: a labelled, focusable scroll region so wide tables stay reachable by keyboard. */
export function TableBox({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}

/** The "Small sample" badge, shown when a number rests on fewer than 30 groups. */
export function SmallSampleBadge({ nRows, nGroups }: { nRows: number; nGroups: number | null }) {
  const t = useT();
  if (!isSmallSample(nRows, nGroups)) return null;
  return (
    <Badge tone="warn">
      {t("lab.small")}
    </Badge>
  );
}

/** "432 rows, 30 groups", or just the rows when the groups are unknown. */
export function Sizes({ nRows, nGroups }: { nRows: number; nGroups: number | null }) {
  const t = useT();
  return (
    <span className="text-xs text-fg-3">
      {nGroups === null ? t("lab.benchmark.sizesRows", { rows: nRows }) : t("lab.benchmark.sizes", { rows: nRows, groups: nGroups })}
    </span>
  );
}

/** Label for a dataset column key: translated when known, as written otherwise. */
export function useDatasetLabel(): (key: string) => string {
  const t = useT();
  return (key) => (DATASET_ORDER.includes(key) ? t(`lab.dataset.${key}` as DictKey) : key);
}

/** One-sentence description of a dataset column, empty for a column we do not know. */
export function useDatasetHelp(): (key: string) => string {
  const t = useT();
  return (key) => (DATASET_ORDER.includes(key) ? t(`lab.datasetHelp.${key}` as DictKey) : "");
}

/** Label for a language slice (`all`, `en`, `ar`, `arabizi`). */
export function useLangLabel(): (key: string) => string {
  const t = useT();
  return (key) => (["all", "en", "ar", "arabizi"].includes(key) ? t(`lab.lang.${key}` as DictKey) : key);
}

/** Label for a target (`category`, `priority`). */
export function useTargetLabel(): (target: Target) => string {
  const t = useT();
  return (target) => t(`lab.target.${target}` as DictKey);
}

