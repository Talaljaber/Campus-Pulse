import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import type { OutboxMessage } from "@/lib/outbox/view";

const m = vi.hoisted(() => ({ list: vi.fn(), subscribe: vi.fn(), off: vi.fn() }));

vi.mock("@/lib/supabase/browser", () => ({ createBrowserSupabase: () => ({}) }));
vi.mock("@/lib/repos/outbox", () => ({ listOutbox: m.list, subscribeOutbox: m.subscribe }));
vi.mock("@/hooks/useSignIn", () => ({ useSignOut: () => vi.fn() }));

import { OutboxScreen } from "../OutboxScreen";
import { OutboxTable } from "../OutboxTable";

const row = (id: string, status: string, o: Partial<OutboxMessage> = {}): OutboxMessage => ({
  id,
  alias: null,
  body: "",
  channel: "email",
  created_at: "2026-11-08T10:00:00Z",
  error: null,
  flags: [],
  kind: "email",
  priority: null,
  provider_id: null,
  request_id: null,
  status,
  subject: `Subject ${id}`,
  to_address: "demo@example.test",
  ...o,
});

const ROWS = [
  row("1", "sent", { kind: "booking", subject: "Your advisor slot", to_address: "advisor+demo@example.test" }),
  row("2", "rejected", { subject: "Reset link", to_address: "someone@real.example", error: "recipient is not on the demo allow-list" }),
  row("3", "simulated", { kind: "broadcast", channel: "in_app", to_address: "", subject: "Wi-Fi in building M: we are on it" }),
  row("4", "deferred", { error: "daily send cap reached" }),
  row("5", "failed", { error: "smtp timeout" }),
];

describe("OutboxTable", () => {
  it("shows every column of a row, with the status in words", () => {
    render(<OutboxTable rows={ROWS} />);
    const table = screen.getByRole("table", { name: "Outbox messages, newest first" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "When",
      "Kind",
      "Channel",
      "To",
      "Subject",
      "Status",
      "Reason or error",
    ]);
    const rejected = within(table).getByText("Reset link").closest("tr") as HTMLElement;
    expect(within(rejected).getByText("REJECTED")).toBeInTheDocument();
    expect(within(rejected).getByText("someone@real.example")).toBeInTheDocument();
    expect(within(rejected).getByText("recipient is not on the demo allow-list")).toBeInTheDocument();
    const simulated = within(table).getByText("Wi-Fi in building M: we are on it").closest("tr") as HTMLElement;
    expect(within(simulated).getByText("SIMULATED")).toBeInTheDocument();
    expect(within(simulated).getByText("Broadcast")).toBeInTheDocument();
    expect(within(simulated).getByText("In-app")).toBeInTheDocument();
    expect(within(simulated).getByText("No address (in-app)")).toBeInTheDocument();
    expect(within(table).getByText("Deferred")).toBeInTheDocument();
    expect(within(table).getByText("Failed")).toBeInTheDocument();
    expect(within(table).getByText("Sent")).toBeInTheDocument();
  });

  it("marks only the rows that need a look with a heavier edge", () => {
    render(<OutboxTable rows={ROWS} />);
    const edged = screen.getAllByRole("row").filter((tr) => tr.querySelector("td.border-danger"));
    expect(edged.map((tr) => tr.getAttribute("data-status"))).toEqual(["rejected", "failed"]);
  });

  it("shows an unknown status and kind as written, without crashing", () => {
    render(<OutboxTable rows={[row("9", "paused", { kind: "sms", channel: "sms" })]} />);
    expect(screen.getByText("paused")).toBeInTheDocument();
    expect(screen.getAllByText("sms")).toHaveLength(2);
  });

  it("is Arabic with an Amman-time date in Latin digits", () => {
    render(
      <LangScope lang="ar">
        <OutboxTable rows={[ROWS[1] as OutboxMessage]} />
      </LangScope>,
    );
    expect(screen.getByText("مرفوضة")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "الحالة" })).toBeInTheDocument();
    expect(screen.getByText(/2026|٢٠٢٦|13:00|1:00/)).toBeInTheDocument();
  });
});

describe("OutboxScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    m.list.mockResolvedValue(ROWS);
    m.subscribe.mockReturnValue(m.off);
  });

  it("shows the demo-accounts banner, the rows, and counts in the status filters", async () => {
    render(<OutboxScreen role="staff" />);
    expect(screen.getByText("Demo accounts only")).toBeInTheDocument();
    await screen.findByRole("table");
    const group = screen.getByRole("radiogroup", { name: "Filter by status" });
    expect(within(group).getByRole("radio", { name: "All (5)" })).toBeChecked();
    expect(within(group).getByRole("radio", { name: "REJECTED (1)" })).toBeInTheDocument();
    expect(within(group).getByRole("radio", { name: "Queued (0)" })).toBeInTheDocument();
    expect(m.list).toHaveBeenCalledWith(expect.anything(), { limit: 200 });
  });

  it("filters to one status and offers a way back when none match", async () => {
    render(<OutboxScreen role="admin" />);
    await screen.findByRole("table");
    await userEvent.click(screen.getByRole("radio", { name: "REJECTED (1)" }));
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(within(table).getByText("Reset link")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "Queued (0)" }));
    expect(screen.getByText("No messages with this status")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "All (5)" }));
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(6);
  });

  it("applies a live status change and a new row", async () => {
    render(<OutboxScreen role="staff" />);
    await screen.findByRole("table");
    const push = m.subscribe.mock.calls[0]?.[1] as (r: OutboxMessage) => void;
    act(() => push(row("5", "sent", { subject: "Subject 5", created_at: "2026-11-08T10:00:00Z" })));
    act(() => push(row("6", "rejected", { subject: "Brand new", created_at: "2026-11-08T11:00:00Z", error: "not allowed" })));
    expect(screen.getByRole("radio", { name: "All (6)" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "REJECTED (2)" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Failed (0)" })).toBeInTheDocument();
    expect(within(screen.getAllByRole("row")[1] as HTMLElement).getByText("Brand new")).toBeInTheDocument();
  });

  it("shows an empty state, an error with retry, and unsubscribes on unmount", async () => {
    m.list.mockResolvedValueOnce([]);
    const { unmount } = render(<OutboxScreen role="staff" />);
    expect(await screen.findByText("Nothing in the outbox yet")).toBeInTheDocument();
    unmount();
    expect(m.off).toHaveBeenCalled();

    m.list.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(ROWS);
    render(<OutboxScreen role="staff" />);
    const alert = await screen.findByRole("alert");
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("offers the Reports tab only to an admin, and the Outbox tile (marked current) only to an admin", async () => {
    const { unmount } = render(<OutboxScreen role="staff" />);
    await screen.findByRole("table");
    const nav = screen.getByRole("navigation", { name: "Main menu" });
    expect(within(nav).queryByRole("link", { name: "Reports" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Outbox" })).not.toBeInTheDocument();
    unmount();
    render(<OutboxScreen role="admin" />);
    await screen.findByRole("table");
    expect(within(screen.getByRole("navigation", { name: "Main menu" })).getByRole("link", { name: "Reports" })).toHaveAttribute("href", "/lab");
    expect(screen.getByRole("link", { name: "Outbox" })).toHaveAttribute("aria-current", "page");
  });
});
