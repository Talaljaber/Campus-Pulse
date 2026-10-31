import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "./cn";
import { Icon } from "./Icon";

/** Props for {@link Button}. Accepts every native button attribute. */
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual weight. `accent` is the orange call to action (use once per view); `danger` is for destructive actions. */
  variant?: "primary" | "accent" | "secondary" | "ghost" | "danger";
  /** `md` meets the 44px touch target; `sm` is for dense toolbars. */
  size?: "sm" | "md";
  /** Shows a spinner, sets `aria-busy` and blocks clicks. The label stays for screen readers. */
  loading?: boolean;
}

const VARIANT: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary: "bg-accent text-on-accent border-transparent hover:brightness-110 active:brightness-95",
  accent: "bg-orange text-on-orange border-transparent hover:brightness-105 active:brightness-95",
  secondary: "bg-surface-0 text-accent border-accent hover:bg-surface-1",
  ghost: "bg-transparent text-accent border-transparent hover:bg-surface-2",
  danger: "bg-danger text-surface-0 border-transparent hover:brightness-110 active:brightness-95",
};

/**
 * Button. Native `<button>`, so keyboard (Enter/Space) and focus work by default.
 * Defaults to `type="button"` so it never submits a form by accident.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading = false, disabled, className, children, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md border font-semibold select-none",
        "transition-[background-color,filter] duration-(--cp-motion-fast)",
        "disabled:cursor-not-allowed disabled:opacity-55",
        size === "md" ? "min-h-11 px-4 text-base" : "min-h-9 px-3 text-sm",
        VARIANT[variant],
        className,
      )}
      {...rest}
    >
      {loading && <Icon name="spinner" className="motion-safe:animate-spin" />}
      {children}
    </button>
  );
});
