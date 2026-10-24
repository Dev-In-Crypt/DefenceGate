/**
 * WP-100: the rows of the exports beside the tenders and funding lists (persona round of 23 October 2026, p07): a supplier's
 * contracts and the market tables, with the tender file's attribution columns (source_name, source_url, licence, attribution,
 * page_url), and the value kind of a tender row. Pure (no API, no Next): lib/wp100.check.ts runs it on its own.
 */
import type { Cell } from './csv';
import { isoUtc, isMidnight } from './csv';
import { cpvGroupName } from './cpv';
import { monthLabel } from './market';
import { countryName } from './taxonomy';
import { sourceStatusWord, valueKindLabel } from './tender-status';
import type { MarketStats, SupplierContract, SupplierContracts, Tender } from './types';

/**
 * What a tender row's value is, on every row that has a value (p09: 143 of 232 rows had none). The kind the notice gives
 * (TED: total, estimated, lot sum, first lot) as it stands; a notice that states none: `estimated` for a call (no award is
 * made yet, so its value is the buyer's estimate) and for a PLACSP notice (its "valor estimado" or the budget, whatever its
 * status), `not stated` for another source's award notice, whose figure may be the awarded amount or the estimate it was made
 * against.
 */
export function csvValueKind(t: Pick<Tender, 'valueKind' | 'statusNative'> & Partial<Pick<Tender, 'awardValue'>> & { source: Pick<Tender['source'], 'sourceId'> }): string {
  // WP-106 (p07): one vocabulary with the supplier file (`KIND`): an award's value by its kind, a notice's own value is an estimate
  if (t.awardValue) return KIND[t.awardValue.kind] ?? t.awardValue.kind;
  const awarded = sourceStatusWord(t) === 'Awarded';
  switch ((t.valueKind ?? '').trim()) {
    case 'estimated': return 'estimate';
    case 'lot_sum': return 'estimate (sum of lots)';
    case 'first_lot': return 'estimate (first lot)';
    // TED's `total`: an award's total is a contract value or a ceiling, not told apart here; on any other notice it is its estimate
    case 'total': return awarded ? 'not stated' : 'estimate';
    case '': break;
    default: return valueKindLabel(t.valueKind) ?? 'not stated';
  }
  const placsp = /placsp/i.test(t.source.sourceId ?? '');
  return !placsp && awarded ? 'not stated' : 'estimate';
}

/** WP-95's value kinds, as the supplier page words them; WP-106: the tender file's words too. */
export const KIND: Record<string, string> = { contract: 'contract', framework: 'framework ceiling', estimate: 'estimate' };

/** WP-106 (p06, p07): the winners an award names (legal entities; natural persons are counted on the page, never named), and their countries. */
export function winnerCells(t: Partial<Pick<Tender, 'awardedTo'>>): [string, string] {
  const w = t.awardedTo ?? [];
  return [w.map((x) => x.name).join(' | '), w.map((x) => x.country ?? '').join(' | ')];
}

export const SUPPLIER_CONTRACT_HEADER = [
  'supplier', 'notice_id', 'title', 'buyer', 'buyer_country', 'published', 'cpv', 'value', 'currency', 'value_kind',
  'in_contract_sum', 'winners_in_notice', 'framework_notice_id', 'source_name', 'source_url', 'licence', 'attribution', 'page_url',
  'result_truncated',
];

/**
 * One contract. The value is the one the profile's sums read, with its kind; `in_contract_sum` says whether the profile adds it
 * (a contract value that is not a unit price): framework ceilings and estimates are listed, never summed. A notice naming several
 * winners states no value for this one; the others are counted (`winners_in_notice`), never named.
 */
export function supplierContractRow(name: string, c: SupplierContract, pageUrl: (path: string) => string, truncated: boolean): Cell[] {
  const has = c.valueAmount !== null;
  return [
    name, c.noticeId, c.title, c.buyerName, c.buyerCountry, isoUtc(c.publishedAt, c.publishedAt !== null && isMidnight(c.publishedAt)), c.cpv,
    has ? c.valueAmount : null, has ? c.valueCurrency : null, has && c.valueKind ? KIND[c.valueKind] ?? c.valueKind : null,
    c.inContractSum ? 'yes' : 'no', c.winnersInNotice, c.frameworkNoticeId,
    c.sourceName, c.sourceUrl, c.licence, c.attribution, pageUrl(`/tenders/${c.slug}`), truncated ? 'true' : 'false',
  ];
}

export function supplierContractRows(s: SupplierContracts, pageUrl: (path: string) => string): Cell[][] {
  return s.items.map((c) => supplierContractRow(s.name, c, pageUrl, s.total > s.items.length));
}

export const MARKET_HEADER = [
  'table', 'key', 'label', 'notices', 'ted', 'national_sources', 'partial_month', 'period', 'buyer_country', 'cpv', 'scope', 'unit',
  'as_of_utc', 'source_name', 'licence', 'attribution', 'page_url',
];

export interface SourceTerms { name: string; licence: string; attribution: string }

/**
 * The market page's tables as shown (/market, the same filters): notices per month (TED and national sources), by buyer
 * country (and the rest), by CPV group, by source. A row of one source carries that source's licence and attribution; a
 * row that counts several carries every one of the sources behind the figures, joined by "; ".
 */
export function marketRows(m: MarketStats, terms: Map<string, SourceTerms>, pageUrl: string): Cell[][] {
  const window = `${m.windowFrom.slice(0, 10)}/${m.windowTo.slice(0, 10)}`;
  const own = (id: string, name: string) => terms.get(id) ?? { name, licence: '', attribution: '' };
  const all = m.sources.map((s) => own(s.id, s.name));
  const join = (k: keyof SourceTerms) => [...new Set(all.map((t) => t[k]).filter(Boolean))].join('; ');
  const every = { name: join('name'), licence: join('licence'), attribution: join('attribution') };
  const row = (table: string, key: string, label: string, n: number, ted: number | null, national: number | null, partial: boolean | null,
    period: string, t: SourceTerms = every): Cell[] => [
    table, key, label, n, ted, national, partial === null ? null : partial ? 'true' : 'false', period, m.country ?? '', (m.cpv ?? []).join(' '),
    m.scope, m.unit, isoUtc(m.asOf), t.name, t.licence, t.attribution, pageUrl,
  ];
  return [
    ...m.months.map((x) => row('month', x.month, monthLabel(x.month), x.count, x.ted, Math.max(0, x.count - x.ted), x.partial, x.month)),
    ...m.countries.items.map((c) => row('country', c.country, countryName(c.country), c.count, null, null, null, window)),
    ...(m.countries.other > 0 ? [row('country', 'other', 'Other countries, or none stated', m.countries.other, null, null, null, window)] : []),
    ...m.cpvGroups.map((g) => row('cpv_group', g.group, cpvGroupName(g.group) ?? 'Group', g.count, null, null, null, window)),
    ...m.sources.map((s) => row('source', s.id, s.name, s.count, null, null, null, window, own(s.id, s.name))),
  ];
}
