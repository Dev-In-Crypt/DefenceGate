/**
 * The server-side read of the regulatory tracker. Same rule as lib/readiness-api.ts: with DG_API_URL set it
 * calls the API; unset, the site builds from lib/mock/regulation.json, generated from the seed by
 * `python -m dgate.regulation --export <root>` and checked by a backend test, so it cannot drift.
 */
import { ApiError, REVALIDATE_SECONDS } from './api';
import mock from './mock/regulation.json';
import type { RegulationFeed } from './regulation';

const API_BASE = process.env.DG_API_URL;

export async function getRegulation(): Promise<RegulationFeed> {
  if (!API_BASE) return mock as unknown as RegulationFeed;
  const res = await fetch(`${API_BASE}/v1/regulation`, {
    headers: { accept: 'application/json' }, signal: AbortSignal.timeout(20_000), next: { revalidate: REVALIDATE_SECONDS },
  });
  if (!res.ok) throw new ApiError(res.status, 'GET /v1/regulation failed');
  return (await res.json()) as RegulationFeed;
}
