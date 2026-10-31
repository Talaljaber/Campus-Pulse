"use client";

import { labelOf, useLang, useT } from "@/i18n";
import { CATEGORY_TONE, toneColor } from "../../ui/tone";
import { DOT_RADIUS } from "./campus";
import { CategoryGlyph } from "./glyphs";

/** Props for {@link RequestDot}. */
export interface RequestDotProps {
  /** Map coordinates (0 to 1000). Use `dotPosition` to place a dot inside its building. */
  x: number;
  /** Map coordinates (0 to 600). */
  y: number;
  /** Exact backend category label. Picks the fill colour. */
  category: string;
  /** `low`, `medium` or `high`. Picks the radius (4, 6, 9) and a heavier outline for `high`. */
  priority: string;
  /** Simulated requests (demo traffic) are drawn hollow with a dashed outline. */
  simulated?: boolean;
}

/**
 * One request on the map. Category is the fill colour plus a small shape inside the dot
 * (square, plus, diamond, triangle, cross, bar; both explained by the legend), priority is the
 * size, so neither depends on colour alone.
 */
export function RequestDot({ x, y, category, priority, simulated = false }: RequestDotProps) {
  const t = useT();
  const { lang } = useLang();
  const r = DOT_RADIUS[priority] ?? DOT_RADIUS.medium!;
  const fill = toneColor(CATEGORY_TONE[category] ?? "neutral");
  const label = t(simulated ? "map.dotSimulated" : "map.dot", {
    category: labelOf("category", category, lang),
    priority: labelOf("priority", priority, lang),
  });
  return (
    <>
      <circle
        role="img"
        aria-label={label}
        data-priority={priority}
        data-simulated={simulated || undefined}
        cx={x}
        cy={y}
        r={r}
        fill={fill}
        fillOpacity={simulated ? 0.3 : 1}
        stroke={simulated ? fill : priority === "high" ? toneColor("pri-high") : "var(--cp-surface-0)"}
        strokeWidth={simulated ? 1.5 : priority === "high" ? 2.5 : 1.5}
        strokeDasharray={simulated ? "3 2" : undefined}
      >
        <title>{label}</title>
      </circle>
      <CategoryGlyph category={category} x={x} y={y} size={r * 0.52} fill={simulated ? fill : "var(--cp-surface-0)"} />
    </>
  );
}
