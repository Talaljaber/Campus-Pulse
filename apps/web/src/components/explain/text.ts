import type { Evidence, TopToken } from "@/lib/ai/types";

/** Direction of a piece of user text: right-to-left when Arabic letters outnumber Latin ones. */
export function textDir(text: string): "ltr" | "rtl" {
  const arabic = (text.match(/[؀-ۿݐ-ݿࢠ-ࣿ]/g) ?? []).length;
  const latin = (text.match(/[A-Za-z]/g) ?? []).length;
  return arabic > latin ? "rtl" : "ltr";
}

/** One run of text, cut at every word edge and every evidence-span edge. */
export interface Segment {
  text: string;
  /** The canonical top token (as returned by the API) when this run is exactly that word. */
  token?: string;
  /** Token weight divided by the heaviest token weight, in (0, 1]. */
  strength?: number;
  /** Evidence types whose span covers this run. */
  evidence: string[];
}

const WORD = /[\p{L}\p{M}\p{N}_']+/gu;

/** Find `needle` in `haystack` ignoring case, without letting case folding shift the offsets. */
function indexOfFold(haystack: string, needle: string): number {
  const lh = haystack.toLowerCase();
  if (lh.length === haystack.length) return lh.indexOf(needle.toLowerCase());
  return haystack.indexOf(needle);
}

/**
 * Cut `text` into runs and tag each with the top token it equals and the evidence
 * spans that cover it. Pure formatting: it never decides anything, it only locates
 * the strings the API already returned.
 */
export function segmentText(text: string, tokens: readonly TopToken[], evidence: readonly Evidence[]): Segment[] {
  if (!text) return [];
  const max = tokens.reduce((m, [, w]) => Math.max(m, w), 0);
  const weights = new Map<string, { token: string; strength: number }>();
  for (const [token, w] of tokens) {
    weights.set(token.toLowerCase(), { token, strength: max > 0 ? Math.max(w / max, 0.05) : 0.05 });
  }

  const ranges: { start: number; end: number; type: string }[] = [];
  for (const ev of evidence) {
    if (!ev.span) continue;
    const start = indexOfFold(text, ev.span);
    if (start >= 0) ranges.push({ start, end: start + ev.span.length, type: ev.type });
  }

  const words = new Map<number, number>();
  const cuts = new Set<number>([0, text.length]);
  for (const m of text.matchAll(WORD)) {
    words.set(m.index, m.index + m[0].length);
    cuts.add(m.index);
    cuts.add(m.index + m[0].length);
  }
  for (const r of ranges) {
    cuts.add(r.start);
    cuts.add(r.end);
  }

  const sorted = [...cuts].sort((a, b) => a - b);
  const out: Segment[] = [];
  for (let i = 0; i < sorted.length - 1; i++) {
    const start = sorted[i]!;
    const end = sorted[i + 1]!;
    const chunk = text.slice(start, end);
    const hit = words.get(start) === end ? weights.get(chunk.toLowerCase()) : undefined;
    out.push({
      text: chunk,
      token: hit?.token,
      strength: hit?.strength,
      evidence: ranges.filter((r) => r.start <= start && r.end >= end).map((r) => r.type),
    });
  }
  return out;
}

/** Human-readable fallback for an evidence type the dictionary does not know yet. */
export function humanize(type: string): string {
  const s = type.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
