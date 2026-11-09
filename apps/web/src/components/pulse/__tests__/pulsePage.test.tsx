import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import type { FeedEvent } from "@/lib/pulse/state";
import type { BuildingRequest } from "@/lib/pulse/view";
import { BuildingRequests } from "../BuildingRequests";
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

describe("BuildingRequests (a building chosen on the map)", () => {
  const r = (o: Partial<BuildingRequest>): BuildingRequest => ({
    id: "r1",
    createdAt: "2026-11-08T09:50:00Z",
    room: "L204",
    category: "IT Support",
    priority: "medium",
    simulated: false,
    ...o,
  });
  const ticket = { id: "ab12cd34-0000-4000-8000-000000000001", status: "in_progress" };

  it("lists each request with its labels, room and age, and links the ticket the office can open", () => {
    render(<BuildingRequests now={NOW} requests={[r({}), r({ id: "r2", category: "Facilities", priority: "low", room: null })]} tickets={new Map([["r1", ticket]])} />);
    expect(screen.getByText("IT Support · Medium priority")).toBeInTheDocument();
    expect(screen.getByText("Room L204")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Open ticket #AB12CD34/ });
    expect(link).toHaveAttribute("href", "/staff/tickets/ab12cd34-0000-4000-8000-000000000001");
    expect(within(link).getByText("In progress")).toBeInTheDocument();
    // the Facilities request has no ticket this office can open
    expect(screen.getByText("Facilities · Low priority")).toBeInTheDocument();
    expect(screen.getByText(/No ticket your office can open/)).toBeInTheDocument();
  });

  it("says so when the building has no requests", () => {
    render(<BuildingRequests requests={[]} tickets={new Map()} />);
    expect(screen.getByText("No requests in this building yet")).toBeInTheDocument();
  });
});
