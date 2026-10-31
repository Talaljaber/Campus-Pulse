import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import type { TriageFlag, TriageResponse } from "@/lib/ai/types";
import { TRIAGE_FIXTURES, type TriageFixtureName } from "@/lib/fixtures/api";
import { ActionSummary } from "../ActionSummary";
import { FlagBadges, isFlagVisible } from "../FlagBadges";
import { ResultCard } from "../ResultCard";
import { UnderstandingView } from "../UnderstandingView";

const fx = (n: TriageFixtureName) => TRIAGE_FIXTURES[n];

describe("ResultCard across the five statuses", () => {
  const cases: [TriageFixtureName, TriageResponse["status"], "en" | "ar"][] = [
    ["enMemory", "decided", "en"],
    ["arBooking", "decided", "ar"],
    ["arabiziExam", "decided", "en"],
    ["arClarification", "needs_clarification", "ar"],
    ["enHumanReview", "human_review", "en"],
    ["enOutOfScope", "out_of_scope", "en"],
    ["arDistress", "distress", "ar"],
  ];

  it.each(cases)("renders %s (%s) in %s without throwing", (name, status, lang) => {
    const { response, text } = fx(name);
    expect(response.status).toBe(status);
    render(
      <LangScope lang={lang}>
        <ResultCard result={response} text={text} now={0} />
      </LangScope>,
    );
    const card = screen.getByRole("article");
    expect(card).toHaveAttribute("data-status", status);
    expect(within(card).getByRole("heading", { level: 2 })).toBeInTheDocument();
  });

  it("decided: shows both meters, the confidence and what happens next", () => {
    const { response, text } = fx("enMemory");
    render(<ResultCard result={response} text={text} now={0} />);
    expect(screen.getByRole("meter", { name: "Category: IT Support" })).toHaveAttribute("aria-valuenow", "78");
    expect(screen.getByRole("meter", { name: "Priority: Medium" })).toHaveAttribute("aria-valuenow", "73");
    expect(screen.getByRole("region", { name: "What happens next" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open CP-47 in Linear" })).toHaveAttribute(
      "href",
      "https://linear.app/campuspulse-demo/issue/CP-47",
    );
  });

  it("needs_clarification: shows the ambiguity, the question, and no actions or explanation", () => {
    const { response } = fx("arClarification");
    render(
      <LangScope lang="ar">
        <ResultCard result={response} />
      </LangScope>,
    );
    expect(screen.getByText("أفضل تخمين لهلأ")).toBeInTheDocument();
    expect(screen.getByText(response.clarification!.text)).toHaveAttribute("dir", "rtl");
    expect(screen.getByRole("group", { name: /ممكن كمان يكون/ })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "شو رح يصير بعدين" })).not.toBeInTheDocument();
  });

  it("human_review: says staff will confirm and the ticket is provisional", () => {
    const { response } = fx("enHumanReview");
    render(<ResultCard result={response} now={0} />);
    expect(screen.getByText("A staff member will confirm this. We opened it as Finance.")).toBeInTheDocument();
    expect(screen.getByText("Ticket opened, waiting for staff to confirm")).toBeInTheDocument();
    expect(screen.getByText("Booking and notifications wait until staff confirm.")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /could also be \(category\)/i })).toBeInTheDocument();
  });

  it("out_of_scope and distress show the service message and no labels", () => {
    const oos = fx("enOutOfScope").response;
    const { unmount } = render(<ResultCard result={oos} />);
    expect(screen.getByText(oos.message!)).toBeInTheDocument();
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
    unmount();

    const dis = fx("arDistress").response;
    render(
      <LangScope lang="ar">
        <ResultCard result={dis} />
      </LangScope>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("911");
    expect(screen.getByRole("status")).toHaveAttribute("dir", "rtl");
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
  });

  it("Arabizi: shows the Arabic transliteration right-to-left", () => {
    const { response } = fx("arabiziExam");
    render(<ResultCard result={response} now={0} />);
    const understood = screen.getByText(response.understood_as!);
    expect(understood).toHaveAttribute("dir", "rtl");
    expect(understood).toHaveAttribute("lang", "ar");
  });

  it("forwards word clicks as onCounterfactual and shows the live answer", async () => {
    const { response, text } = fx("enMemory");
    const onCounterfactual = vi.fn();
    render(<ResultCard result={response} text={text} onCounterfactual={onCounterfactual} now={0} />);
    await userEvent.click(screen.getByRole("button", { name: /^quiz/ }));
    expect(onCounterfactual).toHaveBeenCalledWith("quiz");
  });
});

describe("FlagBadges", () => {
  const all: TriageFlag[] = ["injection_attempt", "urgency_unsupported", "priority_gaming_suspected", "safety", "empty_input"];

  it("never shows staff-only flags to a student, even if the payload carries them", () => {
    render(<FlagBadges flags={all} audience="student" />);
    expect(screen.queryByText(/Urgency claimed/)).not.toBeInTheDocument();
    expect(screen.queryByText(/priority gaming/i)).not.toBeInTheDocument();
    expect(screen.getByText("Instructions in the text were ignored")).toBeInTheDocument();
    expect(screen.getByText("Safety concern")).toBeInTheDocument();
  });

  it("staff see urgency_unsupported but not the admin-only flag; admin sees both", () => {
    const { unmount } = render(<FlagBadges flags={all} audience="staff" />);
    expect(screen.getByText(/Urgency claimed/)).toBeInTheDocument();
    expect(screen.queryByText(/priority gaming/i)).not.toBeInTheDocument();
    unmount();
    render(<FlagBadges flags={all} audience="admin" />);
    expect(screen.getByText(/Possible priority gaming/)).toBeInTheDocument();
  });

  it("hides empty_input from everyone and renders nothing when no flag is visible", () => {
    expect(isFlagVisible("empty_input", "admin")).toBe(false);
    const { container } = render(<FlagBadges flags={["urgency_unsupported"]} audience="student" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("uses the injection fixture's flag and the Arabic label", () => {
    render(
      <LangScope lang="ar">
        <FlagBadges flags={fx("enInjection").response.flags} audience="student" />
      </LangScope>,
    );
    expect(screen.getByRole("list", { name: "ملاحظات عن هالطلب" })).toBeInTheDocument();
    expect(screen.getByText("تجاهلنا تعليمات موجودة بالنص")).toBeInTheDocument();
  });
});

describe("ActionSummary", () => {
  it("ticket: Linear link opens safely in a new tab and the SLA is shown in Amman time", () => {
    const { response } = fx("enMemory");
    render(<ActionSummary action={response.action} status={response.status} />);
    const link = screen.getByRole("link", { name: "Open CP-47 in Linear" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(screen.getByText(/Expected reply by 8 Nov 2026.*11:00/)).toBeInTheDocument();
  });

  it("booking: advisor, time range and no stray left/right layout", () => {
    const { response } = fx("arBooking");
    const b = response.action!.booking!;
    render(
      <LangScope lang="ar">
        <ActionSummary action={response.action} status={response.status} />
      </LangScope>,
    );
    expect(screen.getByText(`مع ${b.advisor_name}`)).toBeInTheDocument();
    expect(screen.getByText(/من .* إلى /)).toBeInTheDocument();
  });

  it("faq: answer, source link and the demo marker", () => {
    const { response } = fx("enFaq");
    render(<ActionSummary action={response.action} status={response.status} />);
    const faq = response.action!.faq!;
    expect(screen.getByText(faq.answer)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: faq.source_url })).toHaveAttribute("href", faq.source_url);
    expect(screen.queryByText("[demo]") !== null).toBe(faq.is_demo);
  });

  it("safety alert is an alert region", () => {
    const { response } = fx("enSafety");
    render(<ActionSummary action={response.action} status={response.status} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Safety alert sent");
  });

  it("does not turn a non-http url into a link", () => {
    const { response } = fx("enMemory");
    const action = { ...response.action!, external: [{ sink: "linear", external_id: "X-1", url: "javascript:alert(1)" }] };
    render(<ActionSummary action={action} status="decided" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("X-1")).toBeInTheDocument();
  });

  it("renders nothing without an action", () => {
    const { container } = render(<ActionSummary action={null} status="out_of_scope" />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("UnderstandingView", () => {
  const u = fx("arBooking").response.understanding!;

  it("shows the summary in the UI language and the entities found", () => {
    const { unmount } = render(<UnderstandingView understanding={u} />);
    expect(screen.getByText(u.summary_en)).toBeInTheDocument();
    expect(screen.getByText(u.student_reply)).toBeInTheDocument();
    unmount();
    render(
      <LangScope lang="ar">
        <UnderstandingView understanding={u} />
      </LangScope>,
    );
    expect(screen.getByText(u.summary_ar)).toHaveAttribute("dir", "rtl");
  });

  it("flags a rules-based summary and hides the ticket draft unless asked", () => {
    const rules = fx("enFaq").response.understanding!;
    expect(rules.source).toBe("rules");
    const { unmount } = render(<UnderstandingView understanding={rules} />);
    expect(screen.getByText(/written by rules/)).toBeInTheDocument();
    expect(screen.queryByText("Ticket draft")).not.toBeInTheDocument();
    unmount();
    render(<UnderstandingView understanding={rules} showTicketDraft />);
    expect(screen.getByText("Ticket draft")).toBeInTheDocument();
  });

  it("renders nothing for null", () => {
    const { container } = render(<UnderstandingView understanding={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
