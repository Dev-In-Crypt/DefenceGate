import { getSupplierExport } from '@/lib/account';
import { getSupplierSummary } from '@/lib/api';
import { toCsv, truncationRow } from '@/lib/csv';
import { formatDateUtc } from '@/lib/format';
import { absoluteUrl } from '@/lib/seo';
import { SUPPLIER_CSV_HEADER, parseSupplierFilters, supplierApiFilters, supplierCsvRows } from '@/lib/supplier-filters';
import { placspCredit, placspNote } from '@/lib/supplier-sources';

export const dynamic = 'force-dynamic';

const NO_STORE = { 'cache-control': 'private, no-store' };

/**
 * WP-156: the supplier map's list as CSV, the paid part (`supplier_map_csv`, Team and Consultant): the list under the page's filters, in its
 * order, up to SUPPLIER_CSV_ROWS companies (the page itself serves the first 500 positions), for an account the API serves it to
 * (/v1/account/suppliers/export). Anyone else, and a filter the list would refuse, goes back to the page, which says what is needed.
 */
export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const f = parseSupplierFilters(Object.fromEntries(url.searchParams));
  const { none, api } = supplierApiFilters(f);
  const back = new Response(null, { status: 303, headers: { location: `/suppliers${url.search}`, ...NO_STORE } });
  if (none) return back;
  const r = await getSupplierExport(api);
  if (!r.ok) return back;
  const placsp = r.data.placsp ? placspNote((await getSupplierSummary().catch(() => null))?.sources) : null;
  const credit = `Source: TED, © European Union.${placsp ? ` ${placspCredit(placsp, formatDateUtc)}` : ''}`;
  const header = [...SUPPLIER_CSV_HEADER, 'source'];
  const rows = supplierCsvRows(r.data.items, absoluteUrl('').replace(/\/$/, '')).map((row) => [...row, credit]);
  const cut = truncationRow(header.length, rows.length, r.data.total, r.data.cap);
  return new Response(toCsv(header, cut ? [...rows, cut] : rows), {
    status: 200,
    headers: {
      'content-type': 'text/csv; charset=utf-8',
      'content-disposition': `attachment; filename="defencegate-suppliers-${r.data.asOf}.csv"`,
      'x-content-type-options': 'nosniff',
      ...NO_STORE,
    },
  });
}
