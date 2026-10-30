/** WP-157: the pure parts of the client profile forms (lib/client-profile.check.ts). Import-free. */

/** A CPV list as typed ("35400000, 35"): 2 to 8 digits each, at most 20, no repeats; null when one is not a code. */
export function parseCpvList(raw: string): string[] | null {
  const codes = [...new Set(raw.split(/[\s,;]+/).map((c) => c.trim()).filter(Boolean))];
  return codes.length <= 20 && codes.every((c) => /^[0-9]{2,8}$/.test(c)) ? codes : null;
}

/** A country as typed: two letters, upper-cased; '' is none; null when it is not a code. */
export function parseCountry(raw: string): string | null | undefined {
  const c = raw.trim().toUpperCase();
  if (!c) return null;
  return /^[A-Z]{2}$/.test(c) ? c : undefined;
}

/** Where the client switcher returns to: one of the pages that use it, else the client list. */
const SWITCH_PAGES = ['/app/searches', '/app/shortlist', '/app/clients'] as const;
export function switchBack(raw: string): (typeof SWITCH_PAGES)[number] {
  return (SWITCH_PAGES as readonly string[]).includes(raw) ? (raw as (typeof SWITCH_PAGES)[number]) : '/app/clients';
}
