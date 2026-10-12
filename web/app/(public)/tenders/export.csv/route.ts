import { tendersCsvResponse } from '@/lib/export';

/** CSV of the public fields of the current /tenders result: same query parameters, at most 2,000 rows. */
export async function GET(request: Request): Promise<Response> {
  return tendersCsvResponse(new URL(request.url));
}
