"use client";

import { useEffect, useRef } from "react";
import { useSpeech } from "@/hooks/useSpeech";
import { useT, type DictKey } from "@/i18n";
import { speechErrorKind, type SpeechErrorKind, type SpeechLang } from "@/lib/voice/speech";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { useToast } from "../ui/Toast";

/** Props for {@link MicButton}. */
export interface MicButtonProps {
  /** Recognition language: `ar-JO` for Arabic, `en-US` for English. */
  lang: SpeechLang;
  /** The transcript so far (interim words included), called on every change. The parent puts it in the composer, never sends it. */
  onTranscript: (transcript: string) => void;
  /** A new dictation session started (the parent remembers what was already typed). */
  onStart?: () => void;
  disabled?: boolean;
}

const ERROR_KEY: Record<SpeechErrorKind, DictKey> = {
  denied: "chat.voice.errorDenied",
  noSpeech: "chat.voice.errorNoSpeech",
  network: "chat.voice.errorNetwork",
  language: "chat.voice.errorLanguage",
  noMic: "chat.voice.errorNoMic",
  generic: "chat.voice.errorGeneric",
};

/**
 * Microphone toggle for the composer. It renders nothing where the browser has no Web
 * Speech API (Firefox), so typing stays the only path there. It is a real button with
 * `aria-pressed`; the listening state is also announced in a polite live region, and a
 * failure becomes a toast. The transcript only fills the text box: the student confirms
 * and sends it.
 */
export function MicButton({ lang, onTranscript, onStart, disabled = false }: MicButtonProps) {
  const t = useT();
  const toast = useToast();
  const { supported, listening, transcript, start, stop, error } = useSpeech(lang);

  const onTranscriptRef = useRef(onTranscript);
  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  useEffect(() => {
    if (transcript) onTranscriptRef.current(transcript);
  }, [transcript]);

  useEffect(() => {
    if (!error) return;
    const kind = speechErrorKind(error);
    if (kind) toast.show(t(ERROR_KEY[kind]), "warn");
    // `t` and `toast` are stable per language; only a new error should toast.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [error]);

  if (!supported) return null;

  const label = listening
    ? t("chat.voice.stop")
    : t("chat.voice.start", { language: t(lang === "ar-JO" ? "chat.voice.langAr" : "chat.voice.langEn") });

  const toggle = () => {
    if (listening) {
      stop();
      return;
    }
    onStart?.();
    start();
  };

  return (
    <>
      <Button
        variant={listening ? "danger" : "secondary"}
        aria-pressed={listening}
        aria-label={label}
        title={label}
        disabled={disabled && !listening}
        onClick={toggle}
        className="px-3"
      >
        <Icon name="mic" size={20} className={listening ? "motion-safe:animate-pulse" : undefined} />
      </Button>
      <span role="status" className="sr-only">
        {listening ? t("chat.voice.listening") : ""}
      </span>
    </>
  );
}
