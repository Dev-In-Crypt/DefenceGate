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

/** UTF-8 with a byte-order mark (spreadsheets then read accents right), CRLF lines, header first. */
export function toCsv(header: string[], rows: Cell[][]): string {
  return `﻿${[header, ...rows].map((r) => r.map(csvCell).join(',')).join('\r\n')}\r\n`;
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
