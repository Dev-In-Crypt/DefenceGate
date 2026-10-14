import { callsCsvResponse } from '@/lib/export';

/** CSV of the public fields of the current /funding result: same query parameters, at most 2,000 rows. */
export async function GET(request: Request): Promise<Response> {
  return callsCsvResponse(new URL(request.url), request.headers.get('x-forwarded-for'));
}
