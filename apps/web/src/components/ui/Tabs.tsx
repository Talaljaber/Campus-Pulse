"use client";

import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "./cn";

/** Props for {@link Tabs}. */
export interface TabsProps {
  items: { id: string; label: string }[];
  /** Selected tab id. */
  value: string;
  onChange: (id: string) => void;
  /** Accessible name of the tablist. */
  label?: string;
  /** Prefix for the ids that link tabs to panels. Pair with {@link TabPanel}. */
  idBase?: string;
  className?: string;
}

const tabId = (base: string, id: string) => `${base}-tab-${id}`;
const panelId = (base: string, id: string) => `${base}-panel-${id}`;

/**
 * Tab list (WAI-ARIA tabs pattern, automatic activation). Roving tabindex; arrow keys
 * are direction-aware in RTL; Home/End jump to the ends.
 */
export function Tabs({ items, value, onChange, label, idBase, className }: TabsProps) {
  const autoId = useId();
  const base = idBase ?? autoId;
  const ref = useRef<HTMLDivElement>(null);

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const rtl = ref.current?.closest("[dir]")?.getAttribute("dir") === "rtl";
    const idx = Math.max(0, items.findIndex((i) => i.id === value));
    let next = idx;
    if (e.key === "ArrowRight") next = idx + (rtl ? -1 : 1);
    else if (e.key === "ArrowLeft") next = idx + (rtl ? 1 : -1);
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = items.length - 1;
    else return;
    e.preventDefault();
    const target = items[(next + items.length) % items.length];
    if (!target) return;
    onChange(target.id);
    document.getElementById(tabId(base, target.id))?.focus();
  }

  return (
    <div ref={ref} role="tablist" aria-label={label} onKeyDown={onKeyDown} className={cn("flex gap-1 border-b border-line", className)}>
      {items.map((it) => {
        const selected = it.id === value;
        return (
          <button
            key={it.id}
            id={tabId(base, it.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={panelId(base, it.id)}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(it.id)}
            className={cn(
              "-mb-px min-h-11 border-b-2 px-4 text-base font-medium transition-colors duration-(--cp-motion-fast)",
              selected ? "border-accent text-fg-1" : "border-transparent text-fg-2 hover:text-fg-1",
            )}
          >
            {it.label}
          </button>
        );
      })}
    </div>
  );
}

/** Props for {@link TabPanel}. */
export interface TabPanelProps {
  idBase: string;
  id: string;
  /** Currently selected tab id; the panel is hidden unless it equals `id`. */
  value: string;
  children: ReactNode;
}

/** Panel linked to the tab with the same `id` (`aria-labelledby`). */
export function TabPanel({ idBase, id, value, children }: TabPanelProps) {
  return (
    <div role="tabpanel" id={panelId(idBase, id)} aria-labelledby={tabId(idBase, id)} hidden={value !== id} tabIndex={0}>
      {value === id ? children : null}
    </div>
  );
}
