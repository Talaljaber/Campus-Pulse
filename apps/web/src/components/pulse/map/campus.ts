/**
 * Geometry of the fictional campus map. Nothing here is a real campus layout.
 *
 * Convention (same as the DB seed, docs/db/schema.md `buildings.map_x/map_y`):
 * - one coordinate space of 1000 x 600 user units, origin at the top-left, x grows
 *   to the right and y grows downward;
 * - `map_x`/`map_y` is the CENTRE of the building footprint;
 * - the map is never mirrored in right-to-left languages. Only labels and legends are.
 */

/** A building as stored in the `buildings` table (`map_x`/`map_y` are nullable there). */
export interface Building {
  id: string;
  code: string;
  name_en: string;
  name_ar: string;
  map_x: number | null;
  map_y: number | null;
}

export const MAP_WIDTH = 1000;
export const MAP_HEIGHT = 600;

/** Footprint size in map units, by building code. Unknown codes use {@link DEFAULT_FOOTPRINT}. */
export const FOOTPRINTS: Record<string, { w: number; h: number }> = {
  A: { w: 150, h: 84 },
  B: { w: 130, h: 76 },
  C: { w: 140, h: 76 },
  D: { w: 130, h: 76 },
  E: { w: 120, h: 110 },
  F: { w: 120, h: 110 },
  G: { w: 150, h: 80 },
  H: { w: 140, h: 80 },
  K: { w: 130, h: 80 },
  L: { w: 120, h: 110 },
  M: { w: 120, h: 90 },
};
export const DEFAULT_FOOTPRINT = { w: 120, h: 80 } as const;

export function footprintOf(code: string): { w: number; h: number } {
  return FOOTPRINTS[code] ?? DEFAULT_FOOTPRINT;
}

/** Decorative ground: roads (stroked) and the central quad (filled). */
export const ROADS: readonly string[] = [
  // inner ring road around the quad
  "M 250 190 H 750 Q 790 190 790 230 V 370 Q 790 410 750 410 H 250 Q 210 410 210 370 V 230 Q 210 190 250 190 Z",
  // north and south avenues
  "M 60 182 H 940",
  "M 60 440 H 940",
  // connectors from the ring to the east and west blocks
  "M 790 300 H 820",
  "M 180 300 H 210",
];
export const QUAD = { cx: 500, cy: 300, rx: 190, ry: 80 } as const;

/**
 * The fictional campus used by `/dev/ui` and the tests until the DB seed exists.
 * Letters A to M without I and J. Only L (the library) has a name; the others are letters only.
 */
export const FIXTURE_BUILDINGS: readonly Building[] = [
  { id: "A", code: "A", name_en: "", name_ar: "", map_x: 140, map_y: 100 },
  { id: "B", code: "B", name_en: "", name_ar: "", map_x: 330, map_y: 95 },
  { id: "C", code: "C", name_en: "", name_ar: "", map_x: 520, map_y: 95 },
  { id: "D", code: "D", name_en: "", name_ar: "", map_x: 720, map_y: 95 },
  { id: "E", code: "E", name_en: "", name_ar: "", map_x: 880, map_y: 250 },
  { id: "F", code: "F", name_en: "", name_ar: "", map_x: 880, map_y: 380 },
  { id: "G", code: "G", name_en: "", name_ar: "", map_x: 700, map_y: 520 },
  { id: "H", code: "H", name_en: "", name_ar: "", map_x: 500, map_y: 520 },
  { id: "K", code: "K", name_en: "", name_ar: "", map_x: 300, map_y: 520 },
  { id: "L", code: "L", name_en: "Library", name_ar: "المكتبة", map_x: 110, map_y: 390 },
  { id: "M", code: "M", name_en: "", name_ar: "", map_x: 110, map_y: 250 },
];

/** The building's name in the UI language; "" when it has none (only L, the library, is named). */
export function buildingName(b: Pick<Building, "name_en" | "name_ar">, lang: "en" | "ar"): string {
  return (lang === "ar" ? b.name_ar : b.name_en).trim();
}

/** Removes the separator an empty `{name}` leaves in "Building {code}, {name}": "Building M, " -> "Building M". */
export function tidyLabel(s: string): string {
  return s.replace(/\s*[,،]\s*(?=$|[,،])/g, "").trim();
}

/** FNV-1a, 32 bit. Stable across runs and platforms. */
export function hash32(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

/**
 * Where to draw a request's dot: the building centre plus a deterministic offset
 * derived from the request id, kept inside the footprint with a margin. The same id
 * always lands on the same spot, so dots do not jump between renders.
 * Returns `null` when the building has no coordinates.
 */
export function dotPosition(b: Pick<Building, "code" | "map_x" | "map_y">, requestId: string): { x: number; y: number } | null {
  if (b.map_x === null || b.map_y === null) return null;
  const { w, h } = footprintOf(b.code);
  const hx = hash32(`${requestId}:x`) / 0xffffffff;
  const hy = hash32(`${requestId}:y`) / 0xffffffff;
  const margin = 12;
  return {
    x: b.map_x + (hx - 0.5) * (w - 2 * margin),
    y: b.map_y + (hy - 0.5) * (h - 2 * margin),
  };
}

/** Dot radius by priority: low 4, medium 6, high 9. */
export const DOT_RADIUS: Record<string, number> = { low: 4, medium: 6, high: 9 };
