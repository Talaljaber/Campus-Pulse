"use client";

import type { KeyboardEvent } from "react";
import { useLang, useT } from "@/i18n";
import { footprintOf, type Building } from "./campus";

/** Props for {@link BuildingShape}. */
export interface BuildingShapeProps {
  b: Building;
  selected?: boolean;
  /** Makes the building a focusable button. Given by `CampusMap` when it has `onBuildingClick`. */
  onSelect?: (id: string) => void;
}

/**
 * One building footprint with its letter and name. Position comes from the DB
 * (`map_x`/`map_y` = centre); the size from `campus.ts`. The name follows the UI
 * language. The shape itself never flips in right-to-left.
 * Renders nothing when the building has no coordinates.
 */
export function BuildingShape({ b, selected = false, onSelect }: BuildingShapeProps) {
  const t = useT();
  const { lang } = useLang();
  if (b.map_x === null || b.map_y === null) return null;
  const { w, h } = footprintOf(b.code);
  const name = lang === "ar" ? b.name_ar : b.name_en;
  const label = t(selected ? "map.buildingSelected" : "map.building", { code: b.code, name });
  const x = b.map_x - w / 2;
  const y = b.map_y - h / 2;

  const interactive = onSelect
    ? {
        role: "button" as const,
        tabIndex: 0,
        "aria-pressed": selected,
        onClick: () => onSelect(b.id),
        onKeyDown: (e: KeyboardEvent<SVGGElement>) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect(b.id);
          }
        },
      }
    : { role: "img" as const };

  return (
    <g
      data-building={b.code}
      aria-label={label}
      className={onSelect ? "group cursor-pointer outline-none" : undefined}
      {...interactive}
    >
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={8}
        className={
          selected
            ? "fill-[color-mix(in_srgb,var(--cp-accent)_22%,var(--cp-surface-1))] stroke-accent"
            : "fill-surface-1 stroke-line-strong group-hover:fill-surface-2"
        }
        strokeWidth={selected ? 4 : 2}
      />
      {onSelect && (
        <rect
          x={x - 5}
          y={y - 5}
          width={w + 10}
          height={h + 10}
          rx={12}
          fill="none"
          strokeWidth={3}
          strokeDasharray="6 4"
          className="stroke-focus opacity-0 group-focus-visible:opacity-100"
        />
      )}
      <g aria-hidden="true" style={{ direction: lang === "ar" ? "rtl" : "ltr" }}>
        <text
          x={b.map_x}
          y={b.map_y - 4}
          textAnchor="middle"
          fontSize={24}
          fontWeight={700}
          className="fill-fg-1"
        >
          {b.code}
        </text>
        <text x={b.map_x} y={b.map_y + 16} textAnchor="middle" fontSize={12} className="fill-fg-2">
          {name}
        </text>
      </g>
    </g>
  );
}
