"use client";

import { useT, type DictKey } from "@/i18n";
import type { RouterStats as RouterStatsDto } from "@/lib/ai/types";
import { percent, tierRows, usd } from "@/lib/lab/metrics";
import { MiniBar, TableBox } from "./parts";

/** Props for {@link RouterStats}. */
export interface RouterStatsProps {
  /** `MetricsResponse.router`. */
  router: RouterStatsDto;
}

const KNOWN_TIERS = ["tier0", "tier1", "human"];

/** One labelled number. */
export function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border border-line bg-surface-0 p-3">
      <dt className="text-sm text-fg-2">{label}</dt>
      <dd className="text-xl font-semibold tabular-nums text-fg-1">{value}</dd>
    </div>
  );
}

/**
 * The live router: how many requests were decided offline (tier 0), by an LLM (tier 1) or sent to
 * a person, and what the LLM tiers cost. `resolved_tier0_pct` is already a percentage from 0 to 100.
 */
export function RouterStats({ router }: RouterStatsProps) {
  const t = useT();
  const tiers = tierRows(router);
  return (
    <section className="flex flex-col gap-3" aria-label={t("lab.router.title")}>
      <h3 className="text-lg font-semibold">{t("lab.router.title")}</h3>
      <p className="text-fg-2">{t("lab.router.intro")}</p>
      {router.total === 0 ? (
        <p className="rounded-lg border border-dashed border-line-strong p-4 text-fg-2">{t("lab.router.none")}</p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Stat label={t("lab.router.total")} value={String(router.total)} />
            <Stat label={t("lab.router.tier0Pct")} value={percent(router.resolved_tier0_pct / 100)} />
            <Stat label={t("lab.router.cost")} value={usd(router.cost_usd)} />
            <Stat label={t("lab.router.costPer1k")} value={usd(router.cost_per_1k_usd)} />
            <Stat label={t("lab.router.cached")} value={String(router.cached_calls)} />
          </dl>
          <TableBox label={t("lab.router.caption")}>
            <table className="w-full border-collapse text-sm">
              <caption className="sr-only">{t("lab.router.caption")}</caption>
              <thead className="bg-surface-2 text-fg-2">
                <tr>
                  {(["tier", "count", "share"] as const).map((k) => (
                    <th key={k} scope="col" className="px-3 py-2 text-start font-semibold">
                      {t(`lab.router.${k}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tiers.map((r) => (
                  <tr key={r.tier} className="border-t border-line">
                    <th scope="row" className="px-3 py-2 text-start font-medium">
                      {KNOWN_TIERS.includes(r.tier) ? t(`lab.router.tiers.${r.tier}` as DictKey) : r.tier}
                    </th>
                    <td className="px-3 py-2 tabular-nums">{r.count}</td>
                    <td className="px-3 py-2">
                      <div className="flex min-w-28 flex-col gap-1">
                        <span className="tabular-nums">{percent(r.share)}</span>
                        <MiniBar value={r.share} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableBox>
        </>
      )}
    </section>
  );
}
