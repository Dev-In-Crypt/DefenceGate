import { withEtag } from '@/lib/etag';
import { callsCsvResponse } from '@/lib/export';

/** CSV of the public fields of the current /funding result: same query parameters, at most 2,000 rows. */
/** WP-114: with an ETag, and 304 for a reader who holds the same file (`lib/etag.ts`). */
export async function GET(request: Request): Promise<Response> {
  return withEtag(request, await build(request));
}

async function build(request: Request): Promise<Response> {
  return callsCsvResponse(new URL(request.url), request.headers.get('x-forwarded-for'));
}
