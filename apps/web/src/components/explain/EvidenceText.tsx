"use client";

import { useMemo, type CSSProperties } from "react";
import { useT } from "@/i18n";
import type { Evidence, TopToken } from "@/lib/ai/types";
import { cn } from "../ui/cn";
import { segmentText, textDir } from "./text";

/** Props for {@link EvidenceText}. */
export interface EvidenceTextProps {
  /** The request text exactly as the student wrote it. */
  text: string;
  /** `explanation.top_tokens`: `[token, weight]` pairs. Heavier words get a stronger highlight. */
  tokens: readonly TopToken[];
  /** `priority.evidence`: spans that justify the priority. They are underlined. */
  evidence?: readonly Evidence[];
  /** Makes every highlighted word a button. Receives the canonical token (as the API returned it). */
  onTokenClick?: (token: string) => void;
  /** The token currently being tested (counterfactual). Marked with `aria-pressed`. */
  activeToken?: string;
  className?: string;
}

const MAX_MIX = 40; // percent of accent colour at the heaviest weight; keeps text >= 4.5:1 in both themes

/**
 * The request text with the words that mattered highlighted (opacity follows the
 * weight) and the urgency evidence underlined. Highlighted words are real
 * `<button>`s when `onTokenClick` is given, so keyboard users can reach them.
 * The text direction follows the text itself, not the page.
 */
export function EvidenceText({ text, tokens, evidence = [], onTokenClick, activeToken, className }: EvidenceTextProps) {
  const t = useT();
  const segments = useMemo(() => segmentText(text, tokens, evidence), [text, tokens, evidence]);
  const active = activeToken?.toLowerCase();

  return (
    <p dir={textDir(text)} className={cn("text-md leading-loose text-fg-1", className)}>
      {segments.map((seg, i) => {
        const underline = seg.evidence.length > 0;
        const evidenceAttr = underline ? seg.evidence.join(" ") : undefined;
        const underlineClass = underline && "underline decoration-2 underline-offset-4 decoration-(--cp-warn)";
        if (!seg.token || seg.strength === undefined) {
          return underline ? (
            <span key={i} data-evidence={evidenceAttr} className={cn(underlineClass)}>
              {seg.text}
            </span>
          ) : (
            seg.text
          );
        }
        const mix = Math.round(10 + (MAX_MIX - 10) * seg.strength);
        const style = {
          backgroundColor: `color-mix(in srgb, var(--cp-accent) ${mix}%, transparent)`,
        } as CSSProperties;
        const common = {
          "data-token": seg.token,
          "data-evidence": evidenceAttr,
          style,
          className: cn("rounded-sm px-0.5 text-inherit", underlineClass),
        };
        if (!onTokenClick) return <mark key={i} {...common}>{seg.text}</mark>;
        const isActive = active === seg.token.toLowerCase();
        const weight = tokens.find(([tk]) => tk === seg.token)?.[1] ?? 0;
        return (
          <button
            key={i}
            type="button"
            {...common}
            aria-pressed={isActive}
            aria-label={t("explain.tokenAria", { token: seg.text, pct: Math.round(weight * 100) })}
            onClick={() => onTokenClick(seg.token!)}
            className={cn(
              common.className,
              "cursor-pointer align-baseline hover:brightness-95",
              isActive && "outline-2 outline-offset-1 outline-(--cp-accent)",
            )}
          >
            {seg.text}
          </button>
        );
      })}
    </p>
  );
}
