"use client";

import { useId } from "react";
import { labelOf, useLang, useT } from "@/i18n";
import type { CounterfactualView, TriageResponse, TriageStatus } from "@/lib/ai/types";
import { Badge } from "../ui/Badge";
import { cn } from "../ui/cn";
import { ProbBar } from "../ui/ProbBar";
import { SetBadge } from "../ui/SetBadge";
import { CATEGORY_TONE, PRIORITY_TONE, type Tone } from "../ui/tone";
import { ExplanationPanel } from "../explain/ExplanationPanel";
import { textDir } from "../explain/text";
import { ActionSummary } from "./ActionSummary";
import { FlagBadges, type Audience } from "./FlagBadges";
import { UnderstandingView } from "./UnderstandingView";

/** Props for {@link ResultCard}. */
export interface ResultCardProps {
  /** One `/v1/triage` response, any of the five statuses. */
  result: TriageResponse;
  /** Who is looking. Staff-only flags are hidden from `student`. Default `student`. */
  audience?: Audience;
  /** The request text, so top words can be highlighted inside it. */
  text?: string;
  /** A word was chosen for a counterfactual. The parent fetches and passes the answer back. */
  onCounterfactual?: (token: string) => void;
  /** The live counterfactual answer. */
  counterfactual?: CounterfactualView | null;
  /** Clock override for "learned N s ago" (epoch ms). Tests and stories pass one. */
  now?: number;
  className?: string;
}

const STATUS_TONE: Record<TriageStatus, Tone> = {
  decided: "ok",
  needs_clarification: "info",
  human_review: "warn",
  out_of_scope: "neutral",
  distress: "info",
};

/**
 * The student-facing result of one triage call: status, category and priority with
 * their confidence and "could also be" sets, flags, what we understood, what happens
 * next, and the explanation. It renders the DTO and nothing else: there is no fetching
 * and no threshold or routing logic here.
 */
export function ResultCard({
  result,
  audience = "student",
  text,
  onCounterfactual,
  counterfactual,
  now,
  className,
}: ResultCardProps) {
  const t = useT();
  const { lang } = useLang();
  const titleId = useId();
  const { status, category, priority } = result;
  const showLabels = category !== null && priority !== null && (status === "decided" || status === "human_review" || status === "needs_clarification");

  return (
    <article
      aria-labelledby={titleId}
      data-status={status}
      className={cn("flex flex-col gap-4 rounded-lg border border-line bg-surface-1 p-4 shadow-1", className)}
    >
      <header className="flex flex-wrap items-center gap-2">
        <h2 id={titleId} className="text-lg font-semibold text-fg-1">
          {t("result.title")}
        </h2>
        <Badge tone={STATUS_TONE[status]}>{t(`result.status.${status}`)}</Badge>
      </header>

      {result.understood_as && (
        <p className="text-sm text-fg-2">
          {t("result.understoodAs")}:{" "}
          <span dir="rtl" lang="ar" className="font-medium text-fg-1">
            {result.understood_as}
          </span>
        </p>
      )}

      {status === "needs_clarification" && category && (
        <p className="text-sm font-medium text-fg-3">{t("result.provisional")}</p>
      )}

      {showLabels && category && priority && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <ProbBar
              label={`${t("result.category")}: ${labelOf("category", category.label, lang)}`}
              prob={category.prob}
              tone={CATEGORY_TONE[category.label] ?? "neutral"}
            />
            <SetBadge set={category.set} kind="category" chosen={category.label} />
          </div>
          <div className="flex flex-col gap-2">
            <ProbBar
              label={`${t("result.priority")}: ${labelOf("priority", priority.label, lang)}`}
              prob={priority.prob}
              tone={PRIORITY_TONE[priority.label] ?? "neutral"}
            />
            <SetBadge set={priority.set} kind="priority" chosen={priority.label} />
          </div>
        </div>
      )}

      <FlagBadges flags={result.flags} audience={audience} />

      {status === "human_review" && category && (
        <p className="text-sm text-fg-1">
          {t("result.humanReview", { category: labelOf("category", category.label, lang) })}
        </p>
      )}

      {status === "needs_clarification" && result.clarification && (
        <p dir={textDir(result.clarification.text)} className="text-fg-1">
          {result.clarification.text}
        </p>
      )}

      {(status === "out_of_scope" || status === "distress") && result.message && (
        <p
          dir={textDir(result.message)}
          role={status === "distress" ? "status" : undefined}
          className={cn("text-fg-1", status === "distress" && "rounded-md border-2 border-info p-3")}
        >
          {result.message}
        </p>
      )}

      <UnderstandingView understanding={result.understanding} showTicketDraft={audience !== "student"} />

      <ActionSummary action={result.action} status={status} />

      {result.explanation && (
        <ExplanationPanel
          explanation={result.explanation}
          text={text}
          evidence={priority?.evidence}
          tier={result.tier}
          onCounterfactual={onCounterfactual}
          counterfactual={counterfactual}
          now={now}
        />
      )}
    </article>
  );
}
