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
