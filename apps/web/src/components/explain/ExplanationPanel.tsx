"use client";

import { useId, useState } from "react";
import { labelOf, useLang, useT, type DictKey } from "@/i18n";
import type { CounterfactualView, Evidence, Explanation, Neighbor, Tier } from "@/lib/ai/types";
import { Badge } from "../ui/Badge";
import { CATEGORY_TONE, PRIORITY_TONE } from "../ui/tone";
import { cn } from "../ui/cn";
import { CounterfactualHint } from "./CounterfactualHint";
import { EvidenceText } from "./EvidenceText";
import { humanize, textDir } from "./text";
import { useNow } from "./useNow";

/** Props for {@link ExplanationPanel}. */
export interface ExplanationPanelProps {
  /** `result.explanation`. */
  explanation: Explanation;
  /** The request text. When given, top words are highlighted inside it; otherwise they are listed as chips. */
  text?: string;
  /** `result.priority.evidence`, shown as "urgency signals" and underlined in `text`. */
  evidence?: readonly Evidence[];
  /** A word was chosen for a counterfactual (from the text, the chips or the hint button). */
  onCounterfactual?: (token: string) => void;
  /** The live counterfactual answer, once the parent has fetched it. */
  counterfactual?: CounterfactualView | null;
  /** `result.tier`, shown first in the trace line. */
  tier?: Tier;
  /** Clock for "learned N s ago" in epoch ms. Defaults to the real time, read after mount. */
  now?: number;
  className?: string;
}

const EVIDENCE_KEYS: Record<string, DictKey> = {
  deadline_today: "explain.evidenceType.deadline_today",
  exam_now: "explain.evidenceType.exam_now",
  safety_risk: "explain.evidenceType.safety_risk",
  info_request: "explain.evidenceType.info_request",
  fault_report: "explain.evidenceType.fault_report",
  transient_glitch: "explain.evidenceType.transient_glitch",
  enrollment_blocked: "explain.evidenceType.enrollment_blocked",
};

const SOURCE_KEYS: Record<Neighbor["source"], DictKey> = {
  train: "explain.source.train",
  augmented: "explain.source.augmented",
  memory: "explain.source.memory",
};

const TIER_KEYS = {
  tier0: "explain.tier.tier0",
  tier1: "explain.tier.tier1",
  tier2: "explain.tier.tier2",
  human: "explain.tier.human",
} as const satisfies Record<string, DictKey>;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-2">
      <h4 id={id} className="text-sm font-semibold text-fg-1">
        {title}
      </h4>
      {children}
    </section>
  );
}

/**
 * Everything the model can say about why it decided: highlighted words, urgency
 * signals, similar past requests (with "learned from a staff correction N s ago" for
 * live memory), the counterfactual and a one-line trace. Formatting only; the parent
 * owns the counterfactual request and passes the answer back.
 */
export function ExplanationPanel({
  explanation,
  text,
  evidence,
  onCounterfactual,
  counterfactual,
  tier,
  now,
  className,
}: ExplanationPanelProps) {
  const t = useT();
  const { lang } = useLang();
  const [picked, setPicked] = useState<string | undefined>();
  const clock = useNow(now);

  const active = counterfactual?.drop ?? picked;
  const pick = onCounterfactual
    ? (token: string) => {
        setPicked(token);
        onCounterfactual(token);
      }
    : undefined;
  const maxWeight = Math.max(0, ...explanation.top_tokens.map(([, w]) => w));

  const ago = (iso: string | null): string | null => {
    if (!iso || clock === null) return null;
    const secs = Math.max(0, Math.round((clock - new Date(iso).getTime()) / 1000));
    if (secs < 60) return t("explain.ago.seconds", { n: secs });
    if (secs < 3600) return t("explain.ago.minutes", { n: Math.round(secs / 60) });
    if (secs < 86400) return t("explain.ago.hours", { n: Math.round(secs / 3600) });
    return t("explain.ago.days", { n: Math.round(secs / 86400) });
  };

  const { trace } = explanation;
  const traceItems = [
    ...(tier ? [t(TIER_KEYS[tier])] : []),
    t("explain.traceSets", { cat: trace.sets.cat, pri: trace.sets.pri }),
    t("explain.traceCost", { cost: trace.cost_usd === 0 ? "0" : trace.cost_usd.toFixed(5) }),
    t("explain.traceLatency", { ms: trace.latency_ms }),
    t("explain.traceArtifact", { version: trace.artifact_version }),
    ...(trace.clarified ? [t("explain.traceClarified")] : []),
  ];

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      <h3 className="text-md font-semibold text-fg-1">{t("explain.why")}</h3>

      <Section title={t("explain.tokensTitle")}>
        {text ? (
          <EvidenceText
            text={text}
            tokens={explanation.top_tokens}
            evidence={evidence}
            onTokenClick={pick}
            activeToken={active}
          />
        ) : (
          <ul className="flex flex-wrap gap-2">
            {explanation.top_tokens.map(([token, w]) => {
              const body = (
                <>
                  <span dir="auto">{token}</span>
                  <span dir="ltr" className="text-xs tabular-nums text-fg-2">
                    {Math.round(w * 100)}%
                  </span>
                  <span aria-hidden className="block h-1 w-full rounded-full bg-surface-2">
                    <span
                      className="block h-full rounded-full bg-accent"
                      style={{ inlineSize: `${maxWeight > 0 ? (w / maxWeight) * 100 : 0}%` }}
                    />
                  </span>
                </>
              );
              const cls = "flex min-w-20 flex-col items-start gap-1 rounded-md border border-line px-3 py-1.5 text-sm text-fg-1";
              return (
                <li key={token}>
                  {pick ? (
                    <button
                      type="button"
                      aria-pressed={active?.toLowerCase() === token.toLowerCase()}
                      aria-label={t("explain.tokenAria", { token, pct: Math.round(w * 100) })}
                      onClick={() => pick(token)}
                      className={cn(cls, "min-h-11 cursor-pointer hover:bg-surface-2 aria-pressed:border-accent aria-pressed:border-2")}
                    >
                      {body}
                    </button>
                  ) : (
                    <div className={cls}>{body}</div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {pick && <p className="text-xs text-fg-3">{t("explain.tokensHint")}</p>}
      </Section>

      {evidence !== undefined && (
        <Section title={t("explain.evidenceTitle")}>
          {evidence.length === 0 ? (
            <p className="text-sm text-fg-2">{t("explain.evidenceNone")}</p>
          ) : (
            <ul className="flex flex-col gap-1 text-sm">
              {evidence.map((ev, i) => (
                <li key={`${ev.type}-${i}`} className="flex flex-wrap items-baseline gap-2">
                  <Badge tone="warn">{EVIDENCE_KEYS[ev.type] ? t(EVIDENCE_KEYS[ev.type]!) : humanize(ev.type)}</Badge>
                  <q dir={textDir(ev.span)} className="text-fg-2">
                    {ev.span}
                  </q>
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}

      <CounterfactualHint hint={explanation.counterfactual} view={counterfactual} onCounterfactual={pick} />

      <Section title={t("explain.neighborsTitle")}>
        {explanation.neighbors.length === 0 ? (
          <p className="text-sm text-fg-2">{t("explain.neighborsNone")}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {explanation.neighbors.map((n, i) => {
              const when = n.source === "memory" ? ago(n.created_at) : null;
              return (
                <li key={`${n.text}-${i}`} className="flex flex-col gap-1 rounded-md border border-line bg-surface-0 p-3">
                  <p dir={textDir(n.text)} className="text-sm text-fg-1">
                    {n.text}
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={CATEGORY_TONE[n.label] ?? "neutral"}>{labelOf("category", n.label, lang)}</Badge>
                    <Badge tone={PRIORITY_TONE[n.priority] ?? "neutral"}>{labelOf("priority", n.priority, lang)}</Badge>
                    <span className="text-xs text-fg-2">{t("explain.neighborSim", { pct: Math.round(n.sim * 100) })}</span>
                    <span className="text-xs text-fg-3">{t(SOURCE_KEYS[n.source])}</span>
                  </div>
                  {n.source === "memory" && (
                    <p className="text-xs font-medium text-fg-1" data-memory>
                      {when ? t("explain.learnedAgo", { ago: when }) : t("explain.learned")}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Section title={t("explain.traceTitle")}>
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-3">
          {traceItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
