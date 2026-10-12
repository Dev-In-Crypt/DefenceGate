/**
 * Pure helpers of the deadline calendar page (re-exported by lib/calendar.ts). Import-free so lib/ui.check.ts
 * can run them without the data layer.
 */

/**
 * The month to show. One outside the window the data covers (this month to `last`) is not silently swapped:
 * `clamped` tells the page to say which month was asked for and which is shown.
 */
export function resolveMonth(requested: string | null, current: string, last: string): { month: string; clamped: boolean } {
  if (!requested) return { month: current, clamped: false };
  if (requested < current) return { month: current, clamped: true };
  if (requested > last) return { month: last, clamped: true };
  return { month: requested, clamped: false };
}

/** The first `max` characters of a title (whole characters, never half a pair), with an ellipsis when cut. */
export function truncateTitle(title: string, max = 28): string {
  const chars = Array.from(title.trim());
  return chars.length <= max ? chars.join('') : `${chars.slice(0, max).join('').trimEnd()}…`;
}

/** Entries `page` of `size` (1-based, clamped into range), and how many pages there are. */
export function pageOf<T>(items: T[], page: number, size: number): { items: T[]; pages: number; page: number } {
  const pages = Math.max(1, Math.ceil(items.length / size));
  const at = Math.min(Math.max(1, page), pages);
  return { items: items.slice((at - 1) * size, at * size), pages, page: at };
}
