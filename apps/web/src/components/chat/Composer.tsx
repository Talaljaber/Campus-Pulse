"use client";

import { useState, type ChangeEvent, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { useT } from "@/i18n";
import { joinTranscript } from "@/lib/voice/speech";
import { Button } from "../ui/Button";
import { TextArea } from "../ui/TextField";

/** What the composer hands to a render-prop `micSlot` so a dictation button can fill the text box. */
export interface ComposerMicApi {
  /** Call when dictation starts: remembers what is already typed so the transcript is appended to it. */
  begin: () => void;
  /** Call with the transcript so far: the text box becomes what was typed plus the transcript, and the message counts as voice. */
  apply: (transcript: string) => void;
}

/** Props for {@link Composer}. */
export interface ComposerProps {
  /** The student sent a request. `mode` is `voice` only for a transcript they confirmed (P5.9). */
  onSubmit: (text: string, mode: "text" | "voice") => void;
  /** A request is in flight: sending is disabled. */
  busy: boolean;
  /** Where the microphone button goes: a node, or a function of {@link ComposerMicApi}. Empty when voice is not offered. */
  micSlot?: ReactNode | ((api: ComposerMicApi) => ReactNode);
  /** Prefills the editor from a starter prompt; the user can always change it before sending. */
  initialText?: string;
}

/**
 * The message box. Enter sends, Shift+Enter adds a line, the send button is a real submit
 * button. The text is cleared only after it was handed to `onSubmit`. Direction follows what
 * is typed (`dir="auto"`), so Arabic and English both read correctly.
 *
 * Voice: a dictated transcript only fills the box. It is editable and is sent only when the
 * student presses send, with `mode` set to `voice`. Emptying the box resets the mode to `text`.
 */
export function Composer({ onSubmit, busy, micSlot, initialText = "" }: ComposerProps) {
  const t = useT();
  const [text, setText] = useState(initialText);
  const [voice, setVoice] = useState(false);
  // What was typed before dictation began; the transcript is appended to it.
  const [base, setBase] = useState("");
  const empty = text.trim() === "";

  // A new starter prompt replaces the text (adjusting state while rendering, not in an effect).
  const [seenInitial, setSeenInitial] = useState(initialText);
  if (initialText !== seenInitial) {
    setSeenInitial(initialText);
    if (initialText) {
      setText(initialText);
      setVoice(false);
    }
  }

  const send = () => {
    if (busy || empty) return;
    onSubmit(text.trim(), voice ? "voice" : "text");
    setText("");
    setVoice(false);
  };
  const onFormSubmit = (e: FormEvent) => {
    e.preventDefault();
    send();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Do not send while an IME composition (Arabic or other input methods) is choosing a word.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };
  const onChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    if (e.target.value.trim() === "") setVoice(false);
  };

  const mic: ComposerMicApi = {
    begin: () => {
      setBase(text);
    },
    apply: (transcript) => {
      setText(joinTranscript(base, transcript));
      setVoice(true);
    },
  };

  return (
    <form onSubmit={onFormSubmit} className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-end gap-2 sm:flex">
      <TextArea
        label={t("chat.composerLabel")}
        hideLabel
        className="col-span-3 min-w-0 sm:flex-1"
        placeholder={t("chat.placeholder")}
        value={text}
        onChange={onChange}
        onKeyDown={onKeyDown}
        rows={2}
      />
      {typeof micSlot === "function" ? micSlot(mic) : micSlot}
      <Button type="submit" loading={busy} disabled={empty}>
        {t("chat.send")}
      </Button>
    </form>
  );
}
