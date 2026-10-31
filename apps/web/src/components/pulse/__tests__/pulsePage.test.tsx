import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import type { FeedEvent } from "@/lib/pulse/state";
import { EventFeed } from "../EventFeed";

const NOW = new Date("2026-11-08T10:00:00Z").getTime();
const ev = (o: Partial<FeedEvent>): FeedEvent => ({
  id: "e1",
  at: "2026-11-08T09:55:00Z",
  kind: "request",
  simulated: false,
  buildingId: "M",
  category: "IT Support",
  priority: "high",
  count: null,
  title: null,
  ...o,
});

describe("EventFeed", () => {
  it("writes a sentence per kind in the page language", () => {
    render(
      <EventFeed
        now={NOW}
        events={[
          ev({ id: "1" }),
          ev({ id: "2", kind: "incident_new", title: "Wi-Fi outage" }),
          ev({ id: "3", kind: "incident_bump", title: "Wi-Fi outage", count: 6 }),
          ev({ id: "4", kind: "broadcast", title: "We are on it" }),
          ev({ id: "5", kind: "resolved", title: "Wi-Fi outage" }),
        ]}
      />,
    );
    const log = screen.getByRole("log", { name: "Live feed" });
    expect(within(log).getByText("New IT Support request, High priority in building M")).toBeInTheDocument();
    expect(within(log).getByText("Incident opened: Wi-Fi outage")).toBeInTheDocument();
    expect(within(log).getByText("Incident grows to 6 reports: Wi-Fi outage")).toBeInTheDocument();
    expect(within(log).getByText("Message sent: We are on it")).toBeInTheDocument();
    expect(within(log).getByText("Incident resolved: Wi-Fi outage")).toBeInTheDocument();
    expect(within(log).getAllByText("5 min ago").length).toBeGreaterThan(0);
  });

  it("shows the SIMULATED badge only for simulated lines", () => {
    render(<EventFeed now={NOW} events={[ev({ id: "1", simulated: true }), ev({ id: "2" })]} />);
    expect(screen.getAllByText("SIMULATED")).toHaveLength(1);
  });

  it("is Arabic and right to left in Arabic", () => {
    render(
      <LangScope lang="ar">
        <EventFeed now={NOW} events={[ev({ id: "1" })]} />
      </LangScope>,
    );
    expect(screen.getByRole("log", { name: "الأحداث المباشرة" })).toBeInTheDocument();
    expect(screen.getByText(/طلب الدعم التقني جديد/)).toBeInTheDocument();
    expect(screen.getByText("قبل 5 د")).toBeInTheDocument();
  });

  it("shows an empty state", () => {
    render(<EventFeed events={[]} />);
    expect(screen.getByText("Nothing has happened yet")).toBeInTheDocument();
  });

  it("does not throw for an unknown category", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<EventFeed now={NOW} events={[ev({ category: "Future Category" })]} />);
    expect(screen.getByText(/Future Category request/)).toBeInTheDocument();
    spy.mockRestore();
  });
});
