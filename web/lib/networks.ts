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
/** WP-88: a programme by its name, never by the code alone (EDIDP and PADR are named in the glossary and About this data). */
export const PROGRAMME_WORD: Record<string, string> = {
  ...Object.fromEntries(PROGRAMME_CHOICES.map((p) => [p.value, p.label])),
  EDIDP: 'European Defence Industrial Development Programme', PADR: 'Preparatory Action on Defence Research',
};
export const programmeName = (code: string) => PROGRAMME_WORD[code] ?? code;

/**
 * The programmes a defence reader means when none is chosen (U10 of the UX verification: the directory opened with CNRS and
 * Oxford, and the Ukraine partners with a cultural-animation firm, because CORDIS is mostly civil research). "All programmes"
 * is one visible choice away (`programme=all`).
 */
export const DEFENCE_PROGRAMMES = ['EDF', 'EDIDP', 'PADR'];
export const DEFENCE_PROGRAMMES_WORDS = 'the European Defence Fund and its two predecessor programmes';

/** The programmes a request filters by: all of them (none), the ones chosen, or the defence-relevant ones. */
export function effectiveProgrammes(f: Pick<OrgFilters, 'programme' | 'allProgrammes'>): string[] {
  return f.allProgrammes ? [] : f.programme?.length ? f.programme : DEFENCE_PROGRAMMES;
}

export const ROLES = ['coordinator', 'participant', 'partner', 'associated_partner', 'international_partner', 'third_party'] as const;
const ROLE_WORD: Record<string, string> = {
  coordinator: 'Coordinator', participant: 'Participant', partner: 'Partner', associated_partner: 'Associated partner',
  international_partner: 'International partner', third_party: 'Third party',
};
export const roleWord = (role: string) => ROLE_WORD[role] ?? role.replace(/_/g, ' ');

/**
 * The EDF capability categories are named by abbreviations in the Commission's own file names. These are our plain reading of the
 * abbreviation (UX walk-through U11: the page listed SMERO 33, DIS 23 with no meaning); a category whose abbreviation we do not
 * read with confidence has no entry and shows the code alone. The EDF work programme is authoritative.
 */
export const EDF_CATEGORY_WORDS: Record<string, string> = {
  GROUND: 'Ground combat', CYBER: 'Cyber', SPACE: 'Space', NAVAL: 'Naval combat', AIR: 'Air combat', AIRDEF: 'Air defence',
  UWW: 'Underwater warfare', SENS: 'Sensors', C4ISR: 'Command, control, communications, computers, intelligence, surveillance and reconnaissance',
  MCBRN: 'Medical and CBRN', DIGIT: 'Digital', ENERENV: 'Energy and environment', MATCOMP: 'Materials and components',
  PROTMOB: 'Protection and mobility', SIMTRAIN: 'Simulation and training', DIS: 'Disruptive technologies', SME: 'Small and medium enterprises',
  SMERO: 'Small and medium enterprises and research organisations',
};

/** Programmes the consortium analysis can be run on. An EDF one needs no topic; any other needs the start of a topic code. */
export const GAP_PROGRAMMES: { value: string; label: string }[] = [
  { value: 'EDF', label: 'European Defence Fund' }, { value: 'EDIDP', label: 'European Defence Industrial Development Programme' }, { value: 'PADR', label: 'Preparatory Action on Defence Research' },
  { value: 'HORIZON', label: 'Horizon Europe (needs a topic code start)' }, { value: 'H2020', label: 'Horizon 2020 (needs a topic code start)' },
];

export const MIN_PROJECT_CHOICES = [2, 5, 10, 25];
export const ORG_SORTS = ['defence', 'projects', 'name'] as const;

/**
 * The order the directory opens on. Limited to the defence programmes (the default), it is by the number of defence projects:
 * the all-programme total put CNRS (4,336 projects, 10 of them in the EDF) above the firms that build defence projects.
 * Any list that includes a civil programme opens on all projects.
 */
export function defaultOrgSort(f: Pick<OrgFilters, 'programme' | 'allProgrammes'>): 'defence' | 'projects' {
  const programmes = effectiveProgrammes(f);
  return programmes.length > 0 && programmes.every((c) => DEFENCE_PROGRAMMES.includes(c)) ? 'defence' : 'projects';
}

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
  const asked = first(sp.sort) ?? '';
  const min = Number(first(sp.min));
  const programmes = tokens(sp.programme, (c) => c.toUpperCase()).filter((c) => /^[A-Z0-9_-]{1,20}$/.test(c));
  const all = programmes.includes('ALL');
  const sort = (ORG_SORTS as readonly string[]).includes(asked) ? (asked as 'defence' | 'projects' | 'name')
    : defaultOrgSort({ programme: all ? [] : programmes, allProgrammes: all });
  return {
    q: q || undefined,
    country: tokens(sp.country, (c) => c.toUpperCase()).filter((c) => /^[A-Z]{2}$/.test(c)),
    programme: all ? [] : programmes,
    ...(all ? { allProgrammes: true } : {}),
    role: tokens(sp.role, (c) => c.toLowerCase()).filter((c) => (ROLES as readonly string[]).includes(c)),
    minProjects: Number.isFinite(min) && min >= 2 ? Math.min(Math.floor(min), 1000) : undefined,
    sort, page: pageOf(first(sp.page)), pageSize: ORG_PAGE_SIZE,
  };
}

function params(f: OrgFilters): URLSearchParams {
  const p = new URLSearchParams();
  if (f.q) p.set('q', f.q);
  if (f.country?.length) p.set('country', f.country.join(','));
  if (f.allProgrammes) p.set('programme', 'all');
  else if (f.programme?.length) p.set('programme', f.programme.join(','));
  if (f.role?.length) p.set('role', f.role.join(','));
  if (f.minProjects) p.set('min', String(f.minProjects));
  if (f.sort && f.sort !== defaultOrgSort(f)) p.set('sort', f.sort);
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
  const programmes = effectiveProgrammes(f);
  if (programmes.length) p.set('programme', programmes.join(',')); else p.delete('programme');
  if (p.has('min')) { p.set('minProjects', p.get('min') as string); p.delete('min'); }
  p.set('sort', f.sort ?? defaultOrgSort(f));
  p.set('pageSize', String(f.pageSize ?? ORG_PAGE_SIZE));
  return `?${p.toString()}`;
}

export function activeOrgFilterCount(f: OrgFilters): number {
  return [f.q, f.country?.length, f.programme?.length || f.allProgrammes, f.role?.length, f.minProjects].filter(Boolean).length;
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

/**
 * WP-87: the words for an EU contribution we hold no figure of. The EDF factsheets publish no amount per participant (only CORDIS
 * does, for Horizon and its forerunners), so an organisation or a programme row of EDF projects only says so; "Not stated" beside
 * Leonardo's 74 EDF projects read as an error.
 */
export function contributionMissing(programmes: readonly string[]): string {
  const codes = programmes.map((p) => p.toUpperCase());
  return codes.length > 0 && codes.every((c) => c === 'EDF' || c === 'EDIDP' || c === 'PADR')
    ? 'Not published per participant (EDF factsheets state no amounts)'
    : 'Not stated';
}
