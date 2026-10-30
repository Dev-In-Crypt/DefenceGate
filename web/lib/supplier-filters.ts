/**
 * The filters of the supplier map (/suppliers) as the address gives them, and as the API takes them. Shared by the page and, WP-156,
 * by its CSV (`/suppliers/export.csv`), so the file holds the list the page shows.
 */
import { CURRENCIES } from './taxonomy';
import { MAX_PAGE, type SearchParams } from './filters';
import { cpvForWords } from './cpv';
import { parseCountries } from './country-input';
import type { SupplierItem, SupplierSort } from './types';
import type { Cell } from './csv';

/** WP-156: the rows of one supplier-map CSV (backend exports.EXPORT_MAX). */
export const SUPPLIER_CSV_ROWS = 5000;
export const SUPPLIER_CSV_HEADER = ['company', 'country', 'contracts_won', 'first_year', 'last_year', 'cpv_divisions', 'contract_values', 'page'];

/**
 * One row per company, as the list shows it: the contracts it won under the filters, its CPV divisions and its contract values per currency
 * (never converted, "EUR 1250000 over 3"; empty when none states one), and its page on the site (`base`: the site's address).
 */
export function supplierCsvRows(items: SupplierItem[], base: string): Cell[][] {
  return items.map((s) => [
    s.name, s.country, s.awardCount, s.firstYear, s.lastYear, s.cpvDivisions.join(' '),
    (s.contractValues ?? []).map((v) => `${v.currency} ${Math.round(v.amount)} over ${v.count}`).join('; '),
    `${base}/suppliers/${s.slug}`,
  ]);
}

const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? '';

/** WP-98b: one order per currency the site shows amounts in; a sum in one currency is never set against another's. */
export const VALUE_SORTS = CURRENCIES.map((c) => ({ value: `value-${c}`, label: `Contract values in ${c}, largest first` }));

export function parseSupplierFilters(sp: SearchParams) {
  const q = first(sp.q).slice(0, 100).trim();
  // A code, a three-letter code or an English name, as typed (lib/country-input.ts reads it); the API is asked with the codes.
  const country = first(sp.country).replace(/[^\p{L}\p{M}\s,.'’&-]/gu, '').replace(/\s+/g, ' ').trim().slice(0, 60);
  // WP-85: the buyer's country (the notice's), as the supplier report's countries; `country` stays the supplier's
  const buyerCountry = first(sp.buyerCountry).replace(/[^\p{L}\p{M}\s,.'’&-]/gu, '').replace(/\s+/g, ' ').trim().slice(0, 60);
  const cpv = first(sp.cpv).replace(/[^0-9,]/g, '').slice(0, 40);
  const product = first(sp.product).replace(/[^\p{L}\p{N}\s-]/gu, ' ').replace(/\s+/g, ' ').trim().slice(0, 60);
  // WP-98b: or the contract values in one currency, largest first
  const asked = first(sp.sort);
  const sort: SupplierSort = asked === 'name' ? 'name' : VALUE_SORTS.some((o) => o.value === asked) ? (asked as SupplierSort) : 'awards';
  // WP-98b (p07): TED's winners only, so countries can be compared on one source
  const source = first(sp.source) === 'ted' ? ('ted' as const) : undefined;
  const n = Number(first(sp.page));
  const page = Number.isFinite(n) && n >= 1 ? Math.min(Math.floor(n), MAX_PAGE) : 1;
  // WP-96: a curated company group (`/suppliers?group=rheinmetall`), its key as the API knows it
  const group = first(sp.group).toLowerCase().replace(/[^a-z]/g, '').slice(0, 40);
  return { q, country, buyerCountry, cpv, product, sort, source, page, group };
}
export type SupplierPageFilters = ReturnType<typeof parseSupplierFilters>;

/**
 * The filters as the API takes them. A product word is turned into CPV prefixes from the finder's vocabulary and replaces the CPV
 * codes typed; a product that matches no code gives no prefixes and an empty answer, never the unfiltered list.
 */
export function supplierApiFilters(f: SupplierPageFilters) {
  const match = f.product ? cpvForWords(f.product) : null;
  // A product word takes the place of the typed codes (the page says so): an intersection of two lists of prefixes is not what anyone means.
  const cpv = match ? match.prefixes.join(',') : f.cpv;
  // A country that is none of the three forms is an answer ("not a country"), never a 404 page and never the unfiltered list.
  const { codes, unknown: u1 } = parseCountries(f.country);
  const { codes: buyerCodes, unknown: u2 } = parseCountries(f.buyerCountry);
  const unknown = [...u1, ...u2];
  return { match, unknown, none: (match !== null && match.prefixes.length === 0) || unknown.length > 0, api: { ...f, cpv, country: codes.join(','), buyerCountry: buyerCodes.join(',') } };
}
