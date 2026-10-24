/**
 * WP-90 (UX audit of 22 October 2026, section 5: the analyst path): the CPV presets and deadline presets of /tenders, and the two
 * subscriptions of a search (its deadline calendar and its change feed) with exactly its filters. Pure and import-light:
 * lib/wp90.check.ts runs it on its own.
 */
import { cpvPrefix } from './cpv';
import { DEFAULT_TENDER_SCOPE, DEFAULT_TENDER_STATUS, toChangeQuery, toTenderQuery } from './filters';
import { SCOPE_CHOICES, countryName } from './taxonomy';
import type { TenderFilters } from './types';

/**
 * Product groups a defence analyst filters by, each a set of official CPV 2008 codes (titles verbatim from the vocabulary,
 * lib/data/cpv-full.json; wp90.check.ts holds each code to it). A preset sets the CPV filter to the codes' prefixes (35700000 ->
 * 357: the code and everything under it), so it is the ordinary CPV filter, editable afterwards.
 */
export const CPV_PRESETS = [
  { id: 'military-electronics', label: 'Military electronics', group: 'goods', codes: ['35700000'] },        // Military electronic systems
  { id: 'radar-sonar', label: 'Radar and sonar', group: 'goods', codes: ['35722000', '35723000', '38115000', '38113000'] },
  { id: 'communications', label: 'Communications', group: 'goods', codes: ['35710000', '32000000'] },
  { id: 'vehicles', label: 'Vehicles and parts', group: 'goods', codes: ['35400000', '34100000', '34300000'] },
  // WP-98b (p04): the energetic materials and initiators (2461x: explosives, propellants, pyrotechnics, fuses and detonators) with 353
  { id: 'weapons', label: 'Ammunition, weapons, explosives and pyrotechnics', group: 'goods', codes: ['35300000', '24610000'] },
  // WP-98b (p02): clothing, footwear, textiles and protective clothing, not only 3581 and 181
  { id: 'uniforms', label: 'Uniforms, footwear and protective gear', group: 'goods',
    codes: ['35810000', '18100000', '18200000', '18300000', '18800000', '35113400', '39500000'] },
  // WP-98b (p03): the mechanical spare parts of the CPV (military vehicles, warships, aircraft; vehicles; other), parts of firearms, fasteners
  { id: 'parts', label: 'Machined parts and spare parts', group: 'goods',
    codes: ['35421000', '35521000', '35641000', '34320000', '34330000', '34913000', '35340000', '44530000'] },
  // WP-98b (p06): services an armed force buys
  { id: 'transport', label: 'Transport and logistics', group: 'services', codes: ['60100000', '63100000', '63520000', '63700000'] },
  { id: 'fuel', label: 'Fuel', group: 'services', codes: ['09100000'] },
  { id: 'facility', label: 'Facility management and cleaning', group: 'services', codes: ['79993000', '90900000'] },
  { id: 'catering', label: 'Catering', group: 'services', codes: ['55500000'] },
  { id: 'vehicle-repair', label: 'Vehicle repair and maintenance', group: 'services', codes: ['50100000'] },
  { id: 'training', label: 'Training', group: 'services', codes: ['80600000'] },
  { id: 'it-services', label: 'IT services', group: 'services', codes: ['72000000'] },
] as const;

/** The two rows the presets are shown in. */
export const PRESET_GROUPS = [{ id: 'goods', label: 'Goods' }, { id: 'services', label: 'Services' }] as const;

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

export interface FilterChip { label: string; /** The list without this filter. */ href: string }

const STATUS_WORDS = { open: 'Open', planned: 'Planned', closed: 'Closed', all: 'Every status' } as const;

/**
 * WP-98b (p02, phone): the filters a tender list has, one chip each with the address of the list without it, so they are seen (and
 * one is taken off) above the results while the filter panel is folded away. The defaults the page assumes are no chip.
 */
export function filterChips(f: TenderFilters, basePath: string, ref: Date): FilterChip[] {
  const out: FilterChip[] = [];
  const without = (patch: Partial<TenderFilters>, label: string) =>
    out.push({ label, href: `${basePath}${toTenderQuery({ ...f, ...patch, page: 1 })}` });
  if (f.q) without({ q: undefined }, `“${f.q}”`);
  const preset = activePreset(f.cpv);
  if (f.cpv?.length) without({ cpv: undefined, cpvMain: undefined }, preset ? preset.label : `CPV ${f.cpv.join(', ')}`);
  if (f.cpvMain) without({ cpvMain: undefined }, 'Main product code only');
  if (f.notCpv?.length) without({ notCpv: undefined }, `Not CPV ${f.notCpv.join(', ')}`);
  for (const c of f.country ?? []) without({ country: f.country?.filter((x) => x !== c) }, countryName(c));
  if (f.status && f.status !== DEFAULT_TENDER_STATUS) without({ status: undefined }, STATUS_WORDS[f.status]);
  if (f.scope && f.scope !== DEFAULT_TENDER_SCOPE) without({ scope: undefined }, SCOPE_CHOICES[f.scope].label);
  if (f.goods === 'defence') without({ goods: undefined }, 'Defence goods only');
  if (f.deadlineFrom || f.deadlineTo) {
    const n = activeDeadlinePreset(f, ref);
    without({ deadlineFrom: undefined, deadlineTo: undefined },
      n ? `Deadline in the next ${n} days` : `Deadline ${f.deadlineFrom ?? '…'} to ${f.deadlineTo ?? '…'}`);
  }
  if (f.valueMin !== undefined || f.valueMax !== undefined || f.currency) {
    const cur = f.currency ?? 'EUR';
    const n = (v: number) => v.toLocaleString('en-GB');
    without({ valueMin: undefined, valueMax: undefined, currency: undefined },
      f.valueMin !== undefined || f.valueMax !== undefined
        ? `Value ${cur} ${f.valueMin !== undefined ? n(f.valueMin) : '0'} to ${f.valueMax !== undefined ? n(f.valueMax) : 'any'}`
        : `Value stated in ${cur}`);
  }
  return out;
}

/** The ceilings of the two subscriptions, said beside them (each file says so too when it cuts: lib/ics.ts, lib/atom.ts). */
export const CALENDAR_API_MAX = 3000;
/** WP-100: the entries of one page of the Atom feed (lib/api.ts FEED_PAGE_ENTRIES); the older ones are on its next pages. */
export const FEED_MAX = 400;

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
