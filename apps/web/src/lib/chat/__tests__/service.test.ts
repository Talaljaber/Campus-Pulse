import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  answerClarification,
  chatErrorKind,
  fetchCounterfactual,
  noticeFromNotification,
  submitTriage,
} from "@/lib/chat/service";
import { failFromNetwork, failFromResponse } from "@/lib/ai/result";

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("requests", () => {
  it("submitTriage posts text, mode and the picked building, and never an alias", async () => {
    await submitTriage("wifi is down", "text", "M");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/ai/triage");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ text: "wifi is down", input_mode: "text", location: { building: "M" } });
  });

  it("submitTriage omits location when no building is picked", async () => {
    await submitTriage("hi", "voice", null);
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual({ text: "hi", input_mode: "voice" });
  });

  it("answerClarification posts the question and option ids", async () => {
    await answerClarification("req-1", "cat:Registration|IT Support", "registration");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/ai/triage/req-1/clarify");
    expect(JSON.parse(init.body)).toEqual({ question_id: "cat:Registration|IT Support", option_id: "registration" });
  });

  it("fetchCounterfactual encodes the token (Arabic words and spaces)", async () => {
    await fetchCounterfactual("req-1", "اليوم");
    expect(fetchMock.mock.calls[0]![0]).toBe(`/api/ai/explain/req-1/counterfactual?drop=${encodeURIComponent("اليوم")}`);
    expect(fetchMock.mock.calls[0]![1].method).toBe("GET");
  });
});

describe("chatErrorKind", () => {
  it("maps failures to a student-facing kind", () => {
    expect(chatErrorKind(failFromResponse(401, { error: { code: "unauthenticated", message: "x", details: null } }))).toBe("session");
    expect(chatErrorKind(failFromNetwork(true))).toBe("waking");
    expect(chatErrorKind(failFromResponse(503, null))).toBe("waking");
    expect(chatErrorKind(failFromResponse(409, { error: { code: "clarification_budget_exceeded", message: "x", details: null } }), "clarify")).toBe(
      "nothingToAnswer",
    );
    expect(chatErrorKind(failFromResponse(404, { error: { code: "not_found", message: "x", details: null } }), "clarify")).toBe("nothingToAnswer");
    expect(chatErrorKind(failFromResponse(404, { error: { code: "not_found", message: "x", details: null } }), "triage")).toBe("generic");
    expect(chatErrorKind(failFromResponse(500, { error: { code: "internal_error", message: "x", details: null } }))).toBe("generic");
  });
});

describe("noticeFromNotification", () => {
  it("recognises a ticket status update", () => {
    expect(noticeFromNotification({ kind: "ticket_status", payload: { status: "resolved", title: "Wi-Fi in M" } })).toEqual({
      type: "ticket_status",
      title: "Wi-Fi in M",
      status: "resolved",
    });
  });
  it("falls back to a message, then to generic, and ignores non-object payloads", () => {
    expect(noticeFromNotification({ kind: "incident_broadcast", payload: { message: "Wi-Fi is back" } })).toEqual({
      type: "message",
      message: "Wi-Fi is back",
    });
    expect(noticeFromNotification({ kind: "x", payload: { n: 1 } })).toEqual({ type: "generic" });
    expect(noticeFromNotification({ kind: "x", payload: "text" })).toEqual({ type: "generic" });
    expect(noticeFromNotification({ kind: "x", payload: null })).toEqual({ type: "generic" });
  });
});
