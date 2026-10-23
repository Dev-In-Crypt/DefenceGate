import { sourceById } from './sources';
import { now } from '../deadline';
import { cpvTitle, titleHasWord } from '../cpv';
import { weekMonday, weekOf } from '../digest';
import { BUYER_PAGE_SIZE, TENDER_PAGE_SIZE, defaultTenderSort } from '../filters';
import type {
  Buyer, BuyerFilters, CalendarItem, CalendarPage, Change, ChangeFilters, ChangePage, CountryCode, Money, Paginated, Tender, TenderFilters, TenderScope,
  TenderVersion,
} from '../types';

/**
 * Mock tenders and buyers for local builds and previews (DG_API_URL unset). All names are invented
 * ("Demo ..."); nothing here is a real notice. Shapes follow docs/design/API_CONTRACT.md.
 */

interface RawBuyer { name: string; country: CountryCode; words: string; defence: boolean }
const RAW_BUYERS: RawBuyer[] = [
  { name: 'Demo Armaments Agency', country: 'PL', words: 'demo-armaments-agency', defence: true },
  { name: 'Demo Defence Materiel Administration', country: 'SE', words: 'demo-defence-materiel-administration', defence: true },
  { name: 'Demo Logistics and Support Command', country: 'ES', words: 'demo-logistics-and-support-command', defence: true },
  { name: 'Demo Defence Materiel Organisation', country: 'NL', words: 'demo-defence-materiel-organisation', defence: true },
  { name: 'Demo Ministry Procurement Office', country: 'FR', words: 'demo-ministry-procurement-office', defence: true },
  { name: 'Demo Regional Fire and Rescue Service', country: 'PL', words: 'demo-regional-fire-and-rescue-service', defence: false },
];

interface RawTender {
  words: string; noticeId: string; sourceId: string; retrievedAt: string;
  title: string; titleLanguage?: string | null; originalTitle?: string; originalLanguage?: string;
  /** 1-based index into RAW_BUYERS; 0 = a buyer we could not resolve. */
  buyer: number; buyerName?: string; country?: CountryCode;
  cpvCodes: string[]; procedure?: string; legalBasis?: string; scope?: TenderScope;
  deadline: string | null; publishedAt: string | null; value?: [number, string];
  native?: string; security?: boolean; subcontracting?: boolean;
  sameNotice?: { source: string; url: string | null; id?: string; noticeId?: string }[];
}

const RAW: RawTender[] = [
  { words: 'framework-agreement-machined-aluminium-housings', noticeId: '561204-2026', sourceId: 'eu-ted', retrievedAt: '2026-10-11T06:20:00Z',
    title: 'Framework agreement for machined aluminium housings', originalTitle: 'Raamovereenkomst voor gefreesde aluminium behuizingen', originalLanguage: 'nl',
    buyer: 4, cpvCodes: ['44316400', '35800000'], procedure: 'Restricted procedure', legalBasis: '32009L0081',
    deadline: '2026-11-26T00:00:00Z', publishedAt: '2026-09-28T00:00:00Z', value: [3_400_000, 'EUR'], subcontracting: true,
    sameNotice: [{ source: 'nl-tenderned', url: 'https://www.tenderned.nl' }] },
  { words: 'workshop-consumables-supply', noticeId: '588310-2026', sourceId: 'eu-ted', retrievedAt: '2026-10-11T06:20:00Z',
    title: 'Supply of workshop consumables', buyer: 1, cpvCodes: ['44510000'], procedure: 'Open procedure', legalBasis: '32009L0081',
    deadline: '2026-11-04T00:00:00Z', publishedAt: '2026-10-05T00:00:00Z', value: [850_000, 'EUR'],
    sameNotice: [{ source: 'pl-ezam', url: 'https://ezamowienia.gov.pl', id: '3', noticeId: '2026/BZP 00412345' }] },
  { words: 'dostawa-materialow-eksploatacyjnych-warsztatow', noticeId: '2026/BZP 00412345', sourceId: 'pl-ezam', retrievedAt: '2026-10-11T06:35:00Z',
    title: 'Dostawa materiałów eksploatacyjnych dla warsztatów', titleLanguage: 'pl', buyer: 1, cpvCodes: ['44510000'],
    procedure: 'Przetarg nieograniczony', legalBasis: '32009L0081', deadline: '2026-10-30T09:00:00Z', publishedAt: '2026-10-02T00:00:00Z', value: [2_100_000, 'PLN'] },
  { words: 'vehicle-fleet-maintenance-services', noticeId: '601778-2026', sourceId: 'eu-ted', retrievedAt: '2026-10-11T06:20:00Z',
    title: 'Maintenance services for a vehicle fleet', buyer: 3, cpvCodes: ['50110000', '34300000'], procedure: 'Open procedure', legalBasis: '32009L0081',
    deadline: '2026-12-10T00:00:00Z', publishedAt: '2026-10-08T00:00:00Z', value: [6_200_000, 'EUR'], security: true, subcontracting: true },
  { words: 'uniform-textiles-framework', noticeId: '540221-2026', sourceId: 'eu-ted', retrievedAt: '2026-10-10T06:20:00Z',
    title: 'Uniform textiles framework', buyer: 5, cpvCodes: ['18100000'], procedure: 'Negotiated procedure', legalBasis: '32009L0081',
    deadline: '2026-10-20T00:00:00Z', publishedAt: '2026-08-30T00:00:00Z', value: [1_150_000, 'EUR'] },
  { words: 'software-maintenance-and-support', noticeId: '577902-2026', sourceId: 'es-placsp', retrievedAt: '2026-10-11T06:58:00Z',
    title: 'Software maintenance and support', originalTitle: 'Mantenimiento y soporte de software', originalLanguage: 'es',
    buyer: 3, cpvCodes: ['72267000'], procedure: 'Open procedure', legalBasis: '32009L0081',
    deadline: null, publishedAt: '2026-10-01T00:00:00Z', security: true },
  { words: 'packaging-and-logistics-services', noticeId: '498440-2026', sourceId: 'eu-ted', retrievedAt: '2026-09-20T06:20:00Z',
    title: 'Packaging and logistics services', buyer: 2, cpvCodes: ['63100000', '60000000'], procedure: 'Open procedure', legalBasis: '32009L0081',
    deadline: '2026-09-15T00:00:00Z', publishedAt: '2026-07-22T00:00:00Z', value: [4_750_000, 'EUR'], native: 'awarded' },
  { words: 'printing-of-training-materials', noticeId: '471003-2026', sourceId: 'eu-ted', retrievedAt: '2026-09-02T06:20:00Z',
    title: 'Printing of training materials', buyer: 5, cpvCodes: ['22000000'], procedure: 'Open procedure', legalBasis: '32009L0081',
    deadline: '2026-08-31T00:00:00Z', publishedAt: '2026-07-10T00:00:00Z', native: 'cancelled' },
  { words: 'laboratory-consumables-supply', noticeId: '605113-2026', sourceId: 'eu-ted', retrievedAt: '2026-10-11T06:20:00Z',
    title: 'Laboratory consumables', buyer: 4, cpvCodes: ['33790000'], procedure: 'Open procedure', legalBasis: '32014L0024',
    deadline: '2026-11-18T00:00:00Z', publishedAt: '2026-10-09T00:00:00Z', value: [420_000, 'SEK'], scope: 'supply' },
  { words: 'station-cleaning-services', noticeId: '598871-2026', sourceId: 'eu-ted', retrievedAt: '2026-10-11T06:20:00Z',
    title: 'Cleaning services for the regional fire and rescue stations', buyer: 6, cpvCodes: ['90910000'], procedure: 'Open procedure', legalBasis: '32014L0024',
    deadline: '2026-11-12T00:00:00Z', publishedAt: '2026-10-07T00:00:00Z', value: [310_000, 'PLN'], scope: 'supply' },
  { words: 'fuel-supply-framework', noticeId: '583664-2026', sourceId: 'eu-ted', retrievedAt: '2026-10-11T06:20:00Z',
    title: 'Fuel supply framework', buyer: 0, buyerName: 'Demo Joint Procurement Cell (not yet matched to a buyer)', country: 'IT',
    cpvCodes: ['09100000'], procedure: 'Restricted procedure', legalBasis: '32009L0081',
    deadline: '2026-12-01T00:00:00Z', publishedAt: '2026-10-03T00:00:00Z', value: [12_000_000, 'EUR'] },
  { words: 'road-transport-services-framework', noticeId: '592450-2026', sourceId: 'eu-ted', retrievedAt: '2026-10-11T06:20:00Z',
    title: 'Road transport services framework', titleLanguage: null, buyer: 4, cpvCodes: ['60100000'], procedure: 'Open procedure', legalBasis: '32009L0081',
    deadline: '2026-11-30T00:00:00Z', publishedAt: '2026-10-06T00:00:00Z', value: [2_900_000, 'EUR'] },
  { words: 'warehouse-racking-supply-and-installation', noticeId: '608821-2026', sourceId: 'eu-ted', retrievedAt: '2026-10-11T06:20:00Z',
    title: 'Warehouse racking: supply and installation', buyer: 1, cpvCodes: ['39150000', '45223000'], procedure: 'Open procedure', legalBasis: '32009L0081',
    deadline: '2026-11-09T00:00:00Z', publishedAt: '2026-10-10T00:00:00Z', value: [1_800_000, 'EUR'], subcontracting: true },
  // A prior information notice: planned, no deadline (WP-52, T8). It is neither open nor closed; first seen before the 14-day window of the change list.
  { words: 'vehicle-spare-parts-framework-prior-information', noticeId: '611904-2026', sourceId: 'eu-ted', retrievedAt: '2026-09-20T06:20:00Z',
    title: 'Prior information: vehicle spare parts framework for 2027', buyer: 3, cpvCodes: ['34300000'], procedure: 'Open procedure', legalBasis: '32009L0081',
    deadline: null, publishedAt: '2026-09-18T00:00:00Z', native: 'forthcoming' },
];

/** Two to three observed versions on the notices that were amended (newest first). */
const RAW_VERSIONS: Record<string, TenderVersion[]> = {
  'framework-agreement-machined-aluminium-housings': [
    { version: 3, detectedAt: '2026-10-10T06:20:00Z', changes: [{ field: 'deadline', label: 'Deadline', before: '12 Nov 2026', after: '26 Nov 2026' }] },
    { version: 2, detectedAt: '2026-10-05T06:20:00Z', changes: [{ field: 'estimated_value', label: 'Estimated value', before: 'EUR 3,100,000', after: 'EUR 3,400,000' }] },
    { version: 1, detectedAt: '2026-09-28T06:20:00Z', changes: [] },
  ],
  'uniform-textiles-framework': [
    { version: 2, detectedAt: '2026-10-02T06:20:00Z', changes: [{ field: 'deadline', label: 'Deadline', before: '12 Oct 2026', after: '20 Oct 2026' }, { field: 'procedure', label: 'Procedure', before: null, after: 'Negotiated procedure' }] },
    { version: 1, detectedAt: '2026-08-30T06:20:00Z', changes: [] },
  ],
  'fuel-supply-framework': [
    // WP-90: two of our own re-readings of the payload we held (`correction`): the page folds them away under the publisher's changes
    { version: 4, sequence: 4, detectedAt: '2026-10-11T06:20:00Z', correction: true, changes: [{ field: 'procedure', label: 'Procedure', before: 'Open procedure', after: 'Restricted procedure' }] },
    { version: 3, sequence: 3, detectedAt: '2026-10-10T06:20:00Z', correction: true, changes: [{ field: 'buyer', label: 'Buyer', before: 'Demo Joint Procurement', after: 'Demo Joint Procurement Cell' }] },
    { version: 2, sequence: 2, detectedAt: '2026-10-09T06:20:00Z', changes: [{ field: 'title', label: 'Title', before: 'Fuel supply', after: 'Fuel supply framework' }] },
    { version: 1, sequence: 1, detectedAt: '2026-10-03T06:20:00Z', changes: [] },
  ],
};

/**
 * WP-90: what the notice's own page adds (GET /v1/tenders/{slug}): the first sentence of the description where it reads as a commercial
 * subject, and the address of the procurement documents where a source names one (invented, as everything here).
 */
const DETAIL: Record<string, Partial<Pick<Tender, 'subject' | 'documentsUrl' | 'awardedTo' | 'awardedPersons' | 'awardValue' | 'otherBuyers'>>> = {
  'framework-agreement-machined-aluminium-housings': {
    subject: 'Framework agreement for the supply of machined aluminium housings for vehicle electronics, in two lots.',
    documentsUrl: 'https://www.example.org/demo-documents/561204-2026',
  },
  // WP-95: an award notice names its winners (a supplier page link where there is one) and says what its value is
  'packaging-and-logistics-services': {
    awardedTo: [{ name: 'Demo Logistics B.V.', slug: '4-demo-logistics-bv', country: 'NL', valueAmount: 4_750_000, valueCurrency: 'EUR', valueKind: 'contract' }],
    awardedPersons: 1,
    awardValue: { amount: 4_750_000, currency: 'EUR', kind: 'contract' },
    otherBuyers: ['Demo Joint Support Service'],
  },
};

const buyerId = (i: number) => String(i + 1);

function isClosed(r: RawTender, ref: Date): boolean {
  // The API's `status` is open | closed: a planned (forthcoming) notice is not open, so it reads closed there; `statusNative` says planned.
  if (r.native === 'awarded' || r.native === 'cancelled' || r.native === 'forthcoming') return true;
  return r.deadline !== null && new Date(r.deadline).getTime() <= ref.getTime();
}

function toTender(r: RawTender, index: number, ref: Date): Tender {
  const src = sourceById(r.sourceId);
  const id = String(index + 1);
  const b = r.buyer > 0 ? RAW_BUYERS[r.buyer - 1] : null;
  const versions = RAW_VERSIONS[r.words];
  const value: Money | null = r.value ? { amount: r.value[0], currency: r.value[1] } : null;
  return {
    id, slug: `${id}-${r.words}`, noticeId: r.noticeId,
    title: r.title, titleLanguage: r.titleLanguage === undefined ? 'en' : r.titleLanguage,
    originalTitle: r.originalTitle ?? null, originalLanguage: r.originalLanguage ?? null,
    buyerId: b ? buyerId(r.buyer - 1) : null, buyerSlug: b ? `${buyerId(r.buyer - 1)}-${b.words}` : null,
    buyerName: b ? b.name : (r.buyerName ?? 'Unknown buyer'), country: b ? b.country : (r.country ?? null),
    cpv: r.cpvCodes[0] ?? null, cpvCodes: r.cpvCodes, procedure: r.procedure ?? null, legalBasis: r.legalBasis ?? null,
    scope: r.scope ?? 'core', deadline: r.deadline, publishedAt: r.publishedAt, estimatedValue: value,
    status: isClosed(r, ref) ? 'closed' : 'open', statusNative: r.native ?? (isClosed(r, ref) ? 'expired' : 'open'),
    amended: (versions?.length ?? 1) > 1, versionCount: versions?.length ?? 1,
    securityClearance: r.security ?? false, subcontracting: r.subcontracting ?? false,
    sameNotice: r.sameNotice ?? [],
    source: {
      sourceId: src.id, sourceName: src.name, url: src.url ? `${src.url}/${r.noticeId.replace(/\W+/g, '-').toLowerCase()}` : null,
      retrievedAt: r.retrievedAt, lastChangeKind: (versions?.length ?? 1) > 1 ? 'amendment' : 'first_seen',
      licence: src.licence, attribution: src.attribution,
    },
  };
}

export function allTenders(ref: Date = now()): Tender[] {
  return RAW.map((r, i) => toTender(r, i, ref));
}

const time = (iso: string) => new Date(iso).getTime();

export function queryTenders(f: TenderFilters, ref: Date = now()): Paginated<Tender> {
  const q = f.q?.toLowerCase();
  const status = f.status ?? 'open';
  const scope = f.scope ?? 'relevant';
  const currency = f.currency ?? 'EUR';
  let items = allTenders(ref).filter((t) => {
    // Like the API: a planned notice is neither open nor closed; `all` has them.
    const planned = t.statusNative === 'forthcoming';
    if (status === 'planned' ? !planned : status === 'closed' ? t.status !== 'closed' || planned : status === 'open' && t.status !== 'open') return false;
    if (scope !== 'all' && scope !== 'relevant' && t.scope !== scope) return false;
    if (f.buyer && t.buyerId !== f.buyer) return false;
    // WP-90: the main code only, and the codes to leave out (any of the notice's), as the API reads them
    const codes = f.cpvMain ? t.cpvCodes.slice(0, 1) : t.cpvCodes;
    if (f.cpv?.length && !codes.some((c) => f.cpv!.some((p) => c.startsWith(p)))) return false;
    if (f.notCpv?.length && t.cpvCodes.some((c) => f.notCpv!.some((p) => c.startsWith(p)))) return false;
    if (f.country && (!t.country || !f.country.includes(t.country))) return false;
    if (f.deadlineFrom || f.deadlineTo) {
      if (t.deadline === null) return false;
      if (f.deadlineFrom && time(t.deadline) < time(`${f.deadlineFrom}T00:00:00Z`)) return false;
      if (f.deadlineTo && time(t.deadline) > time(`${f.deadlineTo}T23:59:59Z`)) return false;
    }
    if (f.valueMin !== undefined || f.valueMax !== undefined || f.currency) {
      // A currency alone lists the notices that state a value in it; a range is read in it (EUR when none is given).
      // Values in another currency are never compared with it.
      const v = t.estimatedValue;
      if (!v || v.amount <= 1 || v.currency !== currency) return false;
      if (f.valueMin !== undefined && v.amount < f.valueMin) return false;
      if (f.valueMax !== undefined && v.amount > f.valueMax) return false;
    }
    // WP-90: or every word begins a word of the English title of one of the notice's own CPV codes
    if (q && ![t.title, t.originalTitle, t.buyerName, t.noticeId].some((s) => s?.toLowerCase().includes(q))
      && !q.split(/\s+/).filter(Boolean).every((w) => t.cpvCodes.some((c) => titleHasWord(cpvTitle(c), w)))) return false;
    return true;
  });
  const sort = f.sort ?? defaultTenderSort(status);
  if (sort === 'published-desc') {
    items = items.sort((a, b) => time(b.publishedAt ?? '1970-01-01T00:00:00Z') - time(a.publishedAt ?? '1970-01-01T00:00:00Z'));
  } else {
    const newestFirst = sort === 'deadline-desc';
    // Like the API (WP-87): the open list's default leads with the core notices, each part soonest deadline first.
    const coreFirst = sort === 'core-first' && status === 'open' && scope === 'relevant';
    items = items.sort((a, b) => {
      if (coreFirst && (a.scope === 'core') !== (b.scope === 'core')) return a.scope === 'core' ? -1 : 1;
      if ((a.deadline === null) !== (b.deadline === null)) return a.deadline === null ? 1 : -1;
      if (a.deadline === null || b.deadline === null) return 0;
      return newestFirst ? time(b.deadline) - time(a.deadline) : time(a.deadline) - time(b.deadline);
    });
  }
  const pageSize = f.pageSize ?? TENDER_PAGE_SIZE;
  const page = f.page ?? 1;
  return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, totalCapped: false, page, pageSize, asOf: ref.toISOString() };
}

/**
 * What GET /v1/tenders/calendar answers: the open notices that state a deadline, soonest first, with what a calendar draws.
 * WP-87: under the tender list's own filters, read as the list reads them.
 */
export function queryCalendar(ref: Date = now(), f: TenderFilters = {}): CalendarPage {
  const items: CalendarItem[] = queryTenders({ ...f, status: 'open', sort: 'deadline-asc', page: 1, pageSize: 100_000 }, ref).items
    .filter((t) => t.status === 'open' && t.deadline !== null)
    .sort((a, b) => time(a.deadline!) - time(b.deadline!))
    .map((t) => ({
      id: t.id, slug: t.slug, noticeId: t.noticeId, title: t.title, buyerName: t.buyerName, country: t.country, deadline: t.deadline!,
      deadlineFrom: null, scope: t.scope, status: t.status, statusNative: t.statusNative, anomalies: t.anomalies ?? [], sourceName: t.source.sourceName,
    }));
  return { items, total: items.length, truncated: false, asOf: ref.toISOString() };
}

const CHANGE_WINDOW_DAYS = 14;
/** The fields an amendment is listed for (the API's allow-list, in the mock's own field names). */
const CHANGE_FIELDS = new Set(['deadline', 'estimated_value', 'status', 'procedure']);

/** Whether the API would answer `week`: the archive began in 2026-W37, and a week that has not ended is not an issue yet. */
export function weekAvailable(week: string, ref: Date = now()): boolean {
  // WP-90: the week under way too, up to now
  return week >= '2026-W37' && (weekMonday(week).getTime() + 7 * 86_400_000 <= ref.getTime() || week === weekOf(ref));
}

/** WP-90: the mock's field names of each kind of change (the API's `changes.KIND_FIELDS`). */
const KIND_FIELDS: Record<string, string[]> = { deadline: ['deadline'], value: ['estimated_value'], status: ['status'] };

/** What the API's /v1/changes answers, built from the mock versions: a notice first seen in the window is new. */
export function queryChanges(f: ChangeFilters, ref: Date = now()): ChangePage {
  // `week` is a week of the digest instead of the last 14 days (weekAvailable says whether the API would answer it).
  const weekStart = f.week ? weekMonday(f.week).getTime() : null;
  const since = weekStart ?? ref.getTime() - CHANGE_WINDOW_DAYS * 86_400_000;
  const end = weekStart !== null ? Math.min(weekStart + 7 * 86_400_000 - 1, ref.getTime()) : ref.getTime();
  const all: Change[] = [];
  // WP-87: the tender list's other filters, read by the list's own rules (any status); WP-90: the rest, and the status as of now
  const narrowed = f.q || f.cpv || f.notCpv || f.status || f.deadlineFrom || f.deadlineTo || f.valueMin !== undefined || f.valueMax !== undefined || f.currency;
  const kept = narrowed ? new Set(queryTenders({
    q: f.q, cpv: f.cpv, cpvMain: f.cpvMain, notCpv: f.notCpv, deadlineFrom: f.deadlineFrom, deadlineTo: f.deadlineTo, valueMin: f.valueMin,
    valueMax: f.valueMax, currency: f.currency, status: f.status ?? 'all', scope: 'all', page: 1, pageSize: 100_000,
  }, ref).items.map((t) => t.id)) : null;
  for (const t of allTenders(ref)) {
    if (kept && !kept.has(t.id)) continue;
    if (f.country?.length && (!t.country || !f.country.includes(t.country))) continue;
    if (f.scope !== 'all' && f.scope !== 'relevant' && t.scope !== (f.scope ?? t.scope)) continue;
    const versions = [...(tenderVersions(t.slug) ?? [])].sort((a, b) => a.version - b.version);
    versions.forEach((v, i) => {
      const at = new Date(v.detectedAt);
      if (at.getTime() < since || at.getTime() > end) return;
      const lines = v.changes.filter((c) => CHANGE_FIELDS.has(c.field));
      if (i > 0 && lines.length === 0) return;
      const day = v.detectedAt.slice(0, 10);
      all.push({ id: `${t.id}-${day.replace(/-/g, '')}`, kind: i === 0 ? 'new' : 'amended', day, detectedAt: v.detectedAt, changes: i === 0 ? [] : lines, tender: t });
    });
  }
  all.sort((a, b) => b.detectedAt.localeCompare(a.detectedAt) || b.id.localeCompare(a.id));
  const shown = !f.kind ? all : all.filter((c) => (f.kind === 'new' || f.kind === 'amended' ? c.kind === f.kind
    : c.kind === 'amended' && c.changes.some((l) => KIND_FIELDS[f.kind!].includes(l.field))));
  const pageSize = f.pageSize ?? 25;
  const page = f.page ?? 1;
  return {
    items: shown.slice((page - 1) * pageSize, page * pageSize), total: shown.length, page, pageSize,
    windowDays: weekStart !== null ? 7 : CHANGE_WINDOW_DAYS, windowFrom: new Date(since).toISOString(), windowTo: new Date(end + (weekStart !== null ? 1 : 0)).toISOString(),
    counts: { new: all.filter((c) => c.kind === 'new').length, amended: all.filter((c) => c.kind === 'amended').length },
  };
}

/** Like the API: only the leading integer of "<id>-<words>" is looked up. */
export function findTender(slug: string, ref: Date = now()): Tender | null {
  const id = /^(\d+)(?:-|$)/.exec(slug)?.[1];
  const t = id ? (allTenders(ref).find((x) => x.id === id) ?? null) : null;
  return t ? { ...t, subject: null, documentsUrl: null, awardedTo: [], awardedPersons: 0, awardValue: null, ...DETAIL[RAW[Number(t.id) - 1].words] } : null;
}

export function tenderVersions(slug: string): TenderVersion[] | null {
  const t = findTender(slug);
  if (!t) return null;
  const raw = RAW[Number(t.id) - 1];
  return RAW_VERSIONS[raw.words] ?? [{ version: 1, detectedAt: t.source.retrievedAt, changes: [] }];
}

export function allBuyers(ref: Date = now()): Buyer[] {
  const tenders = allTenders(ref).filter((t) => t.scope === 'core');
  return RAW_BUYERS.map((b, i) => {
    const mine = tenders.filter((t) => t.buyerId === buyerId(i));
    const published = mine.flatMap((t) => (t.publishedAt ? [t.publishedAt] : [])).sort();
    return {
      id: buyerId(i), slug: `${buyerId(i)}-${b.words}`, name: b.name, country: b.country,
      tenderCount: mine.length, openCount: mine.filter((t) => t.status === 'open').length,
      lastPublishedAt: published.at(-1) ?? null, isDefenceBuyer: b.defence,
      nameVariants: i === 0 ? 2 : 0,
    };
  });
}

export function queryBuyers(f: BuyerFilters, ref: Date = now()): Paginated<Buyer> {
  const q = f.q?.toLowerCase();
  // Only buyers with at least one core-scope notice are listed.
  // WP-89: a CPV filter keeps the buyers with a core notice under one of the prefixes; their counts stay all of their notices
  const withCode = f.cpv?.length
    ? new Set(allTenders(ref).filter((t) => t.scope === 'core' && t.cpvCodes.some((c) => f.cpv!.some((p) => c.startsWith(p)))).map((t) => t.buyerId))
    : null;
  let items = allBuyers(ref).filter((b) => {
    if (b.tenderCount === 0) return false;
    if (withCode && !withCode.has(b.id)) return false;
    if (f.hasOpen && b.openCount === 0) return false;
    if (f.country && (!b.country || !f.country.includes(b.country))) return false;
    if (q && !b.name.toLowerCase().includes(q)) return false;
    return true;
  });
  items = items.sort((a, b) => ((f.sort ?? 'tenders') === 'name' ? a.name.localeCompare(b.name) : b.tenderCount - a.tenderCount || a.name.localeCompare(b.name)));
  const pageSize = f.pageSize ?? BUYER_PAGE_SIZE;
  const page = f.page ?? 1;
  return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, pageSize };
}

export function findBuyer(slug: string, ref: Date = now()): Buyer | null {
  const id = /^(\d+)(?:-|$)/.exec(slug)?.[1];
  return id ? (allBuyers(ref).find((b) => b.id === id) ?? null) : null;
}
