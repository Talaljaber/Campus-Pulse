/**
 * Incident view model and the resolve call, shared by `/staff` (incidents panel) and
 * `/pulse` (incident list and map rings).
 */
import { callAi } from "@/lib/ai/browser";
import type { AiResult } from "@/lib/ai/result";
import type { ResolveIncidentResponse } from "@/lib/ai/types";
import type { IncidentRow } from "@/lib/repos/incidents";

export interface IncidentView {
  id: string;
  /** The building id, which equals its code in the seed. */
  buildingId: string;
  category: string;
  title: string;
  priority: string;
  reportCount: number;
  openedAt: string;
}

export function incidentView(row: IncidentRow): IncidentView {
  return {
    id: row.id,
    buildingId: row.building_id,
    category: row.category,
    title: row.title,
    priority: row.priority,
    reportCount: row.report_count,
    openedAt: row.opened_at,
  };
}

/** `POST /v1/incidents/{id}/resolve`: closes the incident and its merged tickets, and notifies the reporters once. */
export function resolveIncident(id: string, note?: string): Promise<AiResult<ResolveIncidentResponse>> {
  const trimmed = note?.trim();
  return callAi<ResolveIncidentResponse>(`incidents/${encodeURIComponent(id)}/resolve`, {
    method: "POST",
    body: trimmed ? { note: trimmed } : {},
  });
}

/** Open incidents, newest first. A resolved row (from a live update) is dropped. */
export function applyIncident(list: readonly IncidentRow[], row: IncidentRow): IncidentRow[] {
  const rest = list.filter((i) => i.id !== row.id);
  if (row.status !== "open") return rest;
  return [row, ...rest].sort((a, b) => new Date(b.opened_at).getTime() - new Date(a.opened_at).getTime());
}
