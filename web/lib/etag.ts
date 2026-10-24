import { etagOf } from './atom';

/**
 * WP-114: an ETag on a machine-read answer (calendar files, CSV exports, sitemaps) and 304 Not Modified when the reader
 * already holds that body, as the Atom feeds do (coverage audit of 24 October 2026: calendar.ics 1.1 MB and sitemap.xml
 * 1.25 MB came again in full on every conditional request). Only a 200 is tagged; anything else passes unchanged.
 */
export async function withEtag(request: Request, res: Response): Promise<Response> {
  if (res.status !== 200) return res;
  // The bytes as sent: `res.text()` would drop a CSV's UTF-8 byte-order mark (WP-116), which Excel needs
  const body = await res.arrayBuffer();
  const etag = etagOf(new TextDecoder('utf-8', { ignoreBOM: true }).decode(body));
  const headers = new Headers(res.headers);
  headers.set('etag', etag);
  if (matches(request.headers.get('if-none-match'), etag)) {
    headers.delete('content-type');
    headers.delete('content-length');
    return new Response(null, { status: 304, headers });
  }
  return new Response(body, { status: 200, headers });
}

/** RFC 9110 weak comparison of an If-None-Match list against a tag. */
export function matches(header: string | null, etag: string): boolean {
  if (!header) return false;
  const strip = (t: string) => t.trim().replace(/^W\//, '');
  return header.split(',').some((t) => t.trim() === '*' || strip(t) === strip(etag));
}
