"use client";

import { cn } from "../ui/cn";
import type { IconName } from "../ui/Icon";
import { IconTile } from "../ui/IconTile";

/** One tile of a {@link TileRow}. */
export interface TileSpec {
  id: string;
  icon: IconName;
  label: string;
  href: string;
  hint?: string;
  /** Marks the tile for the current page (`aria-current="page"`). */
  selected?: boolean;
}

/** Props for {@link TileRow}. */
export interface TileRowProps {
  tiles: TileSpec[];
  /** Accessible name of the list. */
  label?: string;
  className?: string;
}

/** Row of icon tiles (sub-areas or shortcuts) under the tab bar. Renders nothing for an empty list. */
export function TileRow({ tiles, label, className }: TileRowProps) {
  if (tiles.length === 0) return null;
  return (
    <ul aria-label={label} className={cn("grid gap-3 sm:grid-cols-2 lg:grid-cols-3", className)}>
      {tiles.map((tile) => (
        <li key={tile.id}>
          <IconTile icon={tile.icon} label={tile.label} hint={tile.hint} href={tile.href} selected={tile.selected} />
        </li>
      ))}
    </ul>
  );
}
