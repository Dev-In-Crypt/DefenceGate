import raw from './calls.json';
import { sourceById } from './sources';
import { deadlineState, now } from '../deadline';
import { PROGRAMMES } from '../taxonomy';
import type { Call, CallFilters, CallStatus, CountryCode, CurrencyCode, EligibilityItem, Paginated, ProgrammeCode, Regime } from '../types';
import { DEFAULT_CURRENCY, DEFAULT_PAGE_SIZE } from '../filters';

interface RawCall {
  slug: string; programme: ProgrammeCode; programmeName?: string; callId: string | null; topicId: string;
  title: string; titleLanguage?: string; originalTitle?: string; originalLanguage?: string;
  regime: Regime; country: CountryCode; issuer?: string;
  opening: string | null; deadline: string | null;
  budget: [number, CurrencyCode] | null; budgetScope?: 'call' | 'topic';
  actionType: string | null; fundingRate: string | null; scope: string[];
  sourceId: string; retrievedAt: string; publishedAt?: string; firstSeenAt?: string;
  eligibility?: EligibilityItem[]; conditionsText?: string;
}
const data = raw as unknown as { eligibility: Record<string, EligibilityItem[]>; calls: RawCall[] };

const FIRST_SEEN = '2026-09-01T06:00:00Z';

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
    callId: r.callId, topicId: r.topicId,
    title: r.title, titleLanguage: r.titleLanguage ?? 'en',
    originalTitle: r.originalTitle ?? null, originalLanguage: r.originalLanguage ?? null,
    regime: r.regime, funderCountry: r.country, issuer: r.issuer ?? null,
    status, openingDate: r.opening, deadline: r.deadline,
    budget: r.budget ? { amount: r.budget[0], currency: r.budget[1] } : null,
    budgetScope: r.budget ? (r.budgetScope ?? 'topic') : null,
    actionType: r.actionType, fundingRate: r.fundingRate, scope: r.scope,
    eligibility: r.eligibility ?? data.eligibility[eligKey] ?? [],
    publishedAt: r.publishedAt ?? null,
    firstSeenAt: r.firstSeenAt ?? FIRST_SEEN, lastSeenAt: r.retrievedAt,
    source: {
      sourceId: src.id, sourceName: src.name, url: src.url ? `${src.url}/${r.topicId.toLowerCase()}` : null,
      retrievedAt: r.retrievedAt, licence: src.licence, attribution: src.attribution,
    },
    ...(detail && r.conditionsText ? { conditionsText: r.conditionsText } : {}),
  };
}

export function allCalls(ref: Date = now(), detail = false): Call[] {
  return data.calls.map((r, i) => toCall(r, i, ref, detail));
}

const time = (iso: string) => new Date(iso).getTime();

export function queryCalls(f: CallFilters, ref: Date = now()): Paginated<Call> {
  const q = f.q?.toLowerCase();
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
    if (q && ![c.title, c.originalTitle, c.callId, c.topicId, c.issuer].some((s) => s?.toLowerCase().includes(q))) return false;
    return true;
  });

  const sort = f.sort ?? 'deadline-asc';
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
  return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, pageSize };
}

/** Like the API: only the leading integer of "<id>-<words>" is looked up. */
export function findCall(slug: string, ref: Date = now()): Call | null {
  const id = /^(\d+)(?:-|$)/.exec(slug)?.[1];
  if (!id) return null;
  return allCalls(ref, true).find((c) => c.id === id) ?? null;
}
