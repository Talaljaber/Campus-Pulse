import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LangScope } from "@/i18n";
import { Breadcrumb } from "../Breadcrumb";

describe("Breadcrumb", () => {
  it("is a named nav with an ordered list; the last step is the current page and not a link", () => {
    render(<Breadcrumb crumbs={[{ label: "CampusPulse", href: "/" }, { label: "My requests" }]} />);
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    const items = within(nav).getAllByRole("listitem");
    expect(within(nav).getByRole("list").tagName).toBe("OL");
    expect(within(nav).getByRole("link", { name: "CampusPulse" })).toHaveAttribute("href", "/");
    expect(within(nav).queryByRole("link", { name: "My requests" })).toBeNull();
    expect(screen.getByText("My requests")).toHaveAttribute("aria-current", "page");
    // two steps; the separator between them is hidden from assistive technology
    expect(items).toHaveLength(2);
    expect(nav.querySelectorAll('[aria-hidden="true"]')).toHaveLength(1);
  });

  it("renders nothing for an empty trail", () => {
    const { container } = render(<Breadcrumb crumbs={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("is named in Arabic", () => {
    render(
      <LangScope lang="ar">
        <Breadcrumb crumbs={[{ label: "كامبس بلس" }]} />
      </LangScope>,
    );
    expect(screen.getByRole("navigation", { name: "مسار التنقل" })).toBeInTheDocument();
  });
});
