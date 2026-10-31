"use client";

import { labelOf, useLang, useT } from "@/i18n";
import type { MemoryStats as MemoryStatsDto } from "@/lib/ai/types";
import { memoryRows } from "@/lib/lab/metrics";
import { formatDateTime } from "@/lib/time";
import { TableBox } from "./parts";
import { Stat } from "./RouterStats";

/** Props for {@link MemoryStats}. */
export interface MemoryStatsProps {
  /** `MetricsResponse.memory`. */
  memory: MemoryStatsDto;
}

/**
 * Live memory: how many staff corrections are active, how many were ever added, when the last one
 * arrived (Amman time) and the active examples per category.
 */
export function MemoryStats({ memory }: MemoryStatsProps) {
  const t = useT();
  const { lang } = useLang();
  const rows = memoryRows(memory.by_category);
  return (
    <section className="flex flex-col gap-3" aria-label={t("lab.memory.title")}>
      <h3 className="text-lg font-semibold">{t("lab.memory.title")}</h3>
      <p className="text-fg-2">{t("lab.memory.intro")}</p>
      {memory.total === 0 ? (
        <p className="rounded-lg border border-dashed border-line-strong p-4 text-fg-2">{t("lab.memory.none")}</p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <Stat label={t("lab.memory.active")} value={String(memory.active)} />
            <Stat label={t("lab.memory.total")} value={String(memory.total)} />
            <Stat
              label={t("lab.memory.lastAdded")}
              value={memory.last_added_at ? formatDateTime(memory.last_added_at, lang) : t("lab.memory.never")}
            />
          </dl>
          {rows.length > 0 && (
            <TableBox label={t("lab.memory.caption")}>
              <table className="w-full border-collapse text-sm">
                <caption className="sr-only">{t("lab.memory.caption")}</caption>
                <thead className="bg-surface-2 text-fg-2">
                  <tr>
                    <th scope="col" className="px-3 py-2 text-start font-semibold">
                      {t("lab.memory.category")}
                    </th>
                    <th scope="col" className="px-3 py-2 text-start font-semibold">
                      {t("lab.memory.count")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.category} className="border-t border-line">
                      <th scope="row" className="px-3 py-2 text-start font-medium">
                        {labelOf("category", r.category, lang)}
                      </th>
                      <td className="px-3 py-2 tabular-nums">{r.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableBox>
          )}
        </>
      )}
    </section>
  );
}
