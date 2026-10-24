import { withEtag } from '@/lib/etag';
import { marketCsvResponse } from '@/lib/export';

/** WP-100: CSV of the market overview's tables, for the same year, buyer country and CPV codes as /market. */
/** WP-114: with an ETag, and 304 for a reader who holds the same file (`lib/etag.ts`). */
export async function GET(request: Request): Promise<Response> {
  return withEtag(request, await build(request));
}

async function build(request: Request): Promise<Response> {
  return marketCsvResponse(new URL(request.url));
}
