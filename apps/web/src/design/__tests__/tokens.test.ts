import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(__dirname, "..", "tokens.css"), "utf8");

type Vars = Record<string, string>;

function declsOf(block: string): Vars {
  const out: Vars = {};
  for (const m of block.matchAll(/(--cp-[\w-]+)\s*:\s*([^;]+);/g)) out[m[1]!] = m[2]!.trim();
  return out;
}

/** Body of the first rule whose selector matches `selector` (brace-balanced). */
function blockOf(selector: string): string {
  const start = css.indexOf(selector);
  if (start < 0) throw new Error(`selector not found: ${selector}`);
  const open = css.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === "{") depth++;
    if (css[i] === "}" && --depth === 0) return css.slice(open + 1, i);
  }
  throw new Error("unbalanced");
}

const light = declsOf(blockOf(":root {"));
const darkMedia = declsOf(blockOf(':root:not([data-theme="light"])'));
const darkForced = declsOf(blockOf(':root[data-theme="dark"]'));
const dark: Vars = { ...light, ...darkMedia };

function rgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
}
function lum([r, g, b]: [number, number, number]): number {
  const f = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
function contrast(a: [number, number, number], b: [number, number, number]): number {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}
function mix(fg: [number, number, number], bg: [number, number, number], pct: number): [number, number, number] {
  return fg.map((c, i) => Math.round(c * pct + bg[i]! * (1 - pct))) as [number, number, number];
}

const SURFACES = ["--cp-surface-0", "--cp-surface-1", "--cp-surface-2"];
const TEXTS = ["--cp-text-1", "--cp-text-2", "--cp-text-3"];
const TONES = [
  "--cp-cat-registration",
  "--cp-cat-it",
  "--cp-cat-finance",
  "--cp-cat-transport",
  "--cp-cat-facilities",
  "--cp-cat-academic",
  "--cp-pri-low",
  "--cp-pri-medium",
  "--cp-pri-high",
  "--cp-ok",
  "--cp-warn",
  "--cp-danger",
  "--cp-info",
];

describe.each([
  ["light", light],
  ["dark", dark],
])("%s theme", (_name, v) => {
  it("text tokens reach 4.5:1 on every surface", () => {
    for (const t of TEXTS)
      for (const s of SURFACES) expect(contrast(rgb(v[t]!), rgb(v[s]!)), `${t} on ${s}`).toBeGreaterThanOrEqual(4.5);
  });

  it("tone colours reach 3:1 on every surface", () => {
    for (const t of [...TONES, "--cp-focus", "--cp-border-strong"])
      for (const s of SURFACES) expect(contrast(rgb(v[t]!), rgb(v[s]!)), `${t} on ${s}`).toBeGreaterThanOrEqual(3);
  });

  it("primary text is readable on a 16% tint of every tone (badges)", () => {
    for (const t of TONES)
      for (const s of SURFACES) {
        const tint = mix(rgb(v[t]!), rgb(v[s]!), 0.16);
        expect(contrast(rgb(v["--cp-text-1"]!), tint), `${t} tint on ${s}`).toBeGreaterThanOrEqual(4.5);
      }
  });

  it("accent button text is readable", () => {
    expect(contrast(rgb(v["--cp-on-accent"]!), rgb(v["--cp-accent"]!))).toBeGreaterThanOrEqual(4.5);
  });
});

/**
 * Named foreground/background pairs of the GJU-style shell (UI batch 6). Each is checked in both
 * themes against its WCAG 2.2 AA minimum: 4.5 for text, 3 for large text, icons and borders.
 * Orange itself is decorative; the pairs below are the only ways orange appears with text.
 */
const PAIRS: { name: string; fg: string; bg: string; min: number }[] = [
  { name: "white text on the top band", fg: "--cp-on-band", bg: "--cp-band", min: 4.5 },
  { name: "white text on the icon bar", fg: "--cp-on-band", bg: "--cp-band-2", min: 4.5 },
  { name: "nav link (accent) on the page card", fg: "--cp-accent", bg: "--cp-surface-0", min: 4.5 },
  { name: "nav link (accent) on the inactive tab", fg: "--cp-accent", bg: "--cp-surface-2", min: 4.5 },
  { name: "nav link (accent) on a panel", fg: "--cp-accent", bg: "--cp-surface-1", min: 4.5 },
  { name: "active tab text (accent) on the card", fg: "--cp-accent", bg: "--cp-surface-0", min: 4.5 },
  { name: "inactive tab text on its grey", fg: "--cp-text-1", bg: "--cp-surface-2", min: 4.5 },
  { name: "heading grey on the card", fg: "--cp-heading", bg: "--cp-surface-0", min: 4.5 },
  { name: "heading grey on a panel", fg: "--cp-heading", bg: "--cp-surface-1", min: 4.5 },
  { name: "heading grey on the inactive tab grey", fg: "--cp-heading", bg: "--cp-surface-2", min: 4.5 },
  { name: "heading grey on the page background", fg: "--cp-heading", bg: "--cp-page", min: 4.5 },
  { name: "body text on the page background", fg: "--cp-text-1", bg: "--cp-page", min: 4.5 },
  { name: "muted text on the page background", fg: "--cp-text-3", bg: "--cp-page", min: 4.5 },
  { name: "white caption on the grey-blue panel band", fg: "--cp-on-panel", bg: "--cp-panel", min: 4.5 },
  { name: "dark text on orange (badges, highlights)", fg: "--cp-on-orange", bg: "--cp-orange", min: 4.5 },
  { name: "orange ink (large text, icons) on the card", fg: "--cp-orange-ink", bg: "--cp-surface-0", min: 3 },
  { name: "orange ink (large text, icons) on a panel", fg: "--cp-orange-ink", bg: "--cp-surface-1", min: 3 },
  { name: "brand blue (graphics) on the card", fg: "--cp-brand", bg: "--cp-surface-0", min: 3 },
  { name: "footer text on the footer", fg: "--cp-on-footer", bg: "--cp-footer", min: 4.5 },
  { name: "footer link on the footer", fg: "--cp-footer-link", bg: "--cp-footer", min: 4.5 },
  { name: "focus ring on the card", fg: "--cp-focus", bg: "--cp-surface-0", min: 3 },
  { name: "focus ring on the top band", fg: "--cp-on-band", bg: "--cp-band", min: 3 },
];

describe.each([
  ["light", light],
  ["dark", dark],
])("%s shell pairs", (_name, v) => {
  it.each(PAIRS)("$name reaches its AA minimum", ({ fg, bg, min }) => {
    expect(contrast(rgb(v[fg]!), rgb(v[bg]!)), `${fg} on ${bg}`).toBeGreaterThanOrEqual(min);
  });
});

describe("structure", () => {
  it("forced-dark block overrides the same keys as the media-query block", () => {
    const keys = (o: Vars) => Object.keys(o).filter((k) => !k.startsWith("--cp-space")).sort();
    expect(keys(darkForced)).toEqual(keys(darkMedia));
    for (const k of Object.keys(darkMedia)) expect(darkForced[k], k).toBe(darkMedia[k]);
  });

  it("defines the full token API", () => {
    const required = [
      ...SURFACES,
      ...TEXTS,
      ...TONES,
      ...PAIRS.flatMap((p) => [p.fg, p.bg]),
      "--cp-shadow-card",
      "--cp-border",
      "--cp-focus",
      ...Array.from({ length: 8 }, (_, i) => `--cp-space-${i + 1}`),
      "--cp-radius-sm",
      "--cp-radius-md",
      "--cp-radius-lg",
      "--cp-font-sans",
      "--cp-font-mono",
      ...["xs", "sm", "md", "lg", "xl", "2xl"].map((s) => `--cp-text-${s}`),
      "--cp-shadow-1",
      "--cp-shadow-2",
      "--cp-motion-fast",
      "--cp-motion-slow",
    ];
    for (const k of required) expect(light[k], k).toBeTruthy();
  });

  it("has a Tailwind @theme mapping and no physical-direction properties", () => {
    expect(css).toMatch(/@theme inline\s*\{/);
    expect(css).not.toMatch(/\b(margin|padding)-(left|right)\b/);
  });
});
