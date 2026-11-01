import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LangScope } from "@/i18n";
import { RoleNav } from "../RoleNav";

const links = () => within(screen.getByRole("navigation")).getAllByRole("link");

describe("RoleNav", () => {
  it("gives staff the desk, the review queue, the map and the outbox, in that order, and no model lab", () => {
    render(<RoleNav role="staff" current="staff" />);
    expect(links().map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["Staff desk", "/staff"],
      ["Review queue", "/staff/reviews"],
      ["Pulse map", "/pulse"],
      ["Outbox", "/outbox"],
    ]);
  });

  it("gives an admin the model lab first, then the same pages", () => {
    render(<RoleNav role="admin" current="lab" />);
    expect(links().map((a) => a.getAttribute("href"))).toEqual(["/lab", "/staff", "/staff/reviews", "/pulse", "/outbox"]);
  });

  it("marks exactly the current page", () => {
    render(<RoleNav role="admin" current="pulse" />);
    const current = links().filter((a) => a.getAttribute("aria-current") === "page");
    expect(current.map((a) => a.textContent)).toEqual(["Pulse map"]);
  });

  it("is named and translated in Arabic", () => {
    render(
      <LangScope lang="ar">
        <RoleNav role="admin" current="lab" />
      </LangScope>,
    );
    expect(screen.getByRole("navigation", { name: "صفحات الموظفين" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "مختبر النماذج" })).toHaveAttribute("aria-current", "page");
  });
});
