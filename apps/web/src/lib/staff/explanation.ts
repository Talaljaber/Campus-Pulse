/**
 * Turns a stored `predictions` row into the shapes the explanation components render.
 *
 * Why this exists: the `explanation` column holds the domain object the backend saved
 * (`codec.explanation_json`), which is close to but not the same as the API's
 * `ExplanationOut` that `ExplanationPanel` takes (neighbours say `category` where the API
 * says `label`, and the trace is a free dictionary). Staff pages read Supabase directly, so
 * this module does the mapping, defensively: anything missing becomes an empty value, and a
 * row without an explanation gives `null`.
 */
import type { Category, Evidence, Explanation, Neighbor, Priority, Tier } from "@/lib/ai/types";
import type { PredictionRow } from "@/lib/repos/predictions";

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

const SOURCES: ReadonlySet<string> = new Set<Neighbor["source"]>(["train", "augmented", "memory"]);
const TIERS: ReadonlySet<string> = new Set<Tier>(["tier0", "tier1", "tier2", "human"]);

function topTokens(v: unknown): Explanation["top_tokens"] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((pair): Explanation["top_tokens"] => {
    const [token, weight] = Array.isArray(pair) ? pair : [];
    return typeof token === "string" && typeof weight === "number" ? [[token, weight]] : [];
  });
}

function neighbors(v: unknown): Neighbor[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((n): Neighbor[] => {
    if (!isRecord(n)) return [];
    const text = str(n.text);
    const label = str(n.label) ?? str(n.category);
    const priority = str(n.priority);
    const sim = num(n.sim);
    const source = str(n.source);
    if (text === null || label === null || priority === null || sim === null || source === null || !SOURCES.has(source)) return [];
    return [
      {
        text,
        label: label as Neighbor["label"],
        priority: priority as Neighbor["priority"],
        sim,
        source: source as Neighbor["source"],
        created_at: str(n.created_at),
      },
    ];
  });
}

/** The explanation of a prediction in the API's `ExplanationOut` shape, or null when none was stored. */
export function explanationFromPrediction(p: Pick<PredictionRow, "explanation" | "set_cat" | "set_pri" | "cost_usd" | "latency_ms" | "artifact_version">): Explanation | null {
  const e = p.explanation;
  if (!isRecord(e)) return null;
  const trace = isRecord(e.trace) ? e.trace : {};
  const cf = isRecord(e.counterfactual) ? e.counterfactual : null;
  const drop = cf ? str(cf.drop) : null;
  const cfCat = cf ? str(cf.category) : null;
  const cfPri = cf ? str(cf.priority) : null;
  return {
    top_tokens: topTokens(e.top_tokens),
    neighbors: neighbors(e.neighbors),
    counterfactual:
      drop !== null && cfCat !== null && cfPri !== null
        ? { drop, category: cfCat as Category, priority: cfPri as Priority }
        : null,
    trace: {
      sets: { cat: p.set_cat?.length ?? 0, pri: p.set_pri?.length ?? 0 },
      models_agree: true,
      cost_usd: p.cost_usd ?? 0,
      latency_ms: p.latency_ms ?? 0,
      policy_path: [],
      clarified: trace.clarified === true,
      artifact_version: p.artifact_version ?? "",
      per_model: null,
    },
  };
}

/** The urgency evidence spans saved in the prediction's `core` (`core.evidence.spans`). */
export function evidenceFromPrediction(p: Pick<PredictionRow, "core">): Evidence[] {
  const core = p.core;
  const spans = isRecord(core) && isRecord(core.evidence) && Array.isArray(core.evidence.spans) ? core.evidence.spans : [];
  return spans.flatMap((s): Evidence[] => {
    if (!isRecord(s)) return [];
    const type = str(s.type);
    const span = str(s.span);
    return type !== null && span !== null ? [{ type, span }] : [];
  });
}

/** The tier of a prediction when it is one the UI knows, else undefined. */
export function tierOf(p: Pick<PredictionRow, "tier">): Tier | undefined {
  return p.tier !== null && TIERS.has(p.tier) ? (p.tier as Tier) : undefined;
}
