"use client";

import { useT } from "@/i18n";
import type { CalibrationCurve } from "@/lib/ai/types";
import { fixed2, percent } from "@/lib/lab/metrics";
import { TableBox, useTargetLabel } from "./parts";

/** Props for {@link CalibrationTable}. */
export interface CalibrationTableProps {
  /** `MetricsResponse.calibration`. */
  curves: readonly CalibrationCurve[];
}

/**
 * Reliability bins per target with the expected calibration error. A well-calibrated model has
 * mean confidence close to actual accuracy in every bin; both are printed so the gap can be read
 * directly. Renders nothing when the report has no calibration section.
 */
export function CalibrationTable({ curves }: CalibrationTableProps) {
  const t = useT();
  const targetLabel = useTargetLabel();
  if (curves.length === 0) return null;
  return (
    <section className="flex flex-col gap-3" aria-label={t("lab.calibration.title")}>
      <h3 className="text-lg font-semibold">{t("lab.calibration.title")}</h3>
      <p className="text-fg-2">{t("lab.calibration.intro")}</p>
      {curves.map((c) => {
        const caption = t("lab.calibration.caption", { target: targetLabel(c.target) });
        return (
          <div key={c.target} className="flex flex-col gap-2">
            <p className="font-medium">{t("lab.calibration.ece", { target: targetLabel(c.target), value: c.ece.toFixed(3) })}</p>
            <TableBox label={caption}>
              <table className="w-full border-collapse text-sm">
                <caption className="sr-only">{caption}</caption>
                <thead className="bg-surface-2 text-fg-2">
                  <tr>
                    {(["range", "confidence", "accuracy", "count"] as const).map((k) => (
                      <th key={k} scope="col" className="px-3 py-2 text-start font-semibold">
                        {t(`lab.calibration.${k}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {c.bins.map((b) => (
                    <tr key={`${b.lower}-${b.upper}`} className="border-t border-line">
                      <th scope="row" className="px-3 py-2 text-start font-medium">
                        {t("lab.calibration.rangeValue", { lower: fixed2(b.lower), upper: fixed2(b.upper) })}
                      </th>
                      <td className="px-3 py-2 tabular-nums">{percent(b.confidence)}</td>
                      <td className="px-3 py-2 tabular-nums">{percent(b.accuracy)}</td>
                      <td className="px-3 py-2 tabular-nums">{b.count}</td>
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
