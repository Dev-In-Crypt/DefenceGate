import { supplierContractsCsvResponse } from '@/lib/export';

/** WP-100: CSV of every contract of one supplier (its page lists the newest 50). */
export async function GET(_request: Request, { params }: { params: Promise<{ slug: string }> }): Promise<Response> {
  return supplierContractsCsvResponse((await params).slug);
}
