/**
 * The only data-access module. Pages and components never import lib/mock directly.
 * Set DG_API_URL to talk to the real API; leave it unset to serve mock data.
 * Funding endpoints and shapes: docs/design/API_CONTRACT.md.
 */
import type { Call, CallFilters, Health, Opportunity, OpportunityFilters, OpportunityVersion, Paginated, SiteStats } from './types';
import { DEFAULT_PAGE_SIZE, toQuery } from './filters';
import { now } from './deadline';
import * as callsMock from './mock/calls';
import * as sourcesMock from './mock/sources';
import * as oppMock from './mock/opportunities';

const API_BASE = process.env.DG_API_URL;
/** Data is collected daily; an hour of ISR keeps countdowns fresh. */
export const REVALIDATE_SECONDS = 3600;
const RELATED_LIMIT = 3;
/** A call slug is "<id>-<words>"; anything else cannot be a call (e.g. /funding/open). */
const SLUG_RE = /^\d+(-|$)/;

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function http<T>(path: string): Promise<T | null> {
  const res = await fetch(`${API_BASE}${path}`, { next: { revalidate: REVALIDATE_SECONDS }, headers: { accept: 'application/json' } });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, `GET ${path} failed`);
  return (await res.json()) as T;
}
async function httpOrThrow<T>(path: string): Promise<T> {
  const r = await http<T>(path);
  if (r === null) throw new ApiError(404, `GET ${path} returned 404`);
  return r;
}

/** Query for /v1/funding: the site's URL keys (defaults omitted) plus pageSize. */
function fundingQuery(f: CallFilters): string {
  const p = new URLSearchParams(toQuery(f));
  p.set('pageSize', String(f.pageSize ?? DEFAULT_PAGE_SIZE));
  return `?${p.toString()}`;
}

export async function getCalls(filters: CallFilters = {}): Promise<Paginated<Call>> {
  if (API_BASE) return httpOrThrow<Paginated<Call>>(`/v1/funding${fundingQuery(filters)}`);
  return callsMock.queryCalls(filters);
}

/** `slug` is "<id>-<words>"; the API looks up the leading id only. Callers redirect when the returned slug differs. */
export async function getCall(slug: string): Promise<Call | null> {
  if (!SLUG_RE.test(slug)) return null;
  if (API_BASE) return http<Call>(`/v1/funding/${encodeURIComponent(slug)}`);
  return callsMock.findCall(slug);
}

/** Same programme first, then same funder country; open calls only. */
export async function getRelatedCalls(call: Call): Promise<Call[]> {
  const { items } = await getCalls({ status: 'open', pageSize: 50 });
  const others = items.filter((c) => c.id !== call.id);
  const score = (c: Call) => (c.programme === call.programme ? 2 : 0) + (c.funderCountry === call.funderCountry ? 1 : 0);
  return others.sort((a, b) => score(b) - score(a)).slice(0, RELATED_LIMIT);
}

/** Slugs for the sitemap. */
export async function getAllCallSlugs(): Promise<{ slug: string; updatedAt: string }[]> {
  if (API_BASE) return httpOrThrow<{ slug: string; updatedAt: string }[]>('/v1/funding/slugs');
  return callsMock.allCalls().map((c) => ({ slug: c.slug, updatedAt: c.lastSeenAt }));
}

export async function getOpportunities(filters: OpportunityFilters = {}): Promise<Paginated<Opportunity>> {
  if (API_BASE) return httpOrThrow(`/v1/opportunities?${new URLSearchParams(Object.entries(filters).map(([k, v]) => [k, String(v)]))}`);
  return oppMock.queryOpportunities(filters);
}

export async function getOpportunity(id: string): Promise<Opportunity | null> {
  if (API_BASE) return http(`/v1/opportunities/${encodeURIComponent(id)}`);
  return oppMock.opportunities.find((o) => o.id === id || o.slug === id) ?? null;
}

export async function getOpportunityVersions(id: string): Promise<OpportunityVersion[]> {
  if (API_BASE) return (await http<OpportunityVersion[]>(`/v1/opportunities/${encodeURIComponent(id)}/versions`)) ?? [];
  return oppMock.versions[id] ?? [];
}

/** Source list with run status: GET /v1/sources (the design's Health). */
export async function getHealth(): Promise<Health> {
  if (API_BASE) return httpOrThrow<Health>('/v1/sources');
  return sourcesMock.health();
}

/** Landing counters: open calls from the list total, sources from /v1/sources, last update from generatedAt. */
export async function getSiteStats(): Promise<SiteStats> {
  const [open, health] = await Promise.all([getCalls({ status: 'open', pageSize: 1 }), getHealth()]);
  return { openCalls: open.total, sources: health.sources.length, lastUpdate: health.generatedAt };
}

export { now };
