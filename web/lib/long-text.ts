/**
 * A long source text is shown as its first ~600 characters and a disclosure with the whole of it (WP-56, UX audit C6/F-03).
 * Nothing is cut for good: the disclosure holds the full text and says how long it is.
 */
export const LONG_TEXT_OVER = 800;
export const LONG_TEXT_SHOWN = 600;

/** The text to show before the disclosure: up to `shown` characters, cut at a word, with an ellipsis. Null when the text is short enough to show whole. */
export function textHead(text: string, over = LONG_TEXT_OVER, shown = LONG_TEXT_SHOWN): string | null {
  if (text.length <= over) return null;
  const cut = text.slice(0, shown);
  const at = cut.search(/\s\S*$/);
  return `${(at > 0 ? cut.slice(0, at) : cut).replace(/[\s,;:]+$/, '')}…`;
}

/** "Show full text, 8,591 characters" */
export function fullTextLabel(text: string): string {
  return `Show full text, ${text.length.toLocaleString('en-GB')} characters`;
}

/**
 * Rows of "who can apply" with the same text are one row: the labels are joined. (87 call pages said "Described in
 * section 6 of the call document." twice, once per label.) The first row keeps its place; order and text are otherwise unchanged.
 */
export function mergeSameText<T extends { label: string; value: string }>(rows: T[]): T[] {
  const out: T[] = [];
  for (const r of rows) {
    const same = out.find((o) => o.value === r.value);
    if (same) same.label = `${same.label} and ${r.label.charAt(0).toLowerCase()}${r.label.slice(1)}`;
    else out.push({ ...r });
  }
  return out;
}
