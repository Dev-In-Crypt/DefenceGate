import { etagOf } from './atom';
import { TtlCache } from './export-cache';

/**
 * WP-114: an ETag on a machine-read answer (calendar files, CSV exports, sitemaps) and 304 Not Modified when the reader
 * already holds that body, as the Atom feeds do (coverage audit of 24 October 2026: calendar.ics 1.1 MB and sitemap.xml
 * 1.25 MB came again in full on every conditional request). Only a 200 is tagged; anything else passes unchanged.
 */
export async function withEtag(request: Request, res: Response): Promise<Response> {
  if (res.status !== 200) return res;
  return answer(request, await built(res));
}

type Built = { body: ArrayBuffer; headers: [string, string][]; etag: string };

async function built(res: Response): Promise<Built> {
  // The bytes as sent: `res.text()` would drop a CSV's UTF-8 byte-order mark (WP-116), which Excel needs
  const body = await res.arrayBuffer();
  return { body, headers: [...res.headers], etag: etagOf(new TextDecoder('utf-8', { ignoreBOM: true }).decode(body)) };
}

function answer(request: Request, b: Built): Response {
  const headers = new Headers(b.headers);
  headers.set('etag', b.etag);
  if (matches(request.headers.get('if-none-match'), b.etag)) {
    headers.delete('content-type');
    headers.delete('content-length');
    return new Response(null, { status: 304, headers });
  }
  return new Response(b.body.slice(0), { status: 200, headers });
}

/** WP-120: built answers are kept for as long as their own `max-age` lets any cache keep them, at most this many per lifetime. */
export const BUILT_MAX = 40;
const kept = new Map<number, TtlCache<Built>>();

/**
 * WP-120: `withEtag` over an answer kept `ttlMs` per address (path and query), so a 304, and a repeated 200, cost no build
 * (round-6 system audit: calendar.ics answered 304 in 1.36 s and funding.atom in 1.45 s, the whole file built to hash it).
 * `ttlMs` is the answer's own `max-age`: a reader's or a proxy's cache may hold it that long anyway. Only a 200 is kept.
 */
export async function withCachedEtag(request: Request, ttlMs: number, build: () => Promise<Response>): Promise<Response> {
  let cache = kept.get(ttlMs);
  if (!cache) kept.set(ttlMs, (cache = new TtlCache<Built>(ttlMs, BUILT_MAX)));
  const url = new URL(request.url);
  const key = url.pathname + url.search;
  let hit = cache.get(key);
  if (!hit) {
    const res = await build();
    if (res.status !== 200) return res;
    hit = await built(res);
    cache.set(key, hit);
  }
  return answer(request, hit);
}

/** RFC 9110 weak comparison of an If-None-Match list against a tag. */
export function matches(header: string | null, etag: string): boolean {
  if (!header) return false;
  const strip = (t: string) => t.trim().replace(/^W\//, '');
  return header.split(',').some((t) => t.trim() === '*' || strip(t) === strip(etag));
}

/**
 * WP-120: whether a conditional request is answered 304: If-None-Match when it is sent, else If-Modified-Since against
 * `lastModified` at the whole second a Last-Modified header carries. Compared with the milliseconds, the date the feed itself
 * sent was never "not modified" (changes.atom answered 200 and 40 KB to its own Last-Modified; digest.atom, at midnight, 304).
 */
export function notModified(request: Request, etag: string, lastModified?: Date): boolean {
  const sent = request.headers.get('if-none-match');
  if (sent !== null) return matches(sent, etag);
  const since = request.headers.get('if-modified-since');
  if (since === null || !lastModified) return false;
  const t = Date.parse(since);
  return !Number.isNaN(t) && t >= Math.floor(lastModified.getTime() / 1000) * 1000;
}
