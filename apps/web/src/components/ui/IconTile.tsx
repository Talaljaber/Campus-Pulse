"use client";

import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";
import { Icon, type IconName } from "./Icon";

/** Props for {@link IconTile}. */
export interface IconTileProps {
  /** Illustrative icon drawn at the start of the tile. */
  icon: IconName;
  /** The blue label. This is the tile's accessible name. */
  label: ReactNode;
  /** Optional second line (a count, a status, a hint) in muted text. */
  hint?: ReactNode;
  /** Icon colour: warm grey (default), orange or blue (all decorative). The label always carries the meaning. */
  tone?: "grey" | "orange" | "blue";
  /** Renders a link when set. */
  href?: string;
  /** Renders a button when set (and no `href`). Without either the tile is a static card. */
  onClick?: ButtonHTMLAttributes<HTMLButtonElement>["onClick"];
  disabled?: boolean;
  /** Marks the tile as the current choice (`aria-pressed` for a button, `aria-current` for a link). */
  selected?: boolean;
  className?: string;
  /** Test hook used by the login page's demo buttons. */
  "data-demo-role"?: string;
}

const ICON_TONE = {
  grey: "text-heading",
  orange: "text-orange-ink",
  blue: "text-brand",
} as const;

/**
 * Portal tile: a white card with a thin grey border, an illustrative icon at the start and a
 * blue label beside it (the portal icon row). A link, a button or a static card depending on the
 * props, so a row of tiles can be navigation, actions or an overview. Keyboard and focus work
 * as for the native element underneath.
 */
export function IconTile({ icon, label, hint, tone = "grey", href, onClick, disabled, selected, className, ...rest }: IconTileProps) {
  const body = (
    <>
      <span aria-hidden="true" className={cn("grid size-11 shrink-0 place-items-center rounded-md bg-surface-1", ICON_TONE[tone])}>
        <Icon name={icon} size={26} strokeWidth={1.6} />
      </span>
      <span className="flex min-w-0 flex-col text-start">
        <span className="font-semibold leading-snug text-accent">{label}</span>
        {hint && <span className="text-sm text-fg-2">{hint}</span>}
      </span>
    </>
  );
  const base = cn(
    "flex min-h-16 w-full items-center gap-3 rounded-md border bg-surface-0 p-2.5 shadow-1",
    selected ? "border-accent border-s-4" : "border-line-strong",
    className,
  );
  const interactive = "transition-[border-color,background-color] duration-(--cp-motion-fast) hover:border-accent hover:bg-surface-1";

  if (href && !disabled) {
    return (
      <Link href={href} aria-current={selected ? "page" : undefined} className={cn(base, interactive)} {...rest}>
        {body}
      </Link>
    );
  }
  if (onClick || disabled) {
    return (
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        aria-pressed={selected === undefined ? undefined : selected}
        className={cn(base, interactive, "disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:border-line-strong disabled:hover:bg-surface-0")}
        {...rest}
      >
        {body}
      </button>
    );
  }
  return (
    <div className={base} {...rest}>
      {body}
    </div>
  );
}
