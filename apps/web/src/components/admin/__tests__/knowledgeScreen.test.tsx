import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import { ToastProvider } from "../../ui/Toast";

const m = vi.hoisted(() => ({ callAi: vi.fn() }));

vi.mock("@/lib/ai/browser", () => ({ callAi: m.callAi }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/admin/knowledge" }));
vi.mock("@/lib/supabase/browser", () => ({ createBrowserSupabase: () => ({}) }));
vi.mock("@/hooks/useSignIn", () => ({ useSignOut: () => vi.fn() }));

import { KnowledgeScreen } from "../KnowledgeScreen";

const DOC = {
  id: "6f1c2a9e-3b4d-4e5f-8a7b-1c2d3e4f5a6b",
  title: "Student Handbook 2026",
  filename: "handbook.pdf",
  office: "finance",
  char_count: 18432,
  chunk_count: 24,
  uploaded_by: "admin",
  created_at: "2026-11-08T10:00:00+02:00",
};
const PASTED = { ...DOC, id: "0b9e8d7c", title: "Library opening hours", filename: null, office: null, chunk_count: 2 };

const calls = () => m.callAi.mock.calls as Array<[string, { method?: string; body?: unknown }?]>;

function setup(docs: unknown[] = [DOC, PASTED], lang: "en" | "ar" = "en") {
  m.callAi.mockImplementation(async (path: string, init?: { method?: string }) => {
    if (path === "admin/knowledge" && (init?.method ?? "GET") === "GET") return { ok: true, data: { documents: docs } };
    return { ok: false, status: 500, code: "internal_error", error: "boom", details: null, waking: false };
  });
  return render(
    <LangScope lang={lang}>
      <ToastProvider>
        <KnowledgeScreen alias="admin" name="Admin" />
      </ToastProvider>
    </LangScope>,
  );
}

beforeEach(() => m.callAi.mockReset());

describe("KnowledgeScreen", () => {
  it("lists the documents with office, file or Pasted text, and passages; shows the note", async () => {
    setup();
    const table = await screen.findByRole("table", { name: "Knowledge documents, newest first" });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]!).getByText("Student Handbook 2026")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("handbook.pdf")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("Pasted text")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("Whole campus")).toBeInTheDocument();
    expect(screen.getByText(/will not guess beyond them/)).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    setup([]);
    expect(await screen.findByText(/No documents yet\. Add a handbook or a policy page/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("adds pasted text: counts characters, posts multipart without a file, toasts, and puts the row on top", async () => {
    setup([DOC]);
    await screen.findByRole("table");
    m.callAi.mockImplementationOnce(async (_p: string, init: { body: FormData }) => {
      expect(init.body).toBeInstanceOf(FormData);
      return { ok: true, data: { ...PASTED, title: "Add/drop rules" } };
    });
    await userEvent.type(screen.getByLabelText("Title"), "Add/drop rules");
    await userEvent.selectOptions(screen.getByLabelText("Office"), "registrar");
    await userEvent.click(screen.getByRole("radio", { name: "Paste text" }));
    await userEvent.type(screen.getByLabelText("Text"), "Drop in week two.");
    expect(screen.getByText("17 of 200,000 characters")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByText("Added: Add/drop rules")).toBeInTheDocument();
    const post = calls().find(([, i]) => i?.method === "POST")!;
    expect(post[0]).toBe("admin/knowledge");
    const form = post[1]!.body as FormData;
    expect(form.get("title")).toBe("Add/drop rules");
    expect(form.get("office")).toBe("registrar");
    expect(form.get("text")).toBe("Drop in week two.");
    expect(form.get("file")).toBeNull();
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(within(rows[1]!).getByText("Add/drop rules")).toBeInTheDocument();
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("");
  });

  it("uploads a file, and leaves office out for the whole campus", async () => {
    setup([]);
    await screen.findByText(/No documents yet/);
    m.callAi.mockImplementationOnce(async () => ({ ok: true, data: DOC }));
    await userEvent.type(screen.getByLabelText("Title"), "Student Handbook 2026");
    const file = new File(["Refunds: full in week one."], "handbook.txt", { type: "text/plain" });
    await userEvent.upload(screen.getByLabelText(/^File \(PDF/), file);
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
    const form = calls().find(([, i]) => i?.method === "POST")![1]!.body as FormData;
    expect((form.get("file") as File).name).toBe("handbook.txt");
    expect(form.has("office")).toBe(false);
    expect(form.has("text")).toBe(false);
  });

  it("refuses a wrong type and a file over 5 MB before sending", async () => {
    setup([]);
    await screen.findByText(/No documents yet/);
    await userEvent.type(screen.getByLabelText("Title"), "X");
    const input = screen.getByLabelText(/^File \(PDF/);
    await userEvent.upload(input, new File(["x"], "pic.png", { type: "image/png" }), { applyAccept: false });
    expect(await screen.findByRole("alert")).toHaveTextContent("Only PDF, .txt and .md files are accepted.");
    const big = new File(["x"], "big.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: 5 * 1024 * 1024 + 1 });
    await userEvent.upload(input, big);
    expect(await screen.findByRole("alert")).toHaveTextContent("That file is over 5 MB.");
    expect(calls().some(([, i]) => i?.method === "POST")).toBe(false);
  });

  it("asks for a title and a file before sending", async () => {
    setup([]);
    await screen.findByText(/No documents yet/);
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a title.");
    await userEvent.type(screen.getByLabelText("Title"), "X");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a file.");
    expect(calls().some(([, i]) => i?.method === "POST")).toBe(false);
  });

  it("shows the server's message on a 422", async () => {
    setup([]);
    await screen.findByText(/No documents yet/);
    m.callAi.mockImplementationOnce(async () => ({
      ok: false,
      status: 422,
      code: "invalid_input",
      error: "This PDF has no text (is it a scan?).",
      details: null,
      waking: false,
    }));
    await userEvent.type(screen.getByLabelText("Title"), "Scan");
    await userEvent.click(screen.getByRole("radio", { name: "Paste text" }));
    await userEvent.type(screen.getByLabelText("Text"), "abc");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This PDF has no text (is it a scan?).");
    expect(screen.getByLabelText("Text")).toHaveValue("abc");
  });

  it("shows a generic message for a non-422 failure", async () => {
    setup([]);
    await screen.findByText(/No documents yet/);
    await userEvent.type(screen.getByLabelText("Title"), "T");
    await userEvent.click(screen.getByRole("radio", { name: "Paste text" }));
    await userEvent.type(screen.getByLabelText("Text"), "abc");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not add the document. Try again.");
  });

  it("deletes only after the confirm dialog, and Cancel keeps the row", async () => {
    setup();
    const del = await screen.findByRole("button", { name: "Delete Student Handbook 2026" });
    await userEvent.click(del);
    const dialog = screen.getByRole("dialog", { name: "Delete this document?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(calls().some(([, i]) => i?.method === "DELETE")).toBe(false);

    m.callAi.mockImplementationOnce(async () => ({ ok: true, data: { id: DOC.id, deleted: true } }));
    await userEvent.click(screen.getByRole("button", { name: "Delete Student Handbook 2026" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete document" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Delete Student Handbook 2026" })).toBeNull());
    expect(calls().find(([, i]) => i?.method === "DELETE")![0]).toBe(`admin/knowledge/${DOC.id}`);
    expect(await screen.findByText("Deleted: Student Handbook 2026")).toBeInTheDocument();
    expect(screen.getByText("Library opening hours")).toBeInTheDocument();
  });

  it("renders in Arabic", async () => {
    setup([DOC], "ar");
    expect(await screen.findByRole("table", { name: "مستندات المعرفة، الأحدث أولاً" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "لصق نص" })).toBeInTheDocument();
  });
});
