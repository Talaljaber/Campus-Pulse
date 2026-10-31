"use client";

import { labelOf, useLang, useT, type DictKey } from "@/i18n";
import type { RedTeamFailure, Scorecard } from "@/lib/ai/types";
import { percent, rateRows } from "@/lib/lab/metrics";
import { RED_TEAM_STYLES } from "@/lib/lab/redteam";
import { formatDateTime } from "@/lib/time";
import { Badge } from "../ui/Badge";
import { EmptyState } from "../ui/EmptyState";
import { MiniBar, TableBox, useLangLabel } from "./parts";

/** Props for {@link ScorecardHistory}. */
export interface ScorecardHistoryProps {
  /** Scorecards, newest first. */
  runs: readonly Scorecard[];
}

const OUTCOMES = ["accept", "ask", "escalate", "human_review", "out_of_scope", "distress"];

function RateTable({ caption, rates, label }: { caption: string; rates: Record<string, number>; label: (key: string) => string }) {
  const rows = rateRows(rates);
  if (rows.length === 0) return null;
  return (
    <TableBox label={caption}>
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t border-line first:border-t-0">
              <th scope="row" className="px-3 py-2 text-start font-medium">
                {label(r.key)}
              </th>
              <td className="w-1/2 px-3 py-2">
                <div className="flex flex-col gap-1">
                  <span className="tabular-nums">{percent(r.rate)}</span>
                  <MiniBar value={r.rate} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableBox>
  );
}

function Failures({ run }: { run: Scorecard }) {
  const t = useT();
  const { lang } = useLang();
  const styleLabel = useStyleLabel();
  const caption = t("lab.history.failureCaption", { id: run.run_id });
  const got = (f: RedTeamFailure): string =>
    f.got_category === null || f.got_priority === null
      ? t("lab.history.noDecision")
      : `${labelOf("category", f.got_category, lang)}, ${labelOf("priority", f.got_priority, lang)}`;
  const outcome = (o: string): string => (OUTCOMES.includes(o) ? t(`lab.history.outcomes.${o}` as DictKey) : o);
  return (
    <TableBox label={caption}>
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-surface-2 text-fg-2">
          <tr>
            {(["text", "style", "intended", "got", "outcome", "reason"] as const).map((k) => (
              <th key={k} scope="col" className="px-3 py-2 text-start font-semibold">
                {t(`lab.history.${k}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {run.failures.map((f, i) => (
            <tr key={`${i}|${f.text}`} className="border-t border-line align-top">
              <td className="min-w-48 px-3 py-2 break-words" dir="auto">
                {f.text}
              </td>
              <td className="px-3 py-2">{styleLabel(f.style)}</td>
              <td className="px-3 py-2">
                {labelOf("category", f.intended_category, lang)}, {labelOf("priority", f.intended_priority, lang)}
              </td>
              <td className="px-3 py-2">{got(f)}</td>
              <td className="px-3 py-2">{outcome(f.outcome)}</td>
              <td className="min-w-48 px-3 py-2 break-words" dir="auto">
                {f.reason}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableBox>
  );
}

/** Label for an attack style: translated when known, as written otherwise. */
function useStyleLabel(): (key: string) => string {
  const t = useT();
  return (key) => ((RED_TEAM_STYLES as readonly string[]).includes(key) ? t(`lab.redteam.style.${key}` as DictKey) : key);
}

/**
 * Red-team scorecards, newest first. Each run shows when it ran, how many attacks, the seed and the
 * overall pass rate; then the pass rate per style and per language (weakest first, so the weak
 * spot is read first) and, folded away, the items that failed with what was intended, what came
 * back and why. All numbers are printed; the bars only repeat them.
 */
export function ScorecardHistory({ runs }: ScorecardHistoryProps) {
  const t = useT();
  const { lang } = useLang();
  const styleLabel = useStyleLabel();
  const langLabel = useLangLabel();
  return (
    <section aria-label={t("lab.history.title")} className="flex flex-col gap-3">
      <h3 className="text-lg font-semibold">{t("lab.history.title")}</h3>
      {runs.length === 0 ? (
        <EmptyState title={t("lab.history.empty")} hint={t("lab.history.emptyHint")} />
      ) : (
        <ol aria-label={t("lab.history.caption")} className="flex flex-col gap-4">
          {runs.map((run) => (
            <li key={run.run_id} className="flex flex-col gap-3 rounded-lg border border-line bg-surface-1 p-4" data-testid="scorecard">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="text-lg font-semibold tabular-nums">{t("lab.history.overall")}: {percent(run.overall)}</span>
                <span className="text-sm text-fg-2">{formatDateTime(run.created_at, lang)}</span>
                <span className="text-sm text-fg-2">
                  {t("lab.history.n")}: <span className="tabular-nums">{run.n}</span>
                </span>
                <span className="text-sm text-fg-2">
                  {t("lab.history.seed")}: <span className="tabular-nums">{run.seed}</span>
                </span>
                <Badge tone={run.failures.length === 0 ? "ok" : "warn"}>
                  {run.failures.length === 0 ? t("lab.history.noFailures") : t("lab.history.failures", { count: run.failures.length })}
                </Badge>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <RateTable caption={t("lab.history.byStyle")} rates={run.by_style} label={styleLabel} />
                <RateTable caption={t("lab.history.byLang")} rates={run.by_lang} label={langLabel} />
              </div>
              {run.failures.length > 0 && (
                <details className="rounded-md border border-line bg-surface-0 p-3">
                  <summary className="cursor-pointer font-medium">{t("lab.history.failures", { count: run.failures.length })}</summary>
                  <div className="mt-3">
                    <Failures run={run} />
                  </div>
                </details>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
