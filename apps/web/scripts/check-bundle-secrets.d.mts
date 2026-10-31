export const MARKERS: string[];
export function scan(roots: string[], needles: { value: string; label: string }[]): { file: string; needle: string }[];
export function buildNeedles(env?: Record<string, string | undefined>): { value: string; label: string }[];
