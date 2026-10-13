/**
 * Shapes of the identifiers a server action accepts from a form or a client island, checked before they are
 * put in a path or sent to the API. Import-free, so lib/refs.check.ts can run it on its own.
 *
 * Review of 13 October 2026 (LOW): an id must start with a letter or digit (a leading `.` or `-` is not an
 * identifier), ids that are UUIDs are checked as UUIDs, and a numeric reference is stored and looked up in
 * one form: digits only, no leading zeros, so `007` and `7` are one shortlisted item.
 */

/** Programme codes (`EDF`, `HORIZON`) and anything else that is a word: starts alphanumeric, at most 64. */
export const ID_RE = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const NUMERIC_RE = /^[0-9]{1,18}$/;

/** A saved search or a session of the account. */
export function isUuid(v: string): boolean {
  return UUID_RE.test(v);
}

/** The stored form of a tender, call or buyer id: digits without leading zeros, or null. */
export function numericRef(v: string): string | null {
  if (!NUMERIC_RE.test(v)) return null;
  return v.replace(/^0+(?=[0-9])/, '');
}

/** A follow's reference: a buyer id is numeric, a programme is a code. Null when it is neither. */
export function followRef(kind: 'buyer' | 'programme', v: string): string | null {
  if (kind === 'buyer') return numericRef(v);
  return ID_RE.test(v) ? v : null;
}
