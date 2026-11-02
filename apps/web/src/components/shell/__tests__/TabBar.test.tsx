import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LangScope } from "@/i18n";
import { tabsFor, tilesFor } from "@/lib/nav";
import { TabBar } from "../TabBar";

const links = () => within(screen.getByRole("navigation", { name: "Main menu" })).getAllByRole("link");
const pairs = () => links().map((a) => [a.textContent, a.getAttribute("href")]);

describe("TabBar", () => {
  it("gives a student Home, Ask, My requests and Profile", () => {
    render(<TabBar role="student" current="home" />);
    expect(pairs()).toEqual([
      ["Home", "/"],
      ["Ask", "/ask"],
      ["My requests", "/requests"],
      ["Profile", "/profile"],
    ]);
  });

  it("gives staff the queue, announcements, incidents and corrections, and no accounts or reports", () => {
    render(<TabBar role="staff" current="queue" />);
    expect(pairs()).toEqual([
      ["Queue", "/staff"],
      ["Announcements", "/staff/announcements"],
      ["Incidents", "/pulse"],
      ["Corrections", "/staff/reviews"],
    ]);
  });

  it("gives an admin the staff tabs plus Accounts and Reports", () => {
    render(<TabBar role="admin" current="reports" />);
    expect(pairs().slice(4)).toEqual([
      ["Accounts", "/admin/accounts"],
      ["Reports", "/lab"],
    ]);
    expect(links()).toHaveLength(6);
  });

  it("marks exactly the current tab with aria-current", () => {
    render(<TabBar role="admin" current="incidents" />);
    const current = links().filter((a) => a.getAttribute("aria-current") === "page");
    expect(current.map((a) => a.textContent)).toEqual(["Incidents"]);
  });

  it("marks no tab for a page that has none (the outbox)", () => {
    render(<TabBar role="admin" current="outbox" />);
    expect(links().some((a) => a.hasAttribute("aria-current"))).toBe(false);
  });

  it("is named and translated in Arabic", () => {
    render(
      <LangScope lang="ar">
        <TabBar role="student" current="ask" />
      </LangScope>,
    );
    expect(screen.getByRole("navigation", { name: "القائمة الرئيسية" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "اسأل" })).toHaveAttribute("aria-current", "page");
  });
});

describe("nav tiles", () => {
  it("has no tiles for students, two for staff and the outbox too for admins", () => {
    expect(tilesFor("student")).toEqual([]);
    expect(tilesFor("staff").map((t) => t.href)).toEqual(["/ask", "/requests"]);
    expect(tilesFor("admin").map((t) => t.href)).toEqual(["/ask", "/requests", "/outbox"]);
  });

  it("only lists tabs whose routes the proxy lets that role open", () => {
    expect(tabsFor("student").every((t) => !t.href.startsWith("/staff") && !t.href.startsWith("/admin") && t.href !== "/lab")).toBe(true);
  });
});
