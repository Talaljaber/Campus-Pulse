import { describe, expect, it } from "vitest";
import { changedWords } from "../textDiff";

describe("changedWords", () => {
  it("marks the replaced room and nothing else", () => {
    const parts = changedWords("The printer in H302 is broken.", "The printer in H203 is broken.");
    expect(parts.filter((p) => p.changed).map((p) => p.text)).toEqual(["H203"]);
    expect(parts.map((p) => p.text).join("")).toBe("The printer in H203 is broken.");
  });
  it("ignores case and edge punctuation, and marks added words", () => {
    const parts = changedWords("wifi down", "Wifi, down in building M");
    expect(parts.filter((p) => p.changed).map((p) => p.text)).toEqual(["in", "building", "M"]);
  });
  it("works for Arabic", () => {
    const parts = changedWords("الطابعة بقاعة H302 خربانة", "الطابعة بقاعة H203 خربانة");
    expect(parts.filter((p) => p.changed).map((p) => p.text)).toEqual(["H203"]);
  });
});
