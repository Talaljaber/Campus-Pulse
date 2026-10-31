import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import clarifyFixture from "@fixtures/clarify_decided_ar.json";
import { useChat } from "@/hooks/useChat";
import { COUNTERFACTUAL_FIXTURE, TRIAGE_FIXTURES } from "@/lib/fixtures/api";
import { ChatThread } from "../ChatThread";
import { Composer } from "../Composer";

const { arClarification, enFaq, arDistress } = TRIAGE_FIXTURES;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

/** A thin page: the real `useChat` hook wired to the real thread and composer, with no Supabase. */
function Harness() {
  const chat = useChat();
  return (
    <>
      <ChatThread
        items={chat.items}
        counterfactuals={chat.counterfactuals}
        busy={chat.busy}
        onPick={(id, option) => void chat.pick(id, option)}
        onCounterfactual={(requestId, token) => void chat.counterfactual(requestId, token)}
      />
      <Composer busy={chat.busy} onSubmit={(text, mode) => void chat.send(text, mode, null)} />
    </>
  );
}

const calls: Array<{ url: string; method: string; body: unknown }> = [];
let respond: (url: string, body: Record<string, unknown> | null) => Response;

beforeEach(() => {
  calls.length = 0;
  respond = (url, body) => {
    if (url.endsWith("/api/ai/triage")) {
      if (body?.text === arClarification.text) return json(arClarification.response);
      if (body?.text === arDistress.text) return json(arDistress.response);
      return json(enFaq.response);
    }
    if (url.includes("/clarify")) return json(clarifyFixture.response);
    if (url.includes("/counterfactual")) return json(COUNTERFACTUAL_FIXTURE);
    return json({ error: { code: "not_found", message: "no", details: null } }, 404);
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
      calls.push({ url, method: init?.method ?? "GET", body });
      return respond(url, body);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

async function type(text: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Your request"), `${text}{Enter}`);
  return user;
}

describe("student chat flow (fixture responses)", () => {
  it("a decided request shows the result card with the category and the FAQ answer", async () => {
    render(<Harness />);
    await type(enFaq.text);
    const card = await screen.findByRole("article");
    expect(within(card).getAllByText(/Transportation/).length).toBeGreaterThan(0);
    expect(calls[0]).toMatchObject({ url: "/api/ai/triage", method: "POST", body: { text: enFaq.text, input_mode: "text" } });
    // the composer is cleared and unlocked again
    expect(screen.getByLabelText("Your request")).toHaveValue("");
  });

  it("clarification: the question appears with chips, the answer is sent, the result follows", async () => {
    render(<Harness />);
    const user = await type(arClarification.text);

    const group = await screen.findByRole("group", { name: "Choose one answer" });
    const chips = within(group).getAllByRole("button");
    expect(chips.length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByRole("article")).not.toBeInTheDocument(); // no result card yet

    const option = arClarification.response.clarification!.options.find((o) => o.id === "registration")!;
    await user.click(within(group).getByRole("button", { name: option.text }));

    const card = await screen.findByRole("article");
    expect(within(card).getAllByText(/Registration/).length).toBeGreaterThan(0);

    const clarifyCall = calls.find((c) => c.url.includes("/clarify"))!;
    expect(clarifyCall.url).toBe(`/api/ai/triage/${arClarification.response.request_id}/clarify`);
    expect(clarifyCall.body).toEqual({
      question_id: arClarification.response.clarification!.question_id,
      option_id: "registration",
    });
    // the answered chip stays selected and the question cannot be answered twice
    expect(within(screen.getByRole("group", { name: "Choose one answer" })).getByRole("button", { name: option.text })).toHaveAttribute("aria-pressed", "true");
  });

  it("counterfactual: clicking a highlighted word asks the service and shows the answer", async () => {
    render(<Harness />);
    const user = await type(arClarification.text);
    const group = await screen.findByRole("group", { name: "Choose one answer" });
    await user.click(within(group).getByRole("button", { name: arClarification.response.clarification!.options[0]!.text }));
    const card = await screen.findByRole("article");

    const word = within(card).getAllByRole("button", { name: /اليوم/ })[0]!;
    await user.click(word);

    await waitFor(() => expect(calls.some((c) => c.url.includes("/counterfactual"))).toBe(true));
    const cf = calls.find((c) => c.url.includes("/counterfactual"))!;
    expect(cf.method).toBe("GET");
    expect(decodeURIComponent(cf.url)).toContain("drop=اليوم");
    await waitFor(() => expect(within(card).getAllByText(/medium/i).length).toBeGreaterThan(0));
  });

  it("distress shows the supportive card and no result card", async () => {
    render(<Harness />);
    await type(arDistress.text);
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("911");
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });

  it("a service that is waking up shows the translated message and unlocks the composer", async () => {
    respond = () => json({ error: { code: "ai_waking", message: "starting", details: null }, waking: true }, 503);
    render(<Harness />);
    await type("hello there");
    expect(await screen.findByRole("alert")).toHaveTextContent("waking up");
    expect(screen.getByLabelText("Your request")).not.toBeDisabled();
  });

  it("a failed clarification re-opens the question so it can be answered again", async () => {
    render(<Harness />);
    const user = await type(arClarification.text);
    const group = await screen.findByRole("group", { name: "Choose one answer" });
    respond = () => json({ error: { code: "clarification_budget_exceeded", message: "x", details: null } }, 409);
    const first = arClarification.response.clarification!.options[0]!;
    await user.click(within(group).getByRole("button", { name: first.text }));
    expect(await screen.findByRole("alert")).toHaveTextContent("no longer open");
    expect(within(screen.getByRole("group", { name: "Choose one answer" })).getByRole("button", { name: first.text })).not.toHaveAttribute("aria-pressed", "true");
  });

  it("ignores a second send while one is in flight", async () => {
    let release: (r: Response) => void = () => {};
    respond = () => {
      throw new Error("not used");
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((res) => (release = res))),
    );
    render(<Harness />);
    const user = userEvent.setup();
    const box = screen.getByLabelText("Your request");
    await user.type(box, "first{Enter}");
    await user.type(box, "second{Enter}");
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
    release(json(enFaq.response));
    await screen.findByRole("article");
  });
});
