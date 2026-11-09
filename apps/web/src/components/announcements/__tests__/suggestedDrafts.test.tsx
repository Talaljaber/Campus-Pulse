import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import { ToastProvider } from "../../ui/Toast";

const m = vi.hoisted(() => ({ callAi: vi.fn() }));
vi.mock("@/lib/ai/browser", () => ({ callAi: m.callAi }));

import { SuggestedDrafts } from "../SuggestedDrafts";

const draft = (o: Record<string, unknown> = {}) => ({
  id: "d1",
  incident_id: "i1",
  office: "it",
  title: "Wifi problems in building K",
  body: "Several students report no wifi in K. IT is looking into it.",
  status: "pending",
  version: 3,
  published_announcement_id: null,
  ...o,
});

type Call = [string, { method?: string; body?: unknown }?];
const calls = () => m.callAi.mock.calls as Call[];

function setup(list: unknown[], reply: unknown = { ok: true, data: draft({ status: "published" }) }) {
  m.callAi.mockImplementation(async (path: string, init?: { method?: string }) =>
    path === "announcement-drafts" && !init?.method ? { ok: true, data: list } : reply,
  );
  return render(
    <LangScope lang="en">
      <ToastProvider>
        <SuggestedDrafts />
      </ToastProvider>
    </LangScope>,
  );
}

beforeEach(() => m.callAi.mockReset());

describe("SuggestedDrafts", () => {
  it("renders nothing when there are no pending drafts", async () => {
    setup([draft({ status: "published" }), draft({ id: "d2", status: "dismissed" })]);
    await waitFor(() => expect(m.callAi).toHaveBeenCalled());
    expect(screen.queryByText("Suggested from incidents")).not.toBeInTheDocument();
  });

  it("shows a pending draft with its office and editable fields", async () => {
    setup([draft()]);
    expect(await screen.findByRole("heading", { name: "Suggested from incidents" })).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveValue("Wifi problems in building K");
    expect(screen.getByLabelText("Text")).toHaveValue(draft().body);
    expect(screen.getByRole("button", { name: "Publish" })).toBeInTheDocument();
  });

  it("publishes with the draft version and removes the card", async () => {
    setup([draft()]);
    await userEvent.click(await screen.findByRole("button", { name: "Publish" }));
    expect(await screen.findByText("Announcement published.")).toBeInTheDocument();
    expect(calls().at(-1)).toEqual(["announcement-drafts/d1/publish", { method: "POST", body: { version: 3 } }]);
    expect(screen.queryByLabelText("Title")).not.toBeInTheDocument();
  });

  it("saves edits with a PATCH and keeps the draft", async () => {
    setup([draft()], { ok: true, data: draft({ title: "New", version: 4 }) });
    const title = await screen.findByLabelText("Title");
    await userEvent.clear(title);
    await userEvent.type(title, "New");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Changes saved.")).toBeInTheDocument();
    expect(calls().at(-1)).toEqual([
      "announcement-drafts/d1",
      { method: "PATCH", body: { version: 3, title: "New", body: draft().body } },
    ]);
    expect(screen.getByLabelText("Title")).toHaveValue("New");
  });

  it("dismisses only after confirmation", async () => {
    setup([draft()], { ok: true, data: draft({ status: "dismissed" }) });
    await userEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(screen.getByText("Dismiss this suggestion?")).toBeInTheDocument();
    expect(calls().some(([p]) => p.endsWith("/dismiss"))).toBe(false);
    const buttons = screen.getAllByRole("button", { name: "Dismiss" });
    await userEvent.click(buttons[buttons.length - 1]!);
    expect(await screen.findByText("Suggestion dismissed.")).toBeInTheDocument();
    expect(calls().at(-1)).toEqual(["announcement-drafts/d1/dismiss", { method: "POST", body: { version: 3 } }]);
  });

  it("shows the conflict message on a 409 and keeps the draft", async () => {
    setup([draft()], { ok: false, status: 409, code: "conflict", error: "stale", details: null, waking: false });
    await userEvent.click(await screen.findByRole("button", { name: "Publish" }));
    expect(await screen.findByText("Someone else changed this draft. Reload the page and try again.")).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toBeInTheDocument();
  });
});
