import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ callAi: vi.fn() }));
vi.mock("@/lib/ai/browser", () => ({ callAi: m.callAi }));

import { postStudentAction } from "../service";

beforeEach(() => m.callAi.mockReset().mockResolvedValue({ ok: true, data: {} }));

describe("postStudentAction", () => {
  it.each(["solved", "close", "keep_open"] as const)("posts %s to the student-action endpoint", async (action) => {
    await postStudentAction("t-1", { action });
    expect(m.callAi).toHaveBeenCalledWith("tickets/t-1/student-action", { method: "POST", body: { action } });
  });
});
