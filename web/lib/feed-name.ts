/**
 * WP-100: the name a subscription carries in a feed reader or a calendar app ("DefenceGate: radar, DE+PL"), so three
 * subscriptions are not three "DefenceGate: what changed" (persona round of 23 October 2026, p02). Pure and import-free:
 * lib/wp100.check.ts runs it on its own.
 */
export interface FeedSearch {
  q?: string;
  country?: string[];
  cpv?: string[];
  notCpv?: string[];
  scope?: string;
  goods?: string;
  status?: string;
}

const MAX = 80;

/** What the search is, in a few words: the search text, the countries, the codes; empty for no search. */
export function searchSummary(f: FeedSearch): string {
  const parts = [
    f.q ? f.q.trim() : '',
    f.country?.length ? f.country.join('+') : '',
    f.cpv?.length ? `CPV ${f.cpv.join('+')}` : '',
    f.notCpv?.length ? `not CPV ${f.notCpv.join('+')}` : '',
    // the scope's short labels (lib/taxonomy.ts SCOPE_CHOICES), lower case
    f.scope === 'core' ? 'military goods and works' : f.scope === 'supply' ? 'other purchases by armed forces' : f.scope === 'all' ? 'all notices' : '',
    f.goods === 'defence' ? 'defence goods' : '',
    f.status && f.status !== 'open' ? f.status : '',
  ].filter(Boolean);
  const s = parts.join(', ');
  return s.length > MAX ? `${s.slice(0, MAX - 1).trimEnd()}…` : s;
}

/** `base` alone without a search; with one, the search after it ("DefenceGate deadlines: radar, DE+PL"). */
export function feedName(base: string, f: FeedSearch): string {
  const s = searchSummary(f);
  return s ? `${base}: ${s}` : base;
}
