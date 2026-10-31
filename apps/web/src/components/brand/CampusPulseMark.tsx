import type { SVGProps } from "react";

/** Props for {@link CampusPulseMark}. */
export interface CampusPulseMarkProps extends Omit<SVGProps<SVGSVGElement>, "viewBox" | "children"> {
  /** Pixel size (square). Default 44. */
  size?: number;
}

/**
 * The CampusPulse mark, drawn for this project: a tilted blue square (a campus block seen on its
 * corner) with a white heartbeat line running through it, and a small tilted orange square as the
 * "alert" dot. It is original artwork and deliberately not the university's logo: one big tilted
 * square plus a pulse line, not two squares. Decorative (`aria-hidden`); the wordmark names it.
 */
export function CampusPulseMark({ size = 44, ...rest }: CampusPulseMarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" focusable="false" {...rest}>
      <rect x="9" y="9" width="30" height="30" rx="6" transform="rotate(45 24 24)" fill="var(--cp-brand)" />
      <rect x="35.5" y="4.5" width="7.5" height="7.5" rx="1.8" transform="rotate(20 39.25 8.25)" fill="var(--cp-orange)" />
      <path
        d="M9 25.5h8.5l3-7.5 5 14.5 4-10 2 3h7.5"
        fill="none"
        stroke="#ffffff"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
