import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import type { FileRow } from "@/lib/files/types";
import type { ActivityRow } from "@/lib/tickets/types";
import { RequesterReply } from "../../requests/RequesterReply";
import { FilePicker } from "../FilePicker";
import { ReplyBox } from "../ReplyBox";
import { TicketThread } from "../TicketThread";

const sized = (name: string, size: number): File => {
  const f = new File(["x"], name);
  Object.defineProperty(f, "size", { value: size });
  return f;
};
const fileRow = (o: Partial<FileRow>): FileRow => ({ id: "f1", ticket_id: "t1", activity_id: "a1", visibility: "public", mime: "image/png", size_bytes: 2048, ext: "png", created_at: "2026-11-08T10:00:00Z", ...o });
const activity = (o: Partial<ActivityRow>): ActivityRow => ({
  id: "a1",
  ticket_id: "t1",
  kind: "comment",
  visibility: "public",
  actor_role: "staff",
  actor_alias: "it",
  actor_office: "it",
  body: "See the screenshot",
  from_status: null,
  to_status: null,
  from_office: null,
  to_office: null,
  from_priority: null,
  to_priority: null,
  created_at: "2026-11-08T10:00:00Z",
  ...o,
});
// the picker's `accept` would hide a wrong type from user-event; checkFile and the server must still refuse it
const typer = () => userEvent.setup({ applyAccept: false });

describe("FilePicker", () => {
  it("shows the demo notice and nothing else until a file is chosen", () => {
    render(<FilePicker picked={[]} onChange={() => {}} existing={[]} />);
    expect(screen.getByText("Demo: use sample files only, no real documents.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("adds a valid file and lets it be removed", async () => {
    const user = typer();
    const onChange = vi.fn();
    const { rerender } = render(<FilePicker picked={[]} onChange={onChange} existing={[]} />);
    await user.upload(screen.getByLabelText("Attach files"), new File(["x"], "receipt.png", { type: "image/png" }));
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ name: "receipt.png" })]);
    const kept = new File(["x"], "receipt.png");
    rerender(<FilePicker picked={[kept]} onChange={onChange} existing={[]} />);
    await user.click(screen.getByRole("button", { name: "Remove file receipt.png" }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("says why a file is refused: type, size and count", async () => {
    const user = typer();
    const onChange = vi.fn();
    const { rerender } = render(<FilePicker picked={[]} onChange={onChange} existing={[]} />);
    const input = screen.getByLabelText("Attach files");
    await user.upload(input, new File(["x"], "virus.exe"));
    expect(screen.getByRole("alert")).toHaveTextContent("This file type is not allowed");
    expect(onChange).not.toHaveBeenCalled();
    await user.upload(input, sized("huge.png", 5 * 1024 * 1024 + 1));
    expect(screen.getByRole("alert")).toHaveTextContent("larger than 5 MB");
    const full = Array.from({ length: 5 }, (_, i) => fileRow({ id: `f${i}` }));
    rerender(<FilePicker picked={[]} onChange={onChange} existing={full} />);
    await user.upload(screen.getByLabelText("Attach files"), new File(["x"], "sixth.png"));
    expect(screen.getByRole("alert")).toHaveTextContent("at most 5 files");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("speaks Arabic and warns that internal files are staff only", () => {
    render(
      <LangScope lang="ar">
        <FilePicker picked={[]} onChange={() => {}} existing={[]} internal />
      </LangScope>,
    );
    expect(screen.getByText("تجريبي: استخدم ملفات تجريبية فقط، بدون مستندات حقيقية.")).toBeInTheDocument();
    expect(screen.getByText(/بشوفها الموظفين بس/)).toBeInTheDocument();
  });
});

describe("ReplyBox with files", () => {
  const OPTIONS = ["solved", "closed"] as const;

  it("has no upload control without the files prop", () => {
    render(<ReplyBox statusOptions={OPTIONS} onSend={() => true} />);
    expect(screen.queryByLabelText("Attach files")).toBeNull();
  });

  it("sends the picked files with a public reply and clears them", async () => {
    const user = typer();
    const onSend = vi.fn(() => Promise.resolve(true));
    render(<ReplyBox statusOptions={OPTIONS} files={[]} onSend={onSend} />);
    await user.upload(screen.getByLabelText("Attach files"), new File(["x"], "fix.pdf"));
    await user.type(screen.getByLabelText("Your reply"), "Done");
    expect(screen.queryByText("Files sent with an internal note are only visible to staff.")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    expect(onSend).toHaveBeenCalledWith({ body: "Done", internal: false, status: null }, [expect.objectContaining({ name: "fix.pdf" })]);
    expect(screen.queryByRole("list", { name: "Files to send" })).toBeNull();
  });

  it("the internal toggle makes the files staff-only and sends internal true", async () => {
    const user = typer();
    const onSend = vi.fn(() => Promise.resolve(true));
    render(<ReplyBox statusOptions={OPTIONS} files={[]} onSend={onSend} />);
    await user.click(screen.getByRole("radio", { name: "Internal note" }));
    expect(screen.getByText("Files sent with an internal note are only visible to staff.")).toBeInTheDocument();
    await user.upload(screen.getByLabelText("Attach files"), new File(["x"], "evidence.png"));
    await user.type(screen.getByLabelText("Your note"), "For the team");
    await user.click(screen.getByRole("button", { name: "Save note" }));
    expect(onSend).toHaveBeenCalledWith({ body: "For the team", internal: true, status: null }, [expect.objectContaining({ name: "evidence.png" })]);
  });

  it("keeps the picked files when sending fails", async () => {
    const user = typer();
    render(<ReplyBox statusOptions={OPTIONS} files={[]} onSend={() => Promise.resolve(false)} />);
    await user.upload(screen.getByLabelText("Attach files"), new File(["x"], "keep.png"));
    await user.type(screen.getByLabelText("Your reply"), "Hello");
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    expect(screen.getByRole("list", { name: "Files to send" })).toHaveTextContent("keep.png");
  });
});

describe("RequesterReply with files", () => {
  it("offers public uploads only and sends the files with the message", async () => {
    const user = typer();
    const onSend = vi.fn(() => Promise.resolve(true));
    render(<RequesterReply files={[]} onSend={onSend} />);
    expect(screen.queryByText(/internal/i)).toBeNull();
    await user.upload(screen.getByLabelText("Attach files"), new File(["x"], "proof.png"));
    await user.type(screen.getByRole("textbox"), "Here is the proof");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(onSend).toHaveBeenCalledWith("Here is the proof", [expect.objectContaining({ name: "proof.png" })]);
  });

  it("sends a plain message with a single argument when nothing is picked", async () => {
    const user = typer();
    const onSend = vi.fn(() => Promise.resolve(true));
    render(<RequesterReply files={[]} onSend={onSend} />);
    await user.type(screen.getByRole("textbox"), "Just text");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(onSend).toHaveBeenCalledWith("Just text");
  });
});

describe("file chips in TicketThread", () => {
  it("shows a chip under its message and fetches a link on click", async () => {
    const user = userEvent.setup();
    const onOpenFile = vi.fn(() => Promise.resolve());
    render(<TicketThread activity={[activity({})]} viewer="staff" files={[fileRow({})]} onOpenFile={onOpenFile} />);
    const item = screen.getAllByRole("listitem")[0]!;
    const chip = within(item).getByRole("button", { name: "Open PNG file, 2 KB" });
    await user.click(chip);
    expect(onOpenFile).toHaveBeenCalledWith("f1");
    await waitFor(() => expect(chip).not.toHaveAttribute("aria-busy", "true"));
  });

  it("marks staff-only files for staff and hides them from a requester", () => {
    const files = [fileRow({ id: "pub" }), fileRow({ id: "int", visibility: "internal", ext: "pdf" })];
    const { rerender } = render(<TicketThread activity={[activity({})]} viewer="staff" files={files} onOpenFile={() => {}} />);
    expect(screen.getByRole("button", { name: /Open PDF file/ })).toHaveTextContent("Staff only");
    rerender(<TicketThread activity={[activity({})]} viewer="requester" files={files} onOpenFile={() => {}} />);
    expect(screen.queryByRole("button", { name: /Open PDF file/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Open PNG file/ })).toBeInTheDocument();
  });

  it("lists a file that is not in any message under its own heading", () => {
    render(<TicketThread activity={[activity({})]} viewer="staff" files={[fileRow({ activity_id: null })]} onOpenFile={() => {}} />);
    expect(screen.getByText("Files not in a message")).toBeInTheDocument();
  });
});
