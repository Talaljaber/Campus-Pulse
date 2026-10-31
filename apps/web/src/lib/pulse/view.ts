/** Turns the Pulse state into what the map draws: dots inside their buildings and rings over incidents. */
import type { Building } from "@/components/pulse/map/campus";
import { dotPosition } from "@/components/pulse/map/campus";
import { incidentView, type IncidentView } from "@/lib/incidents";
import type { PulseState } from "./state";

export interface MapDot {
  id: string;
  x: number;
  y: number;
  category: string;
  priority: string;
  simulated: boolean;
}

export interface MapRing {
  id: string;
  x: number;
  y: number;
  priority: string;
  reportCount: number;
}

const byCode = (buildings: readonly Building[]) => new Map(buildings.flatMap((b) => [[b.id, b] as const, [b.code, b] as const]));

/**
 * A dot per request that has a building with coordinates and known labels, placed
 * deterministically inside the footprint. A request whose labels have not arrived is not drawn yet.
 */
export function dotsOf(state: Pick<PulseState, "requests" | "labels">, buildings: readonly Building[]): MapDot[] {
  const at = byCode(buildings);
  return Object.values(state.requests).flatMap((r): MapDot[] => {
    const b = r.building_id ? at.get(r.building_id) : undefined;
    const lab = state.labels[r.id];
    if (!b || !lab?.category || !lab.priority) return [];
    const pos = dotPosition(b, r.id);
    return pos ? [{ id: r.id, ...pos, category: lab.category, priority: lab.priority, simulated: r.simulated }] : [];
  });
}

/** Rings sit above their building's centre; several incidents in one building are spread sideways. */
export function ringsOf(state: Pick<PulseState, "incidents">, buildings: readonly Building[]): MapRing[] {
  const at = byCode(buildings);
  const perBuilding = new Map<string, number>();
  return Object.values(state.incidents)
    .sort((a, b) => a.opened_at.localeCompare(b.opened_at) || a.id.localeCompare(b.id))
    .flatMap((i): MapRing[] => {
      const b = at.get(i.building_id);
      if (!b || b.map_x === null || b.map_y === null) return [];
      const n = perBuilding.get(b.id) ?? 0;
      perBuilding.set(b.id, n + 1);
      return [{ id: i.id, x: b.map_x + n * 44, y: b.map_y - 34, priority: i.priority, reportCount: i.report_count }];
    });
}

/** Open incidents as view models, newest first, optionally only one building's. */
export function openIncidents(state: Pick<PulseState, "incidents">, buildingId: string | null = null): IncidentView[] {
  return Object.values(state.incidents)
    .filter((i) => buildingId === null || i.building_id === buildingId)
    .sort((a, b) => b.opened_at.localeCompare(a.opened_at))
    .map(incidentView);
}
