/**
 * Word search of the demo data (lib/mock/calls.ts). The real search is the API's (backend/dgate/textsearch.py);
 * this is the same rules in a few lines so the demo site and the e2e tests behave like it: accents and hyphens
 * folded, whole words for short queries, a small table of synonyms, and the "also searched" line.
 */
import type { SearchInfo } from './types';

const STOP = new Set(['a', 'an', 'and', 'for', 'in', 'of', 'on', 'or', 'the', 'to', 'with']);
/** The API's table (backend/dgate/textsearch.py SYNONYMS), row for row: lib/wp91.check.ts holds the two equal. */
export const SYNONYMS: string[][] = [
  ['drone', 'uas', 'uav', 'unmanned', 'rpas'],
  ['logistics', 'supply', 'mobility'],
  ['ai', 'artificial intelligence', 'machine learning'],
  ['software', 'algorithms', 'computing', 'data fusion', 'simulation'],
  ['autonomy', 'autonomous', 'uncrewed', 'robotic', 'robotics', 'swarm'],
  ['cyber', 'cybersecurity', 'cyber security', 'cyber defence'],
  ['sme', 'smes', 'small and medium', 'pme', 'pyme', 'msp'],
  // WP-99: ASAP (the Act in Support of Ammunition Production) also finds the EDIP calls; no primary source in the repository names
  // its successor, so no note is shown
  ['asap', 'edip'],
];

/**
 * WP-91 (UX audit 6): a programme a visitor searches for that no source we read publishes as one of its own. The empty result says so
 * instead of "nothing matches". No link: no source in this repository names an official page for it.
 */
const NOT_COLLECTED: Record<string, string> = {
  eudis: 'EUDIS, the EU Defence Innovation Scheme, is not a programme we collect: no source we read publishes calls under that name. Calls the EU portal files under the European Defence Fund are listed here as EDF.',
};

/** The sentences for the words of a search that name a programme we do not collect. */
export function notCollected(q: string | undefined): string[] {
  if (!q) return [];
  return [...new Set(fold(q).split(' ').filter((w) => NOT_COLLECTED[w]))].map((w) => NOT_COLLECTED[w]);
}

/** Lower case, no accents, words separated by single spaces. */
export function fold(text: string): string {
  return text.normalize('NFKD').replace(/\p{M}/gu, '').replace(/ł/gi, 'l').replace(/ø/gi, 'o').toLowerCase()
    .split(/[^\p{L}\p{N}]+/u).filter(Boolean).join(' ');
}

function wordMatches(wanted: string, have: string): boolean {
  if (wanted.length <= 3) return have === wanted;
  if (wanted.length === 4) return have.startsWith(wanted);
  return have.includes(wanted);
}

function phraseIn(phrase: string[], tokens: string[], same: (w: string, h: string) => boolean): boolean {
  for (let i = 0; i + phrase.length <= tokens.length; i++) {
    if (phrase.every((w, j) => same(w, tokens[i + j]))) return true;
  }
  return false;
}

const codeMatches = (w: string, h: string) => h.startsWith(w) || (w.length >= 5 && h.includes(w));

export interface WordQuery extends SearchInfo {
  matches(text: string, codes?: string): boolean;
}

/** null when the text holds no word at all. */
export function parseQuery(q: string): WordQuery | null {
  const typed = fold(q).split(' ').filter(Boolean).slice(0, 16);
  const kept = (typed.filter((w) => !STOP.has(w)).length > 0 ? typed.filter((w) => !STOP.has(w)) : typed).slice(0, 8);
  if (kept.length === 0) return null;
  const groups = kept.map((w) => {
    const alts = [[w]];
    for (const row of SYNONYMS) if (row.includes(w)) for (const o of row) if (o !== w) alts.push(o.split(' '));
    return alts;
  });
  const also = [...new Set(kept.flatMap((w) => SYNONYMS.filter((r) => r.includes(w)).flatMap((r) => r.filter((o) => o !== w))))]
    .filter((a) => !kept.includes(a));
  return {
    terms: kept, alsoSearched: also,
    matches(text, codes = '') {
      const have = fold(text).split(' ');
      const ids = fold(codes).split(' ');
      return groups.every((g) => g.some((alt) => phraseIn(alt, have, wordMatches) || phraseIn(alt, ids, codeMatches)));
    },
  };
}
