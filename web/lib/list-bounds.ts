import { headers } from 'next/headers';
import type { SearchParams } from './filters';

/**
 * The query of a list request past page 1, as the middleware forwarded it (`x-dg-search`, middleware.ts), as page
 * parameters; null for page 1 and for anything else. The list layouts read it to answer a page past the end with a
 * real 307 *before* anything streams: a redirect thrown by the page itself comes after the loading skeleton has
 * been sent with a 200, and arrives as an empty page with a one-second meta refresh (site-qa2:N14).
 */
export async function forwardedSearch(): Promise<SearchParams | null> {
  const raw = (await headers()).get('x-dg-search');
  if (!raw) return null;
  const params = new URLSearchParams(raw);
  const out: Record<string, string | string[]> = {};
  for (const key of new Set(params.keys())) {
    const all = params.getAll(key);
    out[key] = all.length === 1 ? all[0] : all;
  }
  return out;
}
