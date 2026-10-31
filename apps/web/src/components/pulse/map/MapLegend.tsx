"use client";

import { CATEGORY_VALUES, PRIORITY_VALUES, labelOf, useLang, useT } from "@/i18n";
import { cn } from "../../ui/cn";
import { CATEGORY_TONE, toneColor } from "../../ui/tone";
import { DOT_RADIUS } from "./campus";

/** Props for {@link MapLegend}. */
export interface MapLegendProps {
  className?: string;
}

/**
 * Legend for the map. It is plain HTML next to the SVG, so it follows the page
 * direction (mirrored in Arabic) while the map itself stays fixed.
 */
export function MapLegend({ className }: MapLegendProps) {
  const t = useT();
  const { lang } = useLang();
  return (
    <section aria-label={t("map.legendTitle")} className={cn("flex flex-col gap-3 text-sm text-fg-2", className)}>
      <div className="flex flex-col gap-1.5">
        <p className="font-medium text-fg-1">{t("map.legendCategory")}</p>
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          {CATEGORY_VALUES.map((c) => (
            <li key={c} className="flex items-center gap-1.5">
              <span aria-hidden className="size-3 rounded-full" style={{ background: toneColor(CATEGORY_TONE[c] ?? "neutral") }} />
              {labelOf("category", c, lang)}
            </li>
          ))}
        </ul>
      </div>
      <div className="flex flex-col gap-1.5">
        <p className="font-medium text-fg-1">{t("map.legendPriority")}</p>
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          {PRIORITY_VALUES.map((p) => (
            <li key={p} className="flex items-center gap-1.5">
              <span
                aria-hidden
                className="rounded-full bg-fg-3"
                style={{ inlineSize: DOT_RADIUS[p]! * 2, blockSize: DOT_RADIUS[p]! * 2 }}
              />
              {labelOf("priority", p, lang)}
            </li>
          ))}
        </ul>
      </div>
      <ul className="flex flex-col gap-1">
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="size-3 rounded-full border-2 border-dashed border-fg-3" />
          {t("map.legendSimulated")}
        </li>
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="size-4 rounded-full border-[3px] border-danger" />
          {t("map.legendIncident")}
        </li>
      </ul>
      <p className="text-xs text-fg-3">{t("map.fictional")}</p>
    </section>
  );
}
