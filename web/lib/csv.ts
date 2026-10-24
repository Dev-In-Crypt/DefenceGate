/** Plain CSV helpers (no imports): used by the export routes and by lib/export.check.ts. */

export type Cell = string | number | null | undefined;

/** A cell that a spreadsheet would read as a formula gets a leading apostrophe (OWASP CSV injection). */
const FORMULA_START = /^[=+\-@\t\r]/;

export function csvCell(v: Cell): string {
  if (v === null || v === undefined) return '';
  if (typeof v === 'number') return Number.isFinite(v) ? String(v) : '';
  let s = FORMULA_START.test(v) ? `'${v}` : v;
  s = s.replace(/[\r\n]+/g, ' ');
  return /[",]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/**
 * UTF-8 with a byte-order mark (Excel on Windows then reads "Dirección" as UTF-8, not as ANSI), CRLF lines, header
 * first. The mark is an escape, so an editor cannot drop it unseen. `fetch().text()` and TextDecoder strip it when they decode:
 * check the bytes (EF BB BF), not the decoded text (WP-116; the audit's bom=false was its own decoder).
 */
export const CSV_BOM = '﻿';
export function toCsv(header: string[], rows: Cell[][]): string {
  return `${CSV_BOM}${[header, ...rows].map((r) => r.map(csvCell).join(',')).join('\r\n')}\r\n`;
}

/**
 * The last row of a file that holds fewer rows than match (`total` over `cap`): one cell that says so, padded to the
 * header's width. A reader of the file alone would otherwise take 2,000 of 61,521 rows for the whole result
 * (site-qa2:N8; the row count was only in response headers). null when nothing was cut.
 */
export function truncationRow(width: number, rows: number, total: number | null, cap: number, more = false): Cell[] | null {
  // `total` null: the export reads by cursor and never counts; `more` says the cursor was not exhausted.
  if (total === null ? !more : total <= cap) return null;
  const say = (n: number) => n.toLocaleString('en-GB');
  const of = total === null ? `matching rows, and more matched` : `of ${say(total)} matching rows`;
  return [`# Not the whole result: this file holds the first ${say(rows)} ${of} (limit ${say(cap)}). Narrow the filters to get the rest.`,
    ...Array.from({ length: Math.max(0, width - 1) }, () => '')];
}

/** A midnight timestamp is a date: a source that gives only a date arrives as 00:00 UTC. */
export const isMidnight = (iso: string): boolean => /T00:00:00(\.0+)?(Z|\+00:00)$/.test(iso);

/** `YYYY-MM-DDTHH:MM:SSZ`, or `YYYY-MM-DD` for a date-only value. Empty when there is no (valid) value. */
export function isoUtc(iso: string | null | undefined, dateOnly = false): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const s = d.toISOString();
  return dateOnly ? s.slice(0, 10) : `${s.slice(0, 19)}Z`;
}
