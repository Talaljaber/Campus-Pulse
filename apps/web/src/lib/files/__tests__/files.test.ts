import { afterEach, describe, expect, it, vi } from "vitest";
import type { AiFail } from "@/lib/ai/result";
import { failMessage } from "@/lib/tickets/service";
import { checkFile, problemFromServer } from "../limits";
import { uploadAll, type UploadedCache } from "../send";
import { fileLink, openFile, uploadFile } from "../service";
import { MAX_FILE_BYTES, type FileRow } from "../types";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const file = (name: string, size = 10): File => {
  const f = new File(["x"], name);
  Object.defineProperty(f, "size", { value: size });
  return f;
};
const row = (id: string, size = 10): FileRow => ({ id, ticket_id: "t1", visibility: "public", mime: "image/png", size_bytes: size, ext: "png", created_at: "2026-11-08T10:00:00Z" });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

describe("checkFile", () => {
  it.each([
    ["receipt.png", 10, null],
    ["note.TXT", 10, null],
    ["run.exe", 10, "type"],
    ["page.html", 10, "type"],
    ["noextension", 10, "type"],
    ["empty.png", 0, "empty"],
    ["big.png", MAX_FILE_BYTES + 1, "size"],
    ["limit.png", MAX_FILE_BYTES, null],
  ] as const)("%s (%i bytes) -> %s", (name, size, expected) => {
    expect(checkFile(file(name, size), [], [])).toBe(expected);
  });

  it("limits the count to 5 files across the ticket and the picked ones", () => {
    const existing = [row("a"), row("b"), row("c")];
    expect(checkFile(file("d.png"), existing, [file("e.png")])).toBeNull();
    expect(checkFile(file("f.png"), existing, [file("d.png"), file("e.png")])).toBe("count");
  });

  it("limits the total to 15 MB", () => {
    const existing = [row("a", MAX_FILE_BYTES), row("b", MAX_FILE_BYTES)];
    expect(checkFile(file("c.png", MAX_FILE_BYTES), existing, [])).toBeNull();
    expect(checkFile(file("d.png", 100), [...existing, row("c", MAX_FILE_BYTES)], [])).toBe("total");
  });
});

describe("server refusals map to a translated sentence", () => {
  it.each([
    ["this file type is not allowed (images, PDF, Office documents, plain text)", "type"],
    ["the file does not match its name; it was refused", "type"],
    ["the file is larger than 5 MB", "size"],
    ["the file is empty", "empty"],
    ["a ticket holds at most 5 files", "count"],
    ["a ticket holds at most 15 MB of files", "total"],
    ["transition solved -> new not allowed", null],
  ])("%s", (message, expected) => {
    expect(problemFromServer(message)).toBe(expected);
    const fail: AiFail = { ok: false, status: 422, code: "invalid_input", error: message, details: null, waking: false };
    expect(failMessage(fail)).toEqual(expected ? { kind: "dict", key: `files.error.${expected}` } : { kind: "server", text: message });
  });
});

describe("uploadFile and fileLink", () => {
  it("posts multipart through the proxy without a JSON content type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(row("f1")));
    vi.stubGlobal("fetch", fetchMock);
    const res = await uploadFile("t 1", file("My Receipt.png"), true);
    expect(res.ok).toBe(true);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/ai/tickets/t%201/files");
    expect(init.method).toBe("POST");
    expect(init.headers).toBeUndefined(); // the browser sets the multipart boundary itself
    expect(init.body).toBeInstanceOf(FormData);
    const form = init.body as FormData;
    expect(form.get("internal")).toBe("true");
    expect(form.get("file")).toBeInstanceOf(File);
  });

  it("asks for the signed link with a GET", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ url: "https://storage.example/x", expires_in: 60 }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await fileLink("f1");
    expect(res).toEqual({ ok: true, data: { url: "https://storage.example/x", expires_in: 60 } });
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/ai/files/f1/link");
    expect(fetchMock.mock.calls[0]![1].method).toBe("GET");
  });

  it("opens the link in a new tab with noopener noreferrer, and opens nothing on failure", async () => {
    const seen: HTMLAnchorElement[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      seen.push(this);
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ url: "https://storage.example/x?token=t", expires_in: 60 })));
    await openFile("f1");
    expect(seen).toHaveLength(1);
    expect(seen[0]!.href).toBe("https://storage.example/x?token=t");
    expect(seen[0]!.target).toBe("_blank");
    expect(seen[0]!.rel).toBe("noopener noreferrer");

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: { code: "forbidden", message: "no" } }, 403)));
    const res = await openFile("f2");
    expect(res.ok).toBe(false);
    expect(seen).toHaveLength(1);
  });
});

describe("uploadAll", () => {
  it("uploads in order, stops at the first failure and does not upload a file twice on retry", async () => {
    const a = file("a.png");
    const b = file("b.png");
    const calls: string[] = [];
    let fail = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: { body: FormData }) => {
        const name = (init.body.get("file") as File).name;
        calls.push(name);
        if (name === "b.png" && fail) return json({ error: { code: "invalid_input", message: "the file is larger than 5 MB" } }, 422);
        return json(row(`id-${name}`));
      }),
    );
    const cache: UploadedCache = new Map();
    const first = await uploadAll("t1", [a, b], false, cache);
    expect(first.ok).toBe(false);
    expect(calls).toEqual(["a.png", "b.png"]);
    fail = false;
    const second = await uploadAll("t1", [a, b], false, cache);
    expect(second.ok && second.rows.map((r) => r.id)).toEqual(["id-a.png", "id-b.png"]);
    expect(calls).toEqual(["a.png", "b.png", "b.png"]); // a.png was not sent again
    // the same file for a message of the other visibility is uploaded again
    await uploadAll("t1", [a], true, cache);
    expect(calls.at(-1)).toBe("a.png");
  });
});
