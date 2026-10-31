import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "./cn";
import { Icon } from "./Icon";

/** Props for {@link Button}. Accepts every native button attribute. */
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual weight. `danger` is for destructive actions. */
  variant?: "primary" | "secondary" | "ghost" | "danger";
  /** `md` meets the 44px touch target; `sm` is for dense toolbars. */
  size?: "sm" | "md";
  /** Shows a spinner, sets `aria-busy` and blocks clicks. The label stays for screen readers. */
  loading?: boolean;
}

const VARIANT: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary: "bg-accent text-on-accent border-transparent hover:brightness-110 active:brightness-95",
  secondary: "bg-surface-0 text-fg-1 border-line-strong hover:bg-surface-2",
  ghost: "bg-transparent text-fg-1 border-transparent hover:bg-surface-2",
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
        "inline-flex items-center justify-center gap-2 rounded-md border font-medium select-none",
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
