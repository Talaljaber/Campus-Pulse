/**
 * Pure helpers for Web Speech dictation (P5.9). Nothing here touches React or reads
 * `window` on import, so the logic is testable and safe during server rendering.
 */
import type { Lang } from "@/i18n";

/** The two recognition languages we support: Jordanian Arabic and US English. */
export type SpeechLang = "ar-JO" | "en-US";

/** Dictation language that follows the UI language: Arabic page, Arabic speech. */
export function speechLangFor(lang: Lang): SpeechLang {
  return lang === "ar" ? "ar-JO" : "en-US";
}

/** The slice of the browser's `SpeechRecognitionEvent` this app reads (lib.dom has no such types yet). */
export interface SpeechResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}

export interface SpeechErrorEvent {
  error: string;
}

/** The slice of a `SpeechRecognition` instance this app uses. */
export interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: SpeechResultEvent) => void) | null;
  onerror: ((e: SpeechErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

export type RecognitionCtor = new () => RecognitionLike;

/** The recognition constructor of this browser (Chrome and Safari expose the `webkit` one), or null (Firefox). */
export function getRecognitionCtor(win: unknown): RecognitionCtor | null {
  if (typeof win !== "object" || win === null) return null;
  const w = win as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** All results of one session joined into a single string (interim words included). */
export function transcriptOf(e: SpeechResultEvent): string {
  const parts: string[] = [];
  for (let i = 0; i < e.results.length; i++) {
    const alt = e.results[i]?.[0];
    if (alt?.transcript) parts.push(alt.transcript.trim());
  }
  return parts.join(" ").trim();
}

export type SpeechErrorKind = "denied" | "noSpeech" | "network" | "language" | "noMic" | "generic";

/**
 * Maps a recognition error code to a dictionary entry. `aborted` is our own `stop` or a
 * teardown, so it is not an error and returns null.
 */
export function speechErrorKind(code: string): SpeechErrorKind | null {
  switch (code) {
    case "aborted":
      return null;
    case "not-allowed":
    case "service-not-allowed":
      return "denied";
    case "no-speech":
      return "noSpeech";
    case "network":
      return "network";
    case "language-not-supported":
      return "language";
    case "audio-capture":
      return "noMic";
    default:
      return "generic";
  }
}

/** Appends a dictated phrase to what was already typed, with one space between them. */
export function joinTranscript(base: string, transcript: string): string {
  const b = base.trimEnd();
  const t = transcript.trim();
  if (!t) return base;
  return b ? `${b} ${t}` : t;
}
