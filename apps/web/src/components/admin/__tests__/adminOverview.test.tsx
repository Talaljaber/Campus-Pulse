import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import { alertsOf, daysUntil, duration, periodOf, share, usd, type LlmUsage, type Overview } from "@/lib/admin/overview";

const m = vi.hoisted(() => ({ callAi: vi.fn(), push: vi.fn() }));

vi.mock("@/lib/ai/browser", () => ({ callAi: m.callAi }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: m.push }), usePathname: () => "/admin" }));
vi.mock("@/lib/supabase/browser", () => ({ createBrowserSupabase: () => ({}) }));
vi.mock("@/hooks/useSignIn", () => ({ useSignOut: () => vi.fn() }));

import { AdminOverview } from "../AdminOverview";

const NOW = new Date("2026-11-07T12:00:00Z");

const office = (code: string, o: Partial<Overview["offices"][number]> = {}) => ({
  office: code,
  open: 0,
  overdue: 0,
  high_open: 0,
  received: 0,
  resolved: 0,
  median_hours: null,
  sla_met_pct: null,
  ...o,
});

const OVERVIEW: Overview = {
  days: 30,
  generated_at: "2026-11-07T12:00:00Z",
  requests: { total: 21, by_lang: { en: 10, ar: 9, arabizi: 2 }, voice: 1, distress: 1, out_of_scope: 0, students: 3 },
  tickets: { open: 13, overdue: 10, high_open: 0, received: 20, resolved: 7, median_hours: 0.2, sla_met_pct: 100 },
  offices: [office("it", { open: 2, overdue: 2, received: 9, resolved: 7, median_hours: 0.2, sla_met_pct: 100 }), office("finance", { open: 2 })],
  daily: [
    { day: "2026-11-05", requests: 5, high: 2 },
    { day: "2026-11-06", requests: 4, high: 0 },
    { day: "2026-11-07", requests: 0, high: 0 },
  ],
  ai: { classified: 21, automatic: 16, to_human: 5, asked_question: 1, reviews: 11, reviews_open: 7, corrected: 2, confirmed: 2 },
  incidents: { open: 0, opened: 0 },
  delivery: { sent: 41, failed: 6, rejected: 40, queued: 0, sync_errors: 0, synced: 20 },
  people: { students: 3, staff: 7, admins: 1 },
};

const USAGE: LlmUsage = {
  available: true,
  provider: "openrouter",
  spent_today_usd: 0.0457,
  spent_week_usd: 0.22,
  spent_month_usd: 3.33,
  spent_total_usd: 3.68,
  limit_usd: 7,
  limit_remaining_usd: 6.95,
  limit_reset: "daily",
  key_expires_at: "2026-11-30T12:20:01Z",
  models: ["deepseek/deepseek-v4.1-flash"],
  checked_at: "2026-11-07T12:00:00Z",
};

describe("admin overview helpers", () => {
  it("reads the period from the URL and falls back to 30 days", () => {
    expect(periodOf("7")).toBe(7);
    expect(periodOf(["90"])).toBe(90);
    expect(periodOf("12")).toBe(30);
    expect(periodOf(undefined)).toBe(30);
  });

  it("formats shares, durations, money and days left", () => {
    expect(share(16, 21)).toBe(76);
    expect(share(1, 0)).toBeNull();
    expect(duration(0.2)).toEqual({ unit: "min", value: 12 });
    expect(duration(5.25)).toEqual({ unit: "h", value: 5.3 });
    expect(duration(72)).toEqual({ unit: "d", value: 3 });
    expect(duration(null)).toBeNull();
    expect(usd(3.329)).toBe("$3.33");
    expect(usd(0.0045)).toBe("$0.0045");
    expect(daysUntil("2026-11-30T12:20:01Z", NOW)).toBe(23);
  });

  it("raises alerts for what needs attention, most serious first", () => {
    const kinds = alertsOf({ ...OVERVIEW, tickets: { ...OVERVIEW.tickets, high_open: 1 } }, USAGE, NOW).map((a) => a.kind);
    expect(kinds).toEqual(["highOpen", "overdue", "deliveryFailed", "reviewsOpen"]);
    const expiring = alertsOf(OVERVIEW, { ...USAGE, key_expires_at: "2026-11-12T00:00:00Z", limit_remaining_usd: 1 }, NOW);
    expect(expiring.map((a) => a.kind)).toContain("keyExpiring");
    expect(expiring.find((a) => a.kind === "spendNearLimit")?.count).toBe(86);
    const quiet: Overview = {
      ...OVERVIEW,
      tickets: { ...OVERVIEW.tickets, overdue: 0 },
      delivery: { ...OVERVIEW.delivery, failed: 0 },
      ai: { ...OVERVIEW.ai, reviews_open: 0 },
    };
    expect(alertsOf(quiet, null, NOW)).toEqual([]);
  });
});

describe("AdminOverview", () => {
  beforeEach(() => {
    m.callAi.mockReset();
    m.callAi.mockImplementation(async (path: string) =>
      path === "admin/usage"
        ? { ok: true, data: USAGE }
        : { ok: true, data: { status: "ok", artifact: "v1", sha: "a8e2f1e58da5", version: "0", rss_mb: 1, encoder_loaded: true, sinks: [], llm_tiers: [], vector_store: null } },
    );
  });

  it("shows the backlog, the offices, the AI handling, the spend and the service status", async () => {
    render(
      <LangScope lang="en">
        <AdminOverview alias="admin" name="Admin" period={30} overview={OVERVIEW} />
      </LangScope>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
    const alerts = screen.getByRole("region", { name: "Needs attention" });
    expect(within(alerts).getByText(/10 open tickets are past their response time/)).toBeVisible();
    expect(within(alerts).getByText(/6 emails failed to send/)).toBeVisible();

    const kpis = screen.getByRole("region", { name: "Key numbers" });
    expect(within(kpis).getByText("21")).toBeVisible();
    expect(within(kpis).getByText("12 min")).toBeVisible();

    expect(screen.getByRole("region", { name: "Offices" })).toBeVisible();
    expect(screen.getByText("76%")).toBeVisible(); // routed automatically: 16 of 21
    expect(await screen.findByText("$3.33")).toBeVisible();
    expect(screen.getByText("Limit $7.00 per day")).toBeVisible();
    expect(await screen.findByText("Online")).toBeVisible();
    expect(m.callAi).toHaveBeenCalledWith("admin/usage", expect.anything());
    expect(screen.queryByText(/red team/i)).toBeNull();
  });

  it("says when spend is unavailable and when the numbers could not load", async () => {
    m.callAi.mockResolvedValue({ ok: false, error: { code: "not_implemented", message: "" } });
    const { unmount } = render(
      <LangScope lang="en">
        <AdminOverview alias="admin" period={30} overview={OVERVIEW} />
      </LangScope>,
    );
    expect(await screen.findByText(/Spend is not available/)).toBeVisible();
    expect(await screen.findByText("Not responding")).toBeVisible();
    unmount();
    render(
      <LangScope lang="en">
        <AdminOverview alias="admin" period={7} overview={null} />
      </LangScope>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load the overview");
  });

  it("works in Arabic", () => {
    render(
      <LangScope lang="ar">
        <AdminOverview alias="admin" period={30} overview={OVERVIEW} />
      </LangScope>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "نظرة عامة" })).toBeVisible();
  });
});
