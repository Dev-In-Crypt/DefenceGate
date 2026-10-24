import { withEtag } from '@/lib/etag';
import { supplierContractsCsvResponse } from '@/lib/export';

/** WP-100: CSV of every contract of one supplier (its page lists the newest 50). */
export async function GET(request: Request, { params }: { params: Promise<{ slug: string }> }): Promise<Response> {
  return withEtag(request, await supplierContractsCsvResponse((await params).slug));   // WP-114: ETag and 304
}
