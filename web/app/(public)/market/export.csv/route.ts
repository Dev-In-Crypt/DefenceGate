import { marketCsvResponse } from '@/lib/export';

/** WP-100: CSV of the market overview's tables, for the same year, buyer country and CPV codes as /market. */
export async function GET(request: Request): Promise<Response> {
  return marketCsvResponse(new URL(request.url));
}
