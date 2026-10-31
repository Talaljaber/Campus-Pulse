"use client";

import { labelOf, useLang, useT } from "@/i18n";
import type { CounterfactualView } from "@/lib/ai/types";
import type { DetailView } from "@/lib/staff/detail";
import { knownFlags } from "@/lib/staff/flags";
import type { TicketView } from "@/lib/staff/tickets";
import { ExplanationPanel } from "../explain/ExplanationPanel";
import { textDir } from "../explain/text";
import { FlagBadges, isFlagVisible, type Audience } from "../chat/FlagBadges";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { InfoGrid, InfoPanel } from "../ui/InfoPanel";
import { Loadable } from "../ui/Loadable";
import { CATEGORY_TONE, PRIORITY_TONE } from "../ui/tone";

/** Props for {@link RequestDetail}. */
export interface RequestDetailProps {
  ticket: TicketView;
  /** The request and its current decision; null while loading or when it could not be read. */
  detail: DetailView | null;
  load: "loading" | "ready" | "error";
  audience: Exclude<Audience, "student">;
  counterfactual?: CounterfactualView | null;
  onCounterfactual?: (token: string) => void;
  onClose: () => void;
}

/**
 * The request behind a ticket: what the student wrote, the badges, the flags the viewer may see,
 * and the model's explanation (collapsed until asked for). Read-only: status changes live on the queue.
 */
export function RequestDetail({ ticket, detail, load, audience, counterfactual, onCounterfactual, onClose }: RequestDetailProps) {
  const t = useT();
  const { lang } = useLang();
  const p = detail?.prediction ?? null;
  return (
    <Card
      title={t("staff.detail.title")}
      actions={
        <Button variant="ghost" size="sm" onClick={onClose}>
          {t("staff.detail.close")}
        </Button>
      }
    >
      <div className="flex flex-col gap-3">
        <p dir="auto" className="text-base font-semibold text-fg-1">
          {ticket.title}
        </p>
        <Loadable state={load} lines={3}>
          {detail && (
            <>
              <InfoPanel title={t("staff.detail.request")}>
                <p dir={textDir(detail.text)} className="rounded-md bg-surface-1 p-3 text-base text-fg-1">
                  {detail.text}
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  {detail.simulated && <Badge tone="info">{t("staff.detail.simulated")}</Badge>}
                  {detail.inputMode === "voice" && <Badge tone="neutral">{t("staff.detail.voice")}</Badge>}
                  {detail.buildingId && <span className="text-sm text-fg-2">{t("staff.detail.building", { code: detail.buildingId })}</span>}
                  {detail.room && <span className="text-sm text-fg-2">{t("staff.detail.room", { room: detail.room })}</span>}
                </div>
              </InfoPanel>
              <InfoPanel title={t("staff.detail.decision")}>
                {p ? (
                  <InfoGrid
                    rows={[
                      ...(p.category
                        ? [{ label: t("staff.detail.category"), value: <Badge tone={CATEGORY_TONE[p.category] ?? "neutral"}>{labelOf("category", p.category, lang)}</Badge> }]
                        : []),
                      ...(p.priority
                        ? [{ label: t("staff.detail.priority"), value: <Badge tone={PRIORITY_TONE[p.priority] ?? "neutral"}>{labelOf("priority", p.priority, lang)}</Badge> }]
                        : []),
                      ...(knownFlags(p.flags).some((f) => isFlagVisible(f, audience))
                        ? [{ label: t("staff.detail.flags"), value: <FlagBadges flags={knownFlags(p.flags)} audience={audience} /> }]
                        : []),
                    ]}
                  />
                ) : (
                  <p className="text-sm text-fg-2">{t("staff.detail.noDecision")}</p>
                )}
              </InfoPanel>
              {p?.explanation && (
                <details className="rounded-md border border-line bg-surface-0 p-3">
                  <summary className="cursor-pointer text-sm font-medium text-fg-1">{t("staff.detail.explanation")}</summary>
                  <div className="mt-3">
                    <ExplanationPanel
                      explanation={p.explanation}
                      text={detail.text}
                      evidence={p.evidence}
                      tier={p.tier}
                      counterfactual={counterfactual}
                      onCounterfactual={onCounterfactual}
                    />
                  </div>
                </details>
              )}
            </>
          )}
        </Loadable>
      </div>
    </Card>
  );
}
