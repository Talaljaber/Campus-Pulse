"use client";

import { useT } from "@/i18n";
import type { BenchmarkRow } from "@/lib/ai/types";
import {
  TARGETS,
  benchmarkView,
  fixed2,
  hasPerSetRows,
  isOurTest,
  type BenchmarkView,
  type Cell,
} from "@/lib/lab/metrics";
import { Badge } from "../ui/Badge";
import { EmptyState } from "../ui/EmptyState";
import { MiniBar, Sizes, SmallSampleBadge, TableBox, useDatasetHelp, useDatasetLabel, useTargetLabel } from "./parts";

/** Props for {@link BenchmarkTable}. */
export interface BenchmarkTableProps {
  /** `MetricsResponse.benchmark`. */
  rows: readonly BenchmarkRow[];
}

function ScoreCell({ cell }: { cell: Cell | undefined }) {
  const t = useT();
  if (!cell) {
    return (
      <>
        <span aria-hidden="true">-</span>
        <span className="sr-only">{t("lab.benchmark.none")}</span>
      </>
    );
  }
  if (cell.status !== "ok" || cell.macroF1 === null) {
    return (
      <div className="flex flex-col items-start gap-1">
        <Badge tone="neutral" icon={null}>
          {cell.status === "cut" ? t("lab.benchmark.cut") : t("lab.benchmark.na")}
        </Badge>
        {cell.nRows > 0 && <Sizes nRows={cell.nRows} nGroups={cell.nGroups} />}
      </div>
    );
  }
  return (
    <div className="flex min-w-28 flex-col items-start gap-1">
      <span className="text-base font-semibold tabular-nums">{fixed2(cell.macroF1)}</span>
      <MiniBar value={cell.macroF1} />
      {cell.accuracy !== null && <span className="text-xs text-fg-2">{t("lab.benchmark.accuracy", { value: fixed2(cell.accuracy) })}</span>}
      <Sizes nRows={cell.nRows} nGroups={cell.nGroups} />
      <SmallSampleBadge nRows={cell.nRows} nGroups={cell.nGroups} />
    </div>
  );
}

function TargetTable({ view }: { view: BenchmarkView }) {
  const t = useT();
  const datasetLabel = useDatasetLabel();
  const targetLabel = useTargetLabel();
  const caption = t("lab.benchmark.caption", { target: targetLabel(view.target) });
  return (
    <section aria-label={caption} className="flex flex-col gap-2">
      <h4 className="text-base font-semibold">{targetLabel(view.target)}</h4>
      <TableBox label={caption}>
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-surface-2 text-fg-2">
            <tr>
              <th scope="col" className="px-3 py-2 text-start font-semibold">
                {t("lab.benchmark.model")}
              </th>
              {view.columns.map((c) => (
                <th key={c} scope="col" className="px-3 py-2 text-start font-semibold">
                  {datasetLabel(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {view.rows.map((row) => (
              <tr key={row.model} className="border-t border-line align-top">
                <th scope="row" className="px-3 py-2 text-start font-medium text-fg-1">
                  {row.model}
                </th>
                {view.columns.map((c) => (
                  <td key={c} className="px-3 py-2 text-fg-1">
                    <ScoreCell cell={row.cells[c]} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </TableBox>
    </section>
  );
}

/**
 * The model comparison (SPEC section 6.2): one table per target, a row per model, a column per
 * dataset. Scenario-held-out cross-validation sits next to each part of our own test set and the
 * pooled set, and every number carries its row and group counts. A number resting on fewer than
 * 30 groups says so. The column legend and the reading notes sit under the tables so the caveats
 * are on the page with the numbers, not in a footnote elsewhere.
 */
export function BenchmarkTable({ rows }: BenchmarkTableProps) {
  const t = useT();
  const datasetLabel = useDatasetLabel();
  const datasetHelp = useDatasetHelp();
  const views = TARGETS.map((target) => benchmarkView(rows, target)).filter((v) => v.rows.length > 0);
  if (views.length === 0) return <EmptyState title={t("lab.empty.title")} hint={t("lab.empty.hint")} />;

  const columns = [...new Set(views.flatMap((v) => v.columns))];
  const perSet = hasPerSetRows(rows);
  const showsTest = columns.some(isOurTest);
  return (
    <div className="flex flex-col gap-4">
      <p className="text-fg-2">{t("lab.benchmark.intro")}</p>
      {views.map((v) => (
        <TargetTable key={v.target} view={v} />
      ))}
      <div className="flex flex-col gap-3 rounded-lg border border-line bg-surface-1 p-4">
        <h4 className="text-base font-semibold">{t("lab.benchmark.readingTitle")}</h4>
        <ul className="list-disc ps-5 text-sm text-fg-2">
          <li>{t("lab.benchmark.readGroups")}</li>
          {showsTest && !perSet && <li>{t("lab.benchmark.noSets")}</li>}
          {perSet && <li>{t("lab.benchmark.readSets")}</li>}
        </ul>
        <h5 className="text-sm font-semibold">{t("lab.benchmark.datasetsTitle")}</h5>
        <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
          {columns.map((c) => (
            <div key={c} className="contents">
              <dt className="font-medium text-fg-1">{datasetLabel(c)}</dt>
              <dd className="text-fg-2">{datasetHelp(c)}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
