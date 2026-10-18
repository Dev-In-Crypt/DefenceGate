/**
 * Pure helpers of the networks pages (organisations, projects, partners): what a URL asks for, the words for a role
 * and for how a participant was recognised, and the figures behind the funding chart. Import-free apart from types, so
 * lib/networks.check.ts runs on it alone.
 */
import type { FundingRow, OrgFilters } from './networks-types';

type SearchParams = Record<string, string | string[] | undefined>;

export const ORG_PAGE_SIZE = 20;
export const PARTNER_PAGE_SIZE = 20;
export const PROJECT_PAGE_SIZE = 20;
const MAX_PAGE = 1000;
const MAX_QUERY = 100;

/** Programmes the networks data carries (the rest is not offered as a choice; a typed one is still passed on). */
export const PROGRAMME_CHOICES: { value: string; label: string }[] = [
  { value: 'EDF', label: 'European Defence Fund' },
  { value: 'HORIZON', label: 'Horizon Europe' },
  { value: 'H2020', label: 'Horizon 2020' },
  { value: 'FP7', label: 'Seventh Framework Programme' },
];
export const PROGRAMME_WORD: Record<string, string> = Object.fromEntries(PROGRAMME_CHOICES.map((p) => [p.value, p.label]));

export const ROLES = ['coordinator', 'participant', 'partner', 'associated_partner', 'international_partner', 'third_party'] as const;
const ROLE_WORD: Record<string, string> = {
  coordinator: 'Coordinator', participant: 'Participant', partner: 'Partner', associated_partner: 'Associated partner',
  international_partner: 'International partner', third_party: 'Third party',
};
export const roleWord = (role: string) => ROLE_WORD[role] ?? role.replace(/_/g, ' ');

export const MIN_PROJECT_CHOICES = [2, 5, 10, 25];
export const ORG_SORTS = ['projects', 'name'] as const;
export const DEFAULT_ORG_SORT = 'projects';

/** How a participant was recognised as an organisation we hold (`participation.resolution_method`). */
const METHOD_WORD: Record<string, string> = {
  pic: 'PIC', alias: 'known name', exact_name: 'exact name', exact_name_ambiguous: 'name shared with others',
  national_id: 'registration number', vat: 'VAT number',
};
export const methodWord = (m: string) => METHOD_WORD[m] ?? m.replace(/_/g, ' ');

/** An organisation or project slug is "<id>-<words>"; anything else cannot be one and never reaches the API. */
const SLUG_RE = /^[0-9]{1,9}(-[a-z0-9-]{0,80})?$/;
export const isNetworkSlug = (s: string) => SLUG_RE.test(s);

function first(v: string | string[] | undefined): string | undefined { return Array.isArray(v) ? v[0] : v; }
/** The comma-separated values, folded (case) before the repeats are dropped, at most 20. */
function tokens(v: string | string[] | undefined, fold: (s: string) => string = (s) => s): string[] {
  if (!v) return [];
  return [...new Set((Array.isArray(v) ? v : [v]).flatMap((s) => s.split(',')).map((s) => fold(s.trim())).filter(Boolean))].slice(0, 20);
}
function pageOf(v: string | undefined): number {
  const n = Number(v);
  return Number.isFinite(n) && n >= 1 ? Math.min(Math.floor(n), MAX_PAGE) : 1;
}

export function parseOrgFilters(sp: SearchParams): OrgFilters {
  const q = Array.from((first(sp.q) ?? '').trim()).slice(0, MAX_QUERY).join('').trim();
  const sort = (ORG_SORTS as readonly string[]).includes(first(sp.sort) ?? '') ? (first(sp.sort) as 'projects' | 'name') : DEFAULT_ORG_SORT;
  const min = Number(first(sp.min));
  return {
    q: q || undefined,
    country: tokens(sp.country, (c) => c.toUpperCase()).filter((c) => /^[A-Z]{2}$/.test(c)),
    programme: tokens(sp.programme, (c) => c.toUpperCase()).filter((c) => /^[A-Z0-9_-]{1,20}$/.test(c)),
    role: tokens(sp.role, (c) => c.toLowerCase()).filter((c) => (ROLES as readonly string[]).includes(c)),
    minProjects: Number.isFinite(min) && min >= 2 ? Math.min(Math.floor(min), 1000) : undefined,
    sort, page: pageOf(first(sp.page)), pageSize: ORG_PAGE_SIZE,
  };
}

function params(f: OrgFilters): URLSearchParams {
  const p = new URLSearchParams();
  if (f.q) p.set('q', f.q);
  if (f.country?.length) p.set('country', f.country.join(','));
  if (f.programme?.length) p.set('programme', f.programme.join(','));
  if (f.role?.length) p.set('role', f.role.join(','));
  if (f.minProjects) p.set('min', String(f.minProjects));
  if (f.sort && f.sort !== DEFAULT_ORG_SORT) p.set('sort', f.sort);
  if (f.page && f.page > 1) p.set('page', String(f.page));
  return p;
}

/** The query string of the site's own URL (defaults left out). */
export function toOrgQuery(f: OrgFilters): string {
  const s = params(f).toString();
  return s ? `?${s}` : '';
}

/** The query string the API takes (`minProjects`, and the page size). */
export function orgApiQuery(f: OrgFilters): string {
  const p = params(f);
  if (p.has('min')) { p.set('minProjects', p.get('min') as string); p.delete('min'); }
  p.set('sort', f.sort ?? DEFAULT_ORG_SORT);
  p.set('pageSize', String(f.pageSize ?? ORG_PAGE_SIZE));
  return `?${p.toString()}`;
}

export function activeOrgFilterCount(f: OrgFilters): number {
  return [f.q, f.country?.length, f.programme?.length, f.role?.length, f.minProjects].filter(Boolean).length;
}

export function yearsLabel(first: number | null, last: number | null): string {
  if (first === null && last === null) return 'Not stated';
  if (first === null || last === null || first === last) return String(first ?? last);
  return `${first} to ${last}`;
}

export function formatEur(n: number | null): string {
  return n === null ? 'Not stated' : `EUR ${Math.round(n).toLocaleString('en-GB')}`;
}

export interface FundingGroup {
  programme: string;
  /** `eur`: the bars show EU contribution; `projects`: no amount is stated for this programme, so they show projects. */
  measure: 'eur' | 'projects';
  rows: { year: number | null; projects: number; euContribution: number | null; projectsWithoutAmount: number; width: number }[];
  totalProjects: number;
  totalEur: number | null;
}

/**
 * The funding rows grouped by programme, in the order of the most projects first, with the bar width (1 to 100) of each year
 * against the largest of its own programme. A programme that states no amount (EDF) is drawn in projects, and says so.
 */
export function fundingGroups(rows: FundingRow[]): FundingGroup[] {
  const by = new Map<string, FundingRow[]>();
  for (const r of rows) by.set(r.programme, [...(by.get(r.programme) ?? []), r]);
  const out: FundingGroup[] = [];
  for (const [programme, rs] of by) {
    const measure = rs.some((r) => (r.euContribution ?? 0) > 0) ? 'eur' : 'projects';
    const value = (r: FundingRow) => (measure === 'eur' ? r.euContribution ?? 0 : r.projects);
    const top = Math.max(1, ...rs.map(value));
    const sorted = [...rs].sort((a, b) => (a.year ?? 9999) - (b.year ?? 9999));
    out.push({
      programme, measure,
      rows: sorted.map((r) => ({
        year: r.year, projects: r.projects, euContribution: r.euContribution, projectsWithoutAmount: r.projectsWithoutAmount,
        width: value(r) <= 0 ? 0 : Math.max(1, Math.round((value(r) / top) * 100)),
      })),
      totalProjects: rs.reduce((n, r) => n + r.projects, 0),
      totalEur: rs.some((r) => r.euContribution !== null) ? rs.reduce((n, r) => n + (r.euContribution ?? 0), 0) : null,
    });
  }
  return out.sort((a, b) => b.totalProjects - a.totalProjects || a.programme.localeCompare(b.programme));
}
