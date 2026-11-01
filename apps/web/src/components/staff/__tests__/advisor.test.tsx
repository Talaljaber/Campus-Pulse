import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import reviewsFixture from "@fixtures/reviews_open_advisor.json";
import { LangScope } from "@/i18n";
import type { ReviewItem } from "@/lib/ai/types";
import type { TicketView } from "@/lib/staff/tickets";
import { AdvisorReviewDetail, AdvisorReviewList } from "../AdvisorReviews";
import { ForwardForm } from "../ForwardForm";
import { officeOfCategory } from "../office";
import { RequestDetail } from "../RequestDetail";

const ITEMS = reviewsFixture.response as ReviewItem[];
const MINE = ITEMS.find((i) => i.assigned_to_me)!;
const QUEUE = ITEMS.find((i) => !i.assigned_to_me)!;

const ticket: TicketView = {
  id: "t1",
  request_id: "r1",
  incident_id: null,
  office: "it",
  category: "IT Support",
  priority: "high",
  status: "open",
  provisional: false,
  title: "Wi-Fi down in M",
  body: "",
  sla_due_at: "2026-11-09T10:00:00Z",
  escalated_at: null,
  resolved_at: null,
  created_at: "2026-11-08T08:00:00Z",
  link: null,
  tags: [],
};

describe("AdvisorReviewList", () => {
  it("lists the items and marks only the advisor's own student", async () => {
    const onSelect = vi.fn();
    render(<AdvisorReviewList items={ITEMS} selectedId={null} onSelect={onSelect} />);
    const rows = within(screen.getByRole("list", { name: "Requests to review" })).getAllByRole("listitem");
    expect(rows).toHaveLength(ITEMS.length);
    expect(screen.getAllByText("Your student")).toHaveLength(ITEMS.filter((i) => i.assigned_to_me).length);
    await userEvent.setup().click(within(rows[0]!).getByRole("button"));
    expect(onSelect).toHaveBeenCalledWith(ITEMS[0]!.id);
  });

  it("says so when nothing waits", () => {
    render(<AdvisorReviewList items={[]} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText("Nothing to review here")).toBeInTheDocument();
  });
});

describe("AdvisorReviewDetail", () => {
  const props = { onConfirm: vi.fn(), onForward: vi.fn(), onClose: vi.fn() };

  it("shows the text, the guess, the conformal sets and why the model asked", () => {
    render(<AdvisorReviewDetail item={MINE} {...props} />);
    expect(screen.getByText(MINE.text)).toBeInTheDocument();
    expect(screen.getByText("Student talal")).toBeInTheDocument();
    expect(screen.getByText(/Category could be IT Support \/ Academic Support/)).toBeInTheDocument();
    expect(screen.getByText("IT Support / Academic Support")).toBeInTheDocument();
  });

  it("confirms with one click", async () => {
    const onConfirm = vi.fn();
    render(<AdvisorReviewDetail item={MINE} {...props} onConfirm={onConfirm} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalledWith(MINE);
  });

  it("forwards to an office with a note, starting on the office of the guessed category", async () => {
    const user = userEvent.setup();
    const onForward = vi.fn();
    render(<AdvisorReviewDetail item={MINE} {...props} onForward={onForward} />);
    await user.click(screen.getByRole("button", { name: "Forward to an office" }));
    const office = screen.getByLabelText("Office") as HTMLSelectElement;
    expect(office.value).toBe("academic");
    await user.selectOptions(office, "it");
    await user.type(screen.getByLabelText("Note for the office (optional)"), "The platform is down.");
    await user.click(screen.getByRole("button", { name: "Forward" }));
    expect(onForward).toHaveBeenCalledWith(MINE, "it", "The platform is down.");
  });

  it("keeps the form open and shows the not-yours sentence after a refused forward", async () => {
    const user = userEvent.setup();
    render(<AdvisorReviewDetail item={QUEUE} {...props} error="This item is in another advisor's or office's queue, so you cannot resolve it." />);
    // The error shows before the form is opened, next to the actions...
    expect(screen.getByRole("alert")).toHaveTextContent("another advisor's or office's queue");
    await user.click(screen.getByRole("button", { name: "Forward to an office" }));
    // ...and inside the form once it is open, so the reviewer keeps their note.
    expect(within(screen.getByRole("form", { name: "Forward to an office" })).getByRole("alert")).toBeInTheDocument();
  });

  it("offers no actions on a resolved item and shows the outcome", () => {
    const done: ReviewItem = { ...MINE, status: "corrected", corrected_category: "IT Support", note: "Moved to IT." };
    render(<AdvisorReviewDetail item={done} {...props} />);
    expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Forward to an office" })).toBeNull();
    expect(screen.getByText("Resolved as IT Support.")).toBeInTheDocument();
    expect(screen.getByText("Moved to IT.")).toBeInTheDocument();
  });

  it("lets a distress item be forwarded but not confirmed as a label", () => {
    render(<AdvisorReviewDetail item={{ ...MINE, reason: "distress" }} {...props} />);
    expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull();
    expect(screen.getByRole("button", { name: "Forward to an office" })).toBeInTheDocument();
  });

  it("renders in Arabic with the right-to-left text direction on the request", () => {
    render(
      <LangScope lang="ar">
        <AdvisorReviewDetail item={{ ...MINE, text: "ما بقدر أفتح صفحة المساق" }} {...props} />
      </LangScope>,
    );
    expect(screen.getByRole("button", { name: "حوّل لمكتب" })).toBeInTheDocument();
    expect(screen.getByText("ما بقدر أفتح صفحة المساق")).toHaveAttribute("dir", "rtl");
  });
});

describe("ForwardForm", () => {
  it("leaves the excluded office out and falls back to the first one left", () => {
    render(<ForwardForm initialOffice="it" exclude={["it"]} onSubmit={() => {}} onCancel={() => {}} />);
    const options = within(screen.getByLabelText("Office")).getAllByRole("option").map((o) => (o as HTMLOptionElement).value);
    expect(options).not.toContain("it");
    expect(options).toHaveLength(5);
    expect((screen.getByLabelText("Office") as HTMLSelectElement).value).toBe("registrar");
  });

  it("does not submit while busy", async () => {
    const onSubmit = vi.fn();
    render(<ForwardForm initialOffice="it" busy onSubmit={onSubmit} onCancel={() => {}} />);
    expect(screen.getByLabelText("Office")).toBeDisabled();
    await userEvent.setup().type(screen.getByLabelText("Note for the office (optional)"), "x");
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("RequestDetail ticket forward", () => {
  const base = { ticket, detail: null, load: "ready" as const, audience: "staff" as const, onClose: () => {} };

  it("has no forward button unless the page wires it", () => {
    render(<RequestDetail {...base} />);
    expect(screen.queryByRole("button", { name: "Forward to another office" })).toBeNull();
  });

  it("forwards the ticket to another office, never to the one that holds it", async () => {
    const user = userEvent.setup();
    const onForward = vi.fn();
    render(<RequestDetail {...base} onForward={onForward} />);
    await user.click(screen.getByRole("button", { name: "Forward to another office" }));
    const office = screen.getByLabelText("Office") as HTMLSelectElement;
    expect(within(office).queryByRole("option", { name: "IT Support" })).toBeNull();
    await user.selectOptions(office, "facilities");
    await user.click(screen.getByRole("button", { name: "Forward" }));
    expect(onForward).toHaveBeenCalledWith("facilities", "");
  });
});

describe("officeOfCategory", () => {
  it("maps every category to its office and ignores unknown ones", () => {
    expect(officeOfCategory("Registration")).toBe("registrar");
    expect(officeOfCategory("Transportation")).toBe("transport");
    expect(officeOfCategory("Academic Support")).toBe("academic");
    expect(officeOfCategory("Other")).toBeNull();
  });
});
