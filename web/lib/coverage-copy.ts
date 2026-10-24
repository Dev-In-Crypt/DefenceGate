/**
 * What the site says about the national portals it reads, worked out from /v1/sources and not written by hand: the
 * copy said "four countries only" and "Germany is TED only" for days after the German federal feed went live
 * (UX walk-through 16 October 2026). Pure of Next.js so lib/ui.check.ts can run it.
 */
import { countryName } from './taxonomy';

export interface PortalSource { id: string; type: string; country: string | null }

/** Tender sources that are a country's own portal or feed: a country is named, and the load is not a one-off. */
const ONE_OFF = new Set(['pl_atlas']);

/** ISO codes of the countries whose national portal or feed we read, ordered by name. */
export function nationalCountries(sources: PortalSource[]): string[] {
  const codes = new Set(sources.filter((s) => s.type === 'tenders' && s.country && s.country !== 'EU' && !ONE_OFF.has(s.id)).map((s) => s.country as string));
  return [...codes].sort((a, b) => countryName(a).localeCompare(countryName(b)));
}

const NUMBER_WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];

/** "France, Germany, the Netherlands, Poland and Spain" */
export function listWords(names: string[]): string {
  const said = names.map((n) => (n === 'Netherlands' ? 'the Netherlands' : n));
  return said.length < 2 ? said.join('') : `${said.slice(0, -1).join(', ')} and ${said.at(-1)}`;
}

export interface PortalWords {
  /** How many countries, as a word below eleven: "five". */
  count: string;
  /** The countries, said as a list. */
  names: string;
}

export function portalWords(sources: PortalSource[]): PortalWords {
  const codes = nationalCountries(sources);
  return { count: NUMBER_WORDS[codes.length] ?? String(codes.length), names: listWords(codes.map(countryName)) };
}

/**
 * WP-98b (persona round of 23 October 2026, p02, p06, p07): what we collect for a country, said in one line where its results are
 * (/tenders, /suppliers, /market and their empty states), so an empty or a small result does not read as "this country buys none".
 * Mirrored from the tender sources /data lists (the `source` rows of backend/migrations; lib/wp98b.check.ts holds the two together):
 * a country here is one whose own portal or feed we read, every other country is TED only. `awards`: the national award results
 * the supplier map reads (only PLACSP's, WP-61); every other country's winners are TED's.
 */
export const NATIONAL_COVERAGE: Record<string, { portal: string; since?: string; note?: string; awards?: boolean }> = {
  DE: { portal: 'the federal notice service', since: '25 October 2023', note: 'state and municipal portals are not collected' },
  ES: { portal: 'PLACSP', awards: true },
  FR: { portal: 'BOAMP' },
  NL: { portal: 'TenderNed', since: 'January 2026', note: 'in practice chiefly one buyer, the Ministry of Defence' },
  PL: { portal: 'e-Zamówienia' },
};

/** The line for one country: notices (`tenders`, also /market) or the winners of the supplier map (`awards`). No full stop. */
export function coverageLine(country: string, kind: 'tenders' | 'awards' = 'tenders'): string {
  const name = countryName(country);
  const n = NATIONAL_COVERAGE[country];
  if (kind === 'awards') {
    if (n?.awards) return `${name}: winners from TED and from ${n.portal}'s award results`;
    return `${name}: winners from TED only${n ? `; ${n.portal}'s award notices are not read` : '; the national portal is not collected'}`;
  }
  if (!n) return `${name}: TED only; the national portal is not collected`;
  return `${name}: TED + ${n.portal}${n.since ? ` (since ${n.since})` : ''}${n.awards ? ', awards too' : ''}${n.note ? `; ${n.note}` : ''}`;
}

/** The lines of the countries chosen, one sentence each; none for no country (or more than `max`, a line each says nothing then). */
export function coverageLines(countries: string[] | undefined, kind: 'tenders' | 'awards' = 'tenders', max = 6): string[] {
  const codes = [...new Set((countries ?? []).filter((c) => c && c !== 'EU'))];
  return codes.length > max ? [] : codes.map((c) => `${coverageLine(c, kind)}.`);
}
