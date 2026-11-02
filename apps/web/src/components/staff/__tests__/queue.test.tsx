import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import type { TicketView } from "@/lib/staff/tickets";

const m = vi.hoisted(() => ({ push: vi.fn(), queue: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: m.push }), usePathname: () => "/staff" }));
vi.mock("@/hooks/useSignIn", () => ({ useSignOut: () => vi.fn() }));
vi.mock("@/hooks/useNotifications", () => ({ useNotifications: vi.fn() }));
vi.mock("@/hooks/useTicketQueue", () => ({ useTicketQueue: m.queue }));

import { StaffScreen } from "../StaffScreen";

const NOW = new Date("2026-11-08T10:00:00Z");
const H = 3_600_000;
const at = (h: number) => new Date(NOW.getTime() + h * H).toISOString();

const ticket = (o: Partial<TicketView>): TicketView => ({
  id: "t1",
  request_id: "r1",
  incident_id: null,
  office: "it",
  category: "IT Support",
  priority: "medium",
  status: "new",
  provisional: false,
  title: "Ticket",
  body: "",
  sla_due_at: at(10),
  escalated_at: null,
  resolved_at: null,
  clock_started_at: "2026-11-08T08:00:00Z",
  reminder_sent_at: null,
  awaiting_student: false,
  reminder_count: 0,
  requester_alias: null,
  created_at: "2026-11-08T08:00:00Z",
  link: null,
  tags: [],
  ...o,
});

const TICKETS = [
  ticket({ id: "aaaaaaaa-1", title: "Printer jam", priority: "low", sla_due_at: at(3) }),
  ticket({ id: "bbbbbbbb-2", title: "Wi-Fi down", priority: "high", sla_due_at: at(-2) }),
  ticket({ id: "cccccccc-3", title: "Password reset", priority: "medium", status: "in_progress", sla_due_at: at(20) }),
  ticket({ id: "dddddddd-4", title: "Old fix", priority: "high", status: "solved", sla_due_at: at(-30) }),
];

const titles = () =>
  within(screen.getByRole("table"))
    .getAllByRole("row")
    .slice(1)
    .map((r) => within(r).getAllByRole("cell")[1]!.textContent);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
  m.push.mockReset();
  m.queue.mockReturnValue({ tickets: TICKETS, load: "ready", reload: vi.fn() });
});
afterEach(() => vi.useRealTimers());

describe("StaffScreen queue", () => {
  it("lists active tickets: high first, overdue marked in words, finished hidden", () => {
    render(<StaffScreen role="staff" alias="it" office="it" />);
    expect(titles()).toEqual(["Wi-Fi down", "Password reset", "Printer jam"]);
    const first = within(screen.getByRole("table")).getAllByRole("row")[1]!;
    expect(first).toHaveTextContent("Urgent");
    expect(first).toHaveTextContent("overdue by 2 h 00 min");
    expect(within(first).getByText("Overdue")).toBeInTheDocument();
    expect(screen.queryByText("Old fix")).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "Office" })).toBeNull();
  });

  it("passes the viewer alias to the data hook so own requests stay hidden", () => {
    render(<StaffScreen role="staff" alias="rim" office="it" />);
    expect(m.queue).toHaveBeenCalledWith("it", "rim");
  });

  it("opens the workspace on a row click and on Enter", async () => {
    const user = userEvent.setup();
    render(<StaffScreen role="staff" alias="it" office="it" />);
    await user.click(screen.getByText("Printer jam"));
    expect(m.push).toHaveBeenCalledWith("/staff/tickets/aaaaaaaa-1");
    screen.getByText("Wi-Fi down").closest("tr")!.focus();
    await user.keyboard("{Enter}");
    expect(m.push).toHaveBeenLastCalledWith("/staff/tickets/bbbbbbbb-2");
  });

  it("sorts by a clicked header, both ways", async () => {
    const user = userEvent.setup();
    render(<StaffScreen role="staff" alias="it" office="it" />);
    await user.click(screen.getByRole("button", { name: "Title" }));
    expect(titles()).toEqual(["Password reset", "Printer jam", "Wi-Fi down"]);
    await user.click(screen.getByRole("button", { name: "Title" }));
    expect(titles()).toEqual(["Wi-Fi down", "Printer jam", "Password reset"]);
  });

  it("applies the filter form on Search and clears it on Reset", async () => {
    const user = userEvent.setup();
    render(<StaffScreen role="staff" alias="it" office="it" />);
    await user.type(screen.getByLabelText("Search by title or ticket number"), "print");
    expect(titles()).toHaveLength(3);
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(titles()).toEqual(["Printer jam"]);
    await user.click(screen.getByRole("button", { name: "Reset" }));
    expect(titles()).toHaveLength(3);
    await user.selectOptions(screen.getByLabelText("Status"), "done");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(titles()).toEqual(["Old fix"]);
    expect(screen.getByText("Stopped")).toBeInTheDocument();
  });

  it("shows the Office column and filter to an admin only", () => {
    render(<StaffScreen role="admin" alias="admin" office={null} />);
    expect(screen.getByRole("columnheader", { name: /Office/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Office")).toBeInTheDocument();
  });

  it("renders in Arabic with translated headers", () => {
    render(
      <LangScope lang="ar">
        <StaffScreen role="staff" alias="it" office="it" />
      </LangScope>,
    );
    expect(screen.getByRole("columnheader", { name: /رقم التذكرة/ })).toBeInTheDocument();
    expect(screen.getAllByText("عاجل").length).toBeGreaterThan(0);
  });
});
