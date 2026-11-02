"use client";

import { useEffect, useRef } from "react";
import { useT, type DictKey } from "@/i18n";
import type { CounterfactualView } from "@/lib/ai/types";
import type { ChatErrorKind, ChatItem, NoticeData } from "@/lib/chat/types";
import { useOfficeLabel } from "../staff/office";
import { ClarificationBubble } from "./ClarificationBubble";
import { DistressCard } from "./DistressCard";
import { ResultCard } from "./ResultCard";

/** Props for {@link ChatThread}. */
export interface ChatThreadProps {
  items: readonly ChatItem[];
  /** Latest counterfactual answer by `request_id`. */
  counterfactuals?: Readonly<Record<string, CounterfactualView>>;
  /** A request or an answer is in flight: chips are disabled. */
  busy?: boolean;
  /** A clarification chip was chosen: the chat item id and the option id. */
  onPick?: (itemId: string, optionId: string) => void;
  /** A highlighted word was chosen: the result's `request_id` and the token. */
  onCounterfactual?: (requestId: string, token: string) => void;
}

const ERROR_KEY: Record<ChatErrorKind, DictKey> = {
  generic: "chat.errorGeneric",
  waking: "chat.errorWaking",
  session: "chat.errorSession",
  nothingToAnswer: "chat.errorNothingToAnswer",
};

/** Translated sentence for a live notice. Values are rendered as text only. */
export function useNoticeText(): (n: NoticeData) => string {
  const t = useT();
  const officeLabel = useOfficeLabel();
  return (n) => {
    if (n.type === "message") return n.message;
    if (n.type === "review_assigned") return t(n.assigned ? "notice.reviewAssigned" : "notice.reviewQueued");
    if (n.type === "ticket_forwarded") {
      const from = n.fromOffice ? officeLabel(n.fromOffice) : "";
      return n.title && from
        ? t("notice.ticketForwarded", { title: n.title, office: from })
        : t("notice.ticketForwardedNoTitle");
    }
    if (n.type === "generic") return t("chat.updateGeneric");
    const known = ["new", "in_progress", "solved", "closed", "merged"];
    const status = known.includes(n.status) ? t(`chat.status.${n.status}` as DictKey) : n.status;
    return n.title ? t("chat.ticketStatus", { title: n.title, status }) : t("chat.ticketStatusNoTitle", { status });
  };
}

/**
 * The conversation. It composes the existing result components and adds no logic: a
 * student bubble, a `ResultCard` (or the `DistressCard`), a `ClarificationBubble`, a live
 * notice, or an error line per item. The list is a `log` region, so new entries are
 * announced politely, and the newest entry is scrolled into view.
 */
export function ChatThread({ items, counterfactuals = {}, busy = false, onPick, onCounterfactual }: ChatThreadProps) {
  const t = useT();
  const noticeText = useNoticeText();
  const endRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [items.length]);

  return (
    <ol role="log" aria-label={t("chat.thread")} className="flex flex-col gap-4">
      {items.map((item) => (
        <li key={item.id} className={item.role === "student" ? "flex justify-end" : undefined}>
          {item.role === "student" && (
            <p dir="auto" className="max-w-prose rounded-lg bg-accent px-4 py-2 text-on-accent">
              <span className="sr-only">{t("chat.you")}: </span>
              {item.text}
            </p>
          )}

          {item.role === "system" &&
            (item.result.status === "distress" ? (
              <DistressCard message={item.result.message ?? ""} />
            ) : (
              <ResultCard
                result={item.result}
                audience="student"
                text={item.text}
                counterfactual={counterfactuals[item.result.request_id] ?? null}
                onCounterfactual={onCounterfactual ? (token) => onCounterfactual(item.result.request_id, token) : undefined}
              />
            ))}

          {item.role === "clarify" && (
            <ClarificationBubble
              q={item.q}
              answered={item.answered}
              disabled={busy || item.answered !== undefined}
              onPick={(optionId) => onPick?.(item.id, optionId)}
            />
          )}

          {item.role === "notice" && (
            <p className="rounded-md border border-line bg-surface-1 px-3 py-2 text-sm text-fg-2">{noticeText(item.notice)}</p>
          )}

          {item.role === "error" && (
            <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm font-medium text-danger">
              {t(ERROR_KEY[item.kind])}
            </p>
          )}
        </li>
      ))}
      <li ref={endRef} aria-hidden="true" />
    </ol>
  );
}
