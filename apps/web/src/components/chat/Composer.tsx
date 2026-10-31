"use client";

import { useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { useT } from "@/i18n";
import { Button } from "../ui/Button";
import { TextArea } from "../ui/TextField";

/** Props for {@link Composer}. */
export interface ComposerProps {
  /** The student sent a request. `mode` is `voice` only for a transcript they confirmed (P5.9). */
  onSubmit: (text: string, mode: "text" | "voice") => void;
  /** A request is in flight: sending is disabled. */
  busy: boolean;
  /** Slot for the microphone button (P5.9). Empty until voice ships. */
  micSlot?: ReactNode;
}

/**
 * The message box. Enter sends, Shift+Enter adds a line, the send button is a real submit
 * button. The text is cleared only after it was handed to `onSubmit`. Direction follows what
 * is typed (`dir="auto"`), so Arabic and English both read correctly.
 */
export function Composer({ onSubmit, busy, micSlot }: ComposerProps) {
  const t = useT();
  const [text, setText] = useState("");
  const empty = text.trim() === "";

  const send = () => {
    if (busy || empty) return;
    onSubmit(text.trim(), "text");
    setText("");
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

  return (
    <form onSubmit={onFormSubmit} className="flex items-end gap-2">
      <TextArea
        label={t("chat.composerLabel")}
        hideLabel
        className="flex-1"
        placeholder={t("chat.placeholder")}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        rows={2}
      />
      {micSlot}
      <Button type="submit" loading={busy} disabled={empty}>
        {t("chat.send")}
      </Button>
    </form>
  );
}
