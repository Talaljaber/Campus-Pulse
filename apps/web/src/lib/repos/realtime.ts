import type { Sb } from "../supabase/types";

/** What a Realtime subscription reports: the new row, and whether it was an insert or an update. */
export type Change<T> = { kind: "insert" | "update"; row: T };

export interface SubscribeOptions {
  /** `postgres_changes` filter, e.g. `alias=eq.talal`. Omit to receive every row RLS allows. */
  filter?: string;
}

let counter = 0;

/**
 * Subscribes to INSERT and UPDATE events of one table and returns an unsubscribe
 * function. RLS applies to Realtime, so a subscriber only ever receives rows its
 * SELECT policy allows; the optional `filter` only narrows that further.
 */
export function subscribeTable<T extends Record<string, unknown>>(
  sb: Sb,
  table: string,
  onChange: (change: Change<T>) => void,
  options: SubscribeOptions = {},
): () => void {
  counter += 1;
  const channel = sb.channel(`cp-${table}-${counter}`);
  const handler = (kind: Change<T>["kind"]) => (payload: { new: unknown }) => {
    onChange({ kind, row: payload.new as T });
  };
  const base = { schema: "public", table, ...(options.filter ? { filter: options.filter } : {}) } as const;
  channel
    .on("postgres_changes", { ...base, event: "INSERT" }, handler("insert"))
    .on("postgres_changes", { ...base, event: "UPDATE" }, handler("update"))
    .subscribe();
  return () => {
    void sb.removeChannel(channel);
  };
}

/**
 * Builds `column=eq.value` for a Realtime filter. Office codes and aliases are plain
 * slugs; anything else (commas, parentheses) could change the filter, so it is refused.
 */
export function eqFilter(column: string, value: string): string {
  if (!/^[\w.-]{1,64}$/.test(value)) throw new Error(`Unsafe realtime filter value for ${column}.`);
  return `${column}=eq.${value}`;
}

/** Throws the PostgREST error (if any) and returns the rows. Repos use it so callers see one error type. */
export function unwrap<T>(res: { data: T[] | null; error: { message: string } | null }): T[] {
  if (res.error) throw new Error(res.error.message);
  return res.data ?? [];
}
