"use client";

import { useT } from "@/i18n";
import type { FairnessSlice } from "@/lib/ai/types";
import { fairnessGroups, fixed2, points } from "@/lib/lab/metrics";
import { Badge } from "../ui/Badge";
import { MiniBar, Sizes, SmallSampleBadge, TableBox, useDatasetLabel, useLangLabel, useTargetLabel } from "./parts";

/** Props for {@link FairnessChart}. */
export interface FairnessChartProps {
  /** `MetricsResponse.fairness`. */
  rows: readonly FairnessSlice[];
}

/**
 * Macro-F1 per language slice (English, Arabic, Arabizi), one table per target and dataset. The
 * gap to the best slice is printed in points, and the best slice is named, so a weaker language is
 * visible without colour. Each slice carries its counts and a small-sample marker, because the
 * Arabizi slice is usually the smallest.
 */
export function FairnessChart({ rows }: FairnessChartProps) {
  const t = useT();
  const datasetLabel = useDatasetLabel();
  const langLabel = useLangLabel();
  const targetLabel = useTargetLabel();
  const groups = fairnessGroups(rows);
  if (groups.length === 0) return null;
  return (
    <section className="flex flex-col gap-3" aria-label={t("lab.fairness.title")}>
      <h3 className="text-lg font-semibold">{t("lab.fairness.title")}</h3>
      <p className="text-fg-2">{t("lab.fairness.intro")}</p>
      {groups.map((g) => {
        const caption = t("lab.fairness.caption", { target: targetLabel(g.target), dataset: datasetLabel(g.dataset) });
        return (
          <div key={`${g.target}|${g.dataset}`} className="flex flex-col gap-2">
            <h4 className="text-base font-semibold">
              {targetLabel(g.target)}, {datasetLabel(g.dataset)}
            </h4>
            <TableBox label={caption}>
              <table className="w-full border-collapse text-sm">
                <caption className="sr-only">{caption}</caption>
                <thead className="bg-surface-2 text-fg-2">
                  <tr>
                    {(["slice", "f1", "gap", "sizes"] as const).map((k) => (
                      <th key={k} scope="col" className="px-3 py-2 text-start font-semibold">
                        {t(`lab.fairness.${k}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {g.slices.map((s) => (
                    <tr key={s.slice} className="border-t border-line align-top">
                      <th scope="row" className="px-3 py-2 text-start font-medium">
                        {langLabel(s.slice)}
                      </th>
                      <td className="px-3 py-2">
                        {s.macroF1 === null ? (
                          "-"
                        ) : (
                          <div className="flex min-w-28 flex-col gap-1">
                            <span className="font-semibold tabular-nums">{fixed2(s.macroF1)}</span>
                            <MiniBar value={s.macroF1} />
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {s.gap === null ? (
                          "-"
                        ) : Math.abs(s.gap) < 0.005 ? (
                          <Badge tone="ok">{t("lab.fairness.best")}</Badge>
                        ) : (
                          <span dir="ltr">{points(s.gap)}</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-col items-start gap-1">
                          <Sizes nRows={s.nRows} nGroups={s.nGroups} />
                          <SmallSampleBadge nRows={s.nRows} nGroups={s.nGroups} />
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
    </section>
  );
}
