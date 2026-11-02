import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import type { ChatItem } from "@/lib/chat/types";
import { TRIAGE_FIXTURES } from "@/lib/fixtures/api";
import { BuildingPicker } from "../BuildingPicker";
import { ChatThread } from "../ChatThread";
import { ClarificationBubble } from "../ClarificationBubble";
import { Composer } from "../Composer";
import { Disclaimer } from "../Disclaimer";
import { DistressCard } from "../DistressCard";

const q = TRIAGE_FIXTURES.arClarification.response.clarification!;

describe("Composer", () => {
  it("Enter sends and clears, Shift+Enter adds a line, blank text is not sent", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Composer onSubmit={onSubmit} busy={false} />);
    const box = screen.getByLabelText("Your request");
    await user.type(box, "   {Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
    await user.type(box, "line one{Shift>}{Enter}{/Shift}line two");
    expect(onSubmit).not.toHaveBeenCalled();
    expect(box).toHaveValue("   line one\nline two");
    await user.keyboard("{Enter}");
    expect(onSubmit).toHaveBeenCalledWith("line one\nline two", "text");
    expect(box).toHaveValue("");
  });

  it("does not send while busy, and renders the mic slot", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Composer onSubmit={onSubmit} busy micSlot={<button type="button">Mic</button>} />);
    await user.type(screen.getByLabelText("Your request"), "hello{Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Mic" })).toBeInTheDocument();
  });

  it("the send button is a submit button that sends", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Composer onSubmit={onSubmit} busy={false} />);
    const send = screen.getByRole("button", { name: "Send request" });
    expect(send).toBeDisabled();
    await user.type(screen.getByLabelText("Your request"), "hi");
    await user.click(send);
    expect(onSubmit).toHaveBeenCalledWith("hi", "text");
  });
});

describe("ClarificationBubble", () => {
  it("shows the question in its own direction and reports the picked option", async () => {
    const onPick = vi.fn();
    const user = userEvent.setup();
    const { container } = render(<ClarificationBubble q={q} onPick={onPick} disabled={false} />);
    expect(container.firstElementChild).toHaveAttribute("dir", "rtl");
    await user.click(screen.getByRole("button", { name: q.options[1]!.text }));
    expect(onPick).toHaveBeenCalledWith(q.options[1]!.id);
  });

  it("is keyboard operable: Tab moves between chips without answering, Enter answers", async () => {
    const onPick = vi.fn();
    const user = userEvent.setup();
    render(<ClarificationBubble q={q} onPick={onPick} disabled={false} />);
    await user.tab();
    await user.tab();
    expect(onPick).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: q.options[1]!.text })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick).toHaveBeenCalledWith(q.options[1]!.id);
  });

  it("disabled: nothing can be picked; answered chip stays selected", async () => {
    const onPick = vi.fn();
    const user = userEvent.setup();
    render(<ClarificationBubble q={q} onPick={onPick} disabled answered={q.options[0]!.id} />);
    expect(screen.getByRole("button", { name: q.options[0]!.text })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: q.options[1]!.text }));
    expect(onPick).not.toHaveBeenCalled();
  });
});

describe("BuildingPicker", () => {
  const buildings = [
    { id: "M", code: "M", name_en: "Technology Centre", name_ar: "مركز التقنية" },
    { id: "A", code: "A", name_en: "Administration", name_ar: "الإدارة" },
  ];
  it("lists buildings in the UI language and reports null for none", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <LangScope lang="ar">
        <BuildingPicker buildings={buildings} value={null} onChange={onChange} />
      </LangScope>,
    );
    const select = screen.getByRole("combobox", { name: "وين انت؟ (اختياري)" });
    await user.selectOptions(select, "M");
    expect(onChange).toHaveBeenCalledWith("M");
    expect(screen.getByRole("option", { name: "M · مركز التقنية" })).toBeInTheDocument();
    await user.selectOptions(select, "");
    expect(onChange).toHaveBeenLastCalledWith(null);
  });
});

describe("DistressCard and Disclaimer", () => {
  it("shows the message as written and no result UI", () => {
    render(<DistressCard message="Call 911 if you are in danger." />);
    expect(screen.getByRole("status")).toHaveTextContent("Call 911 if you are in danger.");
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });
  it("the disclaimer says prototype on synthetic data", () => {
    render(<Disclaimer />);
    expect(screen.getByText(/Integration-ready prototype on synthetic data/)).toBeInTheDocument();
  });
});

describe("ChatThread items", () => {
  const items: ChatItem[] = [
    { id: "s1", role: "student", text: "hello" },
    { id: "n1", role: "notice", notice: { type: "ticket_status", title: "Wi-Fi in M", status: "solved" } },
    { id: "n2", role: "notice", notice: { type: "ticket_status", title: "", status: "in_progress" } },
    { id: "n3", role: "notice", notice: { type: "generic" } },
    { id: "e1", role: "error", kind: "session" },
  ];

  it("is a labelled log with the student bubble, notices and errors", () => {
    render(<ChatThread items={items} />);
    expect(screen.getByRole("log", { name: "Conversation" })).toBeInTheDocument();
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText('Your ticket "Wi-Fi in M" is now solved.')).toBeInTheDocument();
    expect(screen.getByText("Your ticket is now in progress.")).toBeInTheDocument();
    expect(screen.getByText("You have a new update on your request.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Your session ended");
  });

  it("translates notices into Arabic", () => {
    render(
      <LangScope lang="ar">
        <ChatThread items={items} />
      </LangScope>,
    );
    expect(screen.getByText('تذكرتك "Wi-Fi in M" صارت محلولة.')).toBeInTheDocument();
  });

  it("an unknown ticket status is shown as received, never dropped", () => {
    render(<ChatThread items={[{ id: "n", role: "notice", notice: { type: "ticket_status", title: "T", status: "frozen" } }]} />);
    expect(screen.getByText('Your ticket "T" is now frozen.')).toBeInTheDocument();
  });
});
