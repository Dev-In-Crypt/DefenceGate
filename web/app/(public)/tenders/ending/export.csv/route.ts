import { getFullEnding } from '@/lib/account';
import { parseCountries } from '@/lib/country-input';
import { toCsv, truncationRow } from '@/lib/csv';
import { absoluteUrl } from '@/lib/seo';
import { CSV_ROWS, ENDING_CSV_HEADER, endingCsvRows, parseEndingFilters } from '@/lib/contract-period';

export const dynamic = 'force-dynamic';

const NO_STORE = { 'cache-control': 'private, no-store' };

/**
 * WP-160: the CSV of the contracts ending soon (Team and Consultant, `expiring_contracts_csv`; anyone signed in while no plan is on sale):
 * the whole list up to CSV_ROWS, each row with where its end date comes from. Anyone else goes back to the page, which says what is needed.
 */
export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const f = parseEndingFilters(Object.fromEntries(url.searchParams));
  const { codes, unknown } = parseCountries(f.country);
  const back = new Response(null, { status: 303, headers: { location: `/tenders/ending${url.search}`, ...NO_STORE } });
  if (unknown.length > 0) return back;
  const r = await getFullEnding({ within: f.within, country: codes.join(','), cpv: f.cpv, buyer: f.buyer, estimated: f.estimated }, 1, CSV_ROWS);
  if (!r.ok) return back;
  const header = [...ENDING_CSV_HEADER, 'source'];
  const rows = endingCsvRows(r.data.items, absoluteUrl('').replace(/\/$/, '')).map((row, i) => [...row, r.data.items[i].source.attribution]);
  const cut = truncationRow(header.length, rows.length, r.data.total, CSV_ROWS);
  return new Response(toCsv(header, cut ? [...rows, cut] : rows), {
    status: 200,
    headers: {
      'content-type': 'text/csv; charset=utf-8',
      'content-disposition': `attachment; filename="defencegate-contracts-ending-${f.within}m-${r.data.from}.csv"`,
      'x-content-type-options': 'nosniff',
      ...NO_STORE,
    },
  });
}
