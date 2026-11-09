import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import { COUNTERFACTUAL_FIXTURE, TRIAGE_FIXTURES } from "@/lib/fixtures/api";
import type { ChatConfirmResponse, ChatTurnResponse, ProposalOut } from "@/lib/chat/agentTypes";

vi.mock("@/hooks/useSignIn", () => ({ useSignOut: () => vi.fn() }));

import { AgentScreen } from "../AgentScreen";
import { ProposalCard, RecordedCard } from "../ProposalCard";

const TICKET_ID = "ab12cd34-0000-4000-8000-000000000001";

const PROPOSAL: ProposalOut = {
  token: "tok-1",
  text: "My wifi is down in building M",
  category: "IT Support",
  priority: "high",
  office: "it",
  action_kind: "ticket",
  question: null,
  faq: null,
  hint: null,
  why: {
    category: { label: "IT Support", prob: 0.91, set: ["IT Support", "Facilities"] },
    priority: { label: "high", prob: 0.7, set: ["high", "medium"], evidence: [] },
    neighbors: [{ text: "wifi not working in the lab", label: "IT Support", priority: "high", sim: 0.88, source: "train", created_at: null }],
  },
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const calls: Array<{ url: string; body: Record<string, unknown> | null }> = [];
let respond: (url: string, body: Record<string, unknown> | null) => Response;

const turn = (o: Partial<ChatTurnResponse>): ChatTurnResponse => ({
  mode: "agent",
  reply: "",
  proposal: null,
  ticket_id: null,
  triage: null,
  clear_proposal: false,
  ...o,
});
const confirmed: ChatConfirmResponse = { triage: TRIAGE_FIXTURES.enMemory.response, ticket_id: TICKET_ID, hint_applied: false };

beforeEach(() => {
  localStorage.clear(); // the chat is saved per alias (lib/chat/persist)
  calls.length = 0;
  respond = () => json({ error: { code: "not_found", message: "no", details: null } }, 404);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
      calls.push({ url, body });
      return respond(url, body);
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

describe("ProposalCard", () => {
  it("shows department, priority and action, and calls the two buttons", async () => {
    const onConfirm = vi.fn();
    const onDecline = vi.fn();
    render(<ProposalCard proposal={PROPOSAL} busy={false} onConfirm={onConfirm} onDecline={onDecline} onAnswer={vi.fn()} />);
    expect(screen.getByText("Department: IT Support")).toBeInTheDocument();
    expect(screen.getByText("Priority: High")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Yes, send it" }));
    await userEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onDecline).toHaveBeenCalledTimes(1);
  });

  it("keeps the numbers behind 'Why this?', hidden by default, and toggles them", async () => {
    render(<ProposalCard proposal={PROPOSAL} busy={false} onConfirm={vi.fn()} onDecline={vi.fn()} onAnswer={vi.fn()} />);
    expect(screen.queryByText(/91%/)).not.toBeInTheDocument();
    expect(screen.queryByText(/wifi not working in the lab/)).not.toBeInTheDocument();
    const why = screen.getByRole("button", { name: "Why this?" });
    expect(why).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(why);
    expect(why).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/91%/)).toBeInTheDocument();
    expect(screen.getByText(/wifi not working in the lab/)).toBeInTheDocument();
    await userEvent.click(why);
    expect(screen.queryByText(/91%/)).not.toBeInTheDocument();
  });

  it("shows a FAQ answer with 'Record a request anyway'", async () => {
    const onConfirm = vi.fn();
    const faq: ProposalOut = { ...PROPOSAL, action_kind: "faq_answer", faq: { question: "Bus times?", answer: "Every hour.", source_url: "", is_demo: true, score: 0.9 } };
    render(<ProposalCard proposal={faq} busy={false} onConfirm={onConfirm} onDecline={vi.fn()} onAnswer={vi.fn()} />);
    expect(screen.getByText("Every hour.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yes, send it" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Record a request anyway" }));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("sends the chosen chip as the answer", async () => {
    const onAnswer = vi.fn();
    const asking: ProposalOut = {
      ...PROPOSAL,
      token: "",
      question: { question_id: "q1", text: "Which one?", options: [{ id: "a", text: "Wifi" }, { id: "b", text: "Printer" }] },
    };
    render(<ProposalCard proposal={asking} busy={false} onConfirm={vi.fn()} onDecline={vi.fn()} onAnswer={onAnswer} />);
    await userEvent.click(screen.getByRole("radio", { name: "Printer" }));
    expect(onAnswer).toHaveBeenCalledWith("b");
    expect(screen.queryByRole("button", { name: "Yes, send it" })).not.toBeInTheDocument();
  });

  it("'Why this?' names the past staff correction a hint is based on", async () => {
    const hinted: ProposalOut = { ...PROPOSAL, hint: { hint_id: "h1", category: "IT Support", priority: "high", sim: 0.93 } };
    render(<ProposalCard proposal={hinted} busy={false} onConfirm={vi.fn()} onDecline={vi.fn()} onAnswer={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Why this?" }));
    expect(screen.getByText(/Based on a past staff correction: IT Support, High \(93% similar\)/)).toBeInTheDocument();
  });
});

describe("RecordedCard for a report that joined an incident (P10.25)", () => {
  it("shows the service's sentence about the incident, and nothing extra for a plain ticket", () => {
    const base = TRIAGE_FIXTURES.enMemory.response;
    const merged = {
      ...base,
      action: { ...base.action!, type: "incident_merge" as const, message: "Other students in building M reported the same problem (4 reports so far)." },
    };
    const { rerender } = render(<RecordedCard ticketId={TICKET_ID} triage={merged} proposal={null} />);
    expect(screen.getByText(/Other students in building M reported the same problem/)).toBeInTheDocument();
    rerender(<RecordedCard ticketId={TICKET_ID} triage={base} proposal={null} />);
    expect(screen.queryByText(/Other students in building M/)).not.toBeInTheDocument();
  });
});

describe("AgentScreen typing indicator", () => {
  it("shows three dots while the reply is on its way, then the reply instead", async () => {
    let release: (r: Response) => void = () => {};
    respond = () => json(turn({ reply: "unused" }));
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((resolve) => { release = resolve; })),
    );
    renderScreen();
    await userEvent.type(screen.getByLabelText("Your request"), "hello{Enter}");
    expect(await screen.findByRole("status", { name: "CampusPulse is typing" })).toBeInTheDocument();
    release(json(turn({ reply: "Hi there." })));
    expect(await screen.findByText("Hi there.")).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "CampusPulse is typing" })).not.toBeInTheDocument();
  });
});

describe("AgentScreen keeps the chat across a reload", () => {
  it("shows the same conversation after a reload, and New chat clears it", async () => {
    respond = () => json(turn({ reply: "Which building is it in?" }));
    const first = renderScreen();
    await userEvent.type(screen.getByLabelText("Your request"), "mate we have a wifi issue{Enter}");
    expect(await screen.findByText("Which building is it in?")).toBeInTheDocument();
    first.unmount();

    renderScreen(); // the page opened again
    expect(await screen.findByText("Which building is it in?")).toBeInTheDocument();
    expect(screen.getByText("mate we have a wifi issue")).toBeInTheDocument();

    // the next turn carries the restored history
    respond = () => json(turn({ reply: "Thanks." }));
    await userEvent.type(screen.getByLabelText("Your request"), "L{Enter}");
    await screen.findByText("Thanks.");
    const sentTurn = calls.at(-1)?.body as { messages: Array<{ content: string }> };
    expect(sentTurn.messages.map((m) => m.content)).toEqual(["mate we have a wifi issue", "Which building is it in?", "L"]);

    await userEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.queryByText("Which building is it in?")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New chat" })).not.toBeInTheDocument();
    expect(localStorage.length).toBe(0);
  });

  it("does not show one person's chat to another", async () => {
    respond = () => json(turn({ reply: "Which building is it in?" }));
    const first = renderScreen();
    await userEvent.type(screen.getByLabelText("Your request"), "wifi{Enter}");
    await screen.findByText("Which building is it in?");
    first.unmount();
    render(
      <LangScope lang="en">
        <AgentScreen alias="omar" role="student" />
      </LangScope>,
    );
    await waitFor(() => expect(screen.queryByText("Which building is it in?")).not.toBeInTheDocument());
  });
});

describe("AgentScreen sources (P10.19)", () => {
  it("shows From: <title> under a reply that used documents, and nothing when it used none", async () => {
    respond = () =>
      json(
        turn({
          reply: "Refunds are full in the first week.",
          sources: [
            { id: "knowledge:6f1c", kind: "knowledge", title: "Student Handbook 2026" },
            { id: "announcement:a1", kind: "announcement", title: "Fee deadline moved" },
          ],
        }),
      );
    renderScreen();
    await userEvent.type(screen.getByLabelText("Your request"), "refund?{Enter}");
    expect(await screen.findByText("Refunds are full in the first week.")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Sources" });
    expect(within(list).getByText("From: Student Handbook 2026")).toBeInTheDocument();
    expect(within(list).getByText("From: Fee deadline moved")).toBeInTheDocument();
  });

  it("has no sources line when the reply has none", async () => {
    respond = () => json(turn({ reply: "Hello there." }));
    renderScreen();
    await userEvent.type(screen.getByLabelText("Your request"), "hi{Enter}");
    expect(await screen.findByText("Hello there.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Sources" })).toBeNull();
  });

  it("says المصدر in Arabic", async () => {
    respond = () => json(turn({ reply: "جواب", sources: [{ id: "knowledge:1", kind: "knowledge", title: "دليل الطالب" }] }));
    renderScreen("ar");
    await userEvent.type(screen.getByRole("textbox"), "سؤال{Enter}");
    expect(await screen.findByText("المصدر: دليل الطالب")).toBeInTheDocument();
  });
});

describe("AgentScreen", () => {
  it("happy path: turn, proposal, confirm, recorded with a link and the counterfactual under Why this?", async () => {
    respond = (url) => {
      if (url.endsWith("/chat/turn")) return json(turn({ reply: "I can send this to IT Support.", proposal: PROPOSAL }));
      if (url.endsWith("/chat/confirm")) return json(confirmed);
      if (url.includes("/counterfactual")) return json(COUNTERFACTUAL_FIXTURE);
      return json({}, 404);
    };
    renderScreen();
    expect(screen.queryByText(/no real department/)).toBeNull();
    await userEvent.type(screen.getByLabelText("Your request"), "My wifi is down in building M{Enter}");
    expect(await screen.findByText("I can send this to IT Support.")).toBeInTheDocument();
    expect(calls[0]?.body).toMatchObject({ proposal_token: null, messages: [{ role: "user", content: "My wifi is down in building M" }] });

    await userEvent.click(await screen.findByRole("button", { name: "Yes, send it" }));
    expect(calls[1]?.body).toEqual({ proposal_token: "tok-1" });
    const recorded = await screen.findByText("Request recorded #AB12CD34");
    const card = recorded.closest("section") as HTMLElement;
    expect(within(card).getByRole("link", { name: "View this request" })).toHaveAttribute("href", `/requests/${TICKET_ID}`);
    expect(screen.queryByRole("button", { name: "Yes, send it" })).not.toBeInTheDocument();

    await userEvent.click(within(card).getByRole("button", { name: "Why this?" }));
    const hint = TRIAGE_FIXTURES.enMemory.response.explanation?.counterfactual;
    expect(hint).toBeTruthy();
    await userEvent.click(within(card).getByRole("button", { name: new RegExp(`${hint?.drop}`) }));
    await waitFor(() => expect(calls.some((c) => c.url.includes("/counterfactual"))).toBe(true));
  });

  it("'Not now' clears the proposal without calling the service", async () => {
    respond = () => json(turn({ reply: "Here is what I suggest.", proposal: PROPOSAL }));
    renderScreen();
    await userEvent.type(screen.getByLabelText("Your request"), "wifi{Enter}");
    await userEvent.click(await screen.findByRole("button", { name: "Not now" }));
    expect(screen.queryByRole("button", { name: "Yes, send it" })).not.toBeInTheDocument();
    expect(screen.getByText("Okay, nothing was sent.")).toBeInTheDocument();
    expect(calls).toHaveLength(1);
  });

  it("typing 'yes' sends the pending token to chat/turn", async () => {
    let n = 0;
    respond = () =>
      ++n === 1
        ? json(turn({ reply: "Suggestion ready.", proposal: PROPOSAL }))
        : json(turn({ reply: "Request recorded", ticket_id: TICKET_ID, triage: confirmed.triage, clear_proposal: true }));
    renderScreen();
    await userEvent.type(screen.getByLabelText("Your request"), "wifi{Enter}");
    await screen.findByRole("button", { name: "Yes, send it" });
    await userEvent.type(screen.getByLabelText("Your request"), "yes{Enter}");
    expect(await screen.findByText("Request recorded #AB12CD34")).toBeInTheDocument();
    expect(calls[1]?.body).toMatchObject({ proposal_token: "tok-1" });
  });

  it("a question chip calls chat/preview with the answer and the asked ids (plain form)", async () => {
    const asking: ProposalOut = {
      ...PROPOSAL,
      token: "",
      question: { question_id: "q1", text: "Which one?", options: [{ id: "a", text: "Wifi" }, { id: "b", text: "Printer" }] },
    };
    respond = (url) => {
      if (url.endsWith("/chat/turn")) return json(turn({ mode: "fallback" }));
      const body = calls.at(-1)?.body;
      return json(body?.answer ? PROPOSAL : asking);
    };
    renderScreen();
    await userEvent.type(screen.getByLabelText("Your request"), "it is broken{Enter}");
    await userEvent.click(await screen.findByRole("button", { name: "Check" }));
    expect(screen.queryByRole("button", { name: "Yes, send it" })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("radio", { name: "Wifi" }));
    await waitFor(() => expect(calls).toHaveLength(3));
    expect(calls[2]?.url).toContain("/chat/preview");
    expect(calls[2]?.body).toEqual({ text: asking.text, asked: ["q1"], answer: "a" });
    expect(await screen.findByRole("button", { name: "Yes, send it" })).toBeInTheDocument();
  });

  it("a distress preview shows the distress card and no proposal", async () => {
    const distress: ProposalOut = {
      ...PROPOSAL,
      token: "",
      question: { question_id: "distress", text: "You are not alone. Please talk to someone.", options: [] },
    };
    respond = (url) => (url.endsWith("/chat/turn") ? json(turn({ mode: "fallback" })) : json(distress));
    renderScreen();
    await userEvent.type(screen.getByLabelText("Your request"), "I cannot cope{Enter}");
    await userEvent.click(await screen.findByRole("button", { name: "Check" }));
    expect(await screen.findByText("You are not alone. Please talk to someone.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yes, send it" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Not now" })).not.toBeInTheDocument();
  });

  it("switches to the plain form when the turn says fallback, then Check -> card -> confirm", async () => {
    respond = (url) => {
      if (url.endsWith("/chat/turn")) return json(turn({ mode: "fallback" }));
      if (url.endsWith("/chat/preview")) return json(PROPOSAL);
      return json(confirmed);
    };
    renderScreen();
    await userEvent.type(screen.getByLabelText("Your request"), "My wifi is down in building M{Enter}");
    const check = await screen.findByRole("button", { name: "Check" });
    expect(screen.getByLabelText("Your request")).toHaveValue("My wifi is down in building M");
    await userEvent.click(check);
    await userEvent.click(await screen.findByRole("button", { name: "Yes, send it" }));
    expect(await screen.findByText("Request recorded #AB12CD34")).toBeInTheDocument();
    expect(calls.map((c) => c.url.split("/api/ai/")[1])).toEqual(["chat/turn", "chat/preview", "chat/confirm"]);
  });

  it("switches to the plain form on a network error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    renderScreen();
    await userEvent.type(screen.getByLabelText("Your request"), "wifi{Enter}");
    expect(await screen.findByRole("button", { name: "Check" })).toBeInTheDocument();
    expect(screen.getByText(/assistant is not available/)).toBeInTheDocument();
  });

  it("renders the distress card for a distress turn", async () => {
    const distress = TRIAGE_FIXTURES.arDistress.response;
    respond = () => json(turn({ reply: "x", triage: distress, clear_proposal: true }));
    renderScreen("ar");
    await userEvent.type(screen.getByRole("textbox"), "مرحبا{Enter}");
    expect(await screen.findByRole("heading", { name: "مش لحالك" })).toBeInTheDocument();
    expect(screen.getByText(distress.message as string)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Why|ليش/ })).not.toBeInTheDocument();
  });
});
