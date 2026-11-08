/** One piece of the corrected text: `changed` is true for a word that is not in the old text. */
export interface DiffPart {
  text: string;
  changed: boolean;
}

const norm = (w: string) => w.toLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");

/**
 * Marks the words of `next` that do not appear in `prev` (case and edge punctuation ignored), so the
 * student sees what the correction changed ("H302" -> "H203"). Whitespace is kept as it is.
 */
export function changedWords(prev: string, next: string): DiffPart[] {
  const known = new Set(prev.split(/\s+/).map(norm).filter(Boolean));
  return next
    .split(/(\s+)/)
    .filter((piece) => piece !== "")
    .map((piece) => ({ text: piece, changed: /\S/.test(piece) && !known.has(norm(piece)) }));
}
