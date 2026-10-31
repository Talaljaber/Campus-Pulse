"use client";

import { useId, type ReactNode } from "react";
import { useT } from "@/i18n";
import { cn } from "../../ui/cn";
import { BuildingShape } from "./BuildingShape";
import { MAP_HEIGHT, MAP_WIDTH, QUAD, ROADS, type Building } from "./campus";

/** Props for {@link CampusMap}. */
export interface CampusMapProps {
  /** Rows of the `buildings` table. Buildings without `map_x`/`map_y` are skipped. */
  buildings: readonly Building[];
  /** Overlay layer in map coordinates: `RequestDot`s and `IncidentRing`s. Drawn above the buildings. */
  children?: ReactNode;
  /** Makes buildings focusable buttons (Enter or Space). */
  onBuildingClick?: (id: string) => void;
  /** Id of the selected building. */
  selected?: string;
  className?: string;
}

// `dir` is a valid attribute on SVG but missing from React's SVG prop types.
const LTR = { dir: "ltr" } as object;

/**
 * Hand-built SVG of a fictional campus (viewBox 0 0 1000 600, no map library).
 *
 * Accessibility: with no click handler the map is one `role="img"` with a title and a
 * description. With `onBuildingClick` it is a `role="group"` instead, because an
 * image role would hide the building buttons from assistive technology.
 *
 * Direction: the SVG is pinned to `dir="ltr"`, so the geometry is identical in English
 * and Arabic. Only the building names (and the legend, outside the SVG) follow the language.
 */
export function CampusMap({ buildings, children, onBuildingClick, selected, className }: CampusMapProps) {
  const t = useT();
  const uid = useId();
  const drawn = buildings.filter((b) => b.map_x !== null && b.map_y !== null);
  return (
    <svg
      viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
      {...LTR}
      role={onBuildingClick ? "group" : "img"}
      aria-labelledby={`${uid}-t`}
      aria-describedby={`${uid}-d`}
      preserveAspectRatio="xMidYMid meet"
      className={cn("block h-auto w-full rounded-lg border border-line bg-surface-0", className)}
    >
      <title id={`${uid}-t`}>{t("map.label")}</title>
      <desc id={`${uid}-d`}>{t("map.description", { count: drawn.length })}</desc>

      <g aria-hidden="true">
        <ellipse
          cx={QUAD.cx}
          cy={QUAD.cy}
          rx={QUAD.rx}
          ry={QUAD.ry}
          fill="color-mix(in srgb, var(--cp-ok) 14%, var(--cp-surface-0))"
          stroke="var(--cp-border)"
          strokeWidth={2}
        />
        {ROADS.map((d) => (
          <path key={d} d={d} fill="none" stroke="var(--cp-border)" strokeWidth={14} strokeLinecap="round" strokeLinejoin="round" />
        ))}
      </g>

      <g>
        {drawn.map((b) => (
          <BuildingShape key={b.id} b={b} selected={b.id === selected} onSelect={onBuildingClick} />
        ))}
      </g>

      <g>{children}</g>
    </svg>
  );
}
