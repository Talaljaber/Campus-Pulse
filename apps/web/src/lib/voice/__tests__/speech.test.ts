import { describe, expect, it } from "vitest";
import { getRecognitionCtor, joinTranscript, speechErrorKind, speechLangFor, transcriptOf } from "../speech";

describe("speechLangFor", () => {
  it("follows the UI language", () => {
    expect(speechLangFor("ar")).toBe("ar-JO");
    expect(speechLangFor("en")).toBe("en-US");
  });
});

describe("getRecognitionCtor", () => {
  it("prefers the standard name, falls back to webkit, and is null without either", () => {
    class A {}
    class B {}
    expect(getRecognitionCtor({ SpeechRecognition: A, webkitSpeechRecognition: B })).toBe(A);
    expect(getRecognitionCtor({ webkitSpeechRecognition: B })).toBe(B);
    expect(getRecognitionCtor({})).toBeNull();
    expect(getRecognitionCtor(undefined)).toBeNull();
  });
});

describe("transcriptOf", () => {
  it("joins the best alternative of every result and trims", () => {
    expect(transcriptOf({ results: [[{ transcript: " hello " }], [{ transcript: "world" }]] })).toBe("hello world");
    expect(transcriptOf({ results: [] })).toBe("");
  });
});

describe("speechErrorKind", () => {
  it.each([
    ["not-allowed", "denied"],
    ["service-not-allowed", "denied"],
    ["no-speech", "noSpeech"],
    ["network", "network"],
    ["language-not-supported", "language"],
    ["audio-capture", "noMic"],
    ["something-new", "generic"],
  ])("%s -> %s", (code, kind) => expect(speechErrorKind(code)).toBe(kind));

  it("treats aborted as no error", () => expect(speechErrorKind("aborted")).toBeNull());
});

describe("joinTranscript", () => {
  it("appends with one space, or replaces an empty base", () => {
    expect(joinTranscript("", "hello")).toBe("hello");
    expect(joinTranscript("my wifi  ", "is down")).toBe("my wifi is down");
    expect(joinTranscript("kept", "   ")).toBe("kept");
  });
});
