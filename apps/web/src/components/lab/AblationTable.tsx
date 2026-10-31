"use client";

import { useT } from "@/i18n";
import type { AblationRow } from "@/lib/ai/types";
import { datasetKeyOf, fixed2, points } from "@/lib/lab/metrics";
import { Badge } from "../ui/Badge";
import { TableBox, useDatasetLabel, useTargetLabel } from "./parts";

/** Props for {@link AblationTable}. */
export interface AblationTableProps {
  /** `MetricsResponse.ablations`. */
  rows: readonly AblationRow[];
}

/**
 * What each ablation arm scores and how far it moves from the full system. The change is printed
 * in points with a sign, so a drop is readable without colour; renders nothing when there are none.
 */
export function AblationTable({ rows }: AblationTableProps) {
  const t = useT();
  const datasetLabel = useDatasetLabel();
  const targetLabel = useTargetLabel();
  if (rows.length === 0) return null;
  return (
    <section className="flex flex-col gap-2" aria-label={t("lab.ablation.title")}>
      <h3 className="text-lg font-semibold">{t("lab.ablation.title")}</h3>
      <p className="text-fg-2">{t("lab.ablation.intro")}</p>
      <TableBox label={t("lab.ablation.caption")}>
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">{t("lab.ablation.caption")}</caption>
          <thead className="bg-surface-2 text-fg-2">
            <tr>
              {(["arm", "target", "dataset", "f1", "delta"] as const).map((k) => (
                <th key={k} scope="col" className="px-3 py-2 text-start font-semibold">
                  {t(`lab.ablation.${k}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.arm}|${r.target}|${r.dataset}`} className="border-t border-line">
                <th scope="row" className="px-3 py-2 text-start font-medium">
                  {r.arm}
                </th>
                <td className="px-3 py-2">{targetLabel(r.target)}</td>
                <td className="px-3 py-2">{datasetLabel(datasetKeyOf(r.dataset))}</td>
                <td className="px-3 py-2 tabular-nums">{r.macro_f1 === null ? "-" : fixed2(r.macro_f1)}</td>
                <td className="px-3 py-2 tabular-nums">
                  {r.delta === null ? (
                    "-"
                  ) : (
                    <Badge tone={r.delta < 0 ? "warn" : "neutral"} icon={null}>
                      <span dir="ltr">{points(r.delta)}</span>
                    </Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableBox>
    </section>
  );
}
