import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import metricsFixture from "@fixtures/metrics.json";
import redteamFixture from "@fixtures/redteam_run.json";
import type { AiFail } from "@/lib/ai/result";
import type { MetricsResponse, Scorecard } from "@/lib/ai/types";

const m = vi.hoisted(() => ({ fetchMetrics: vi.fn(), runRedTeam: vi.fn() }));

vi.mock("@/lib/lab/service", async (orig) => ({
  ...(await orig<typeof import("@/lib/lab/service")>()),
  fetchMetrics: m.fetchMetrics,
  runRedTeam: m.runRedTeam,
}));
vi.mock("@/hooks/useSignIn", () => ({ useSignOut: () => vi.fn() }));

import { ToastProvider } from "../../ui/Toast";
import { LabScreen } from "../LabScreen";

const METRICS = metricsFixture.response as MetricsResponse;
const SCORECARD = redteamFixture.response as Scorecard;
const EMPTY: MetricsResponse = {
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
  redteam: [],
  artifact: { version: "none", sha: "" },
};
const fail = (o: Partial<AiFail>): AiFail => ({ ok: false, status: 500, code: "internal_error", error: "x", details: null, waking: false, ...o });

const renderLab = () =>
  render(
    <ToastProvider>
      <LabScreen />
    </ToastProvider>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  m.fetchMetrics.mockResolvedValue({ ok: true, data: METRICS });
});

describe("LabScreen", () => {
  it("shows the header facts and the benchmark tab with the admin navigation", async () => {
    renderLab();
    expect(screen.getByRole("heading", { level: 1, name: "Model lab" })).toBeInTheDocument();
    await screen.findByRole("table", { name: /Category benchmark/ });
    expect(screen.getByText("Model artifact v1 (3f9a2c71)")).toBeInTheDocument();
    expect(screen.getByText(/Report written/)).toBeInTheDocument();
    expect(screen.getByText("Questions asked back: 22%, Proxy estimate")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main menu" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual([
      "Queue",
      "Ask",
      "Announcements",
      "Incidents",
      "Corrections",
      "Accounts",
      "Reports",
    ]);
    expect(within(nav).getByRole("link", { name: "Reports" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("tab", { name: "Benchmark", selected: true })).toBeInTheDocument();
  });

  it("moves through the tabs: calibration and fairness, live system, red team", async () => {
    renderLab();
    await screen.findByRole("table", { name: /Category benchmark/ });
    await userEvent.click(screen.getByRole("tab", { name: "Calibration and fairness" }));
    expect(await screen.findByRole("table", { name: /Category coverage/ })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /macro-F1 per language/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Live system" }));
    expect(await screen.findByRole("table", { name: "Requests by tier" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Red team" }));
    // The history lists the run the service already holds.
    expect(await screen.findAllByTestId("scorecard")).toHaveLength(1);
  });

  it("says there are no model metrics yet, and keeps the live system and the red team usable", async () => {
    m.fetchMetrics.mockResolvedValue({ ok: true, data: EMPTY });
    renderLab();
    expect(await screen.findByText("No model metrics yet")).toBeInTheDocument();
    expect(screen.getByText("No report written yet")).toBeInTheDocument();
    expect(screen.getByText("No model artifact loaded")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Calibration and fairness" }));
    expect(await screen.findByText("No model metrics yet")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Live system" }));
    expect(await screen.findByRole("table", { name: "Requests by tier" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Red team" }));
    expect(screen.getByRole("button", { name: "Run red team" })).toBeEnabled();
    expect(screen.getByText("No red-team runs yet")).toBeInTheDocument();
  });

  it("shows a retry when the metrics cannot be read, and recovers", async () => {
    m.fetchMetrics.mockResolvedValueOnce(fail({ status: 503, code: "ai_waking", waking: true }));
    renderLab();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not load this list.");
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("table", { name: /Category benchmark/ })).toBeInTheDocument();
    expect(m.fetchMetrics).toHaveBeenCalledTimes(2);
  });

  it("runs the red team, adds the scorecard at the top of the history and re-reads the metrics quietly", async () => {
    m.fetchMetrics.mockResolvedValue({ ok: true, data: { ...METRICS, redteam: [] } });
    m.runRedTeam.mockResolvedValue({ ok: true, data: SCORECARD });
    renderLab();
    await screen.findByRole("table", { name: /Category benchmark/ });
    await userEvent.click(screen.getByRole("tab", { name: "Red team" }));
    expect(screen.getByText("No red-team runs yet")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Run red team" }));
    expect(m.runRedTeam).toHaveBeenCalledWith({ n: 20, styles: null, seed: 42 });
    expect(await screen.findAllByTestId("scorecard")).toHaveLength(1);
    expect(screen.getByText("Red team finished: 85% passed.")).toBeInTheDocument();
    // The quiet re-read does not blank the page.
    await waitFor(() => expect(m.fetchMetrics).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("Loading content")).not.toBeInTheDocument();
    // Running it again with the same id does not duplicate the card.
    await userEvent.click(screen.getByRole("button", { name: "Run red team" }));
    await waitFor(() => expect(m.runRedTeam).toHaveBeenCalledTimes(2));
    expect(screen.getAllByTestId("scorecard")).toHaveLength(1);
  });

  it("tells the admin in words when the run fails", async () => {
    m.runRedTeam.mockResolvedValue(fail({ status: 403, code: "forbidden" }));
    renderLab();
    await screen.findByRole("table", { name: /Category benchmark/ });
    await userEvent.click(screen.getByRole("tab", { name: "Red team" }));
    await userEvent.click(screen.getByRole("button", { name: "Run red team" }));
    expect(await screen.findByText("Your account is not allowed to do this.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run red team" })).toBeEnabled();
  });
});
