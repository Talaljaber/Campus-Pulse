"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { getRecognitionCtor, transcriptOf, type RecognitionLike, type SpeechLang } from "@/lib/voice/speech";

export interface SpeechApi {
  /** False on browsers without the Web Speech API (Firefox) and during server rendering. */
  supported: boolean;
  listening: boolean;
  /** Everything recognised in the current session, interim words included. Empty before the first result. */
  transcript: string;
  /** Starts a new session (clears the transcript and the error). A no-op when unsupported or already listening. */
  start: () => void;
  /** Ends the session; the last words still arrive as a final result. */
  stop: () => void;
  /** The browser's error code (`not-allowed`, `no-speech`, ...) of the last session, if it failed. */
  error?: string;
}

const noop = () => () => {};
const clientSupported = () => getRecognitionCtor(window) !== null;
const serverSupported = () => false;

/**
 * Dictation through the browser's Web Speech API, in `ar-JO` or `en-US`. It does nothing
 * until `start()` is called from a user action, and everything is torn down on unmount.
 * The browser's own speech service hears the audio; this app never receives it.
 */
export function useSpeech(lang: SpeechLang): SpeechApi {
  const supported = useSyncExternalStore(noop, clientSupported, serverSupported);
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | undefined>();
  const rec = useRef<RecognitionLike | null>(null);

  const start = useCallback(() => {
    const Ctor = getRecognitionCtor(window);
    if (!Ctor || rec.current) return;
    const r = new Ctor();
    r.lang = lang;
    r.continuous = false;
    r.interimResults = true;
    r.maxAlternatives = 1;
    r.onresult = (e) => setTranscript(transcriptOf(e));
    r.onerror = (e) => setError(e.error);
    r.onend = () => {
      if (rec.current === r) rec.current = null;
      setListening(false);
    };
    setTranscript("");
    setError(undefined);
    rec.current = r;
    try {
      r.start();
      setListening(true);
    } catch {
      // `start()` throws when the page may not listen or a session is already running.
      rec.current = null;
      setError("generic");
    }
  }, [lang]);

  const stop = useCallback(() => {
    rec.current?.stop();
  }, []);

  useEffect(
    () => () => {
      const r = rec.current;
      if (!r) return;
      r.onresult = r.onerror = r.onend = null;
      r.abort();
      rec.current = null;
    },
    [],
  );

  return { supported, listening, transcript, start, stop, error };
}
