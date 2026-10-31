"use client";

import { forwardRef, useRef, type ButtonHTMLAttributes, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "./cn";
import { Icon } from "./Icon";
import { tintClass, toneColor, type Tone } from "./tone";

/** Props for {@link Chip}. Use inside a {@link ChipGroup} (a radiogroup). */
export interface ChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onSelect" | "role"> {
  selected?: boolean;
  onSelect?: () => void;
  tone?: Tone;
  children: ReactNode;
}

/** A single-choice option rendered as `role="radio"`. Selected state shows a check, not only colour. */
export const Chip = forwardRef<HTMLButtonElement, ChipProps>(function Chip(
  { selected = false, onSelect, tone = "neutral", className, children, onClick, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      role="radio"
      aria-checked={selected}
      style={{ "--tone": toneColor(tone) } as CSSProperties}
      onClick={(e) => {
        onClick?.(e);
        if (!e.defaultPrevented) onSelect?.();
      }}
      className={cn(
        "inline-flex min-h-11 items-center gap-1.5 rounded-full border px-4 text-sm font-medium text-fg-1",
        "transition-colors duration-(--cp-motion-fast) disabled:cursor-not-allowed disabled:opacity-55",
        selected
          ? cn("border-(--tone) border-2", tintClass(28))
          : "border-line-strong bg-surface-0 hover:bg-surface-2",
        className,
      )}
      {...rest}
    >
      {selected && <Icon name="check" size={14} className="text-(--tone)" />}
      {children}
    </button>
  );
});

/** Props for {@link ChipGroup}. */
export interface ChipGroupProps {
  /** Accessible name of the group (required: a radiogroup needs one). */
  label: string;
  items: { id: string; label: string; tone?: Tone; disabled?: boolean }[];
  /** Selected id, or `null` for none. */
  value: string | null;
  onChange: (id: string) => void;
  className?: string;
}

/**
 * `role="radiogroup"` of chips with a roving tabindex: Tab enters once, arrow keys
 * move and select (direction-aware in RTL), Home/End jump to the ends.
 */
export function ChipGroup({ label, items, value, onChange, className }: ChipGroupProps) {
  const ref = useRef<HTMLDivElement>(null);
  const enabled = items.filter((i) => !i.disabled);
  const tabStop = value !== null && enabled.some((i) => i.id === value) ? value : enabled[0]?.id;

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const rtl = ref.current?.closest("[dir]")?.getAttribute("dir") === "rtl";
    const idx = Math.max(0, enabled.findIndex((i) => i.id === (value ?? tabStop)));
    let next = idx;
    if (e.key === "ArrowRight") next = idx + (rtl ? -1 : 1);
    else if (e.key === "ArrowLeft") next = idx + (rtl ? 1 : -1);
    else if (e.key === "ArrowDown") next = idx + 1;
    else if (e.key === "ArrowUp") next = idx - 1;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = enabled.length - 1;
    else return;
    e.preventDefault();
    const target = enabled[(next + enabled.length) % enabled.length];
    if (!target) return;
    onChange(target.id);
    ref.current?.querySelector<HTMLElement>(`[data-chip-id="${CSS.escape(target.id)}"]`)?.focus();
  }

  return (
    <div ref={ref} role="radiogroup" aria-label={label} onKeyDown={onKeyDown} className={cn("flex flex-wrap gap-2", className)}>
      {items.map((it) => (
        <Chip
          key={it.id}
          data-chip-id={it.id}
          tone={it.tone}
          disabled={it.disabled}
          selected={it.id === value}
          tabIndex={it.id === tabStop ? 0 : -1}
          onSelect={() => onChange(it.id)}
        >
          {it.label}
        </Chip>
      ))}
    </div>
  );
}
