import { displayName } from './display-name';
import { formatNumber } from './format';
import type { BuyerUnit } from './types';

/**
 * WP-144: a buyer's units on its page (one legal body, the names its notices state: "Politechnika Warszawska, Wydział
 * Transportu"). The API counts each (`BuyerUnit`) and reads `unit=` on the tender list; this picks the one the address names.
 */

/** The folded form the API compares (`dg_fold`, migration 0054): lower case, accents off, punctuation and spaces as one space. */
export function unitKey(s: string): string {
  return s.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase()
    .replace(/ł/g, 'l').replace(/đ/g, 'd').replace(/ß/g, 'ss').replace(/æ/g, 'ae').replace(/œ/g, 'oe')
    .replace(/[\s\-–—/_.,;:()"'’]+/gu, ' ').trim();
}

/** The unit `?unit=` names among the buyer's own units; null when none is named, the buyer has fewer than two, or it is not one of them. */
export function chosenUnit(units: readonly BuyerUnit[] | undefined, raw: string | string[] | undefined): BuyerUnit | null {
  const v = (Array.isArray(raw) ? raw[0] : raw)?.trim();
  if (!v || !units || units.length < 2) return null;
  const k = unitKey(v);
  return units.find((u) => unitKey(u.key) === k) ?? null;
}

/** A unit's name as the page shows it. */
export function unitName(u: BuyerUnit): string {
  return displayName(u.name, 'title');
}

/** The options of the Unit select, after "All units": each unit with its tenders. */
export function unitOptions(units: readonly BuyerUnit[]): { value: string; label: string }[] {
  return units.map((u) => ({ value: u.key, label: `${unitName(u)} (${formatNumber(u.tenderCount)})` }));
}
