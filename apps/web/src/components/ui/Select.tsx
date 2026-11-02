import { forwardRef, useId, type ReactNode, type SelectHTMLAttributes } from "react";
import { cn } from "./cn";

/** One choice of a {@link Select}. */
export interface SelectOption {
  value: string;
  label: string;
}

/** Props for {@link Select}: every native select attribute plus a required label and the options. */
export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "className" | "children"> {
  label: string;
  options: readonly SelectOption[];
  /** Hide the visible label (it is still read by assistive technology). */
  hideLabel?: boolean;
  /** Helper text under the control, tied to it with `aria-describedby`. */
  description?: ReactNode;
  className?: string;
}

/**
 * Labelled native `<select>`. The browser's own control gives keyboard and screen-reader
 * behaviour for free; the wrapper adds the label, a 44px target (36px when `compact`
 * is wanted through `className`) and the shared focus ring.
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, options, hideLabel = false, description, className, id, ...rest },
  ref,
) {
  const auto = useId();
  const selectId = id ?? auto;
  const descId = description ? `${selectId}-desc` : undefined;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={selectId} className={hideLabel ? "sr-only" : "text-sm font-bold text-accent"}>
        {label}
      </label>
      <select
        ref={ref}
        id={selectId}
        aria-describedby={descId}
        className="min-h-11 w-full rounded-md border border-line-strong bg-input px-3 text-base text-fg-1 transition-colors duration-(--cp-motion-fast) hover:border-accent focus-visible:border-accent disabled:cursor-not-allowed disabled:opacity-55"
        {...rest}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {description && (
        <p id={descId} className="text-sm text-fg-3">
          {description}
        </p>
      )}
    </div>
  );
});
