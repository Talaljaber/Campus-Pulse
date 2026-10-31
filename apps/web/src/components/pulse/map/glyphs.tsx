import { CATEGORY_TONE, toneColor } from "../../ui/tone";

/**
 * One small white shape per category, drawn inside the coloured dot so the category is not told
 * by colour alone (colour-blind safe, and it survives a greyscale print). Paths are centred on
 * (0,0) in a box of about 2 units; callers scale them.
 */
const PLUS = "M-.25 -.9h.5v.65h.65v.5h-.65v.65h-.5v-.65h-.65v-.5h.65z";

const GLYPHS: Record<string, { d: string; rotate?: number }> = {
  Registration: { d: "M-.7 -.7h1.4v1.4h-1.4z" }, // square
  "IT Support": { d: PLUS }, // plus
  Finance: { d: "M0 -1L.95 0 0 1 -.95 0z" }, // diamond
  Transportation: { d: "M0 -.95L1 .8h-2z" }, // triangle
  Facilities: { d: PLUS, rotate: 45 }, // cross
  "Academic Support": { d: "M-.95 -.22h1.9v.44h-1.9z" }, // bar
};

/** Props for {@link CategoryGlyph}. */
export interface CategoryGlyphProps {
  category: string;
  x: number;
  y: number;
  /** Half-width of the shape in map units. */
  size: number;
  fill?: string;
}

/** The category's shape as an SVG `<path>`, or null for an unknown category. Decorative. */
export function CategoryGlyph({ category, x, y, size, fill = "var(--cp-surface-0)" }: CategoryGlyphProps) {
  const g = GLYPHS[category];
  if (!g) return null;
  return (
    <path
      aria-hidden="true"
      d={g.d}
      fill={fill}
      transform={`translate(${x} ${y}) scale(${size})${g.rotate ? ` rotate(${g.rotate})` : ""}`}
      pointerEvents="none"
    />
  );
}

/** Props for {@link CategoryMarker}. */
export interface CategoryMarkerProps {
  category: string;
  /** Pixel size. Default 18. */
  size?: number;
}

/** A dot of the category's colour with its shape, as an inline icon for the legend. */
export function CategoryMarker({ category, size = 18 }: CategoryMarkerProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false" className="shrink-0">
      <circle cx={8} cy={8} r={7.5} fill={toneColor(CATEGORY_TONE[category] ?? "neutral")} />
      <CategoryGlyph category={category} x={8} y={8} size={4.2} />
    </svg>
  );
}
