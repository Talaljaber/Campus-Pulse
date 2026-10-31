"use client";

import { useId, useState } from "react";
import { CATEGORY_VALUES, PRIORITY_VALUES, labelOf, useLang, useT } from "@/i18n";
import type { ReviewView } from "@/lib/staff/review";
import { textDir } from "../explain/text";
import { ExplanationPanel } from "../explain/ExplanationPanel";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { CATEGORY_TONE, PRIORITY_TONE } from "../ui/tone";
import { CorrectionForm } from "./CorrectionForm";

/** Props for {@link ReviewQueue}. */
export interface ReviewQueueProps {
  items: readonly ReviewView[];
  /** Prediction ids whose decision is being sent. */
  pendingIds?: ReadonlySet<string>;
  /** Staff agree with the model's best guess. */
  onConfirm: (predictionId: string) => void;
  /** Staff changed the labels (and maybe left a note). A label left as the model chose is still sent. */
  onCorrect: (predictionId: string, category?: string, priority?: string, note?: string) => void;
}

function ReviewItem({
  item,
  pending,
  onConfirm,
  onCorrect,
}: {
  item: ReviewView;
  pending: boolean;
  onConfirm: ReviewQueueProps["onConfirm"];
  onCorrect: ReviewQueueProps["onCorrect"];
}) {
  const t = useT();
  const { lang } = useLang();
  const textId = useId();
  const [correcting, setCorrecting] = useState(false);

  const sets = (set: readonly string[], kind: "category" | "priority") => set.map((v) => labelOf(kind, v, lang)).join(" / ");
  const reasons = item.distress
    ? [t("staff.review.reasonDistress")]
    : [
        ...(item.setCat.length > 1 ? [t("staff.review.reasonCategory", { labels: sets(item.setCat, "category") })] : []),
        ...(item.setPri.length > 1 ? [t("staff.review.reasonPriority", { labels: sets(item.setPri, "priority") })] : []),
      ];
  if (reasons.length === 0) reasons.push(t("staff.review.reasonGeneric"));

  return (
    <article
      aria-labelledby={textId}
      data-distress={item.distress || undefined}
      className="flex flex-col gap-3 rounded-lg border border-line bg-surface-1 p-4"
    >
      <p id={textId} dir={item.text ? textDir(item.text) : undefined} className="text-base text-fg-1">
        {item.text ?? t("staff.review.noText")}
      </p>

      <div className="flex flex-wrap items-center gap-2">
        {item.category && item.priority ? (
          <>
            <span className="text-sm text-fg-2">{t("staff.review.bestGuess")}</span>
            <Badge tone={CATEGORY_TONE[item.category] ?? "neutral"}>{labelOf("category", item.category, lang)}</Badge>
            <Badge tone={PRIORITY_TONE[item.priority] ?? "neutral"}>{labelOf("priority", item.priority, lang)}</Badge>
          </>
        ) : (
          <Badge tone={item.distress ? "danger" : "neutral"}>{t("staff.review.noGuess")}</Badge>
        )}
      </div>

      <ul className="flex flex-col gap-1 text-sm text-fg-2">
        {reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>

      {item.explanation && (
        <details className="rounded-md border border-line bg-surface-0 p-3">
          <summary className="cursor-pointer text-sm font-medium text-fg-1">{t("staff.review.explanation")}</summary>
          <div className="mt-3">
            <ExplanationPanel
              explanation={item.explanation}
              text={item.text ?? undefined}
              evidence={item.evidence}
              tier={item.tier}
            />
          </div>
        </details>
      )}

      {correcting && !item.distress && (
        <CorrectionForm
          categories={CATEGORY_VALUES}
          priorities={PRIORITY_VALUES}
          initial={{
            category: item.category ?? CATEGORY_VALUES[0]!,
            priority: item.priority ?? "medium",
          }}
          busy={pending}
          onCancel={() => setCorrecting(false)}
          onSubmit={(v) => onCorrect(item.predictionId, v.category, v.priority, v.note)}
        />
      )}

      {!correcting && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => onConfirm(item.predictionId)} loading={pending}>
            {t("staff.review.confirm")}
          </Button>
          {!item.distress && (
            <Button variant="secondary" onClick={() => setCorrecting(true)} disabled={pending}>
              {t("staff.review.correct")}
            </Button>
          )}
        </div>
      )}
    </article>
  );
}

/**
 * The human-review queue: requests the model could not decide alone. Each item shows the
 * request, the model's best guess and why it was unsure, the explanation (collapsed), and the
 * two staff actions: confirm the guess, or correct it. A distress item can only be
 * acknowledged, because there is nothing to classify.
 */
export function ReviewQueue({ items, pendingIds, onConfirm, onCorrect }: ReviewQueueProps) {
  const t = useT();
  if (items.length === 0) return <EmptyState title={t("staff.review.empty")} hint={t("staff.review.emptyHint")} />;
  return (
    <ul aria-label={t("staff.review.title")} className="flex flex-col gap-3">
      {items.map((item) => (
        <li key={item.id}>
          <ReviewItem item={item} pending={pendingIds?.has(item.predictionId) ?? false} onConfirm={onConfirm} onCorrect={onCorrect} />
        </li>
      ))}
    </ul>
  );
}
