"use client";

import { useT } from "@/i18n";
import type { CoverageRow } from "@/lib/ai/types";
import { coverageGroups, fixed2, percent } from "@/lib/lab/metrics";
import { MiniBar, Sizes, SmallSampleBadge, TableBox, useDatasetLabel, useLangLabel, useTargetLabel } from "./parts";

/** Props for {@link CoverageChart}. */
export interface CoverageChartProps {
  /** `MetricsResponse.coverage`. */
  rows: readonly CoverageRow[];
}

/**
 * Conformal coverage and set size, one table per target: how often the true label is inside the
 * prediction set, the mean set size and the share of single-label sets, per dataset and language,
 * each with its row and group counts. The numbers are the content; the bar only repeats coverage.
 * The caveat that coverage is approximate sits right under the tables.
 */
export function CoverageChart({ rows }: CoverageChartProps) {
  const t = useT();
  const datasetLabel = useDatasetLabel();
  const langLabel = useLangLabel();
  const targetLabel = useTargetLabel();
  const groups = coverageGroups(rows);
  if (groups.length === 0) return null;
  return (
    <section className="flex flex-col gap-3" aria-label={t("lab.coverage.title")}>
      <h3 className="text-lg font-semibold">{t("lab.coverage.title")}</h3>
      <p className="text-fg-2">{t("lab.coverage.intro")}</p>
      {groups.map((g) => {
        const caption = t("lab.coverage.caption", { target: targetLabel(g.target) });
        return (
          <div key={g.target} className="flex flex-col gap-2">
            <h4 className="text-base font-semibold">{targetLabel(g.target)}</h4>
            <TableBox label={caption}>
              <table className="w-full border-collapse text-sm">
                <caption className="sr-only">{caption}</caption>
                <thead className="bg-surface-2 text-fg-2">
                  <tr>
                    {(["slice", "coverage", "setSize", "singleton", "sizes"] as const).map((k) => (
                      <th key={k} scope="col" className="px-3 py-2 text-start font-semibold">
                        {t(`lab.coverage.${k}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {g.rows.map((r) => (
                    <tr key={`${r.key}|${r.lang}`} className="border-t border-line align-top">
                      <th scope="row" className="px-3 py-2 text-start font-medium">
                        {datasetLabel(r.key)}, {langLabel(r.lang)}
                      </th>
                      <td className="px-3 py-2">
                        <div className="flex min-w-28 flex-col gap-1">
                          <span className="font-semibold tabular-nums">{percent(r.coverage)}</span>
                          <MiniBar value={r.coverage} />
                        </div>
                      </td>
                      <td className="px-3 py-2 tabular-nums">{fixed2(r.mean_set_size)}</td>
                      <td className="px-3 py-2 tabular-nums">{percent(r.singleton_rate)}</td>
                      <td className="px-3 py-2">
                        <div className="flex flex-col items-start gap-1">
                          <Sizes nRows={r.n_rows} nGroups={r.n_groups} />
                          <SmallSampleBadge nRows={r.n_rows} nGroups={r.n_groups} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableBox>
          </div>
        );
      })}
      <p className="text-sm text-fg-2">{t("lab.coverage.caveat")}</p>
    </section>
  );
}
