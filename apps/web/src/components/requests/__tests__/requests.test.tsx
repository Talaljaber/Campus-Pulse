import { render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import type { TicketRow } from "@/lib/repos/tickets";
import type { ActivityRow } from "@/lib/tickets/types";

const m = vi.hoisted(() => ({
  push: vi.fn(),
  ticket: vi.fn(),
  listMy: vi.fn(),
  last: vi.fn(),
  subscribe: vi.fn(() => () => {}),
  toast: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: m.push }), usePathname: () => "/requests" }));
vi.mock("@/hooks/useSignIn", () => ({ useSignOut: () => vi.fn() }));
vi.mock("@/hooks/useMyTicket", () => ({ useMyTicket: m.ticket }));
vi.mock("@/lib/supabase/browser", () => ({ createBrowserSupabase: () => ({}) }));
vi.mock("@/lib/repos/tickets", () => ({ listMyTickets: m.listMy, listLastActivity: m.last, subscribeTickets: m.subscribe }));
vi.mock("../../ui/Toast", () => ({ useToast: () => ({ show: m.toast }) }));

import { useMyRequests } from "@/hooks/useMyRequests";
import { messageReopens, showStudentActions } from "@/lib/tickets/requester";
import { RequestScreen } from "../RequestScreen";

const ticket = (o: Partial<TicketRow> = {}): TicketRow => ({
  id: "aaaaaaaa-1",
  request_id: "r1",
  incident_id: null,
  office: "it",
  category: "IT Support",
  priority: "medium",
  status: "in_progress",
  provisional: false,
  title: "Wi-Fi down",
  body: "The Wi-Fi is down in building M",
  sla_due_at: "2026-11-09T10:00:00Z",
  escalated_at: null,
  resolved_at: null,
  clock_started_at: "2026-11-08T08:00:00Z",
  reminder_sent_at: null,
  awaiting_student: false,
  reminder_count: 0,
  requester_alias: "lina",
  created_at: "2026-11-08T08:00:00Z",
  tags: [],
  ...o,
});

const act = (o: Partial<ActivityRow>): ActivityRow => ({
  id: "a1",
  ticket_id: "t1",
  kind: "comment",
  visibility: "public",
  actor_role: "staff",
  actor_alias: "it",
  actor_office: "it",
  body: "",
  from_status: null,
  to_status: null,
  from_office: null,
  to_office: null,
  from_priority: null,
  to_priority: null,
  created_at: "2026-11-08T10:00:00Z",
  ...o,
});

beforeEach(() => {
  for (const f of [m.push, m.ticket, m.listMy, m.last, m.toast]) f.mockReset();
  m.subscribe.mockImplementation(() => () => {});
});

describe("requester rules", () => {
  it("shows the three buttons only when staff wait for the requester or the ticket is solved", () => {
    const show = (status: string, awaiting_student: boolean) => showStudentActions({ status, awaiting_student });
    expect(show("in_progress", true)).toBe(true);
    expect(show("new", true)).toBe(true);
    expect(show("solved", false)).toBe(true);
    expect(show("in_progress", false)).toBe(false);
    expect(show("new", false)).toBe(false);
    expect(show("closed", false)).toBe(false);
    expect(show("closed", true)).toBe(false);
  });

  it("says a message reopens only a solved or closed request", () => {
    expect(["new", "in_progress", "solved", "closed"].map(messageReopens)).toEqual([false, false, true, true]);
  });
});

describe("useMyRequests", () => {
  it("keeps only tickets whose requester is me and adds the last update time", async () => {
    m.listMy.mockResolvedValue([ticket({ id: "t1" }), ticket({ id: "t2", requester_alias: "someone" })]);
    m.last.mockResolvedValue(new Map([["t1", "2026-11-08T12:00:00Z"]]));
    const { result } = renderHook(() => useMyRequests("lina"));
    await waitFor(() => expect(result.current.load).toBe("ready"));
    expect(result.current.tickets.map((t) => t.id)).toEqual(["t1"]);
    expect(result.current.tickets[0]!.lastUpdate).toBe("2026-11-08T12:00:00Z");
    expect(m.listMy.mock.calls[0]![1]).toBe("lina");
  });

  it("reads nothing without an alias", async () => {
    const { result } = renderHook(() => useMyRequests(null));
    await waitFor(() => expect(result.current.load).toBe("ready"));
    expect(result.current.tickets).toEqual([]);
    expect(m.listMy).not.toHaveBeenCalled();
  });
});

describe("RequestScreen", () => {
  const state = (t: TicketRow | null, o: Record<string, unknown> = {}) => ({
    ticket: t,
    activity: [] as ActivityRow[],
    load: t ? "ready" : "notfound",
    busy: false,
    reload: vi.fn(),
    comment: vi.fn().mockResolvedValue({ ok: true }),
    act: vi.fn().mockResolvedValue({ ok: true }),
    ...o,
  });
  const show = (s: ReturnType<typeof state>) => {
    m.ticket.mockReturnValue(s);
    return render(
      <LangScope lang="en">
        <RequestScreen ticketId="aaaaaaaa-1" role="student" alias="lina" />
      </LangScope>,
    );
  };

  it("shows the request text, the department and no answer buttons while the ticket just runs", () => {
    show(state(ticket()));
    expect(screen.getByText("The Wi-Fi is down in building M")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Solved" })).toBeNull();
    expect(screen.queryByText("Sending a message reopens your request.")).toBeNull();
  });

  it.each([
    ["awaiting", { status: "in_progress", awaiting_student: true }, true],
    ["in progress", { status: "in_progress" }, false],
    ["solved", { status: "solved" }, true],
    ["closed", { status: "closed" }, false],
    ["new", { status: "new" }, false],
  ] as const)("button visibility, %s", (_name, o, visible) => {
    show(state(ticket(o)));
    for (const label of ["Solved", "Close", "Keep open"]) {
      const q = screen.queryByRole("button", { name: label });
      if (visible) expect(q).toBeInTheDocument();
      else expect(q).toBeNull();
    }
  });

  it.each([
    ["Solved", "solved"],
    ["Close", "close"],
    ["Keep open", "keep_open"],
  ] as const)("the %s button sends %s", async (label, action) => {
    const s = state(ticket({ status: "solved" }));
    show(s);
    await userEvent.setup().click(screen.getByRole("button", { name: label }));
    expect(s.act).toHaveBeenCalledWith({ action });
    await waitFor(() => expect(m.toast).toHaveBeenCalledWith(expect.any(String), "ok"));
  });

  it("shows the server's message on a refused action", async () => {
    const s = state(ticket({ status: "solved" }), {
      act: vi.fn().mockResolvedValue({ ok: false, status: 422, code: "invalid_input", error: "transition not allowed", details: null, waking: false }),
    });
    show(s);
    await userEvent.setup().click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(m.toast).toHaveBeenCalledWith("transition not allowed", "danger"));
  });

  it("disables the buttons while posting", () => {
    show(state(ticket({ status: "solved" }), { busy: true }));
    expect(screen.getByRole("button", { name: "Solved" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Close" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Keep open" })).toBeDisabled();
  });

  it("never renders internal rows", () => {
    show(
      state(ticket(), {
        activity: [
          act({ id: "1", body: "We are on it" }),
          act({ id: "2", kind: "note", visibility: "internal", body: "Secret staff note" }),
          act({ id: "3", visibility: "internal", body: "Another hidden one" }),
        ],
      }),
    );
    expect(screen.getByText("We are on it")).toBeInTheDocument();
    expect(screen.queryByText("Secret staff note")).toBeNull();
    expect(screen.queryByText("Another hidden one")).toBeNull();
  });

  it.each(["solved", "closed"])("tells the requester a message reopens a %s request", (status) => {
    show(state(ticket({ status })));
    expect(screen.getByText("Sending a message reopens your request.")).toBeInTheDocument();
  });

  it("sends a public message with no status", async () => {
    const s = state(ticket());
    show(s);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Your message"), "Any news?");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(s.comment).toHaveBeenCalledWith("Any news?");
  });

  it("shows not found for a ticket that is not mine", () => {
    show(state(null));
    expect(screen.getByRole("alert")).toHaveTextContent("This request does not exist, or you cannot open it.");
  });
});
