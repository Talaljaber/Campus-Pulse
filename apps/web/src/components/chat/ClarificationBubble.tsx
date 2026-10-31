"use client";

import { useT } from "@/i18n";
import type { Clarification } from "@/lib/ai/types";
import { textDir } from "../explain/text";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";

/** Props for {@link ClarificationBubble}. */
export interface ClarificationBubbleProps {
  /** The question and its answer chips, in the request language (server text). */
  q: Clarification;
  /** The chip the student chose. */
  onPick: (optionId: string) => void;
  /** True while an answer is in flight, or once the question has been answered. */
  disabled: boolean;
  /** The option already chosen, shown pressed with a check. */
  answered?: string;
}

/**
 * One clarifying question with its answer chips. The text direction follows the question's
 * own script, not the page language, because the service asks in the language of the request.
 *
 * The chips are plain buttons in a labelled group, not a radiogroup: choosing sends the
 * answer to the server at once, and a radiogroup would send one every time an arrow key
 * moved the selection. Tab moves between chips; Enter or Space answers.
 */
export function ClarificationBubble({ q, onPick, disabled, answered }: ClarificationBubbleProps) {
  const t = useT();
  return (
    <div dir={textDir(q.text)} className="flex max-w-prose flex-col gap-3 rounded-lg border border-line bg-surface-1 p-4">
      <p className="text-fg-1">{q.text}</p>
      <div role="group" aria-label={t("chat.clarifyGroup")} className="flex flex-wrap gap-2">
        {q.options.map((o) => {
          const chosen = o.id === answered;
          return (
            <Button
              key={o.id}
              variant="secondary"
              aria-pressed={answered === undefined ? undefined : chosen}
              disabled={disabled && !chosen}
              onClick={() => {
                if (!disabled) onPick(o.id);
              }}
              className={chosen ? "rounded-full border-2 border-accent" : "rounded-full"}
            >
              {chosen && <Icon name="check" size={14} />}
              {o.text}
            </Button>
          );
        })}
      </div>
    </div>
  );
}
