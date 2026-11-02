import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import type { AnnouncementRow } from "@/lib/repos/announcements";
import type { ProfileRow } from "@/lib/profiles/types";

const m = vi.hoisted(() => ({
  live: vi.fn(),
  office: vi.fn(),
  subscribe: vi.fn(),
  off: vi.fn(),
  create: vi.fn(),
  archive: vi.fn(),
}));

vi.mock("@/lib/supabase/browser", () => ({ createBrowserSupabase: () => ({}) }));
vi.mock("@/lib/repos/announcements", () => ({
  listLiveAnnouncements: m.live,
  listOfficeAnnouncements: m.office,
  subscribeAnnouncements: m.subscribe,
}));
vi.mock("@/lib/announcements/service", async (orig) => ({
  ...(await orig<typeof import("@/lib/announcements/service")>()),
  createAnnouncement: m.create,
  archiveAnnouncement: m.archive,
}));
vi.mock("@/hooks/useSignIn", () => ({ useSignOut: () => vi.fn() }));

import { AccountsScreen } from "../../accounts/AccountsScreen";
import { HomeScreen } from "../../home/HomeScreen";
import { ProfileScreen } from "../../profile/ProfileScreen";
import { StaffAnnouncements } from "../StaffAnnouncements";

const row = (id: string, o: Partial<AnnouncementRow> = {}): AnnouncementRow => ({
  id,
  office: "it",
  kind: "info",
  title: `Title ${id}`,
  body: "Body text",
  starts_at: "2026-11-05T05:00:00Z",
  ends_at: null,
  archived_at: null,
  created_by: null,
  created_at: "2026-11-05T05:00:00Z",
  ...o,
});

const OUTAGE = row("1", { kind: "outage", title: "Library wifi is down", body: "Use the lab network. الشبكة متوقفة." });
const MAINT = row("2", { kind: "maintenance", title: "Outlook unavailable for two hours", office: null });

beforeEach(() => {
  vi.clearAllMocks();
  m.subscribe.mockReturnValue(m.off);
});

describe("HomeScreen", () => {
  it("greets by first name and lists the announcements with kind, office and time", async () => {
    m.live.mockResolvedValue([OUTAGE, MAINT]);
    render(<HomeScreen role="student" alias="lina" name="Lina Haddad" />);
    expect(screen.getByRole("heading", { level: 1, name: "Welcome, Lina" })).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Announcements" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]!).getByText("Outage")).toBeInTheDocument();
    expect(within(items[0]!).getByText("IT Support")).toBeInTheDocument();
    expect(within(items[0]!).getByText("Library wifi is down")).toBeInTheDocument();
    expect(within(items[0]!).getByText(/Use the lab network/)).toBeInTheDocument();
    expect(within(items[0]!).getByText(/2026/)).toBeInTheDocument();
    expect(within(items[1]!).getByText("Maintenance")).toBeInTheDocument();
    expect(within(items[1]!).getByText("Campus-wide")).toBeInTheDocument();
  });

  it("shows the empty state when nothing is live", async () => {
    m.live.mockResolvedValue([]);
    render(<HomeScreen role="student" alias="lina" name="Lina Haddad" />);
    expect(await screen.findByText("No announcements right now.")).toBeInTheDocument();
  });

  it("offers a retry when the read fails", async () => {
    m.live.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce([OUTAGE]);
    render(<HomeScreen role="student" alias="lina" name={null} />);
    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Library wifi is down")).toBeInTheDocument();
  });

  it("has the Ask and My requests tiles for a student", async () => {
    m.live.mockResolvedValue([]);
    render(<HomeScreen role="student" alias="lina" name="Lina Haddad" />);
    const tiles = screen.getByRole("list", { name: "Shortcuts" });
    expect(within(tiles).getByRole("link", { name: /Ask a question/ })).toHaveAttribute("href", "/ask");
    expect(within(tiles).getByRole("link", { name: /My requests/ })).toHaveAttribute("href", "/requests");
  });

  it("adds a live announcement when Realtime delivers it, and drops it when it is archived", async () => {
    m.live.mockResolvedValue([]);
    render(<HomeScreen role="student" alias="lina" name="Lina Haddad" />);
    await screen.findByText("No announcements right now.");
    const push = m.subscribe.mock.calls[0]![1] as (r: AnnouncementRow) => void;
    const started = new Date(Date.now() - 60_000).toISOString();
    act(() => push(row("9", { title: "Bus 7 is late", starts_at: started })));
    expect(await screen.findByText("Bus 7 is late")).toBeInTheDocument();
    act(() => push(row("9", { title: "Bus 7 is late", starts_at: started, archived_at: started })));
    await waitFor(() => expect(screen.queryByText("Bus 7 is late")).not.toBeInTheDocument());
    expect(screen.getByText("No announcements right now.")).toBeInTheDocument();
  });

  it("is Arabic and right to left", async () => {
    m.live.mockResolvedValue([OUTAGE]);
    render(
      <LangScope lang="ar">
        <HomeScreen role="student" alias="lina" name="Lina Haddad" />
      </LangScope>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "أهلاً Lina" })).toBeInTheDocument();
    expect(await screen.findByText("انقطاع")).toBeInTheDocument();
  });
});

describe("StaffAnnouncements", () => {
  it("shows the validation messages and posts nothing for an empty form", async () => {
    m.office.mockResolvedValue([]);
    render(<StaffAnnouncements role="staff" alias="it" office="it" />);
    await screen.findByText("No announcements yet.");
    await userEvent.click(screen.getByRole("button", { name: "Post announcement" }));
    expect(screen.getByText("Enter a title.")).toBeInTheDocument();
    expect(screen.getByText("Enter the text.")).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveAttribute("aria-invalid", "true");
    expect(m.create).not.toHaveBeenCalled();
  });

  it("rejects an end time in the past", async () => {
    m.office.mockResolvedValue([]);
    render(<StaffAnnouncements role="staff" alias="it" office="it" />);
    await userEvent.type(screen.getByLabelText("Title"), "Wifi");
    await userEvent.type(screen.getByLabelText("Text"), "Down");
    await userEvent.type(screen.getByLabelText("Ends at (optional)"), "2020-01-01T10:00");
    await userEvent.click(screen.getByRole("button", { name: "Post announcement" }));
    expect(screen.getByText("The end must be a time in the future.")).toBeInTheDocument();
    expect(m.create).not.toHaveBeenCalled();
  });

  it("lets staff post for their own office only (no office field) and shows the new row", async () => {
    m.office.mockResolvedValue([]);
    m.create.mockResolvedValue({ ok: true, data: { ...row("7", { title: "Printer down" }) } });
    render(<StaffAnnouncements role="staff" alias="it" office="it" />);
    expect(screen.queryByLabelText("Office")).not.toBeInTheDocument();
    expect(screen.getByText("Posted for your office: IT Support")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Title"), "  Printer down ");
    await userEvent.type(screen.getByLabelText("Text"), "Room 3");
    await userEvent.selectOptions(screen.getByLabelText("Kind"), "maintenance");
    await userEvent.click(screen.getByRole("button", { name: "Post announcement" }));
    expect(m.create).toHaveBeenCalledWith({
      title: "  Printer down ",
      body: "Room 3",
      kind: "maintenance",
      office: null,
      endsAt: null,
    });
    expect(await screen.findByText("Announcement posted. Students see it on Home now.")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Announcements you manage" });
    expect(within(table).getByText("Printer down")).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveValue("");
  });

  it("lets an admin pick an office or campus-wide", async () => {
    m.office.mockResolvedValue([]);
    m.create.mockResolvedValue({ ok: true, data: { ...row("8", { office: "finance" }) } });
    render(<StaffAnnouncements role="admin" alias="admin" office={null} />);
    const office = screen.getByLabelText("Office");
    expect(within(office).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Campus-wide",
      "Registrar",
      "IT Support",
      "Finance",
      "Transport",
      "Facilities",
      "Academic advising",
    ]);
    await userEvent.type(screen.getByLabelText("Title"), "Fees");
    await userEvent.type(screen.getByLabelText("Text"), "Deadline moved");
    await userEvent.selectOptions(office, "finance");
    await userEvent.click(screen.getByRole("button", { name: "Post announcement" }));
    expect(m.create.mock.calls[0]![0]).toMatchObject({ office: "finance" });
    expect(m.office).toHaveBeenCalledWith(expect.anything(), null);
  });

  it("words a failed post and keeps the form", async () => {
    m.office.mockResolvedValue([]);
    m.create.mockResolvedValue({ ok: false, status: 403, code: "forbidden", error: "x", details: null, waking: false });
    render(<StaffAnnouncements role="staff" alias="it" office="it" />);
    await userEvent.type(screen.getByLabelText("Title"), "Wifi");
    await userEvent.type(screen.getByLabelText("Text"), "Down");
    await userEvent.click(screen.getByRole("button", { name: "Post announcement" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You cannot do this for this office.");
    expect(screen.getByLabelText("Title")).toHaveValue("Wifi");
  });

  it("archives a live row and marks it archived", async () => {
    m.office.mockResolvedValue([OUTAGE]);
    m.archive.mockResolvedValue({ ok: true, data: { ...OUTAGE, archived_at: "2026-11-05T06:00:00Z" } });
    render(<StaffAnnouncements role="staff" alias="it" office="it" />);
    const table = await screen.findByRole("table", { name: "Announcements you manage" });
    const rowEl = within(table).getByText("Library wifi is down").closest("tr") as HTMLElement;
    await userEvent.click(within(rowEl).getByRole("button", { name: 'Archive "Library wifi is down"' }));
    expect(m.archive).toHaveBeenCalledWith("1");
    await waitFor(() => expect(within(rowEl).getByText("Archived")).toBeInTheDocument());
    expect(within(rowEl).getByRole("button", { name: /Archive/ })).toBeDisabled();
  });
});

const profiles: ProfileRow[] = [
  { id: "p1", role: "student", office: null, alias: "lina", display_name: "Lina Haddad", student_number: "20260001", faculty: "Engineering", university_email: "lina@demo.invalid" },
  { id: "p2", role: "staff", office: "it", alias: "it", display_name: "IT Desk", student_number: null, faculty: null, university_email: null },
  { id: "p3", role: "admin", office: null, alias: "admin", display_name: "Admin One", student_number: null, faculty: null, university_email: null },
];

describe("AccountsScreen", () => {
  it("lists every account in a read-only table, admin first by role order", () => {
    render(<AccountsScreen alias="admin" name="Admin One" rows={profiles} />);
    const table = screen.getByRole("table", { name: "Accounts" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Name",
      "Role",
      "Office",
      "Alias",
      "Student number",
    ]);
    const body = within(table).getAllByRole("row").slice(1);
    expect(body.map((r) => within(r).getAllByRole("cell")[1]!.textContent)).toEqual(["Admin", "Staff", "Student"]);
    const lina = within(table).getByText("Lina Haddad").closest("tr") as HTMLElement;
    expect(within(lina).getByText("20260001")).toBeInTheDocument();
    expect(within(table).getByText("IT Support")).toBeInTheDocument();
    expect(within(table).queryByRole("button", { name: /edit|delete/i })).not.toBeInTheDocument();
    expect(screen.getByText("Simulated account: fictional data.")).toBeInTheDocument();
  });

  it("shows the empty text without rows", () => {
    render(<AccountsScreen alias="admin" rows={[]} />);
    expect(screen.getByText("No accounts found.")).toBeInTheDocument();
  });
});

describe("ProfileScreen", () => {
  it("shows a student's fields read-only with the simulated-account note", () => {
    render(<ProfileScreen role="student" profile={profiles[0]!} />);
    expect(screen.getByText("Lina Haddad")).toBeInTheDocument();
    expect(screen.getByText("20260001")).toBeInTheDocument();
    expect(screen.getByText("Engineering")).toBeInTheDocument();
    expect(screen.getByText("lina@demo.invalid")).toBeInTheDocument();
    expect(screen.getByText("Student")).toBeInTheDocument();
    expect(screen.getByText("Simulated account: fictional data.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("shows the office of a staff member and no student fields", () => {
    render(<ProfileScreen role="staff" profile={profiles[1]!} />);
    expect(screen.getByText("IT Support")).toBeInTheDocument();
    expect(screen.queryByText("Student number")).not.toBeInTheDocument();
  });
});
