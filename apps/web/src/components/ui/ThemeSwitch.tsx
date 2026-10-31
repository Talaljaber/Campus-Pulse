"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useT } from "@/i18n";
import { cn } from "./cn";

/** Theme choice: follow the OS, or force light or dark. */
export type ThemeChoice = "system" | "light" | "dark";

const KEY = "cp_theme";
const EVENT = "cp-theme-change";
const CHOICES: ThemeChoice[] = ["system", "light", "dark"];

function read(): ThemeChoice {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // storage unavailable: stay on system
  }
  return "system";
}

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

function apply(choice: ThemeChoice) {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
}

/** Props for {@link ThemeSwitch}. */
export interface ThemeSwitchProps {
  className?: string;
}

/**
 * Three-way theme control (radio buttons in a labelled group). Persists to
 * localStorage when available and sets `data-theme` on `<html>` (see tokens.css).
 */
export function ThemeSwitch({ className }: ThemeSwitchProps) {
  const t = useT();
  const choice = useSyncExternalStore(subscribe, read, () => "system" as ThemeChoice);

  useEffect(() => apply(choice), [choice]);

  function pick(next: ThemeChoice) {
    try {
      if (next === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {
      // ignore: the choice then lasts until reload
    }
    apply(next);
    window.dispatchEvent(new Event(EVENT));
  }

  return (
    <div role="radiogroup" aria-label={t("theme.label")} className={cn("inline-flex rounded-md border border-line-strong p-0.5", className)}>
      {CHOICES.map((c) => (
        <button
          key={c}
          type="button"
          role="radio"
          aria-checked={choice === c}
          onClick={() => pick(c)}
          className={cn(
            "min-h-9 rounded-sm px-3 text-sm font-medium",
            choice === c ? "bg-accent text-on-accent" : "text-fg-2 hover:bg-surface-2",
          )}
        >
          {t(`theme.${c}`)}
        </button>
      ))}
    </div>
  );
}
