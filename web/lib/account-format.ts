/**
 * Plain helpers for the account pages and the save/follow islands. No server-only import: the islands use
 * them too. Nothing here reads a cookie or calls the API.
 */
import type { Cadence, FollowKind, Role, SearchFilters, SearchKind, ShortlistKind, ShortlistStatus, Track } from './types';
import { PROGRAMMES, REGIMES, countryName } from './taxonomy';
import { formatDateUtc, formatNumber } from './format';

export const STATUS_LABEL: Record<ShortlistStatus, string> = {
  watching: 'Watching', evaluating: 'Evaluating', bidding: 'Bidding', submitted: 'Submitted', dropped: 'Dropped',
};
export const STATUS_ORDER: ShortlistStatus[] = ['watching', 'evaluating', 'bidding', 'submitted', 'dropped'];

export const ROLE_LABEL: Record<Role, string> = {
  supplier: 'Supplier or manufacturer', prime: 'Prime contractor', consultant: 'Consultant',
  grant_writer: 'Grant writer', other: 'Other',
};
export const TRACK_LABEL: Record<Track, string> = { tenders: 'Tenders', funding: 'Funding calls' };
export const CADENCE_LABEL: Record<Cadence, string> = { instant: 'Instant', daily: 'Daily digest', weekly: 'Weekly summary', off: 'Off' };
export const KIND_LABEL: Record<SearchKind, string> = { tender: 'Tenders', call: 'Funding calls' };

/** Public detail pages look up the leading id only, so an id alone is a working link (it redirects to the full slug). */
const ID_RE = /^[0-9]{1,9}$/;
const SLUG_RE = /^[0-9]{1,9}(-[a-z0-9-]{0,80})?$/;

export function itemHref(kind: ShortlistKind, ref: string, slug?: string | null): string | null {
  const s = slug && SLUG_RE.test(slug) ? slug : ID_RE.test(ref) ? ref : null;
  return s ? `${kind === 'tender' ? '/tenders' : '/funding'}/${s}` : null;
}

export function followHref(kind: FollowKind, ref: string, slug?: string | null): string | null {
  if (kind === 'programme') return /^[A-Z_]{2,20}$/.test(ref) ? `/funding?programme=${ref}` : null;
  const s = slug && SLUG_RE.test(slug) ? slug : ID_RE.test(ref) ? ref : null;
  return s ? `/buyers/${s}` : null;
}

/** The query keys the public list pages read. Anything else in a stored filter is dropped from the link. */
export const FILTER_KEYS: Record<SearchKind, readonly string[]> = {
  tender: ['q', 'country', 'status', 'scope', 'from', 'to', 'min', 'max', 'currency', 'sort'],
  call: ['q', 'programme', 'regime', 'country', 'status', 'from', 'to', 'min', 'max', 'currency', 'sort'],
};

function text(v: SearchFilters[string] | undefined): string {
  if (v === undefined) return '';
  return Array.isArray(v) ? v.join(',') : String(v);
}

/** Link to the public list page with the stored filters applied. */
export function searchHref(kind: SearchKind, filters: SearchFilters): string {
  const p = new URLSearchParams();
  for (const k of FILTER_KEYS[kind]) {
    const v = text(filters[k]);
    if (v) p.set(k, v);
  }
  const q = p.toString();
  return `${kind === 'tender' ? '/tenders' : '/funding'}${q ? `?${q}` : ''}`;
}

const STATUS_WORDS: Record<string, string> = {
  open: 'Open', closed: 'Closed', all: 'Any status', forthcoming: 'Opens soon', 'closing-soon': 'Closing soon',
};
const SCOPE_WORDS: Record<string, string> = { core: 'Defence notices', supply: 'Supplies to defence buyers', all: 'All notices' };

const codes = (v: string) => v.split(',').map((s) => s.trim()).filter(Boolean);

/** A short, human list of what a stored filter selects. Always starts with the status; never empty. */
export function describeFilters(kind: SearchKind, filters: SearchFilters): string[] {
  const out: string[] = [];
  const status = text(filters.status) || 'open';
  out.push(STATUS_WORDS[status] ?? status);
  if (kind === 'tender') {
    const scope = text(filters.scope) || 'core';
    out.push(SCOPE_WORDS[scope] ?? scope);
  }
  const q = text(filters.q);
  if (q) out.push(`Keyword "${q.slice(0, 60)}"`);
  const programme = codes(text(filters.programme));
  if (kind === 'call' && programme.length) out.push(programme.map((c) => PROGRAMMES[c as keyof typeof PROGRAMMES]?.label ?? c).join(', '));
  const regime = codes(text(filters.regime));
  if (kind === 'call' && regime.length) out.push(regime.map((c) => REGIMES[c as keyof typeof REGIMES] ?? c).join(', '));
  const country = codes(text(filters.country));
  if (country.length) out.push(`${kind === 'tender' ? 'Buyer' : 'Funder'} country: ${country.map(countryName).join(', ')}`);
  const from = text(filters.from);
  const to = text(filters.to);
  if (from) out.push(`Deadline from ${from}`);
  if (to) out.push(`Deadline to ${to}`);
  const cur = text(filters.currency).toUpperCase() || 'EUR';
  const noun = kind === 'tender' ? 'Value' : 'Budget';
  const min = Number(text(filters.min));
  const max = Number(text(filters.max));
  if (text(filters.min) && Number.isFinite(min)) out.push(`${noun} from ${cur} ${formatNumber(min)}`);
  if (text(filters.max) && Number.isFinite(max)) out.push(`${noun} up to ${cur} ${formatNumber(max)}`);
  return out;
}

/** A starting name for a new saved search, at most 80 characters. */
export function suggestSearchName(kind: SearchKind, filters: SearchFilters): string {
  const parts = describeFilters(kind, filters).filter((p) => p !== 'Open' && p !== 'Defence notices');
  const name = parts.length ? `${KIND_LABEL[kind]}: ${parts.slice(0, 3).join(', ')}` : `All open ${KIND_LABEL[kind].toLowerCase()}`;
  return name.slice(0, 80);
}

/**
 * The filters of a list page as a stored search wants them: the URL query without page and pageSize, every
 * value a string (lists comma-joined, as the list endpoints read them).
 */
export function filtersFromQuery(query: string): SearchFilters {
  const out: SearchFilters = {};
  for (const [k, v] of new URLSearchParams(query)) {
    if (k === 'page' || k === 'pageSize' || k === 'view') continue;
    if (v) out[k] = v;
  }
  return out;
}

/** "26 Nov 2026, 16:05 UTC": a moment, for session lists. Unlike deadlines, midnight is a real time here. */
export function formatStamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${formatDateUtc(iso)}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}
