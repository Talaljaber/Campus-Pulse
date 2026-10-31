import type { SVGProps } from "react";

/** Names of the built-in icons. */
export type IconName = "mic" | "check" | "alert" | "info" | "close" | "arrow-down" | "equal" | "chevrons-up" | "spinner" | "dot";

const PATHS: Record<IconName, string> = {
  check: "M5 12.5l4.5 4.5L19 7.5",
  alert: "M12 3.5l9.5 16.5h-19L12 3.5z M12 10v4.5 M12 17.5v.01",
  info: "M12 21a9 9 0 100-18 9 9 0 000 18z M12 11v5.5 M12 7.5v.01",
  close: "M6 6l12 12 M18 6L6 18",
  "arrow-down": "M12 5v14 M6 13l6 6 6-6",
  equal: "M5 9h14 M5 15h14",
  "chevrons-up": "M6 11l6-6 6 6 M6 19l6-6 6 6",
  spinner: "M12 3a9 9 0 019 9",
  dot: "M12 12m-4 0a4 4 0 108 0 4 4 0 10-8 0",
  mic: "M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3z M5 11a7 7 0 0014 0 M12 18v3",
};

/** Props for {@link Icon}. */
export interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: IconName;
  /** Pixel size (square). Default 16. */
  size?: number;
}

/**
 * Decorative inline icon (`aria-hidden`). Meaning must always be carried by adjacent
 * text; icons only reinforce it (priority is never conveyed by colour alone).
 */
export function Icon({ name, size = 16, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={name === "dot" ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={2.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
