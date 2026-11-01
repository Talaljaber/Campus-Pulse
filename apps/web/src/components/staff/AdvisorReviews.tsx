"use client";

import { useState } from "react";
import { labelOf, useLang, useT } from "@/i18n";
import type { ReviewItem } from "@/lib/ai/types";
import { textDir } from "../explain/text";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { cn } from "../ui/cn";
import { EmptyState } from "../ui/EmptyState";
import { InfoGrid, InfoPanel } from "../ui/InfoPanel";
import { CATEGORY_TONE, PRIORITY_TONE } from "../ui/tone";
import { ForwardForm } from "./ForwardForm";
import { officeOfCategory, useOfficeLabel } from "./office";

const LANG_KEY = { en: "advisor.lang.en", ar: "advisor.lang.ar", arabizi: "advisor.lang.arabizi" } as const;

/** Props for {@link AdvisorReviewList}. */
export interface AdvisorReviewListProps {
  items: readonly ReviewItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/**
 * The advisor's queue: one button per item with the request, the model's guess and where it
 * sits. Items assigned to the signed-in advisor carry a badge and come first (the API orders them).
 */
export function AdvisorReviewList({ items, selectedId, onSelect }: AdvisorReviewListProps) {
  const t = useT();
  const { lang } = useLang();
  const officeLabel = useOfficeLabel();
  if (items.length === 0) return <EmptyState title={t("advisor.empty")} hint={t("advisor.emptyHint")} />;
  return (
    <ul aria-label={t("advisor.listLabel")} className="flex flex-col gap-2">
      {items.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            aria-pressed={item.id === selectedId}
            onClick={() => onSelect(item.id)}
            className={cn(
              "flex w-full flex-col gap-2 rounded-lg border border-line bg-surface-1 p-3 text-start hover:border-accent",
              item.id === selectedId && "outline-2 outline-accent",
            )}
          >
            <span dir={textDir(item.text)} className="line-clamp-2 text-base font-semibold text-fg-1">
              {item.text}
            </span>
            <span className="flex flex-wrap items-center gap-2">
              <Badge tone={CATEGORY_TONE[item.category] ?? "neutral"}>{labelOf("category", item.category, lang)}</Badge>
              <Badge tone={PRIORITY_TONE[item.priority] ?? "neutral"}>{labelOf("priority", item.priority, lang)}</Badge>
              {item.assigned_to_me && <Badge tone="info">{t("advisor.mine")}</Badge>}
              {item.reason === "distress" && <Badge tone="danger">{t("advisor.distress")}</Badge>}
              {item.office && <span className="text-sm text-fg-2">{officeLabel(item.office)}</span>}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Props for {@link AdvisorReviewDetail}. */
export interface AdvisorReviewDetailProps {
  item: ReviewItem;
  busy?: boolean;
  /** A sentence for a failed forward (for example "not yours"); the form stays open. */
  error?: string | null;
  onConfirm: (item: ReviewItem) => void;
  onForward: (item: ReviewItem, office: string, note: string) => void;
  onClose: () => void;
}

/**
 * One review item in full: the student's text, the model's best guess with its conformal sets
 * (more than one label means it could not decide), why it asked a human, and the two actions.
 * A resolved item shows the outcome and no actions.
 */
export function AdvisorReviewDetail({ item, busy = false, error = null, onConfirm, onForward, onClose }: AdvisorReviewDetailProps) {
  const t = useT();
  const { lang } = useLang();
  const officeLabel = useOfficeLabel();
  const [forwarding, setForwarding] = useState(false);
  const open = item.status === "open";
  const sets = (set: readonly string[], kind: "category" | "priority") => set.map((v) => labelOf(kind, v, lang)).join(" / ");

  const reasons =
    item.reason === "distress"
      ? [t("staff.review.reasonDistress")]
      : [
          ...(item.set_cat.length > 1 ? [t("staff.review.reasonCategory", { labels: sets(item.set_cat, "category") })] : []),
          ...(item.set_pri.length > 1 ? [t("staff.review.reasonPriority", { labels: sets(item.set_pri, "priority") })] : []),
        ];
  if (reasons.length === 0) reasons.push(t("staff.review.reasonGeneric"));

  return (
    <Card
      title={t("advisor.detail")}
      actions={
        <Button variant="ghost" size="sm" onClick={onClose}>
          {t("staff.detail.close")}
        </Button>
      }
    >
      <div className="flex flex-col gap-3">
        <InfoPanel title={t("staff.detail.request")}>
          <p dir={textDir(item.text)} className="rounded-md bg-surface-1 p-3 text-base text-fg-1">
            {item.text}
          </p>
          <div className="flex flex-wrap items-center gap-2 text-sm text-fg-2">
            <Badge tone="neutral">{t(LANG_KEY[item.lang] ?? LANG_KEY.en)}</Badge>
            <span>{t("advisor.student", { alias: item.student_alias })}</span>
            {item.office && <span>{officeLabel(item.office)}</span>}
          </div>
        </InfoPanel>

        <InfoPanel title={t("advisor.reasoning")}>
          <InfoGrid
            rows={[
              {
                label: t("staff.review.bestGuess"),
                value: (
                  <span className="flex flex-wrap gap-2">
                    <Badge tone={CATEGORY_TONE[item.category] ?? "neutral"}>{labelOf("category", item.category, lang)}</Badge>
                    <Badge tone={PRIORITY_TONE[item.priority] ?? "neutral"}>{labelOf("priority", item.priority, lang)}</Badge>
                  </span>
                ),
              },
              { label: t("advisor.setCategory"), value: sets(item.set_cat, "category") || t("advisor.none") },
              { label: t("advisor.setPriority"), value: sets(item.set_pri, "priority") || t("advisor.none") },
            ]}
          />
          <ul className="flex flex-col gap-1 text-sm text-fg-2">
            {reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </InfoPanel>

        {!open && (
          <InfoPanel title={t("advisor.outcome")}>
            <p className="text-sm text-fg-1">
              {t(item.status === "confirmed" ? "advisor.confirmed" : "advisor.corrected", {
                category: labelOf("category", item.corrected_category ?? item.category, lang),
              })}
            </p>
            {item.note && (
              <p dir="auto" className="text-sm text-fg-2">
                {item.note}
              </p>
            )}
          </InfoPanel>
        )}

        {open && forwarding && (
          <ForwardForm
            initialOffice={officeOfCategory(item.category) ?? item.office ?? "academic"}
            busy={busy}
            error={error}
            onSubmit={(office, note) => onForward(item, office, note)}
            onCancel={() => setForwarding(false)}
          />
        )}

        {open && !forwarding && (
          <>
            {error && (
              <p role="alert" className="text-sm font-medium text-danger">
                {error}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              {item.reason !== "distress" && (
                <Button onClick={() => onConfirm(item)} loading={busy}>
                  {t("staff.review.confirm")}
                </Button>
              )}
              <Button variant="secondary" onClick={() => setForwarding(true)} disabled={busy}>
                {t("advisor.forward")}
              </Button>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}
