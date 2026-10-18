import raw from './calls.json';
import { sourceById } from './sources';
import { deadlineState, now } from '../deadline';
import { PROGRAMMES } from '../taxonomy';
import type { Call, CallFilters, CallStatus, CountryCode, CurrencyCode, EligibilityItem, Paginated, ProgrammeCode, Regime } from '../types';
import { DEFAULT_CURRENCY, DEFAULT_PAGE_SIZE, defaultCallSort } from '../filters';
import { parseQuery } from '../text-search';

interface RawCall {
  slug: string; programme: ProgrammeCode; programmeName?: string; callId: string | null; topicId: string;
  title: string; titleLanguage?: string; originalTitle?: string; originalLanguage?: string;
  regime: Regime; country: CountryCode; issuer?: string;
  opening: string | null; deadline: string | null;
  budget: [number, CurrencyCode] | null; budgetScope?: 'call' | 'topic';
  actionType: string | null; fundingRate: string | null; scope: string[];
  sourceId: string; retrievedAt: string; publishedAt?: string; firstSeenAt?: string;
  eligibility?: EligibilityItem[]; conditionsText?: string; cascade?: boolean; ukraine?: boolean;
}
const data = raw as unknown as { eligibility: Record<string, EligibilityItem[]>; calls: RawCall[] };

const FIRST_SEEN = '2026-09-01T06:00:00Z';

const EDF_CATEGORIES = new Set(['GROUND', 'CYBER', 'SPACE', 'NAVAL', 'AIR', 'UWW', 'SENS', 'C4ISR', 'MCBRN', 'DIGIT', 'ENERENV', 'MATCOMP', 'PROTMOB', 'SIMTRAIN', 'DIS', 'SME', 'SMERO', 'AIRDEF', 'DS']);

/** The area of the API's `partnerArea` (backend/dgate/partners.py `area_label`) for the demo calls: EDF category, or Horizon cluster and destination. */
function mockPartnerArea(topic: string): string | null {
  const t = topic.toUpperCase().split('-');
  if (t[0] === 'EDF') {
    const c = t.slice(1).find((x) => EDF_CATEGORIES.has(x));
    return c ? `EDF capability category ${c}` : 'all projects of the European Defence Fund';
  }
  const year = t.findIndex((x, i) => i >= 2 && /^20\d\d$/.test(x));
  if (t[0] !== 'HORIZON' || year < 0) return null;
  const rest = t.slice(year + 1);
  if (rest.length > 1 && /^\d{2}$/.test(rest[0]) && /^[A-Z]+$/.test(rest[1])) rest.shift();
  const family = t.slice(1, year).join('-');
  return /^[A-Z]+$/.test(rest[0] ?? '') ? `Horizon Europe, ${family}, destination ${rest[0]}` : `Horizon Europe, ${family}`;
}

/** Mirrors the API: ids are 1-based positions, slug is "<id>-<words>", conditionsText is detail-only. */
function toCall(r: RawCall, index: number, ref: Date, detail: boolean): Call {
  const src = sourceById(r.sourceId);
  const id = String(index + 1);
  const eligKey = r.programme === 'NATIONAL' ? `NATIONAL-${r.country}` : r.programme;
  const closed = r.deadline !== null && deadlineState(r.deadline, ref) === 'closed';
  const forthcoming = !closed && r.opening !== null && new Date(r.opening).getTime() > ref.getTime();
  const status: CallStatus = closed ? 'closed' : forthcoming ? 'forthcoming' : 'open';
  return {
    id, slug: `${id}-${r.slug}`, programme: r.programme,
    programmeName: r.programmeName ?? PROGRAMMES[r.programme].name,
    // The issuing body of a national call, otherwise the Commission (backend/dgate/funding.py funder_of).
    funder: r.issuer ?? (r.programme === 'NATIONAL' ? (r.programmeName ?? PROGRAMMES[r.programme].name) : 'European Commission'),
    callId: r.callId, topicId: r.topicId,
    title: r.title, titleLanguage: r.titleLanguage ?? 'en',
    originalTitle: r.originalTitle ?? null, originalLanguage: r.originalLanguage ?? null,
    regime: r.regime, funderCountry: r.country, issuer: r.issuer ?? null,
    status, sourceStatus: status, openingDate: r.opening, deadline: r.deadline,
    budget: r.budget ? { amount: r.budget[0], currency: r.budget[1] } : null,
    budgetScope: r.budget ? (r.budgetScope ?? 'topic') : null,
    actionType: r.actionType, fundingRate: r.fundingRate, scope: r.scope,
    eligibility: r.eligibility ?? data.eligibility[eligKey] ?? [],
    cascade: r.cascade ?? null,
    openToUkraine: r.ukraine ?? null,
    publishedAt: r.publishedAt ?? null,
    firstSeenAt: r.firstSeenAt ?? FIRST_SEEN, lastSeenAt: r.retrievedAt,
    source: {
      sourceId: src.id, sourceName: src.name, url: src.url ? `${src.url}/${r.topicId.toLowerCase()}` : null,
      retrievedAt: r.retrievedAt, licence: src.licence, attribution: src.attribution,
    },
    ...(detail && r.conditionsText ? { conditionsText: r.conditionsText } : {}),
    ...(detail ? { partnerArea: mockPartnerArea(r.topicId) } : {}),
    ...(detail ? mockDetail(r) : {}),
  };
}

/** The detail-only fields the demo shows: how the Ukraine flag was decided, and the rules block of an EDF call. */
function mockDetail(r: RawCall): Partial<Call> {
  const out: Partial<Call> = {};
  if (r.ukraine !== undefined) {
    out.ukraineBasis = { reason: 'call_document', evidence: 'non-EU countries: − Ukraine' };
  }
  if (r.programme === 'EDF') {
    out.rulesApply = {
      regime: { code: 'EDF', name: 'European Defence Fund', why: 'The topic code starts with EDF- and the programme is the EDF.' },
      encoded: true, action: null,
      programme: { code: 'EDF', name: 'European Defence Fund', legalBasis: 'Regulation (EU) 2021/697, as amended by Regulation (EU) 2025/2653' },
      rules: [{
        rule: 'EDF-ESTABLISH', title: 'Established in the Union or an associated country', kind: 'establishment', requirement: 'REQ-EDF-ELIG',
        caveat: 'For an applicant established in Ukraine this is conditional on the EU-Ukraine association agreement, which is not confirmed: the EDF call documents say participation of entities established in Ukraine is pending its signature.',
        source: { url: 'http://data.europa.eu/eli/reg/2021/697/oj', ref: 'Regulation (EU) 2021/697, Article 9(1)', origin: 'primary', verificationStatus: 'V', lastReviewed: '2026-10-18',
          text: '[Regulation (EU) 2021/697, Article 9(1)] Recipients and subcontractors involved in an action shall be established in the Union or in an associated country.' },
      }],
      alsoRead: null,
      notice: 'Indicative, not legal advice. The call text and the contracting authority decide.',
    };
  }
  return out;
}

export function allCalls(ref: Date = now(), detail = false): Call[] {
  return data.calls.map((r, i) => toCall(r, i, ref, detail));
}

const time = (iso: string) => new Date(iso).getTime();

export function queryCalls(f: CallFilters, ref: Date = now()): Paginated<Call> {
  const query = f.q ? parseQuery(f.q) : undefined;
  const status = f.status ?? 'open';
  const currency = f.currency ?? DEFAULT_CURRENCY;
  /** Budget amount in the selected currency only. Amounts in other currencies are never compared with it. */
  const amountIn = (c: Call): number | null => (c.budget && c.budget.currency === currency ? c.budget.amount : null);

  let items = allCalls(ref).filter((c) => {
    if (status === 'open' && c.status !== 'open') return false;
    if (status === 'forthcoming' && c.status !== 'forthcoming') return false;
    if (status === 'closed' && c.status !== 'closed') return false;
    if (status === 'closing-soon') {
      const st = deadlineState(c.deadline, ref);
      if (c.status !== 'open' || (st !== 'soon' && st !== 'urgent')) return false;
    }
    if (f.programme && !f.programme.includes(c.programme)) return false;
    if (f.regime && !f.regime.includes(c.regime)) return false;
    if (f.country && !f.country.includes(c.funderCountry)) return false;
    if (f.deadlineFrom || f.deadlineTo) {
      if (c.deadline === null) return false;
      if (f.deadlineFrom && time(c.deadline) < time(`${f.deadlineFrom}T00:00:00Z`)) return false;
      if (f.deadlineTo && time(c.deadline) > time(`${f.deadlineTo}T23:59:59Z`)) return false;
    }
    if (f.budgetMin !== undefined || f.budgetMax !== undefined) {
      const amount = amountIn(c);
      if (amount === null) return false;
      if (f.budgetMin !== undefined && amount < f.budgetMin) return false;
      if (f.budgetMax !== undefined && amount > f.budgetMax) return false;
    }
    if (f.q && !(query && query.matches([c.title, c.originalTitle, c.issuer].filter(Boolean).join(' '), [c.callId, c.topicId].filter(Boolean).join(' ')))) return false;
    return true;
  });
  // The calls with cascade funding among those that match every other filter (the API's `cascadeTotal`).
  const cascadeTotal = items.filter((c) => c.cascade === true).length;
  if (f.cascade) items = items.filter((c) => c.cascade === true);
  const ukraineTotal = items.length === 0 ? 0 : allCalls(ref).filter((c) => items.some((i) => i.id === c.id) && c.openToUkraine === true).length;
  if (f.ukraine) items = items.filter((c) => c.openToUkraine === true);

  const sort = f.sort ?? defaultCallSort(status);
  items = items.sort((a, b) => {
    // Closed calls always last; calls without a deadline after those with one.
    const closedA = a.status === 'closed', closedB = b.status === 'closed';
    if (closedA !== closedB) return closedA ? 1 : -1;
    if (sort === 'budget-desc') {
      const x = amountIn(a), y = amountIn(b);
      if ((x === null) !== (y === null)) return x === null ? 1 : -1;
      if (x !== null && y !== null && x !== y) return y - x;
    }
    const da = a.deadline, db = b.deadline;
    if ((da === null) !== (db === null)) return da === null ? 1 : -1;
    if (da === null || db === null) return 0;
    return sort === 'deadline-desc' ? time(db) - time(da) : time(da) - time(db);
  });

  const pageSize = f.pageSize ?? DEFAULT_PAGE_SIZE;
  const page = f.page ?? 1;
  return {
    items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, pageSize, cascadeTotal, ukraineTotal,
    search: f.q ? { terms: query?.terms ?? [], alsoSearched: query?.alsoSearched ?? [] } : null,
  };
}

/** Like the API: only the leading integer of "<id>-<words>" is looked up. */
export function findCall(slug: string, ref: Date = now()): Call | null {
  const id = /^(\d+)(?:-|$)/.exec(slug)?.[1];
  if (!id) return null;
  return allCalls(ref, true).find((c) => c.id === id) ?? null;
}
