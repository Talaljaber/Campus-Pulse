"use client";

import { useSyncExternalStore } from "react";

/**
 * True while the media query matches. Server render and environments without `matchMedia` (tests)
 * report `false`, so the wide layout is the default and a phone switches on the client.
 */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (notify) => {
      if (typeof window === "undefined" || !window.matchMedia) return () => {};
      const mql = window.matchMedia(query);
      mql.addEventListener("change", notify);
      return () => mql.removeEventListener("change", notify);
    },
    () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false),
    () => false,
  );
}
