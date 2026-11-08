import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import { TRIAGE_FIXTURES } from "@/lib/fixtures/api";
import type { ChatConfirmResponse, ChatCorrectionOut, ChatTicketOut, ChatTurnResponse, ProposalOut } from "@/lib/chat/agentTypes";

vi.mock("@/hooks/useSignIn", () => ({ useSignOut: () => vi.fn() }));

import { AgentScreen } from "../AgentScreen";
import { ProposalCard } from "../ProposalCard";
import { WithdrawCard } from "../WithdrawCard";

const OLD: ChatTicketOut = {
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
const CORRECTION: ChatCorrectionOut = { ticket: OLD, old_text: "The printer in H302 is broken." };
const PROPOSAL: ProposalOut = {
  token: "tok-fix",
  text: "The printer in H203 is broken.",
  category: "Facilities",
  priority: "medium",
  office: "facilities",
  action_kind: "ticket",
  question: null,
  faq: null,
  hint: null,
  why: {
    category: { label: "Facilities", prob: 0.9, set: ["Facilities"] },
    priority: { label: "medium", prob: 0.7, set: ["medium"], evidence: [] },
    neighbors: [],
  },
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const calls: Array<{ url: string; body: Record<string, unknown> | null }> = [];
let respond: (url: string) => Response;

const turn = (o: Partial<ChatTurnResponse>): ChatTurnResponse => ({
  mode: "agent",
  reply: "",
  proposal: null,
  ticket_id: null,
  triage: null,
  clear_proposal: false,
  tickets: [],
  correction: null,
  withdraw: null,
  ...o,
});

beforeEach(() => {
  calls.length = 0;
  respond = () => json({}, 404);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null });
      return respond(url);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const renderScreen = (lang: "en" | "ar" = "en") =>
  render(
    <LangScope lang={lang}>
      <AgentScreen alias="talal" role="student" />
    </LangScope>,
  );

describe("ProposalCard as a correction", () => {
  const setup = () => {
    const onConfirm = vi.fn();
    const onDecline = vi.fn();
    render(<ProposalCard proposal={PROPOSAL} correction={CORRECTION} busy={false} onConfirm={onConfirm} onDecline={onDecline} onAnswer={vi.fn()} />);
    return { onConfirm, onDecline };
  };

  it("asks 'Fix request #n?' and shows the old and the corrected text with the change marked", () => {
    setup();
    expect(screen.getByRole("heading", { level: 2, name: "Fix request #AB12CD34?" })).toBeInTheDocument();
    expect(screen.getByText("The printer in H302 is broken.")).toBeInTheDocument();
    const changed = screen.getByText("H203");
    expect(changed.tagName).toBe("MARK");
    expect(screen.queryByRole("button", { name: "Yes, send it" })).not.toBeInTheDocument();
  });

  it("'Yes, replace' confirms with replace true, 'separate' with false, 'Cancel' drops it", async () => {
    const { onConfirm, onDecline } = setup();
    await userEvent.click(screen.getByRole("button", { name: "Yes, replace #AB12CD34" }));
    expect(onConfirm).toHaveBeenLastCalledWith(true);
    await userEvent.click(screen.getByRole("button", { name: "No, it's a separate request" }));
    expect(onConfirm).toHaveBeenLastCalledWith(false);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onDecline).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledTimes(2);
  });

  it("is in Arabic in Arabic", () => {
    render(
      <LangScope lang="ar">
        <ProposalCard proposal={PROPOSAL} correction={CORRECTION} busy={false} onConfirm={vi.fn()} onDecline={vi.fn()} onAnswer={vi.fn()} />
      </LangScope>,
    );
    expect(screen.getByRole("heading", { level: 2, name: "تصحيح الطلب #AB12CD34؟" })).toBeInTheDocument();
  });
});

describe("WithdrawCard", () => {
  it("shows the request and the two buttons", async () => {
    const onClose = vi.fn();
    const onKeep = vi.fn();
    render(<WithdrawCard ticket={OLD} busy={false} onClose={onClose} onKeep={onKeep} />);
    expect(screen.getByRole("heading", { level: 2, name: "Close request #AB12CD34?" })).toBeInTheDocument();
    expect(screen.getByText("Printer broken in H302")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close it" }));
    await userEvent.click(screen.getByRole("button", { name: "Keep it" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onKeep).toHaveBeenCalledTimes(1);
  });
});

describe("AgentScreen cards", () => {
  const send = async (text: string) => userEvent.type(screen.getByLabelText("Your request"), `${text}{Enter}`);

  it("a status turn shows one card per request under the reply", async () => {
    respond = () => json(turn({ reply: "You have two requests.", tickets: [OLD, { ...OLD, ticket_id: "t2", number: "FF00FF00", title: "Wifi", status: "solved" }] }));
    renderScreen();
    await send("what is the status of my requests");
    expect(await screen.findByText("You have two requests.")).toBeInTheDocument();
    const cards = await screen.findAllByRole("article");
    expect(cards.map((c) => c.getAttribute("data-status"))).toEqual(["new", "solved"]);
  });

  it("a correction turn: 'Yes, replace' sends replace true and shows the new ticket and the old one as Closed", async () => {
    const confirmed: ChatConfirmResponse = {
      triage: TRIAGE_FIXTURES.enMemory.response,
      ticket_id: "cd34ab12-0000-4000-8000-000000000002",
      hint_applied: false,
      closed_ticket: { ...OLD, status: "closed", resolved_at: "2026-11-08T10:00:00Z" },
    };
    respond = (url) => (url.endsWith("/chat/turn") ? json(turn({ reply: "Did you mean to fix #AB12CD34?", proposal: PROPOSAL, correction: CORRECTION })) : json(confirmed));
    renderScreen();
    await send("I wrote H302, it is H203");
    await userEvent.click(await screen.findByRole("button", { name: "Yes, replace #AB12CD34" }));
    expect(calls[1]?.body).toEqual({ proposal_token: "tok-fix", replace: true });
    const closed = await screen.findByRole("article");
    expect(closed).toHaveAttribute("data-status", "closed");
    expect(screen.getByText(/Request recorded/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Yes, replace/ })).not.toBeInTheDocument();
  });

  it("'No, it's a separate request' sends replace false and shows no Closed card", async () => {
    const confirmed: ChatConfirmResponse = { triage: TRIAGE_FIXTURES.enMemory.response, ticket_id: "cd34ab12-0000-4000-8000-000000000002", hint_applied: false, closed_ticket: null };
    respond = (url) => (url.endsWith("/chat/turn") ? json(turn({ reply: "Fix it?", proposal: PROPOSAL, correction: CORRECTION })) : json(confirmed));
    renderScreen();
    await send("same printer problem in H203");
    await userEvent.click(await screen.findByRole("button", { name: "No, it's a separate request" }));
    await screen.findByText(/Request recorded/);
    expect(calls[1]?.body).toEqual({ proposal_token: "tok-fix", replace: false });
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });

  it("'Cancel' on a correction drops the proposal and calls nothing", async () => {
    respond = () => json(turn({ reply: "Fix it?", proposal: PROPOSAL, correction: CORRECTION }));
    renderScreen();
    await send("I wrote H302, it is H203");
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(calls).toHaveLength(1);
    expect(screen.queryByRole("heading", { name: /Fix request/ })).not.toBeInTheDocument();
    expect(screen.getByText("Okay, nothing was sent.")).toBeInTheDocument();
  });

  it("a withdraw turn: 'Close it' posts the close action and the card becomes Closed", async () => {
    respond = (url) =>
      url.endsWith("/chat/turn")
        ? json(turn({ reply: "Close request #AB12CD34?", withdraw: OLD }))
        : json({ ticket_id: OLD.ticket_id, status: "closed", resolved_at: "2026-11-08T10:00:00Z" });
    renderScreen();
    await send("please cancel my printer request");
    const card = (await screen.findByRole("heading", { name: "Close request #AB12CD34?" })).closest("section") as HTMLElement;
    await userEvent.click(within(card).getByRole("button", { name: "Close it" }));
    await waitFor(() => expect(calls[1]?.url).toContain(`/tickets/${OLD.ticket_id}/student-action`));
    expect(calls[1]?.body).toEqual({ action: "close" });
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Close request #AB12CD34?" })).not.toBeInTheDocument());
    expect(screen.getByRole("article")).toHaveAttribute("data-status", "closed");
    expect(screen.getByText("Request #AB12CD34 is closed.")).toBeInTheDocument();
  });

  it("'Keep it' sends nothing and keeps the request open", async () => {
    respond = () => json(turn({ reply: "Close request #AB12CD34?", withdraw: OLD }));
    renderScreen();
    await send("please cancel my printer request");
    await userEvent.click(await screen.findByRole("button", { name: "Keep it" }));
    expect(calls).toHaveLength(1);
    expect(screen.getByText("Okay, the request stays open.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Close it" })).not.toBeInTheDocument();
  });

  it("a failed close shows the error and keeps the card", async () => {
    respond = (url) => (url.endsWith("/chat/turn") ? json(turn({ reply: "Close?", withdraw: OLD })) : json({ error: { code: "internal", message: "x", details: null } }, 400));
    renderScreen();
    await send("cancel it");
    await userEvent.click(await screen.findByRole("button", { name: "Close it" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close it" })).toBeInTheDocument();
  });
});
