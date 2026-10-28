/**
 * WP-154: company signals (/signals): facts about companies from public procurement and EU defence funding, for investors and
 * analysts. The shapes of GET /v1/signals/{kind} and /v1/account/signals/{kind} (backend dgate/signals.py), the page's filters,
 * what the paid part shows, and the CSV. No imports beyond relative ones: lib/wp154.check.ts compiles it on its own.
 */
import type { Cell } from './csv';

export type SignalKind = 'growing' | 'markets' | 'funding';
export const SIGNAL_KINDS: readonly SignalKind[] = ['growing', 'markets', 'funding'];
export const SIGNAL_PROGRAMMES = ['EDF', 'EDIDP', 'EDIP', 'PADR'] as const;
export const NOT_ADVICE = 'Facts from public records, not investment advice.';
export const FULL_PAGE_SIZE = 50;
export const CSV_ROWS = 2000;

export interface SignalCompany { id: string; slug: string; name: string; country: string | null }
export interface SignalNotice { id: string; slug: string; noticeId: string; title: string; publishedAt: string | null; sourceUrl: string | null; source: string }
export interface SignalSum { currency: string; amount: number; count: number }
export interface GrowingRow {
  company: SignalCompany; recent: number; prior: number; recentValues: SignalSum[]; priorValues: SignalSum[];
  comparable: { currency: string; recent: number; recentCount: number; prior: number; priorCount: number } | null;
  latest: SignalNotice | null;
}
export interface MarketRow { company: SignalCompany; market: string; firstWinAt: string | null; winsThere: number; winsBefore: number; firstWin: SignalNotice | null }
export interface SignalProject { slug: string; acronym: string | null; title: string; programme: string; year: number | null; role: string; source: string; factsheetUrl: string | null }
export interface FundingRow { company: SignalCompany; year: number; first: boolean; newProjects: number; earlierProjects: number; projects: SignalProject[] }
export type SignalRow = GrowingRow | MarketRow | FundingRow;

export interface SignalAnswer<R = SignalRow> {
  kind: SignalKind; asOf: string; recentFrom: string; priorFrom: string; windowFrom: string; minRecent: number;
  items: R[]; total: number; offset: number; fullOpen: boolean; freeRows: number; note: string;
  sources: { code: string; name: string; attribution: string | null }[];
  page?: number; pageSize?: number;
  /** WP-155: the anonymous answer, whose rows leave out the companies with fewer than `smallBelow` procurements (mosaic rule). */
  public?: boolean; smallBelow?: number;
  /** WP-155: the account may download the CSV (Team and Consultant, or anyone while no plan is on sale). */
  csv?: boolean;
}

/**
 * WP-155: the line under the first rows (never the full list). The count is the whole list's, whoever looks. Anonymous, the rows
 * leave out small companies (mosaic rule), so the line says so, and that signing in shows the rest when the full list is open.
 */
export function firstRowsLine(a: Pick<SignalAnswer, 'items' | 'total' | 'public' | 'smallBelow' | 'fullOpen'>): string {
  const total = a.total.toLocaleString('en-GB');
  const noun = a.total === 1 ? 'company' : 'companies';
  if (a.items.length >= a.total) return `All ${total} ${noun}.`;
  if (!a.public) return `The first ${a.items.length} of ${total} ${noun}.`;
  const rest = a.fullOpen ? '; sign in for the rest' : '';
  return `${a.items.length} of ${total} ${noun} shown${rest}. Rows of companies with fewer than ${a.smallBelow ?? 10} awarded procurements in three years are shown only after sign-in.`;
}

export interface SignalFilters { kind: SignalKind; country: string; cpv: string; programme: string; page: number }

type SP = Record<string, string | string[] | undefined>;
const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? '';

/** The page's query as the API takes it: a kind, the company's country (code or English name), a CPV prefix, a programme. */
export function parseSignalFilters(sp: SP): SignalFilters {
  const asked = first(sp.kind);
  const kind = (SIGNAL_KINDS as readonly string[]).includes(asked) ? (asked as SignalKind) : 'growing';
  const country = first(sp.country).replace(/[^\p{L}\p{M}\s,.'’&-]/gu, '').replace(/\s+/g, ' ').trim().slice(0, 60);
  // CPV only for the procurement signals, a programme only for funding: the API refuses the other (422)
  const cpv = kind === 'funding' ? '' : first(sp.cpv).replace(/[^0-9,]/g, '').slice(0, 40);
  const programme = kind === 'funding' ? first(sp.programme).toUpperCase().split(',').filter((p) => (SIGNAL_PROGRAMMES as readonly string[]).includes(p)).join(',') : '';
  const n = Number(first(sp.page));
  const page = Number.isFinite(n) && n >= 1 ? Math.min(Math.floor(n), 1000) : 1;
  return { kind, country, cpv, programme, page };
}

/** The API's query string of the filters (no page). */
export function signalQuery(f: Pick<SignalFilters, 'country' | 'cpv' | 'programme'>): string {
  const p = new URLSearchParams();
  if (f.country) p.set('country', f.country);
  if (f.cpv) p.set('cpv', f.cpv);
  if (f.programme) p.set('programme', f.programme);
  return p.toString();
}

/** A link to the page with these filters (`page` 1 is left out). */
export function signalHref(f: SignalFilters, over: Partial<SignalFilters> = {}, path = '/signals'): string {
  const g = { ...f, ...over };
  const p = new URLSearchParams();
  if (g.kind !== 'growing') p.set('kind', g.kind);
  const q = new URLSearchParams(signalQuery(g));
  q.forEach((v, k) => p.set(k, v));
  if (g.page > 1) p.set('page', String(g.page));
  return `${path}${p.size ? `?${p.toString()}` : ''}`;
}

/**
 * What the visitor gets beyond the first rows. `closed`: the paid part is switched off (nothing offered); `signin`: open, not
 * signed in; `plan`: signed in, the plan does not include it; `full`: the whole list and the CSV. From the public answer's
 * `fullOpen` and the status of the account call (0: not asked).
 */
export type FullState = 'closed' | 'signin' | 'plan' | 'full';
export function fullState(fullOpen: boolean, accountStatus: number): FullState {
  if (!fullOpen || accountStatus === 404) return 'closed';
  if (accountStatus === 200) return 'full';
  if (accountStatus === 402) return 'plan';
  return 'signin';
}

export const KIND_TITLE: Record<SignalKind, string> = {
  growing: 'Growing in defence',
  markets: 'New markets',
  funding: 'New EU defence funding',
};

/** One line on what a row of the kind is, with its windows (shown under the tabs). */
export function kindLine(a: Pick<SignalAnswer, 'kind' | 'recentFrom' | 'priorFrom' | 'windowFrom' | 'minRecent'>, day: (iso: string) => string, latestYear?: number | null): string {
  if (a.kind === 'growing') return `Companies with more awarded defence procurements from ${day(a.recentFrom)} than in the 12 months before (at least ${a.minRecent}).`;
  if (a.kind === 'markets') return `A company's first win with the buyers of a country since ${day(a.recentFrom)}, after wins elsewhere (records from ${day(a.windowFrom)}).`;
  return `Companies in projects of the ${latestYear ?? 'latest'} calls of the EU defence programmes (EDF, EDIDP, EDIP, PADR), first participations first.`;
}

const money = (n: number) => Math.round(n).toLocaleString('en-GB');

/** "EUR 3,000,000 (2) against EUR 500,000 (1)", or null when no currency has contract values in both periods. */
export function comparableLine(r: GrowingRow): string | null {
  const c = r.comparable;
  return c ? `${c.currency} ${money(c.recent)} (${c.recentCount}) against ${c.currency} ${money(c.prior)} (${c.priorCount})` : null;
}

export const SIGNAL_CSV_HEADER: Record<SignalKind, string[]> = {
  growing: ['company', 'company_country', 'procurements_last_12_months', 'procurements_12_months_before', 'currency', 'contract_value_last_12_months', 'valued_last_12_months', 'contract_value_12_months_before', 'valued_12_months_before', 'latest_notice', 'latest_notice_url', 'company_page'],
  markets: ['company', 'company_country', 'new_market', 'first_win', 'wins_there', 'wins_before_elsewhere', 'first_win_notice', 'first_win_url', 'company_page'],
  funding: ['company', 'company_country', 'call_year', 'first_participation', 'new_projects', 'earlier_defence_projects', 'projects', 'company_page'],
};

/** The CSV rows of an answer; `site` is the absolute origin for the company page links. */
export function signalCsvRows(kind: SignalKind, items: SignalRow[], site: string): Cell[][] {
  return items.map((it) => {
    const c = it.company;
    if (kind === 'growing') {
      const r = it as GrowingRow;
      const v = r.comparable;
      return [c.name, c.country, r.recent, r.prior, v?.currency, v?.recent, v?.recentCount, v?.prior, v?.priorCount, r.latest?.noticeId, r.latest?.sourceUrl, `${site}/suppliers/${c.slug}`];
    }
    if (kind === 'markets') {
      const r = it as MarketRow;
      return [c.name, c.country, r.market, r.firstWinAt?.slice(0, 10), r.winsThere, r.winsBefore, r.firstWin?.noticeId, r.firstWin?.sourceUrl, `${site}/suppliers/${c.slug}`];
    }
    const r = it as FundingRow;
    return [c.name, c.country, r.year, r.first ? 'yes' : 'no', r.newProjects, r.earlierProjects, r.projects.map((p) => p.acronym ?? p.title).join(' | '), `${site}/organisations/${c.slug}`];
  });
}
