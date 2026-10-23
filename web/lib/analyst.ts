/**
 * WP-90 (UX audit of 22 October 2026, section 5: the analyst path): the CPV presets and deadline presets of /tenders, and the two
 * subscriptions of a search (its deadline calendar and its change feed) with exactly its filters. Pure and import-light:
 * lib/wp90.check.ts runs it on its own.
 */
import { cpvPrefix } from './cpv';
import { DEFAULT_TENDER_SCOPE, toChangeQuery, toTenderQuery } from './filters';
import type { TenderFilters } from './types';

/**
 * Product groups a defence analyst filters by, each a set of official CPV 2008 codes (titles verbatim from the vocabulary,
 * lib/data/cpv-full.json; wp90.check.ts holds each code to it). A preset sets the CPV filter to the codes' prefixes (35700000 ->
 * 357: the code and everything under it), so it is the ordinary CPV filter, editable afterwards.
 */
export const CPV_PRESETS = [
  { id: 'military-electronics', label: 'Military electronics', codes: ['35700000'] },        // Military electronic systems
  { id: 'radar-sonar', label: 'Radar and sonar', codes: ['35722000', '35723000', '38115000', '38113000'] },
  { id: 'communications', label: 'Communications', codes: ['35710000', '32000000'] },
  { id: 'vehicles', label: 'Vehicles and parts', codes: ['35400000', '34100000', '34300000'] },
  { id: 'weapons', label: 'Ammunition and weapons', codes: ['35300000'] },
  { id: 'uniforms', label: 'Uniforms and protective gear', codes: ['35810000', '18100000'] },
] as const;

export type CpvPreset = (typeof CPV_PRESETS)[number];

/** The prefixes a preset puts in the CPV filter. */
export const presetPrefixes = (p: Pick<CpvPreset, 'codes'>): string[] => p.codes.map(cpvPrefix);

/** The preset the CPV filter is set to, if it is one exactly (any order). */
export function activePreset(cpv: string[] | undefined): CpvPreset | null {
  if (!cpv?.length) return null;
  const asked = [...cpv].sort().join(',');
  return CPV_PRESETS.find((p) => [...presetPrefixes(p)].sort().join(',') === asked) ?? null;
}

export const DEADLINE_PRESETS = [7, 14, 30] as const;

const day = (d: Date) => d.toISOString().slice(0, 10);

/** "Deadline in the next N days": from today to today + N (UTC days, both included, as the list reads `from` and `to`). */
export function deadlineWindow(days: number, ref: Date): { deadlineFrom: string; deadlineTo: string } {
  return { deadlineFrom: day(ref), deadlineTo: day(new Date(ref.getTime() + days * 86_400_000)) };
}

/** The preset the deadline range is, if it is one (from today). */
export function activeDeadlinePreset(f: Pick<TenderFilters, 'deadlineFrom' | 'deadlineTo'>, ref: Date): number | null {
  return DEADLINE_PRESETS.find((n) => {
    const w = deadlineWindow(n, ref);
    return f.deadlineFrom === w.deadlineFrom && f.deadlineTo === w.deadlineTo;
  }) ?? null;
}

/** The ceilings of the two subscriptions, said beside them (each file says so too when it cuts: lib/ics.ts, lib/atom.ts). */
export const CALENDAR_API_MAX = 3000;
export const FEED_MAX = 2400;

export interface Subscription {
  /** The calendar file of the search (open tenders with a deadline), and the same as a webcal:// address a calendar app subscribes to. Null when the status holds no open tender. */
  ics: string | null;
  webcal: string | null;
  /** The Atom feed of the search's new notices and changes. */
  atom: string;
}

/**
 * The calendar and the change feed of a tender search, with every filter it has: search words, countries, CPV codes (main code
 * only, excluded codes), scope, defence goods, deadline and value range; the feed also the status (as of now: a feed of Open holds
 * what is open today). The calendar holds open tenders by what it is, so a Closed or Planned search has none. The sort and the page
 * are the list's, not the feed's.
 */
export function subscription(f: TenderFilters, origin: string): Subscription {
  const tender: TenderFilters = {
    q: f.q, cpv: f.cpv, cpvMain: f.cpvMain, notCpv: f.notCpv, scope: f.scope, goods: f.goods, deadlineFrom: f.deadlineFrom,
    deadlineTo: f.deadlineTo, valueMin: f.valueMin, valueMax: f.valueMax, currency: f.currency,
  };
  const q = new URLSearchParams({ kind: 'tenders' });
  if (f.country?.length) q.set('country', f.country.join(','));
  for (const [k, v] of new URLSearchParams(toTenderQuery(tender))) q.set(k, v);
  const open = (f.status ?? 'open') === 'open' || f.status === 'all';
  const ics = open ? `/calendar.ics?${q.toString()}` : null;
  const host = origin.replace(/^https?:\/\//, '').replace(/\/$/, '');
  return {
    ics,
    webcal: ics ? `webcal://${host}${ics}` : null,
    atom: `/changes.atom${toChangeQuery({
      country: f.country, scope: f.scope === DEFAULT_TENDER_SCOPE ? undefined : f.scope, goods: f.goods, q: f.q, cpv: f.cpv,
      cpvMain: f.cpvMain, notCpv: f.notCpv, status: f.status ?? 'open', deadlineFrom: f.deadlineFrom, deadlineTo: f.deadlineTo,
      valueMin: f.valueMin, valueMax: f.valueMax, currency: f.currency,
    })}`,
  };
}
