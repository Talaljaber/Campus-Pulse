import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import type { TicketRow } from "@/lib/repos/tickets";

const m = vi.hoisted(() => ({ push: vi.fn(), my: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: m.push }), usePathname: () => "/requests" }));
vi.mock("@/hooks/useSignIn", () => ({ useSignOut: () => vi.fn() }));
vi.mock("@/hooks/useMyRequests", () => ({ useMyRequests: m.my }));

import { MyRequestsScreen } from "../MyRequestsScreen";

const mine = (o: Partial<TicketRow>) => ({
  id: "aaaaaaaa-1",
  request_id: "r1",
  incident_id: null,
  office: "it",
  category: "IT Support",
  priority: "medium",
  status: "in_progress",
  provisional: false,
  title: "Ticket",
  body: "",
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
  lastUpdate: "2026-11-08T12:00:00Z",
  ...o,
});

beforeEach(() => {
  m.push.mockReset();
  m.my.mockReturnValue({
    tickets: [mine({ id: "aaaaaaaa-1", title: "Open one" }), mine({ id: "bbbbbbbb-2", title: "Done one", status: "solved" })],
    load: "ready",
    reload: vi.fn(),
  });
});

describe("MyRequestsScreen", () => {
  it("shows the demo line, the six columns and only active tickets by default", () => {
    render(
      <LangScope lang="en">
        <MyRequestsScreen role="student" alias="lina" />
      </LangScope>,
    );
    expect(m.my).toHaveBeenCalledWith("lina");
    expect(screen.queryByText(/no real department/)).toBeNull();
    const heads = within(screen.getByRole("table")).getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads.join("|")).toMatch(/Ticket #.*Title.*Department.*Status.*Last update.*We aim to reply by/);
    expect(screen.getByText("Open one")).toBeInTheDocument();
    expect(screen.queryByText("Done one")).toBeNull();
  });

  it("filters to finished tickets and opens a request on click", async () => {
    const user = userEvent.setup();
    render(
      <LangScope lang="en">
        <MyRequestsScreen role="staff" alias="lina" />
      </LangScope>,
    );
    await user.selectOptions(screen.getByLabelText("Status"), "done");
    await user.click(screen.getByRole("button", { name: /search/i }));
    expect(screen.getByText("Done one")).toBeInTheDocument();
    expect(screen.queryByText("Open one")).toBeNull();
    await user.click(screen.getByText("Done one"));
    expect(m.push).toHaveBeenCalledWith("/requests/bbbbbbbb-2");
  });
});
