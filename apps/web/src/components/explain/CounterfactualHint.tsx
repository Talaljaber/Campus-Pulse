"use client";

import { labelOf, useLang, useT } from "@/i18n";
import type { CounterfactualHint as Hint, CounterfactualView } from "@/lib/ai/types";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";

/** Props for {@link CounterfactualHint}. */
export interface CounterfactualHintProps {
  /** `explanation.counterfactual`: the precomputed "if this word were gone" hint, or `null`. */
  hint: Hint | null;
  /** The live answer of the counterfactual endpoint after a click, or `null`/`undefined` before. */
  view?: CounterfactualView | null;
  /** Called with the word to drop when the student presses the "try without" button. */
  onCounterfactual?: (token: string) => void;
  className?: string;
}

/**
 * "What if..." block. Shows the hint from the triage response with a button that asks
 * the parent to run the real counterfactual, and (in a polite live region) the result
 * once the parent passes it back. No fetching happens here.
 */
export function CounterfactualHint({ hint, view, onCounterfactual, className }: CounterfactualHintProps) {
  const t = useT();
  const { lang } = useLang();
  if (!hint && !view) return null;
  const cat = (v: string) => labelOf("category", v, lang);
  const pri = (v: string) => labelOf("priority", v, lang);

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <h5 className="text-sm font-semibold text-fg-1">{t("explain.cf.title")}</h5>
      {hint && (
        <>
          <p className="text-sm text-fg-2">
            {t("explain.cf.hint", { drop: hint.drop, category: cat(hint.category), priority: pri(hint.priority) })}
          </p>
          {onCounterfactual && (
            <div>
              <Button size="sm" variant="secondary" onClick={() => onCounterfactual(hint.drop)}>
                {t("explain.cf.try", { drop: hint.drop })}
              </Button>
            </div>
          )}
        </>
      )}
      <div role="status" aria-live="polite" className="flex flex-col gap-1 text-sm">
        {view && (
          <>
            <p className="text-fg-2">
              {t("explain.cf.from", { category: cat(view.original_category), priority: pri(view.original_priority) })}
            </p>
            <p className="text-fg-1">
              {t("explain.cf.result", {
                drop: view.drop,
                category: cat(view.category),
                catProb: Math.round(view.category_prob * 100),
                priority: pri(view.priority),
                priProb: Math.round(view.priority_prob * 100),
              })}
            </p>
            <div>
              <Badge tone={view.flipped ? "warn" : "ok"}>
                {view.flipped ? t("explain.cf.flipped") : t("explain.cf.unchanged")}
              </Badge>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
