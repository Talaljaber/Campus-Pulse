import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LangScope } from "@/i18n";
import type { ChatTicketOut } from "@/lib/chat/agentTypes";
import { StatusCard, StatusCards } from "../StatusCard";

const TICKET: ChatTicketOut = {
  ticket_id: "ab12cd34-0000-4000-8000-000000000009",
  number: "AB12CD34",
  title: "Printer broken in H302",
  office: "facilities",
  category: "Facilities",
  priority: "medium",
  status: "new",
  awaiting_student: false,
  created_at: "2026-11-01T10:00:00Z",
  resolved_at: null,
};

const WORD: Record<ChatTicketOut["status"], string> = {
  new: "Received",
  in_progress: "In progress",
  solved: "Solved",
  closed: "Closed",
  merged: "Merged",
};

describe("StatusCard", () => {
  it.each(Object.keys(WORD) as ChatTicketOut["status"][])("shows %s as a word with its own mark and a link to the request", (status) => {
    const { container } = render(<StatusCard ticket={{ ...TICKET, status }} />);
    const card = screen.getByRole("article");
    expect(card).toHaveAttribute("data-status", status);
    expect(screen.getByRole("status")).toHaveTextContent(WORD[status]);
    expect(card).toHaveTextContent("#AB12CD34");
    expect(card).toHaveTextContent("Printer broken in H302");
    expect(screen.getByRole("link", { name: "Open request #AB12CD34" })).toHaveAttribute("href", `/requests/${TICKET.ticket_id}`);
    expect(screen.getByText("Medium")).toBeInTheDocument();
    expect(container.querySelector(`.cp-st-${status.replace("_", "-")}`)).not.toBeNull();
  });

  it("in progress has three dots, merged has two, solved has the check path", () => {
    const { container, rerender } = render(<StatusCard ticket={{ ...TICKET, status: "in_progress" }} />);
    expect(container.querySelectorAll(".cp-st-in-progress i")).toHaveLength(3);
    rerender(<StatusCard ticket={{ ...TICKET, status: "merged" }} />);
    expect(container.querySelectorAll(".cp-st-merged i")).toHaveLength(2);
    rerender(<StatusCard ticket={{ ...TICKET, status: "solved" }} />);
    expect(container.querySelector(".cp-st-check")).not.toBeNull();
  });

  it("says when the office replied and waits, and only then", () => {
    const { rerender } = render(<StatusCard ticket={TICKET} />);
    expect(screen.queryByText("The office replied, please check")).not.toBeInTheDocument();
    rerender(<StatusCard ticket={{ ...TICKET, awaiting_student: true }} />);
    expect(screen.getByText("The office replied, please check")).toBeInTheDocument();
  });

  it("speaks Arabic in Arabic", () => {
    render(
      <LangScope lang="ar">
        <StatusCards tickets={[{ ...TICKET, status: "closed" }]} />
      </LangScope>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("مسكّر");
  });

  it("every animation lives under prefers-reduced-motion: no-preference, so reduced motion shows only the final state", () => {
    const css = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
    const start = css.indexOf("Chat status cards");
    expect(start).toBeGreaterThan(-1);
    const block = css.slice(start);
    const media = block.indexOf("@media (prefers-reduced-motion: no-preference)");
    expect(media).toBeGreaterThan(-1);
    // Outside the media query only static layout is allowed: no animation property before it.
    expect(block.slice(0, media)).not.toMatch(/animation\s*:/);
    // The animated rules and keyframes come after it.
    const inside = block.slice(media);
    for (const name of ["cp-st-ripple", "cp-st-breathe", "cp-st-draw", "cp-st-glow", "cp-st-settle", "cp-st-join-a", "cp-st-join-b"]) {
      expect(inside).toContain(`@keyframes ${name}`);
    }
  });
});

