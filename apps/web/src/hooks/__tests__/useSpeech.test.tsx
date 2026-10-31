import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RecognitionLike, SpeechErrorEvent, SpeechResultEvent } from "@/lib/voice/speech";
import { useSpeech } from "../useSpeech";

/** A stand-in for `webkitSpeechRecognition` that the test drives by hand. */
class FakeRecognition implements RecognitionLike {
  static last: FakeRecognition | null = null;
  static startError: Error | null = null;
  lang = "";
  continuous = true;
  interimResults = false;
  maxAlternatives = 0;
  onresult: ((e: SpeechResultEvent) => void) | null = null;
  onerror: ((e: SpeechErrorEvent) => void) | null = null;
  onend: (() => void) | null = null;
  start = vi.fn(() => {
    if (FakeRecognition.startError) throw FakeRecognition.startError;
  });
  stop = vi.fn(() => this.onend?.());
  abort = vi.fn();
  constructor() {
    FakeRecognition.last = this;
  }
  say(...phrases: string[]) {
    this.onresult?.({ results: phrases.map((transcript) => [{ transcript }]) });
  }
}

const win = window as unknown as { webkitSpeechRecognition?: unknown; SpeechRecognition?: unknown };

beforeEach(() => {
  FakeRecognition.last = null;
  FakeRecognition.startError = null;
  win.webkitSpeechRecognition = FakeRecognition;
});
afterEach(() => {
  delete win.webkitSpeechRecognition;
  delete win.SpeechRecognition;
});

describe("useSpeech", () => {
  it("reports unsupported when the browser has no Web Speech API and does nothing on start", () => {
    delete win.webkitSpeechRecognition;
    const { result } = renderHook(() => useSpeech("en-US"));
    expect(result.current.supported).toBe(false);
    act(() => result.current.start());
    expect(result.current.listening).toBe(false);
    expect(FakeRecognition.last).toBeNull();
  });

  it("also finds the unprefixed constructor", () => {
    delete win.webkitSpeechRecognition;
    win.SpeechRecognition = FakeRecognition;
    const { result } = renderHook(() => useSpeech("en-US"));
    expect(result.current.supported).toBe(true);
  });

  it("starts in the requested language with interim results and collects the transcript", () => {
    const { result } = renderHook(() => useSpeech("ar-JO"));
    expect(result.current.supported).toBe(true);
    act(() => result.current.start());
    const rec = FakeRecognition.last!;
    expect(rec.lang).toBe("ar-JO");
    expect(rec.interimResults).toBe(true);
    expect(rec.continuous).toBe(false);
    expect(rec.start).toHaveBeenCalledTimes(1);
    expect(result.current.listening).toBe(true);

    act(() => rec.say("النظام مش زابط"));
    expect(result.current.transcript).toBe("النظام مش زابط");
    act(() => rec.say("النظام مش زابط", "وبدي اسجل"));
    expect(result.current.transcript).toBe("النظام مش زابط وبدي اسجل");
  });

  it("uses en-US for English", () => {
    const { result } = renderHook(() => useSpeech("en-US"));
    act(() => result.current.start());
    expect(FakeRecognition.last!.lang).toBe("en-US");
  });

  it("stop ends the session and keeps the transcript", () => {
    const { result } = renderHook(() => useSpeech("en-US"));
    act(() => result.current.start());
    act(() => FakeRecognition.last!.say("where is the bus"));
    act(() => result.current.stop());
    expect(result.current.listening).toBe(false);
    expect(result.current.transcript).toBe("where is the bus");
  });

  it("ignores a second start while listening, and clears the transcript on a new session", () => {
    const { result } = renderHook(() => useSpeech("en-US"));
    act(() => result.current.start());
    const first = FakeRecognition.last!;
    act(() => result.current.start());
    expect(FakeRecognition.last).toBe(first);
    act(() => first.say("one"));
    act(() => result.current.stop());
    act(() => result.current.start());
    expect(FakeRecognition.last).not.toBe(first);
    expect(result.current.transcript).toBe("");
  });

  it("surfaces the browser's error code and stops listening", () => {
    const { result } = renderHook(() => useSpeech("en-US"));
    act(() => result.current.start());
    act(() => {
      FakeRecognition.last!.onerror?.({ error: "not-allowed" });
      FakeRecognition.last!.onend?.();
    });
    expect(result.current.error).toBe("not-allowed");
    expect(result.current.listening).toBe(false);
    act(() => result.current.start());
    expect(result.current.error).toBeUndefined();
  });

  it("reports a generic error when start throws", () => {
    FakeRecognition.startError = new Error("InvalidStateError");
    const { result } = renderHook(() => useSpeech("en-US"));
    act(() => result.current.start());
    expect(result.current.listening).toBe(false);
    expect(result.current.error).toBe("generic");
  });

  it("aborts a running session on unmount", () => {
    const { result, unmount } = renderHook(() => useSpeech("en-US"));
    act(() => result.current.start());
    const rec = FakeRecognition.last!;
    unmount();
    expect(rec.abort).toHaveBeenCalledTimes(1);
    expect(rec.onresult).toBeNull();
  });
});
