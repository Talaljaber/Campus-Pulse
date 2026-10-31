"use client";

import { useId } from "react";
import { useLang, useT } from "@/i18n";
import type { Understanding } from "@/lib/ai/types";
import { Badge } from "../ui/Badge";
import { cn } from "../ui/cn";
import { textDir } from "../explain/text";

/** Props for {@link UnderstandingView}. */
export interface UnderstandingViewProps {
  /** `result.understanding` (UD-10). `null` renders nothing. */
  understanding: Understanding | null;
  /** Also show the ticket title and body the service drafted. For staff views. */
  showTicketDraft?: boolean;
  className?: string;
}

const ENTITY_KEYS = ["building", "room", "course_code", "deadline", "system"] as const;

/**
 * The structured understanding: a one-sentence summary in the UI language, the
 * entities it found, and the student-facing reply. It describes the request; it never
 * changes the labels. When the summary came from the rule-based fallback, a short
 * note says so.
 */
export function UnderstandingView({ understanding, showTicketDraft = false, className }: UnderstandingViewProps) {
  const t = useT();
  const { lang } = useLang();
  const id = useId();
  if (!understanding) return null;
  const summary = lang === "ar" ? understanding.summary_ar : understanding.summary_en;
  const found = ENTITY_KEYS.flatMap((k) => {
    const value = understanding.entities[k];
    return value ? [{ k, value }] : [];
  });

  return (
    <section aria-labelledby={id} className={cn("flex flex-col gap-3", className)}>
      <h3 id={id} className="text-md font-semibold text-fg-1">
        {t("result.summary")}
      </h3>
      <p dir={textDir(summary)} className="text-fg-1">
        {summary}
      </p>
      {found.length > 0 && (
        <dl className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {found.map(({ k, value }) => (
            <div key={k} className="flex gap-1.5">
              <dt className="text-fg-3">{t(`result.entities.${k}`)}:</dt>
              <dd dir="auto" className="font-medium text-fg-1">
                {value}
              </dd>
            </div>
          ))}
        </dl>
      )}
      <blockquote className="border-s-4 border-line-strong ps-3">
        <p className="text-xs font-medium text-fg-3">{t("result.reply")}</p>
        <p dir={textDir(understanding.student_reply)} className="text-fg-1">
          {understanding.student_reply}
        </p>
      </blockquote>
      {showTicketDraft && (
        <div className="flex flex-col gap-1 text-sm">
          <p className="font-semibold text-fg-1">{t("result.ticketDraft")}</p>
          <p dir={textDir(understanding.ticket_title)}>
            <span className="text-fg-3">{t("result.ticketTitle")}: </span>
            {understanding.ticket_title}
          </p>
          <p dir={textDir(understanding.ticket_body)}>
            <span className="text-fg-3">{t("result.ticketBody")}: </span>
            {understanding.ticket_body}
          </p>
        </div>
      )}
      {understanding.source === "rules" && (
        <div>
          <Badge tone="neutral" icon="info">
            {t("result.sourceRules")}
          </Badge>
        </div>
      )}
    </section>
  );
}
