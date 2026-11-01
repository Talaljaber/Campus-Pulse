/**
 * Pure helpers that turn the `GET /v1/metrics` response into what the model lab renders.
 * No fetching and no React: the components only lay these shapes out.
 *
 * About the `dataset` field. The API contract names seven datasets (`oof_official`, `oof_all`,
 * `our_test`, `our_test_set1`, `our_test_set2`, `our_test_set3`, `probes`), where `our_test` is the
 * pooled own test set. The own test set has three parts (`set1` written by hand by the team, `set2`
 * and `set3` by a language model) and each is shown next to the pooled numbers, so any row whose
 * dataset reads `our_test_set1`, `our_test:set1`, `our_test/set1` or just `set1` is placed in that
 * set's column. If a report carries no such rows the page shows the pooled column and says so. A
 * dataset name we do not know is shown as written, never dropped.
 *
 * M2-proto is a category-only model (it has no priority head), so its priority cells read "n/a"
 * whatever the report holds.
 */
import type { BenchmarkRow, CoverageRow, FairnessSlice, MetricsResponse, RouterStats, Scorecard } from "@/lib/ai/types";

/** A column of the benchmark: one dataset (or one part of the own test set). */
export type DatasetKey = string;

/** The columns in reading order. Anything not listed comes after, alphabetically. */
export const DATASET_ORDER: readonly string[] = ["oof_official", "oof_all", "set1", "set2", "set3", "pooled", "probes"];

/** The three parts of the own test set. */
export const TEST_SETS: readonly string[] = ["set1", "set2", "set3"];

/** Below this many independent groups (or rows when groups are unknown) a number is only indicative. */
export const SMALL_N = 30;

/** Maps the API's `dataset` string to a column key (see the module comment). */
export function datasetKeyOf(dataset: string): DatasetKey {
  const d = dataset.trim().toLowerCase();
  if (d === "our_test") return "pooled";
  const part = /^(?:our_test[\s:_./-]*)?(set[123]|pooled)$/.exec(d);
  if (part?.[1]) return part[1];
  return d;
}

/** Sort order of two column keys. */
export function compareDatasets(a: DatasetKey, b: DatasetKey): number {
  const ia = DATASET_ORDER.indexOf(a);
  const ib = DATASET_ORDER.indexOf(b);
  if (ia !== -1 && ib !== -1) return ia - ib;
  if (ia !== -1) return -1;
  if (ib !== -1) return 1;
  return a.localeCompare(b);
}

/** True when the key is one of the scenario-held-out cross-validation datasets. */
export const isCrossValidation = (key: DatasetKey): boolean => key === "oof_official" || key === "oof_all";

/** True when the key is a part of (or all of) our own test set. */
export const isOurTest = (key: DatasetKey): boolean => key === "pooled" || TEST_SETS.includes(key);

export type Target = "category" | "priority";
export const TARGETS: readonly Target[] = ["category", "priority"];

/** The M2-proto model (`MEMBER_NAMES["m2proto"]`), which has no priority result. */
export const isPrototypeModel = (model: string): boolean => model.trim().toLowerCase() === "m2-proto";

/** One benchmark number with the sizes it was measured on. */
export interface Cell {
  macroF1: number | null;
  accuracy: number | null;
  nRows: number;
  nGroups: number | null;
  status: BenchmarkRow["status"];
}

export interface BenchmarkView {
  target: Target;
  /** Dataset columns that have at least one row for this target, in reading order. */
  columns: DatasetKey[];
  rows: { model: string; cells: Record<DatasetKey, Cell | undefined> }[];
}

/**
 * Pivots the benchmark rows of one target into model rows by dataset column. Models keep the order
 * the report lists them in; when a model has two rows for one dataset the later one wins.
 */
export function benchmarkView(rows: readonly BenchmarkRow[], target: Target): BenchmarkView {
  const models: string[] = [];
  const byModel = new Map<string, Record<DatasetKey, Cell | undefined>>();
  const columns = new Set<DatasetKey>();
  for (const r of rows) {
    if (r.target !== target) continue;
    const key = datasetKeyOf(r.dataset);
    columns.add(key);
    let cells = byModel.get(r.model);
    if (!cells) {
      cells = {};
      byModel.set(r.model, cells);
      models.push(r.model);
    }
    cells[key] =
      target === "priority" && isPrototypeModel(r.model)
        ? { macroF1: null, accuracy: null, nRows: 0, nGroups: null, status: "n/a" }
        : { macroF1: r.macro_f1, accuracy: r.accuracy, nRows: r.n_rows, nGroups: r.n_groups, status: r.status };
  }
  return {
    target,
    columns: [...columns].sort(compareDatasets),
    rows: models.map((model) => ({ model, cells: byModel.get(model) ?? {} })),
  };
}

/** True when the rows carry numbers for at least one of set1, set2, set3. */
export function hasPerSetRows(rows: readonly { dataset: string }[]): boolean {
  return rows.some((r) => TEST_SETS.includes(datasetKeyOf(r.dataset)));
}

/** True when the number rests on fewer than {@link SMALL_N} independent groups. */
export function isSmallSample(nRows: number, nGroups: number | null): boolean {
  const n = nGroups ?? nRows;
  return n > 0 && n < SMALL_N;
}

const LANG_ORDER = ["all", "en", "ar", "arabizi"];
const langRank = (l: string): number => {
  const i = LANG_ORDER.indexOf(l);
  return i === -1 ? LANG_ORDER.length : i;
};

export interface CoverageGroup {
  target: Target;
  rows: (CoverageRow & { key: DatasetKey })[];
}

/** Coverage rows per target, ordered by dataset column then language (`all`, `en`, `ar`, `arabizi`). */
export function coverageGroups(rows: readonly CoverageRow[]): CoverageGroup[] {
  return TARGETS.map((target) => ({
    target,
    rows: rows
      .filter((r) => r.target === target)
      .map((r) => ({ ...r, key: datasetKeyOf(r.dataset) }))
      .sort((a, b) => compareDatasets(a.key, b.key) || langRank(a.lang) - langRank(b.lang) || a.lang.localeCompare(b.lang)),
  })).filter((g) => g.rows.length > 0);
}

export interface FairnessGroup {
  target: Target;
  dataset: DatasetKey;
  /** Slices in the order en, ar, arabizi, others. `gap` is macro-F1 minus the best slice's (0 or negative); null when unscored. */
  slices: { slice: string; macroF1: number | null; nRows: number; nGroups: number | null; gap: number | null }[];
}

/** Fairness slices grouped by target and dataset, each with its gap to the best slice. */
export function fairnessGroups(rows: readonly FairnessSlice[]): FairnessGroup[] {
  const groups = new Map<string, { target: Target; dataset: DatasetKey; items: FairnessSlice[] }>();
  for (const r of rows) {
    const dataset = datasetKeyOf(r.dataset);
    const id = `${r.target}|${dataset}`;
    const g = groups.get(id) ?? { target: r.target, dataset, items: [] };
    g.items.push(r);
    groups.set(id, g);
  }
  return [...groups.values()]
    .sort((a, b) => TARGETS.indexOf(a.target) - TARGETS.indexOf(b.target) || compareDatasets(a.dataset, b.dataset))
    .map((g) => {
      const best = Math.max(...g.items.map((i) => i.macro_f1 ?? -Infinity));
      return {
        target: g.target,
        dataset: g.dataset,
        slices: [...g.items]
          .sort((a, b) => langRank(a.slice) - langRank(b.slice) || a.slice.localeCompare(b.slice))
          .map((i) => ({
            slice: i.slice,
            macroF1: i.macro_f1,
            nRows: i.n_rows,
            nGroups: i.n_groups,
            gap: i.macro_f1 === null || !Number.isFinite(best) ? null : i.macro_f1 - best,
          })),
      };
    });
}

const TIER_ORDER = ["tier0", "tier1", "human"];

/** Router tiers with their share of all requests (0 to 1). Known tiers first. */
export function tierRows(router: RouterStats): { tier: string; count: number; share: number }[] {
  const entries = Object.entries(router.by_tier);
  const rank = (t: string): number => {
    const i = TIER_ORDER.indexOf(t);
    return i === -1 ? TIER_ORDER.length : i;
  };
  return entries
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
    .map(([tier, count]) => ({ tier, count, share: router.total > 0 ? count / router.total : 0 }));
}

/** Memory categories, most examples first. */
export function memoryRows(by: Record<string, number>): { category: string; count: number }[] {
  return Object.entries(by)
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count || a.category.localeCompare(b.category));
}

/** Pass rates (0 to 1) as rows, worst first, so the weak spot is the first thing read. */
export function rateRows(rates: Record<string, number>): { key: string; rate: number }[] {
  return Object.entries(rates)
    .map(([key, rate]) => ({ key, rate }))
    .sort((a, b) => a.rate - b.rate || a.key.localeCompare(b.key));
}

const time = (iso: string): number => {
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? 0 : ms;
};

/** Scorecards from this session and from the service, newest first, one per `run_id` (the service's copy wins). */
export function mergeScorecards(local: readonly Scorecard[], remote: readonly Scorecard[]): Scorecard[] {
  const byId = new Map<string, Scorecard>();
  for (const s of local) byId.set(s.run_id, s);
  for (const s of remote) byId.set(s.run_id, s);
  return [...byId.values()].sort((a, b) => time(b.created_at) - time(a.created_at));
}

/** True when the offline report has not been written: every offline section is empty. */
export function noOfflineReport(m: MetricsResponse): boolean {
  return (
    m.generated_at === null &&
    m.benchmark.length === 0 &&
    m.coverage.length === 0 &&
    m.fairness.length === 0 &&
    m.calibration.length === 0 &&
    m.ablations.length === 0 &&
    m.confusions.length === 0
  );
}

/** Two decimals, for scores in 0 to 1. */
export const fixed2 = (x: number): string => x.toFixed(2);
/** A whole percent, for rates in 0 to 1. */
export const percent = (x: number): string => `${Math.round(x * 100)}%`;
/** A signed difference in points of 100, e.g. `-0.05` gives `-5`. */
export const points = (delta: number): string => {
  const p = Math.round(delta * 100);
  return p > 0 ? `+${p}` : String(p);
};
/** A dollar amount with enough digits for fractions of a cent. */
export const usd = (x: number): string => `$${x < 0.01 && x > 0 ? x.toFixed(4) : x.toFixed(2)}`;
