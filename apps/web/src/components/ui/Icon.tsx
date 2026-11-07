import type { SVGProps } from "react";

/** Names of the built-in icons. */
export type IconName =
  | "mic"
  | "check"
  | "alert"
  | "info"
  | "close"
  | "arrow-down"
  | "equal"
  | "chevrons-up"
  | "spinner"
  | "dot"
  | "help"
  | "logout"
  | "globe"
  | "user"
  | "graduation"
  | "briefcase"
  | "shield"
  | "chat"
  | "ticket"
  | "map"
  | "mail"
  | "flask"
  | "chart"
  | "home"
  | "megaphone"
  | "chevron-down";

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
  help: "M12 21a9 9 0 100-18 9 9 0 000 18z M9.5 9.5a2.5 2.5 0 114 2c-.9.6-1.5 1.1-1.5 2.2 M12 17v.01",
  logout: "M9 4H5v16h4 M16 8l4 4-4 4 M20 12H9",
  globe:
    "M12 21a9 9 0 100-18 9 9 0 000 18z M3 12h18 M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z",
  user: "M12 12a4 4 0 100-8 4 4 0 000 8z M4.5 20a7.5 7.5 0 0115 0",
  graduation: "M2.5 9.5L12 5l9.5 4.5L12 14 2.5 9.5z M6.5 11.5v4.5c0 1 2.5 2.5 5.5 2.5s5.5-1.5 5.5-2.5v-4.5 M21.5 9.5v5",
  briefcase: "M4 8h16v11H4z M9 8V5.5h6V8 M4 13h16",
  shield: "M12 3l7.5 3v5.5c0 4.5-3.2 8-7.5 9.5-4.3-1.5-7.5-5-7.5-9.5V6L12 3z M9 12l2.2 2.2L15.5 10",
  chat: "M4 5h16v11H9l-5 4V5z M8 9.5h8 M8 12.5h5",
  ticket: "M3 8.5V6h18v2.5a2 2 0 000 4V15H3v-2.5a2 2 0 000-4z M13 6v9",
  map: "M9 4L3 6.5V20l6-2.5 6 2.5 6-2.5V4l-6 2.5L9 4z M9 4v13.5 M15 6.5V20",
  mail: "M3.5 6h17v12h-17z M3.5 7l8.5 6.5L20.5 7",
  flask: "M9 3h6 M10 3v6l-5 9a2 2 0 001.8 3h10.4A2 2 0 0019 18l-5-9V3 M7.5 15h9",
  chart: "M4 20h16 M6.5 20v-7 M11 20V5 M15.5 20v-10 M20 20v-4",
  home: "M3 11l9-7.5 9 7.5 M5.5 9.5V20h13V9.5 M10 20v-5.5h4V20",
  megaphone: "M3 10v4h3l8 4V6L6 10H3z M17.5 9a4 4 0 010 6 M20 7a7 7 0 010 10",
  "chevron-down": "M6 9l6 6 6-6",
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
