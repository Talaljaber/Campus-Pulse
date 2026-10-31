import { describe, expect, it } from "vitest";
import metricsFixture from "@fixtures/metrics.json";
import type { AiFail } from "@/lib/ai/result";
import type { BenchmarkRow, CoverageRow, FairnessSlice, MetricsResponse, Scorecard } from "@/lib/ai/types";
import {
  benchmarkView,
  coverageGroups,
  datasetKeyOf,
  fairnessGroups,
  fixed2,
  hasPerSetRows,
  isSmallSample,
  memoryRows,
  mergeScorecards,
  noOfflineReport,
  percent,
  points,
  rateRows,
  tierRows,
  usd,
} from "../metrics";
import { RED_TEAM_MAX_N, RED_TEAM_STYLES, redTeamRequest, validRedTeamN } from "../redteam";
import { labErrorKind } from "../service";

const METRICS = metricsFixture.response as MetricsResponse;

/** A row whose dataset may be a per-set name the generated contract type does not list yet. */
const bench = (o: Omit<Partial<BenchmarkRow>, "dataset"> & { dataset?: string }): BenchmarkRow => ({
  model: "M2-LR",
  target: "category",
  dataset: "oof_official",
  macro_f1: 0.8,
  accuracy: 0.82,
  n_rows: 400,
  n_groups: 30,
  status: "ok",
  ...o,
} as BenchmarkRow);

describe("datasetKeyOf", () => {
  it("keeps the contract names and reads our_test as the pooled set", () => {
    expect(datasetKeyOf("oof_official")).toBe("oof_official");
    expect(datasetKeyOf("oof_all")).toBe("oof_all");
    expect(datasetKeyOf("probes")).toBe("probes");
    expect(datasetKeyOf("our_test")).toBe("pooled");
  });

  it("places a part of our own test set in its column, whatever the separator", () => {
    for (const d of ["our_test:set1", "our_test_set1", "our_test/set1", "our_test.set1", "set1", "OUR_TEST:SET1"]) {
      expect(datasetKeyOf(d)).toBe("set1");
    }
    expect(datasetKeyOf("our_test:pooled")).toBe("pooled");
    expect(datasetKeyOf("our_test_set3")).toBe("set3");
  });

  it("passes an unknown dataset through instead of dropping it", () => {
    expect(datasetKeyOf("holdout_2027")).toBe("holdout_2027");
  });
});

describe("benchmarkView", () => {
  it("pivots model rows by dataset, in reading order, keeping the report's model order", () => {
    const rows = [
      bench({ model: "M1", dataset: "our_test", macro_f1: 0.7, n_rows: 204, n_groups: 104 }),
      bench({ model: "M1" }),
      bench({ model: "M2-LR", dataset: "our_test:set2", macro_f1: 0.9, n_rows: 72, n_groups: 40 }),
      bench({ model: "M2-LR", dataset: "our_test:set1", macro_f1: 0.85, n_rows: 60, n_groups: 30 }),
      bench({ model: "M2-LR", target: "priority", macro_f1: 0.5 }),
    ];
    const v = benchmarkView(rows, "category");
    expect(v.columns).toEqual(["oof_official", "set1", "set2", "pooled"]);
    expect(v.rows.map((r) => r.model)).toEqual(["M1", "M2-LR"]);
    expect(v.rows[0]?.cells.pooled?.macroF1).toBe(0.7);
    expect(v.rows[0]?.cells.pooled?.nGroups).toBe(104);
    expect(v.rows[0]?.cells.set1).toBeUndefined();
    expect(v.rows[1]?.cells.set1?.macroF1).toBe(0.85);
    // The priority row is not in the category view.
    expect(benchmarkView(rows, "priority").rows).toHaveLength(1);
  });

  it("keeps cut and not-available rows as cells with their status", () => {
    const v = benchmarkView(
      [bench({ model: "M3", macro_f1: null, accuracy: null, n_rows: 0, n_groups: null, status: "cut" }), bench({ model: "M4", macro_f1: null, status: "n/a", n_rows: 64 })],
      "category",
    );
    expect(v.rows.map((r) => r.cells.oof_official?.status)).toEqual(["cut", "n/a"]);
  });

  it("builds the benchmark of the API fixture: at least five model rows over both targets", () => {
    const total = (["category", "priority"] as const).reduce((n, t) => n + benchmarkView(METRICS.benchmark, t).rows.length, 0);
    expect(total).toBeGreaterThanOrEqual(5);
    expect(hasPerSetRows(METRICS.benchmark)).toBe(false);
  });
});

describe("hasPerSetRows and isSmallSample", () => {
  it("sees a per-set row only when one exists", () => {
    expect(hasPerSetRows([bench({ dataset: "our_test" })])).toBe(false);
    expect(hasPerSetRows([bench({ dataset: "our_test:set3" })])).toBe(true);
  });

  it("calls fewer than 30 groups a small sample, and uses rows when the groups are unknown", () => {
    expect(isSmallSample(432, 29)).toBe(true);
    expect(isSmallSample(432, 30)).toBe(false);
    expect(isSmallSample(12, null)).toBe(true);
    expect(isSmallSample(0, null)).toBe(false);
  });
});

describe("coverageGroups", () => {
  const cov = (o: Partial<CoverageRow>): CoverageRow => ({
    target: "category",
    dataset: "our_test",
    lang: "all",
    coverage: 0.9,
    mean_set_size: 1.2,
    singleton_rate: 0.8,
    n_rows: 64,
    n_groups: 64,
    ...o,
  });

  it("orders by dataset column then language and drops empty targets", () => {
    const groups = coverageGroups([cov({ lang: "ar" }), cov({ dataset: "oof_official", lang: "arabizi" }), cov({ lang: "all" }), cov({ dataset: "oof_official", lang: "en" })]);
    expect(groups).toHaveLength(1);
    expect(groups[0]?.rows.map((r) => `${r.key}:${r.lang}`)).toEqual(["oof_official:en", "oof_official:arabizi", "pooled:all", "pooled:ar"]);
  });
});

describe("fairnessGroups", () => {
  const f = (slice: string, macro_f1: number | null, o: Partial<FairnessSlice> = {}): FairnessSlice => ({
    slice,
    target: "category",
    dataset: "our_test",
    macro_f1,
    n_rows: 20,
    n_groups: 20,
    ...o,
  });

  it("measures each language against the best slice and orders en, ar, arabizi", () => {
    const [g] = fairnessGroups([f("arabizi", 0.82), f("en", 0.9), f("ar", 0.87)]);
    expect(g?.slices.map((s) => s.slice)).toEqual(["en", "ar", "arabizi"]);
    expect(g?.slices.map((s) => points(s.gap ?? 0))).toEqual(["0", "-3", "-8"]);
  });

  it("gives no gap to an unscored slice and groups by target and dataset", () => {
    const groups = fairnessGroups([f("en", 0.9), f("ar", null), f("en", 0.7, { dataset: "oof_official" }), f("en", 0.6, { target: "priority" })]);
    expect(groups.map((g) => `${g.target}:${g.dataset}`)).toEqual(["category:oof_official", "category:pooled", "priority:pooled"]);
    expect(groups[1]?.slices.find((s) => s.slice === "ar")?.gap).toBeNull();
  });
});

describe("router, memory and rates", () => {
  it("lists tiers in order with their share of all requests", () => {
    const rows = tierRows(METRICS.router);
    expect(rows.map((r) => r.tier)).toEqual(["tier0", "tier1", "human"]);
    expect(rows[0]?.share).toBeCloseTo(109 / 128);
    expect(tierRows({ ...METRICS.router, total: 0, by_tier: {} })).toEqual([]);
    expect(tierRows({ ...METRICS.router, total: 0, by_tier: { tier0: 0 } })[0]?.share).toBe(0);
  });

  it("sorts memory categories by count and pass rates weakest first", () => {
    expect(memoryRows({ A: 1, B: 3, C: 3 }).map((r) => r.category)).toEqual(["B", "C", "A"]);
    expect(rateRows({ typos: 0.67, injection: 1, arabizi: 0.5 }).map((r) => r.key)).toEqual(["arabizi", "typos", "injection"]);
  });
});

describe("scorecards", () => {
  const card = (run_id: string, created_at: string): Scorecard => ({ run_id, created_at, n: 20, seed: 42, overall: 0.8, by_style: {}, by_lang: {}, failures: [] });

  it("merges session and service runs by id, newest first, the service's copy winning", () => {
    const local = [card("a", "2026-11-05T10:00:00Z"), card("b", "2026-11-05T12:00:00Z")];
    const remote = [{ ...card("a", "2026-11-05T10:00:00Z"), overall: 0.5 }, card("c", "2026-11-05T11:00:00Z")];
    const merged = mergeScorecards(local, remote);
    expect(merged.map((s) => s.run_id)).toEqual(["b", "c", "a"]);
    expect(merged.find((s) => s.run_id === "a")?.overall).toBe(0.5);
  });

  it("keeps a run with an unreadable date instead of dropping it", () => {
    expect(mergeScorecards([card("x", "not a date")], [])).toHaveLength(1);
  });
});

describe("noOfflineReport", () => {
  it("is true only when every offline section is empty and no report was written", () => {
    const empty: MetricsResponse = {
      ...METRICS,
      generated_at: null,
      benchmark: [],
      coverage: [],
      calibration: [],
      fairness: [],
      ablations: [],
      confusions: [],
      ask_rate: null,
      ask_rate_is_proxy: true,
    };
    expect(noOfflineReport(empty)).toBe(true);
    expect(noOfflineReport(METRICS)).toBe(false);
    expect(noOfflineReport({ ...empty, fairness: METRICS.fairness })).toBe(false);
  });
});

describe("formatting", () => {
  it("prints scores, percentages, points and money", () => {
    expect(fixed2(0.861)).toBe("0.86");
    expect(percent(0.924)).toBe("92%");
    expect(points(-0.054)).toBe("-5");
    expect(points(0.03)).toBe("+3");
    expect(points(-0.001)).toBe("0");
    expect(usd(0.0019)).toBe("$0.0019");
    expect(usd(0)).toBe("$0.00");
    expect(usd(12.5)).toBe("$12.50");
  });
});

describe("red-team request", () => {
  it("sends null styles when every style is chosen, else the chosen ones in form order", () => {
    expect(redTeamRequest({ styles: new Set(RED_TEAM_STYLES), n: 20, seed: 42 })).toEqual({ n: 20, styles: null, seed: 42 });
    expect(redTeamRequest({ styles: new Set(["injection", "fake_urgency"]), n: 5, seed: 7 })).toEqual({
      n: 5,
      styles: ["fake_urgency", "injection"],
      seed: 7,
    });
  });

  it("accepts only whole numbers from 1 to the service's cap", () => {
    expect(validRedTeamN(1)).toBe(true);
    expect(validRedTeamN(RED_TEAM_MAX_N)).toBe(true);
    expect(validRedTeamN(0)).toBe(false);
    expect(validRedTeamN(RED_TEAM_MAX_N + 1)).toBe(false);
    expect(validRedTeamN(2.5)).toBe(false);
    expect(validRedTeamN(Number.NaN)).toBe(false);
  });

  it("lists exactly the ten styles the API documents", () => {
    expect(RED_TEAM_STYLES).toHaveLength(10);
  });
});

describe("labErrorKind", () => {
  const fail = (o: Partial<AiFail>): AiFail => ({ ok: false, status: 500, code: "internal_error", error: "x", details: null, waking: false, ...o });
  it("maps failures to dictionary kinds", () => {
    expect(labErrorKind(fail({ status: 401, code: "unauthenticated" }))).toBe("session");
    expect(labErrorKind(fail({ status: 403, code: "forbidden" }))).toBe("forbidden");
    expect(labErrorKind(fail({ status: 422, code: "invalid_input" }))).toBe("invalid");
    expect(labErrorKind(fail({ status: 503, code: "artifact_unavailable" }))).toBe("unavailable");
    expect(labErrorKind(fail({ status: 503, code: "ai_waking", waking: true }))).toBe("waking");
    expect(labErrorKind(fail({}))).toBe("generic");
  });
});
