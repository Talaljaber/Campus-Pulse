import { useSyncExternalStore } from "react";

// One shared clock for every panel on the page. It is 0 until the first subscriber
// mounts, so the server and the first client render agree ("no time yet") and the
// real time only appears after hydration.
let current = 0;

function subscribe(onChange: () => void): () => void {
  current = Date.now();
  const id = setInterval(() => {
    current = Date.now();
    onChange();
  }, 30_000);
  return () => clearInterval(id);
}

/**
 * Current time in epoch ms for relative labels ("N s ago"), or `null` before hydration.
 * Pass `override` (tests, stories) to pin it.
 */
export function useNow(override?: number): number | null {
  const live = useSyncExternalStore(
    subscribe,
    () => current,
    () => 0,
  );
  if (override !== undefined) return override;
  return live === 0 ? null : live;
}
