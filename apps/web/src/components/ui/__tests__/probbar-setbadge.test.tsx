import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LangScope } from "@/i18n";
import { TRIAGE_FIXTURES } from "@/lib/fixtures/api";
import { ProbBar } from "../ProbBar";
import { SetBadge } from "../SetBadge";

describe("ProbBar", () => {
  it("is a named meter with the rounded percentage", () => {
    render(<ProbBar label="Category: IT Support" prob={0.784} tone="cat-it" />);
    const meter = screen.getByRole("meter", { name: "Category: IT Support" });
    expect(meter).toHaveAttribute("aria-valuenow", "78");
    expect(meter).toHaveAttribute("aria-valuemin", "0");
    expect(meter).toHaveAttribute("aria-valuemax", "100");
    expect(meter).toHaveAttribute("aria-valuetext", "78%");
    expect(screen.getByText("78%")).toBeInTheDocument();
  });

  it("clamps out-of-range and non-finite values", () => {
    const { rerender } = render(<ProbBar label="x" prob={1.4} />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "100");
    rerender(<ProbBar label="x" prob={-2} />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "0");
    rerender(<ProbBar label="x" prob={Number.NaN} />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "0");
  });

  it("keeps the digits left-to-right inside an Arabic layout and fills by logical width", () => {
    const { response } = TRIAGE_FIXTURES.arBooking;
    render(
      <LangScope lang="ar">
        <ProbBar label="التصنيف" prob={response.category!.prob} />
      </LangScope>,
    );
    const pct = screen.getByText(`${Math.round(response.category!.prob * 100)}%`);
    expect(pct).toHaveAttribute("dir", "ltr");
    const fill = screen.getByRole("meter").firstElementChild as HTMLElement;
    expect(fill.style.inlineSize).toBe(`${Math.round(response.category!.prob * 100)}%`);
  });
});

describe("SetBadge", () => {
  it("lists the labels other than the chosen one", () => {
    const { response } = TRIAGE_FIXTURES.arClarification;
    render(<SetBadge set={response.category!.set} kind="category" chosen="Registration" />);
    const group = screen.getByRole("group", { name: /could also be \(category\)/i });
    expect(within(group).getByText("IT Support")).toBeInTheDocument();
    expect(within(group).queryByText("Registration")).not.toBeInTheDocument();
  });

  it("renders nothing for a singleton set", () => {
    const { container } = render(<SetBadge set={["high"]} kind="priority" chosen="high" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("translates labels and the heading in Arabic", () => {
    render(
      <LangScope lang="ar">
        <SetBadge set={["Registration", "IT Support"]} kind="category" chosen="Registration" />
      </LangScope>,
    );
    expect(screen.getByText(/ممكن كمان يكون/)).toBeInTheDocument();
    expect(screen.queryByText("IT Support")).not.toBeInTheDocument();
  });
});
