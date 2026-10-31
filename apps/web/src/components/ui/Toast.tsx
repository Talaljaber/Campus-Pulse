"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { useT } from "@/i18n";
import { cn } from "./cn";
import { Icon } from "./Icon";
import { tintClass, toneColor, type Tone } from "./tone";

interface ToastItem {
  id: number;
  msg: string;
  tone: Tone;
}

/** The value returned by {@link useToast}. */
export interface ToastApi {
  /** Show a message. `ms` is the auto-dismiss delay (default 5000; `0` keeps it until dismissed). */
  show: (msg: string, tone?: Tone, ms?: number) => void;
}

const ToastContext = createContext<ToastApi>({ show: () => {} });

/** Imperative toast API. Outside a {@link ToastProvider} it is a harmless no-op. */
export function useToast(): ToastApi {
  return useContext(ToastContext);
}

/** Props for {@link ToastProvider}. */
export interface ToastProviderProps {
  children: ReactNode;
}

/**
 * Holds the toast queue and renders the viewport. The viewport is a polite live
 * region (`aria-live="polite"`) so screen readers announce messages without stealing
 * focus. Timers are cleared on unmount.
 */
export function ToastProvider({ children }: ToastProviderProps) {
  const t = useT();
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer) clearTimeout(timer);
    timers.current.delete(id);
    setItems((cur) => cur.filter((i) => i.id !== id));
  }, []);

  const show = useCallback<ToastApi["show"]>(
    (msg, tone = "neutral", ms = 5000) => {
      const id = nextId.current++;
      setItems((cur) => [...cur, { id, msg, tone }]);
      if (ms > 0) timers.current.set(id, setTimeout(() => dismiss(id), ms));
    },
    [dismiss],
  );

  useEffect(() => {
    const current = timers.current;
    return () => current.forEach((timer) => clearTimeout(timer));
  }, []);

  const api = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        role="region"
        aria-label={t("ui.toast.region")}
        className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col items-end gap-2 sm:inset-x-auto sm:end-4 sm:w-96"
      >
        <div aria-live="polite" aria-atomic="false" className="flex w-full flex-col gap-2">
          {items.map((i) => (
            <div
              key={i.id}
              role="status"
              style={{ "--tone": toneColor(i.tone) } as CSSProperties}
              className={cn(
                "pointer-events-auto flex items-start gap-3 rounded-md border border-line border-s-4 border-s-(--tone) p-3 text-sm text-fg-1 shadow-2",
                tintClass(16),
              )}
            >
              <p className="flex-1">{i.msg}</p>
              <button
                type="button"
                aria-label={t("common.dismiss")}
                onClick={() => dismiss(i.id)}
                className="grid size-8 shrink-0 place-items-center rounded-sm text-fg-2 hover:bg-surface-2"
              >
                <Icon name="close" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </ToastContext.Provider>
  );
}
