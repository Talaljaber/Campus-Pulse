"use client";

import { useLayoutEffect, useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from "react";
import { useT } from "@/i18n";
import { cn } from "../ui/cn";
import { Icon } from "../ui/Icon";

/** The box grows to about six lines (6 x 1.5rem) and then scrolls. */
const MAX_HEIGHT_REM = 9;

/** Props for {@link Composer}. */
export interface ComposerProps {
  /** The student sent a message. */
  onSubmit: (text: string) => void;
  /** A request is in flight: sending is disabled. */
  busy: boolean;
  /** Prefills the editor from a starter prompt; the user can always change it before sending. */
  initialText?: string;
}

/**
 * The message box, like any chatbot: one rounded box, a textarea that grows from one line to about
 * six, and a round send button inside it at the end of the line (the left in Arabic). Enter sends,
 * Shift+Enter adds a line, and Enter while an IME is composing a word does nothing. The text is
 * cleared only after it was handed to `onSubmit`. Direction follows what is typed (`dir="auto"`).
 */
export function Composer({ onSubmit, busy, initialText = "" }: ComposerProps) {
  const t = useT();
  const [text, setText] = useState(initialText);
  const areaRef = useRef<HTMLTextAreaElement>(null);
  const empty = text.trim() === "";

  // A new starter prompt replaces the text (adjusting state while rendering, not in an effect).
  const [seenInitial, setSeenInitial] = useState(initialText);
  if (initialText !== seenInitial) {
    setSeenInitial(initialText);
    if (initialText) setText(initialText);
  }

  // Grow with the content: reset, then measure.
  useLayoutEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const max = MAX_HEIGHT_REM * parseFloat(getComputedStyle(document.documentElement).fontSize || "16");
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
    el.style.overflowY = el.scrollHeight > max ? "auto" : "hidden";
  }, [text]);

  const send = () => {
    if (busy || empty) return;
    onSubmit(text.trim());
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
  const onChange = (e: ChangeEvent<HTMLTextAreaElement>) => setText(e.target.value);

  return (
    <form
      onSubmit={onFormSubmit}
      className={cn(
        "mx-auto flex w-full max-w-5xl items-end gap-2 rounded-3xl border border-line-strong bg-input py-1.5 ps-4 pe-1.5",
        "transition-colors duration-(--cp-motion-fast) hover:border-accent focus-within:border-accent",
      )}
    >
      <label htmlFor="chat-composer" className="sr-only">
        {t("chat.composerLabel")}
      </label>
      <textarea
        id="chat-composer"
        ref={areaRef}
        dir="auto"
        rows={1}
        value={text}
        onChange={onChange}
        onKeyDown={onKeyDown}
        placeholder={t("chat.placeholder")}
        style={{ maxHeight: `${MAX_HEIGHT_REM}rem` }}
        className="min-h-9 min-w-0 flex-1 resize-none self-center bg-transparent py-1.5 text-base leading-6 text-fg-1 outline-none placeholder:text-fg-3"
      />
      <button
        type="submit"
        disabled={busy || empty}
        aria-label={t("chat.send")}
        aria-busy={busy || undefined}
        className={cn(
          "grid size-11 shrink-0 place-items-center rounded-full bg-accent text-on-accent",
          "transition-[filter,opacity] duration-(--cp-motion-fast) hover:brightness-110 active:brightness-95",
          "disabled:cursor-not-allowed disabled:opacity-45",
        )}
      >
        {busy ? <Icon name="spinner" size={20} className="motion-safe:animate-spin" /> : <Icon name="send" size={20} />}
      </button>
    </form>
  );
}
