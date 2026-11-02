import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnnouncementRow } from "@/lib/repos/announcements";
import { EMPTY_DRAFT, ammanToIso, validateDraft } from "../form";
import { announcementErrorKind, archiveAnnouncement, createAnnouncement } from "../service";
import { applyChange, firstName, isLive, kindKey, kindTone, sortNewest } from "../view";

afterEach(() => vi.unstubAllGlobals());

function stubFetch(status: number, body: unknown) {
  const fn = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
    async () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

const NOW = new Date("2026-11-05T06:05:00Z");

const row = (id: string, o: Partial<AnnouncementRow> = {}): AnnouncementRow => ({
  id,
  office: "it",
  kind: "info",
  title: `Title ${id}`,
  body: "Body",
  starts_at: "2026-11-05T05:00:00Z",
  ends_at: null,
  archived_at: null,
  created_by: null,
  created_at: "2026-11-05T05:00:00Z",
  ...o,
});

describe("validateDraft", () => {
  const ok = { ...EMPTY_DRAFT, title: "Wifi down", body: "Use the lab network." };

  it("accepts a title and a text, with no end", () => {
    expect(validateDraft(ok, NOW)).toEqual({});
  });

  it("asks for a title and a text", () => {
    expect(validateDraft({ ...ok, title: "   ", body: "" }, NOW)).toEqual({
      title: "announcements.form.errTitleRequired",
      body: "announcements.form.errBodyRequired",
    });
  });

  it("limits the title to 120 and the text to 1000 characters", () => {
    expect(validateDraft({ ...ok, title: "x".repeat(121) }, NOW).title).toBe("announcements.form.errTitleLong");
    expect(validateDraft({ ...ok, title: "x".repeat(120) }, NOW).title).toBeUndefined();
    expect(validateDraft({ ...ok, body: "x".repeat(1001) }, NOW).body).toBe("announcements.form.errBodyLong");
  });

  it("wants the end in the future, read as Amman time", () => {
    // 09:05 in Amman (UTC+3) is 06:05Z, so an end of 09:05 is not after now and 09:06 is.
    expect(validateDraft({ ...ok, endsAt: "2026-11-05T09:05" }, NOW).endsAt).toBe("announcements.form.errEnds");
    expect(validateDraft({ ...ok, endsAt: "2026-11-05T09:06" }, NOW).endsAt).toBeUndefined();
    expect(validateDraft({ ...ok, endsAt: "garbage" }, NOW).endsAt).toBe("announcements.form.errEnds");
  });
});

describe("ammanToIso", () => {
  it("converts a datetime-local value to UTC", () => {
    expect(ammanToIso("2026-11-06T22:00")).toBe("2026-11-06T19:00:00.000Z");
    expect(ammanToIso("")).toBeNull();
    expect(ammanToIso("2026-13-40T99:99")).toBeNull();
  });
});

describe("view helpers", () => {
  it("isLive mirrors the SQL: not archived, started, not ended", () => {
    expect(isLive(row("a"), NOW)).toBe(true);
    expect(isLive(row("a", { archived_at: "2026-11-05T05:30:00Z" }), NOW)).toBe(false);
    expect(isLive(row("a", { starts_at: "2026-11-05T07:00:00Z" }), NOW)).toBe(false);
    expect(isLive(row("a", { ends_at: "2026-11-05T06:05:00Z" }), NOW)).toBe(false);
    expect(isLive(row("a", { ends_at: "2026-11-05T06:06:00Z" }), NOW)).toBe(true);
  });

  it("applyChange adds, replaces and removes by id, newest first", () => {
    const a = row("a", { starts_at: "2026-11-05T01:00:00Z" });
    const b = row("b", { starts_at: "2026-11-05T02:00:00Z" });
    let rows = applyChange(applyChange([], a, NOW), b, NOW);
    expect(rows.map((r) => r.id)).toEqual(["b", "a"]);
    rows = applyChange(rows, { ...a, title: "Changed" }, NOW);
    expect(rows.find((r) => r.id === "a")!.title).toBe("Changed");
    rows = applyChange(rows, { ...b, archived_at: "2026-11-05T05:59:00Z" }, NOW);
    expect(rows.map((r) => r.id)).toEqual(["a"]);
  });

  it("applyChange keeps the limit", () => {
    const many = Array.from({ length: 3 }, (_, i) => row(`r${i}`, { starts_at: `2026-11-05T0${i}:00:00Z` }));
    const rows = many.reduce<AnnouncementRow[]>((acc, r) => applyChange(acc, r, NOW, 2), []);
    expect(rows.map((r) => r.id)).toEqual(["r2", "r1"]);
  });

  it("labels kinds and treats an unknown kind as info", () => {
    expect(kindKey("outage")).toBe("announcements.kind.outage");
    expect(kindKey("maintenance")).toBe("announcements.kind.maintenance");
    expect(kindKey("weird")).toBe("announcements.kind.info");
    expect(kindTone("outage")).toBe("danger");
    expect(kindTone("maintenance")).toBe("warn");
    expect(kindTone("info")).toBe("info");
  });

  it("sortNewest does not mutate and firstName takes the first word", () => {
    const rows = [row("a", { starts_at: "2026-11-05T01:00:00Z" }), row("b", { starts_at: "2026-11-05T02:00:00Z" })];
    expect(sortNewest(rows).map((r) => r.id)).toEqual(["b", "a"]);
    expect(rows.map((r) => r.id)).toEqual(["a", "b"]);
    expect(firstName("Lina Haddad")).toBe("Lina");
    expect(firstName("  talal ")).toBe("talal");
    expect(firstName(null)).toBe("");
  });
});

describe("announcement calls", () => {
  it("posts the trimmed fields through the proxy", async () => {
    const fn = stubFetch(200, { id: "a1" });
    const res = await createAnnouncement({ title: " Wifi ", body: " Down ", kind: "outage", office: null, endsAt: "2026-11-06T19:00:00.000Z" });
    expect(res.ok).toBe(true);
    const [url, init] = fn.mock.calls[0]! as unknown as [string, RequestInit];
    expect(url).toBe("/api/ai/announcements");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      title: "Wifi",
      body: "Down",
      kind: "outage",
      office: null,
      ends_at: "2026-11-06T19:00:00.000Z",
    });
  });

  it("archives by id with the id encoded", async () => {
    const fn = stubFetch(200, { id: "a/1" });
    await archiveAnnouncement("a/1");
    expect(fn.mock.calls[0]![0]).toBe("/api/ai/announcements/a%2F1/archive");
  });

  it("words the failures", async () => {
    const err = (status: number, code: string) => ({ error: { code, message: "x", details: null } }) as const;
    const kinds: Array<[number, string, string]> = [
      [403, "forbidden", "forbidden"],
      [404, "not_found", "notFound"],
      [422, "invalid_input", "invalid"],
      [401, "unauthenticated", "session"],
      [500, "internal_error", "generic"],
    ];
    for (const [status, code, kind] of kinds) {
      stubFetch(status, err(status, code));
      const res = await archiveAnnouncement("a1");
      expect(res.ok).toBe(false);
      if (!res.ok) expect(announcementErrorKind(res)).toBe(kind);
    }
  });
});
