/**
 * The Pulse page's state as a pure reducer: located requests (with the category and priority
 * their prediction gave), open incidents and a feed of what happened. Realtime rows and the
 * first snapshot are all folded in here, so the rules (when a dot may be drawn, what counts
 * as a new incident or a bump, how the feed is deduplicated) are tested without React.
 */
import type { IncidentRow } from "@/lib/repos/incidents";
import type { OutboxRow } from "@/lib/repos/outbox";
import type { PredictionBrief } from "@/lib/repos/predictions";
import type { LocatedRequest } from "@/lib/repos/requests";

export type FeedKind = "request" | "incident_new" | "incident_bump" | "broadcast" | "resolved";

/** One line of the live feed. The sentence is built in the UI language by the component. */
export interface FeedEvent {
  /** Stable and unique: a row that is delivered twice (an update after an insert) adds one line. */
  id: string;
  at: string;
  kind: FeedKind;
  /** Demo traffic: shown with a SIMULATED badge. */
  simulated: boolean;
  buildingId: string | null;
  category: string | null;
  priority: string | null;
  /** The incident's report count (`incident_bump`). */
  count: number | null;
  /** The incident title or the broadcast subject, as written by the service. */
  title: string | null;
}

export interface Labels {
  category: string | null;
  priority: string | null;
}

export interface PulseState {
  requests: Record<string, LocatedRequest>;
  /** Category and priority by request id, from the latest prediction. */
  labels: Record<string, Labels>;
  incidents: Record<string, IncidentRow>;
  feed: FeedEvent[];
  /** Ids of feed events already added (dedupe). */
  fed: Record<string, true>;
}

export const INITIAL_PULSE: PulseState = { requests: {}, labels: {}, incidents: {}, feed: [], fed: {} };

export const FEED_LIMIT = 50;

export type PulseAction =
  | { type: "snapshot"; requests: LocatedRequest[]; predictions: PredictionBrief[]; incidents: IncidentRow[]; broadcasts: OutboxRow[] }
  | { type: "request"; row: LocatedRequest }
  | { type: "prediction"; requestId: string; category: string | null; priority: string | null }
  | { type: "incident"; row: IncidentRow; at: string }
  | { type: "broadcast"; row: OutboxRow };

const time = (iso: string) => new Date(iso).getTime();

/** Adds events that are not in the feed yet, newest first, capped. */
function addEvents(state: PulseState, events: FeedEvent[]): PulseState {
  const fresh = events.filter((e) => !state.fed[e.id]);
  if (fresh.length === 0) return state;
  const fed = { ...state.fed };
  for (const e of fresh) fed[e.id] = true;
  const feed = [...fresh, ...state.feed].sort((a, b) => time(b.at) - time(a.at)).slice(0, FEED_LIMIT);
  return { ...state, fed, feed };
}

/** A request is on the feed once both the request and its labels are known. */
function requestEvent(state: PulseState, id: string): FeedEvent[] {
  const req = state.requests[id];
  const lab = state.labels[id];
  if (!req || !lab?.category || !lab.priority) return [];
  return [
    {
      id: `req:${id}`,
      at: req.created_at,
      kind: "request",
      simulated: req.simulated,
      buildingId: req.building_id,
      category: lab.category,
      priority: lab.priority,
      count: null,
      title: null,
    },
  ];
}

/** Demo traffic: every located request in the building is simulated. A real report there makes the incident real. */
export function incidentSimulated(state: Pick<PulseState, "requests">, buildingId: string): boolean {
  const here = Object.values(state.requests).filter((r) => r.building_id === buildingId);
  return here.length > 0 && here.every((r) => r.simulated);
}

function incidentEvent(
  state: PulseState,
  row: IncidentRow,
  kind: "incident_new" | "incident_bump" | "resolved",
  at: string,
): FeedEvent {
  const suffix = kind === "incident_bump" ? `bump:${row.report_count}` : kind === "resolved" ? "resolved" : "new";
  return {
    id: `inc:${row.id}:${suffix}`,
    at,
    kind,
    simulated: incidentSimulated(state, row.building_id),
    buildingId: row.building_id,
    category: row.category,
    priority: row.priority,
    count: row.report_count,
    title: row.title,
  };
}

export function pulseReducer(state: PulseState, action: PulseAction): PulseState {
  switch (action.type) {
    case "snapshot": {
      const requests = Object.fromEntries(action.requests.map((r) => [r.id, r]));
      const labels: Record<string, Labels> = {};
      for (const p of action.predictions) labels[p.request_id] = { category: p.category, priority: p.priority };
      const incidents = Object.fromEntries(action.incidents.filter((i) => i.status === "open").map((i) => [i.id, i]));
      let next: PulseState = { ...INITIAL_PULSE, requests, labels, incidents };
      next = addEvents(next, action.requests.flatMap((r) => requestEvent(next, r.id)));
      next = addEvents(
        next,
        action.incidents.filter((i) => i.status === "open").map((i) => incidentEvent(next, i, "incident_new", i.opened_at)),
      );
      return addEvents(next, action.broadcasts.flatMap((b) => broadcastEvent(b)));
    }
    case "request": {
      const known = state.requests[action.row.id];
      const next = { ...state, requests: { ...state.requests, [action.row.id]: action.row } };
      return known ? next : addEvents(next, requestEvent(next, action.row.id));
    }
    case "prediction": {
      const next = { ...state, labels: { ...state.labels, [action.requestId]: { category: action.category, priority: action.priority } } };
      return addEvents(next, requestEvent(next, action.requestId));
    }
    case "incident": {
      const { row, at } = action;
      const prev = state.incidents[row.id];
      if (row.status !== "open") {
        if (!prev) return state;
        const rest = { ...state.incidents };
        delete rest[row.id];
        return addEvents({ ...state, incidents: rest }, [incidentEvent(state, row, "resolved", at)]);
      }
      const next = { ...state, incidents: { ...state.incidents, [row.id]: row } };
      if (!prev) return addEvents(next, [incidentEvent(next, row, "incident_new", row.opened_at)]);
      if (row.report_count > prev.report_count) return addEvents(next, [incidentEvent(next, row, "incident_bump", at)]);
      return next;
    }
    case "broadcast":
      return addEvents(state, broadcastEvent(action.row));
    default:
      return state;
  }
}

function broadcastEvent(row: OutboxRow): FeedEvent[] {
  if (row.kind !== "broadcast") return [];
  return [
    {
      id: `b:${row.id}`,
      at: row.created_at,
      kind: "broadcast",
      simulated: row.status === "simulated",
      buildingId: null,
      category: null,
      priority: row.priority,
      count: null,
      title: row.subject,
    },
  ];
}
