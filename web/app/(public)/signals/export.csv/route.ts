import { getFullSignal } from '@/lib/account';
import { parseCountries } from '@/lib/country-input';
import { toCsv, truncationRow } from '@/lib/csv';
import { absoluteUrl } from '@/lib/seo';
import { CSV_ROWS, SIGNAL_CSV_HEADER, parseSignalFilters, signalCsvRows } from '@/lib/signals';

export const dynamic = 'force-dynamic';

const NO_STORE = { 'cache-control': 'private, no-store' };

/**
 * WP-154: the CSV of a company signal, the paid part: the whole list (up to CSV_ROWS) for an account the API serves it to
 * (/v1/account/signals: DGATE_SIGNALS_FULL_OPEN and a plan). Anyone else goes back to the page, which says what is needed.
 */
export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const f = parseSignalFilters(Object.fromEntries(url.searchParams));
  const { codes, unknown } = parseCountries(f.country);
  const back = new Response(null, { status: 303, headers: { location: `/signals${url.search}`, ...NO_STORE } });
  if (unknown.length > 0) return back;
  const r = await getFullSignal({ kind: f.kind, country: codes.join(','), cpv: f.cpv, programme: f.programme }, 1, CSV_ROWS);
  if (!r.ok) return back;
  const header = [...SIGNAL_CSV_HEADER[f.kind], 'source', 'note'];
  const credit = r.data.sources.map((s) => s.attribution ?? s.name).join(' ');
  const rows = signalCsvRows(f.kind, r.data.items, absoluteUrl('').replace(/\/$/, '')).map((row) => [...row, credit, r.data.note]);
  const cut = truncationRow(header.length, rows.length, r.data.total, CSV_ROWS);
  return new Response(toCsv(header, cut ? [...rows, cut] : rows), {
    status: 200,
    headers: {
      'content-type': 'text/csv; charset=utf-8',
      'content-disposition': `attachment; filename="defencegate-signals-${f.kind}-${r.data.asOf}.csv"`,
      'x-content-type-options': 'nosniff',
      ...NO_STORE,
    },
  });
}
