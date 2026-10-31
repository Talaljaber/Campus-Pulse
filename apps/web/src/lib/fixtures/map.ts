/**
 * Deterministic map stories: 20 fixture requests spread over the fictional campus and
 * the open incident from the API fixtures. Used by `/dev/ui` and the map tests.
 */
import { CATEGORY_VALUES, PRIORITY_VALUES } from "@/i18n";
import { FIXTURE_BUILDINGS, dotPosition } from "@/components/pulse/map/campus";
import { INCIDENT_FIXTURES } from "./api";

export interface FixtureDot {
  id: string;
  building: string;
  category: string;
  priority: string;
  simulated: boolean;
  x: number;
  y: number;
}

/** 20 dots. Category and priority cycle; every fourth request is simulated. */
export const FIXTURE_DOTS: readonly FixtureDot[] = Array.from({ length: 20 }, (_, i) => {
  const b = FIXTURE_BUILDINGS[(i * 3) % FIXTURE_BUILDINGS.length]!;
  const id = `fixture-request-${i}`;
  const pos = dotPosition(b, id)!;
  return {
    id,
    building: b.code,
    category: CATEGORY_VALUES[i % CATEGORY_VALUES.length]!,
    priority: PRIORITY_VALUES[(i * 2) % PRIORITY_VALUES.length]!,
    simulated: i % 4 === 3,
    ...pos,
  };
});

/** Open incidents from `incidents_open.json`, placed at their building's centre. */
export const FIXTURE_RINGS = INCIDENT_FIXTURES.flatMap((inc) => {
  const b = FIXTURE_BUILDINGS.find((x) => x.code === inc.building);
  return b && b.map_x !== null && b.map_y !== null
    ? [{ id: inc.id, x: b.map_x, y: b.map_y - 34, priority: inc.priority, reportCount: inc.report_count }]
    : [];
});
