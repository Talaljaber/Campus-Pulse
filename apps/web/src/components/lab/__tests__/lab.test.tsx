import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import metricsFixture from "@fixtures/metrics.json";
import redteamFixture from "@fixtures/redteam_run.json";
import { LangScope } from "@/i18n";
import type { BenchmarkRow, MetricsResponse, Scorecard } from "@/lib/ai/types";
import {
  AblationTable,
  BenchmarkTable,
  CalibrationTable,
  ConfusionMatrix,
  CoverageChart,
  FairnessChart,
  MemoryStats,
  RedTeamRunner,
  RouterStats,
  ScorecardHistory,
} from "../index";

const METRICS = metricsFixture.response as MetricsResponse;
const SCORECARD = redteamFixture.response as Scorecard;

/** A row whose dataset may be a per-set name the generated contract type does not list yet. */
const row = (o: Omit<Partial<BenchmarkRow>, "dataset"> & { dataset?: string }): BenchmarkRow => ({
  model: "Ensemble (tier 0)",
  target: "category",
  dataset: "our_test",
  macro_f1: 0.88,
  accuracy: 0.89,
  n_rows: 204,
  n_groups: 104,
  status: "ok",
  ...o,
} as BenchmarkRow);

describe("BenchmarkTable", () => {
  it("shows the fixture as one row per model, with counts and the pooled-only note", () => {
    render(<BenchmarkTable rows={METRICS.benchmark} />);
    const category = screen.getByRole("table", { name: /Category benchmark/ });
    // M1, M2-LR, M2-kNN, M3, Ensemble, LLM zero-shot
    expect(within(category).getAllByRole("row")).toHaveLength(1 + 6);
    expect(within(category).getByRole("columnheader", { name: "CV official" })).toBeInTheDocument();
    expect(within(category).getByRole("columnheader", { name: "Pooled" })).toBeInTheDocument();
    const m1 = within(category).getByRole("row", { name: /M1/ });
    expect(within(m1).getByText("0.81")).toBeInTheDocument();
    expect(within(m1).getByText("432 rows, 30 groups")).toBeInTheDocument();
    // Cut and not-available cells say so in words.
    expect(within(category).getByText("Cut")).toBeInTheDocument();
    expect(within(category).getByText("Not available")).toBeInTheDocument();
    expect(screen.getByText(/no separate rows for set 1, set 2 and set 3/)).toBeInTheDocument();
    // Priority is its own table.
    expect(screen.getByRole("table", { name: /Priority benchmark/ })).toBeInTheDocument();
  });

  it("shows set 1, set 2, set 3 and pooled side by side and flags the small ones", () => {
    render(
      <BenchmarkTable
        rows={[
          row({ dataset: "oof_official", n_rows: 432, n_groups: 30, macro_f1: 0.86 }),
          row({ dataset: "our_test:set1", n_rows: 60, n_groups: 18, macro_f1: 0.8 }),
          row({ dataset: "our_test:set2", n_rows: 72, n_groups: 40, macro_f1: 0.9 }),
          row({ dataset: "our_test:set3", n_rows: 72, n_groups: 40, macro_f1: 0.91 }),
          row({ dataset: "our_test", macro_f1: 0.88 }),
        ]}
      />,
    );
    const table = screen.getByRole("table", { name: /Category benchmark/ });
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Model", "CV official", "Set 1", "Set 2", "Set 3", "Pooled"]);
    const r = within(table).getByRole("row", { name: /Ensemble/ });
    expect(within(r).getByText("60 rows, 18 groups")).toBeInTheDocument();
    // Only set 1 rests on fewer than 30 groups.
    expect(within(r).getAllByText("Small sample")).toHaveLength(1);
    expect(screen.queryByText(/no separate rows/)).not.toBeInTheDocument();
    expect(screen.getByText(/Compare the three test sets/)).toBeInTheDocument();
  });

  it("shows an empty state, not a crash, when there are no rows", () => {
    render(<BenchmarkTable rows={[]} />);
    expect(screen.getByText("No model metrics yet")).toBeInTheDocument();
  });

  it("is Arabic with translated column headers", () => {
    render(
      <LangScope lang="ar">
        <BenchmarkTable rows={METRICS.benchmark} />
      </LangScope>,
    );
    expect(screen.getAllByRole("columnheader", { name: "النموذج" }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("ملغى").length).toBeGreaterThan(0);
  });
});

describe("CoverageChart, CalibrationTable, FairnessChart, AblationTable", () => {
  it("prints coverage, set size and counts per dataset and language, with the caveat", () => {
    render(<CoverageChart rows={METRICS.coverage} />);
    const table = screen.getByRole("table", { name: /Category coverage/ });
    const ar = within(table).getByRole("row", { name: /Pooled, Arabic/ });
    expect(within(ar).getByText("90%")).toBeInTheDocument();
    expect(within(ar).getByText("1.28")).toBeInTheDocument();
    expect(within(ar).getByText("25 rows, 25 groups")).toBeInTheDocument();
    // 25 groups is below 30.
    expect(within(ar).getByText("Small sample")).toBeInTheDocument();
    expect(screen.getByText(/Coverage is approximate/)).toBeInTheDocument();
  });

  it("prints the calibration error and each bin", () => {
    render(<CalibrationTable curves={METRICS.calibration} />);
    expect(screen.getByText(/expected calibration error 0.041/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: /reliability bins/ });
    expect(within(table).getByRole("row", { name: /0.90 to 1.00/ })).toHaveTextContent("96%");
  });

  it("prints the gap to the best language and names the best one", () => {
    render(<FairnessChart rows={METRICS.fairness} />);
    const table = screen.getByRole("table", { name: /macro-F1 per language/ });
    expect(within(within(table).getByRole("row", { name: /English/ })).getByText("Best")).toBeInTheDocument();
    expect(within(within(table).getByRole("row", { name: /Arabizi/ })).getByText("-8")).toBeInTheDocument();
    // Arabizi has 12 rows: a small sample.
    expect(within(within(table).getByRole("row", { name: /Arabizi/ })).getByText("Small sample")).toBeInTheDocument();
  });

  it("prints the signed change of an ablation arm", () => {
    render(<AblationTable rows={METRICS.ablations} />);
    expect(screen.getByRole("row", { name: /no wrapper stripping/ })).toHaveTextContent("-5");
  });

  it("render nothing without rows", () => {
    const { container } = render(
      <>
        <CoverageChart rows={[]} />
        <CalibrationTable curves={[]} />
        <FairnessChart rows={[]} />
        <AblationTable rows={[]} />
        <ConfusionMatrix confusions={[]} />
      </>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ConfusionMatrix", () => {
  it("lays out true by predicted labels with counts, shares and row totals", () => {
    render(<ConfusionMatrix confusions={METRICS.confusions} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["True label / Predicted", "Low", "Medium", "High", "Total"]);
    const high = within(table).getByRole("rowheader", { name: "High" }).closest("tr");
    // The true-high row holds 0, 4 and 17 of 21: a count and its share of the row in each cell.
    expect(within(high as HTMLElement).getAllByRole("cell").map((c) => c.textContent)).toEqual(["00%", "419%", "1781%", "21"]);
  });

  it("names the labels in Arabic", () => {
    render(
      <LangScope lang="ar">
        <ConfusionMatrix confusions={METRICS.confusions} />
      </LangScope>,
    );
    expect(screen.getAllByText("عالية").length).toBeGreaterThan(0);
  });
});

describe("RouterStats and MemoryStats", () => {
  it("prints the router numbers and the tier table", () => {
    render(<RouterStats router={METRICS.router} />);
    expect(screen.getByText("128")).toBeInTheDocument();
    expect(screen.getAllByText("85%")).toHaveLength(2); // the headline tile and the tier 0 share
    expect(screen.getByText("$0.0019")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Requests by tier" });
    expect(within(table).getByRole("row", { name: /Tier 0/ })).toHaveTextContent("109");
    expect(within(table).getByRole("row", { name: /Human review/ })).toHaveTextContent("12");
  });

  it("says so when nothing was routed", () => {
    render(<RouterStats router={{ ...METRICS.router, total: 0, by_tier: {} }} />);
    expect(screen.getByText("No requests have been routed yet.")).toBeInTheDocument();
  });

  it("prints the memory counts and the categories in the page language", () => {
    render(
      <LangScope lang="ar">
        <MemoryStats memory={METRICS.memory} />
      </LangScope>,
    );
    expect(screen.getByText("الدعم التقني")).toBeInTheDocument();
    expect(screen.getByText("التسجيل")).toBeInTheDocument();
  });

  it("says so when memory is empty", () => {
    render(<MemoryStats memory={{ active: 0, total: 0, by_category: {}, last_added_at: null }} />);
    expect(screen.getByText(/No corrections yet/)).toBeInTheDocument();
  });
});

describe("RedTeamRunner", () => {
  it("runs with every style (sent as all), 20 attacks and seed 42 by default", async () => {
    const onRun = vi.fn();
    render(<RedTeamRunner running={false} onRun={onRun} />);
    await userEvent.click(screen.getByRole("button", { name: "Run red team" }));
    expect(onRun).toHaveBeenCalledWith({ n: 20, styles: null, seed: 42 });
  });

  it("sends only the chosen styles", async () => {
    const onRun = vi.fn();
    render(<RedTeamRunner running={false} onRun={onRun} />);
    await userEvent.click(screen.getByRole("button", { name: "Clear all" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Injection" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Typos" }));
    await userEvent.click(screen.getByRole("button", { name: "Run red team" }));
    expect(onRun).toHaveBeenCalledWith({ n: 20, styles: ["typos", "injection"], seed: 42 });
  });

  it("refuses an empty style list and a bad count, and says why", async () => {
    const onRun = vi.fn();
    render(<RedTeamRunner running={false} onRun={onRun} />);
    await userEvent.click(screen.getByRole("button", { name: "Clear all" }));
    await userEvent.click(screen.getByRole("button", { name: "Run red team" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose at least one style.");
    await userEvent.click(screen.getByRole("button", { name: "Select all" }));
    const n = screen.getByRole("textbox", { name: "Number of attacks" });
    await userEvent.clear(n);
    await userEvent.type(n, "201");
    await userEvent.click(screen.getByRole("button", { name: "Run red team" }));
    expect(n).toHaveAccessibleDescription("Enter a whole number from 1 to 200.");
    expect(n).toBeInvalid();
    await userEvent.clear(n);
    await userEvent.type(n, "2.5");
    await userEvent.click(screen.getByRole("button", { name: "Run red team" }));
    expect(onRun).not.toHaveBeenCalled();
  });

  it("is busy and does not submit while a run is in flight", async () => {
    const onRun = vi.fn();
    render(<RedTeamRunner running onRun={onRun} />);
    const button = screen.getByRole("button", { name: "Running red team" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });
});

describe("ScorecardHistory", () => {
  it("shows an empty state with no runs", () => {
    render(<ScorecardHistory runs={[]} />);
    expect(screen.getByText("No red-team runs yet")).toBeInTheDocument();
  });

  it("shows the overall pass rate, rates weakest first, and the failures folded away", async () => {
    render(<ScorecardHistory runs={[SCORECARD]} />);
    const card = screen.getByTestId("scorecard");
    expect(within(card).getByText(/Passed: 85%/)).toBeInTheDocument();
    expect(within(card).getByText("20")).toBeInTheDocument();
    expect(within(card).getByText("3 failures", { selector: "span" })).toBeInTheDocument();
    const styles = within(card).getByRole("table", { name: /by style/ });
    // Weakest first: arabizi and typos (0.67) before the 100% styles.
    const names = within(styles).getAllByRole("rowheader").map((h) => h.textContent);
    expect(names.slice(0, 2)).toEqual(["Arabizi", "Typos"]);
    // Failures are inside a closed <details>.
    const details = card.querySelector("details");
    expect(details).not.toHaveAttribute("open");
    await userEvent.click(within(card).getByText("3 failures", { selector: "summary" }));
    const failures = within(card).getByRole("table", { name: /Failures of run rt-2026-11-05-01/ });
    expect(within(failures).getByText("el printer bil lab 5arban mn embare7")).toBeInTheDocument();
    expect(within(failures).getByText("No decision")).toBeInTheDocument();
    expect(within(failures).getByText("Out of scope")).toBeInTheDocument();
  });

  it("says no failures for a clean run", () => {
    render(<ScorecardHistory runs={[{ ...SCORECARD, failures: [], overall: 1 }]} />);
    expect(screen.getByText("No failures")).toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });
});
