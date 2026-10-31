"use client";

import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { useT } from "@/i18n";
import { Icon } from "./Icon";

/** Props for {@link Dialog}. */
export interface DialogProps {
  open: boolean;
  onClose: () => void;
  /** Visible heading; also the dialog's accessible name. */
  title: string;
  children: ReactNode;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Modal dialog (`role="dialog" aria-modal`). Moves focus inside on open, traps Tab,
 * closes on Escape or backdrop click, locks page scroll, and restores focus to the
 * opener on close.
 */
export function Dialog({ open, onClose, title, children }: DialogProps) {
  const t = useT();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const first = panel.current?.querySelectorAll<HTMLElement>(FOCUSABLE)[0];
    (first ?? panel.current)?.focus();
    return () => {
      document.body.style.overflow = prevOverflow;
      opener?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== "Tab" || !panel.current) return;
    const nodes = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (nodes.length === 0) {
      e.preventDefault();
      return;
    }
    const first = nodes[0]!;
    const last = nodes[nodes.length - 1]!;
    const active = document.activeElement;
    if (e.shiftKey && (active === first || active === panel.current)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-(--cp-overlay) p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-lg border border-line border-t-4 border-t-orange bg-surface-0 p-5 shadow-2"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <h2 id={titleId} className="text-xl font-bold text-accent">
            {title}
          </h2>
          <button
            type="button"
            aria-label={t("ui.dialog.closeLabel")}
            onClick={onClose}
            className="grid size-9 shrink-0 place-items-center rounded-sm text-fg-2 hover:bg-surface-2"
          >
            <Icon name="close" size={18} />
          </button>
        </div>
        <div className="text-fg-2">{children}</div>
      </div>
    </div>
  );
}
