"use client";

import type { CSSProperties } from "react";
import { labelOf, useLang, useT } from "@/i18n";
import type { Confusion } from "@/lib/ai/types";
import { datasetKeyOf, percent } from "@/lib/lab/metrics";
import { TableBox, useDatasetLabel, useTargetLabel } from "./parts";

/** Props for {@link ConfusionMatrix}. */
export interface ConfusionMatrixProps {
  /** `MetricsResponse.confusions`. */
  confusions: readonly Confusion[];
}

/** The strongest tint a cell gets. The text stays the primary colour, so it keeps its contrast on the tint. */
const MAX_TINT = 32;

/** Tint of a cell: green on the diagonal (correct), red off it (a mix-up), stronger for a bigger share of the row. */
function tint(share: number, correct: boolean): CSSProperties {
  const pct = Math.round(Math.max(0, Math.min(1, share)) * MAX_TINT);
  const tone = correct ? "var(--cp-ok)" : "var(--cp-danger)";
  return { backgroundColor: `color-mix(in srgb, ${tone} ${pct}%, var(--cp-surface-0))` };
}

/**
 * Confusion matrices as tables: true label down the side, predicted label across the top, with the
 * row total and, in each cell, the count and its share of that row. The tint repeats the share
 * (green for correct, red for a mix-up) and the diagonal is also bold and outlined, so the matrix
 * reads without colour. Category and priority names follow the page language.
 */
export function ConfusionMatrix({ confusions }: ConfusionMatrixProps) {
  const t = useT();
  const { lang } = useLang();
  const datasetLabel = useDatasetLabel();
  const targetLabel = useTargetLabel();
  if (confusions.length === 0) return null;
  return (
    <section className="flex flex-col gap-3" aria-label={t("lab.confusion.title")}>
      <h3 className="text-lg font-semibold">{t("lab.confusion.title")}</h3>
      <p className="text-fg-2">{t("lab.confusion.intro")}</p>
      {confusions.map((c) => {
        const name = (label: string) => labelOf(c.target, label, lang);
        const caption = t("lab.confusion.caption", {
          model: c.model,
          target: targetLabel(c.target),
          dataset: datasetLabel(datasetKeyOf(c.dataset)),
        });
        return (
          <div key={`${c.model}|${c.target}|${c.dataset}`} className="flex flex-col gap-2">
            <h4 className="text-base font-semibold">{caption}</h4>
            <TableBox label={caption}>
              <table className="w-full border-collapse text-center text-sm">
                <caption className="sr-only">{caption}</caption>
                <thead className="bg-surface-2 text-fg-2">
                  <tr>
                    <th scope="col" className="px-3 py-2 text-start font-semibold">
                      {t("lab.confusion.trueLabel")} / {t("lab.confusion.predicted")}
                    </th>
                    {c.labels.map((l) => (
                      <th key={l} scope="col" className="px-3 py-2 font-semibold">
                        {name(l)}
                      </th>
                    ))}
                    <th scope="col" className="px-3 py-2 font-semibold">
                      {t("lab.confusion.total")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {c.labels.map((rowLabel, i) => {
                    const row = c.matrix[i] ?? [];
                    const total = row.reduce((a, b) => a + b, 0);
                    return (
                      <tr key={rowLabel} className="border-t border-line">
                        <th scope="row" className="px-3 py-2 text-start font-medium">
                          {name(rowLabel)}
                        </th>
                        {c.labels.map((colLabel, j) => {
                          const n = row[j] ?? 0;
                          const share = total > 0 ? n / total : 0;
                          const correct = i === j;
                          return (
                            <td
                              key={colLabel}
                              style={tint(share, correct)}
                              className={correct ? "border-2 border-line-strong px-3 py-2 font-bold text-fg-1" : "px-3 py-2 text-fg-1"}
                            >
                              <span className="tabular-nums">{n}</span>
                              <span className="block text-xs font-normal text-fg-2 tabular-nums">{percent(share)}</span>
                            </td>
                          );
                        })}
                        <td className="px-3 py-2 tabular-nums text-fg-2">{total}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </TableBox>
          </div>
        );
      })}
    </section>
  );
}
