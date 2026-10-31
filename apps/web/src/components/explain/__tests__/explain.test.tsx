import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import { COUNTERFACTUAL_FIXTURE, TRIAGE_FIXTURES } from "@/lib/fixtures/api";
import { CounterfactualHint } from "../CounterfactualHint";
import { EvidenceText } from "../EvidenceText";
import { ExplanationPanel } from "../ExplanationPanel";
import { segmentText, textDir } from "../text";

const mem = TRIAGE_FIXTURES.enMemory;
const ar = TRIAGE_FIXTURES.arBooking;

describe("segmentText", () => {
  it("marks top tokens case-insensitively with relative strength and keeps the text intact", () => {
    const segs = segmentText(mem.text, mem.response.explanation!.top_tokens, mem.response.priority!.evidence ?? []);
    expect(segs.map((s) => s.text).join("")).toBe(mem.text);
    const moodle = segs.find((s) => s.token === "Moodle");
    const freezing = segs.find((s) => s.token === "freezing");
    expect(moodle).toBeDefined();
    expect(freezing!.strength).toBe(1);
    expect(moodle!.strength!).toBeLessThan(freezing!.strength!);
  });

  it("covers every run of an evidence span, including the spaces between its words", () => {
    const segs = segmentText(mem.text, [], mem.response.priority!.evidence ?? []);
    const underlined = segs.filter((s) => s.evidence.length > 0).map((s) => s.text).join("");
    expect(underlined).toBe("keeps freezing");
  });

  it("detects direction from the script", () => {
    expect(textDir(ar.text)).toBe("rtl");
    expect(textDir(mem.text)).toBe("ltr");
    expect(textDir(TRIAGE_FIXTURES.arabiziExam.text)).toBe("ltr");
  });
});

describe("EvidenceText", () => {
  const e = mem.response;

  it("highlights top tokens as marks and underlines evidence when not clickable", () => {
    const { container } = render(
      <EvidenceText text={mem.text} tokens={e.explanation!.top_tokens} evidence={e.priority!.evidence ?? []} />,
    );
    const marks = [...container.querySelectorAll("mark")].map((m) => m.getAttribute("data-token"));
    expect(marks).toEqual(expect.arrayContaining(["freezing", "quiz", "submit", "Moodle"]));
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(container.querySelector('[data-evidence="transient_glitch"]')).not.toBeNull();
  });

  it("makes highlighted words buttons that report the canonical token, by mouse and keyboard", async () => {
    const onTokenClick = vi.fn();
    const user = userEvent.setup();
    render(
      <EvidenceText
        text={mem.text}
        tokens={e.explanation!.top_tokens}
        evidence={e.priority!.evidence ?? []}
        onTokenClick={onTokenClick}
        activeToken="quiz"
      />,
    );
    await user.click(screen.getByRole("button", { name: /^freezing, influence 31%/ }));
    expect(onTokenClick).toHaveBeenLastCalledWith("freezing");
    expect(screen.getByRole("button", { name: /^quiz/ })).toHaveAttribute("aria-pressed", "true");

    const moodle = screen.getByRole("button", { name: /^Moodle/ });
    moodle.focus();
    await user.keyboard("{Enter}");
    expect(onTokenClick).toHaveBeenLastCalledWith("Moodle");
    await user.keyboard(" ");
    expect(onTokenClick).toHaveBeenCalledTimes(3);
  });

  it("renders Arabic text right-to-left, even inside an English page", () => {
    const { container } = render(
      <EvidenceText text={ar.text} tokens={ar.response.explanation!.top_tokens} evidence={ar.response.priority!.evidence} />,
    );
    expect(container.querySelector("p")).toHaveAttribute("dir", "rtl");
    expect(container.querySelector('mark[data-token="مرشد"]')).not.toBeNull();
    expect(container.querySelector('[data-evidence~="exam_now"]')).not.toBeNull();
  });
});

describe("CounterfactualHint", () => {
  it("states the hint and asks the parent to run it", async () => {
    const onCounterfactual = vi.fn();
    render(<CounterfactualHint hint={mem.response.explanation!.counterfactual} onCounterfactual={onCounterfactual} />);
    expect(screen.getByText(/this would be Academic Support, Low priority/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try without .freezing./i }));
    expect(onCounterfactual).toHaveBeenCalledWith("freezing");
  });

  it("announces the live answer in a polite status region", () => {
    render(<CounterfactualHint hint={null} view={COUNTERFACTUAL_FIXTURE} />);
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(within(status).getByText(/The decision would change/)).toBeInTheDocument();
    expect(within(status).getByText(/Without .اليوم.: Registration \(97%\), Medium priority \(66%\)/)).toBeInTheDocument();
  });

  it("renders nothing without a hint or a view", () => {
    const { container } = render(<CounterfactualHint hint={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ExplanationPanel", () => {
  const e = mem.response;
  const at = (iso: string, secs: number) => new Date(iso).getTime() + secs * 1000;
  const memoryNeighbor = e.explanation!.neighbors.find((n) => n.source === "memory")!;

  it("shows 'learned from a staff correction N s ago' for memory neighbours only", () => {
    render(<ExplanationPanel explanation={e.explanation!} tier={e.tier} now={at(memoryNeighbor.created_at!, 42)} />);
    expect(screen.getAllByText(/Learned from a staff correction/)).toHaveLength(1);
    expect(screen.getByText("Learned from a staff correction 42 s ago")).toBeInTheDocument();
    expect(screen.getByText(/The e-learning quiz page hangs/)).toBeInTheDocument();
    expect(screen.getByText("Staff correction")).toBeInTheDocument();
  });

  it("prints a trace line with tier, set sizes, cost, latency and artifact", () => {
    render(<ExplanationPanel explanation={e.explanation!} tier={e.tier} now={0} />);
    const trace = screen.getByRole("region", { name: "How it was decided" });
    expect(within(trace).getByText("Tier 1, constrained LLM")).toBeInTheDocument();
    expect(within(trace).getByText("Set sizes: category 1, priority 1")).toBeInTheDocument();
    expect(within(trace).getByText("Cost $0.00021")).toBeInTheDocument();
    expect(within(trace).getByText("980 ms")).toBeInTheDocument();
    expect(within(trace).getByText("Model v1")).toBeInTheDocument();
  });

  it("lists urgency signals with translated types and quotes the span", () => {
    render(<ExplanationPanel explanation={e.explanation!} evidence={e.priority!.evidence} />);
    const section = screen.getByRole("region", { name: "Urgency signals" });
    expect(within(section).getByText("Temporary glitch")).toBeInTheDocument();
    expect(within(section).getByText("keeps freezing")).toBeInTheDocument();
  });

  it("without text, lists top words as keyboard-operable chips that start a counterfactual", async () => {
    const onCounterfactual = vi.fn();
    const user = userEvent.setup();
    render(<ExplanationPanel explanation={e.explanation!} onCounterfactual={onCounterfactual} now={0} />);
    const chip = screen.getByRole("button", { name: /^quiz, influence 20%/ });
    await user.tab();
    expect(screen.getByRole("button", { name: /^freezing/ })).toHaveFocus();
    await user.tab();
    expect(chip).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onCounterfactual).toHaveBeenCalledWith("quiz");
    expect(chip).toHaveAttribute("aria-pressed", "true");
  });

  it("with text, highlights inside it and the live counterfactual marks the dropped word", () => {
    const view = { ...COUNTERFACTUAL_FIXTURE, drop: "freezing" };
    render(
      <ExplanationPanel
        explanation={e.explanation!}
        text={mem.text}
        evidence={e.priority!.evidence}
        counterfactual={view}
        onCounterfactual={() => {}}
        now={0}
      />,
    );
    expect(screen.getByRole("button", { name: /^freezing/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows Arabic headings and right-to-left neighbour text under the Arabic scope", () => {
    render(
      <LangScope lang="ar">
        <ExplanationPanel explanation={ar.response.explanation!} tier={ar.response.tier} now={0} />
      </LangScope>,
    );
    expect(screen.getByRole("heading", { name: "ليش طلعت هالنتيجة" })).toBeInTheDocument();
    const arabicNeighbor = ar.response.explanation!.neighbors.find((n) => textDir(n.text) === "rtl");
    if (arabicNeighbor) expect(screen.getByText(arabicNeighbor.text)).toHaveAttribute("dir", "rtl");
    expect(screen.getByRole("heading", { name: "ليش طلعت هالنتيجة" }).closest("[dir]")).toHaveAttribute("dir", "rtl");
  });
});
