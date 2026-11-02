import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import type { ActivityRow } from "@/lib/tickets/types";
import { ReplyBox } from "../ReplyBox";
import { TicketThread } from "../TicketThread";

const row = (o: Partial<ActivityRow>): ActivityRow => ({
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

const THREAD: ActivityRow[] = [
  row({ id: "1", kind: "created", actor_role: "system", actor_alias: null, actor_office: null }),
  row({ id: "2", kind: "comment", body: "We are on it", from_status: "new", to_status: "in_progress" }),
  row({ id: "3", kind: "note", visibility: "internal", body: "Call the vendor" }),
  row({ id: "4", kind: "status", from_status: "in_progress", to_status: "solved", body: "Fixed" }),
  row({ id: "5", kind: "forward", from_office: "it", to_office: "facilities", body: "Wrong office" }),
  row({ id: "6", kind: "priority", from_priority: "medium", to_priority: "high" }),
  row({ id: "7", kind: "student_action", actor_role: "student", actor_alias: "lina", actor_office: null, to_status: "closed" }),
  row({ id: "8", kind: "reminder", visibility: "internal", actor_role: "system", actor_alias: null, actor_office: null }),
];

describe("TicketThread", () => {
  it("renders every kind for staff, with internal rows marked in words", () => {
    render(<TicketThread activity={THREAD} viewer="staff" />);
    const items = within(screen.getByRole("list", { name: "Ticket history" })).getAllByRole("listitem");
    expect(items).toHaveLength(8);
    expect(items[0]).toHaveTextContent("Ticket created");
    expect(items[1]).toHaveTextContent("We are on it");
    expect(items[1]).toHaveTextContent("Status: New to In progress");
    expect(items[2]).toHaveTextContent("Internal note, not visible to the requester");
    expect(items[2]).toHaveTextContent("Call the vendor");
    expect(items[3]).toHaveTextContent("Status: In progress to Solved");
    expect(items[4]).toHaveTextContent("Forwarded from IT Support to Facilities");
    expect(items[5]).toHaveTextContent("Priority: Medium to High");
    expect(items[6]).toHaveTextContent("lina");
    expect(items[6]).toHaveTextContent("The requester set the status to Closed");
    expect(items[7]).toHaveTextContent("Reminder: this ticket is overdue");
    expect(items[7]).toHaveTextContent("Internal note, not visible to the requester");
  });

  it("hides internal rows from a requester, even if they arrive", () => {
    render(<TicketThread activity={THREAD} viewer="requester" />);
    expect(screen.queryByText("Call the vendor")).toBeNull();
    expect(screen.queryByText(/Reminder/)).toBeNull();
    expect(screen.queryByText(/Internal note/)).toBeNull();
    expect(screen.getAllByRole("listitem")).toHaveLength(6);
  });

  it("shows an empty line and works in Arabic", () => {
    const { rerender } = render(<TicketThread activity={[]} viewer="staff" />);
    expect(screen.getByText("Nothing here yet.")).toBeInTheDocument();
    rerender(
      <LangScope lang="ar">
        <TicketThread activity={THREAD} viewer="staff" />
      </LangScope>,
    );
    expect(screen.getByRole("list", { name: "سجل التذكرة" })).toBeInTheDocument();
  });
});

describe("ReplyBox", () => {
  const OPTIONS = ["solved", "closed"] as const;

  it("sends a public reply with the chosen status", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn(() => Promise.resolve(true));
    render(<ReplyBox statusOptions={OPTIONS} onSend={onSend} />);
    expect(screen.getByRole("button", { name: "Send reply" })).toBeDisabled();
    await user.type(screen.getByLabelText("Your reply"), "  Done, please check  ");
    await user.selectOptions(screen.getByLabelText("Set status (optional)"), "solved");
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    expect(onSend).toHaveBeenCalledWith({ body: "Done, please check", internal: false, status: "solved" });
    expect(screen.getByLabelText("Your reply")).toHaveValue("");
  });

  it("the Internal note toggle sends internal true and no status", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn(() => Promise.resolve(true));
    render(<ReplyBox statusOptions={OPTIONS} onSend={onSend} />);
    await user.click(screen.getByRole("radio", { name: "Internal note" }));
    expect(screen.getByLabelText("Set status (optional)")).toBeDisabled();
    await user.type(screen.getByLabelText("Your note"), "Call the vendor");
    await user.click(screen.getByRole("button", { name: "Save note" }));
    expect(onSend).toHaveBeenCalledWith({ body: "Call the vendor", internal: true, status: null });
  });

  it("keeps the text when sending fails", async () => {
    const user = userEvent.setup();
    render(<ReplyBox statusOptions={OPTIONS} onSend={() => Promise.resolve(false)} />);
    await user.type(screen.getByLabelText("Your reply"), "Hello");
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    expect(screen.getByLabelText("Your reply")).toHaveValue("Hello");
  });

  it("offers only an internal note on a finished ticket, and nothing while busy", () => {
    const { rerender } = render(<ReplyBox statusOptions={[]} publicAllowed={false} onSend={vi.fn()} />);
    expect(screen.getByRole("radio", { name: "Public reply" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Internal note" })).toBeChecked();
    expect(screen.queryByLabelText("Set status (optional)")).toBeNull();
    rerender(<ReplyBox statusOptions={OPTIONS} busy onSend={vi.fn()} />);
    expect(screen.getByLabelText("Your reply")).toBeDisabled();
  });
});
