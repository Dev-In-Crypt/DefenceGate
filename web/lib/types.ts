// Domain types. The funding types follow docs/design/API_CONTRACT.md (/v1/funding, /v1/sources),
// which is authoritative. Tender types (Opportunity*) are P2 and still modelled on the design.

/** Funder countries we collect. 'EU' = an EU programme. */
export type CountryCode = 'EU' | 'PL' | 'SE' | 'FR' | 'ES' | 'FI' | 'DE' | 'IT' | 'NL';
/** ISO 4217 as the source states it. Amounts are never converted. */
export type CurrencyCode = string;
export type ProgrammeCode = 'EDF' | 'EDIP' | 'HORIZON' | 'DIGITAL' | 'NATIONAL';
export type Regime = 'defence' | 'dual-use';
export type CallStatus = 'open' | 'forthcoming' | 'closed';
/** Deadline presentation state, derived in lib/deadline.ts — never stored. 'none' = no stated deadline. */
export type DeadlineState = 'normal' | 'soon' | 'urgent' | 'closed' | 'none';
/** UI status pill values. 'upcoming' = a forthcoming call ("Opens soon"). */
export type StatusKind = 'open' | 'upcoming' | 'soon' | 'closed' | 'amended';

/** ISO 8601 timestamp, always UTC (e.g. "2026-11-26T16:00:00Z"). */
export type IsoDateTime = string;

export interface Money {
  amount: number;
  currency: CurrencyCode;
}

/** Provenance for every fact shown. Rendered by <SourceBadge>. */
export interface SourceAttribution {
  sourceId: string;
  sourceName: string;
  /** Link to the original record at the source. */
  url: string | null;
  /** = lastSeenAt of the call. */
  retrievedAt: IsoDateTime;
  licence: string;
  attribution: string;
}

export interface EligibilityItem {
  label: string;
  value: string;
}

/** GET /v1/funding (list), GET /v1/funding/{slug} (detail, with conditionsText) */
export interface Call {
  /** Numeric id as a string. */
  id: string;
  /** "<id>-<words>"; only the leading integer is looked up by the API. */
  slug: string;
  programme: ProgrammeCode;
  /** "Horizon Europe", "Vinnova calls in the civil-military ..." */
  programmeName: string;
  /** EU call identifier; null for national sources. */
  callId: string | null;
  /** EU topic code, or the source's own identifier. */
  topicId: string;
  /** The heading: English where the source publishes one, otherwise the source language. */
  title: string;
  /** ISO 639-1 of `title`. */
  titleLanguage: string;
  /** The other language, when the source gives both. */
  originalTitle: string | null;
  /** ISO 639-1 of `originalTitle`. */
  originalLanguage: string | null;
  regime: Regime;
  /** 'EU' for an EU programme. */
  funderCountry: CountryCode;
  /** The body that issues a national call. */
  issuer: string | null;
  status: CallStatus;
  openingDate: IsoDateTime | null;
  /** null: no stated deadline (a standing call). Never "closed". */
  deadline: IsoDateTime | null;
  budget: Money | null;
  /** 'call': the pot several topics share. */
  budgetScope: 'call' | 'topic' | null;
  actionType: string | null;
  /** Not collected yet; always null. */
  fundingRate: string | null;
  /** Keywords the source publishes; may be empty. */
  scope: string[];
  /** Structured rows only; may be empty. */
  eligibility: EligibilityItem[];
  /** The source's own date for the call, where it states one. */
  publishedAt: IsoDateTime | null;
  firstSeenAt: IsoDateTime;
  /** When we last saw the source list it. */
  lastSeenAt: IsoDateTime;
  source: SourceAttribution;
  /** Detail only: the source's own conditions text, in its language, unedited. */
  conditionsText?: string | null;
}

export type CallStatusFilter = 'open' | 'forthcoming' | 'closing-soon' | 'closed' | 'all';
export type CallSort = 'deadline-asc' | 'deadline-desc' | 'budget-desc';
export type ListView = 'list' | 'calendar';

export interface CallFilters {
  q?: string;
  programme?: ProgrammeCode[];
  regime?: Regime[];
  country?: CountryCode[];
  status?: CallStatusFilter;
  /** YYYY-MM-DD, inclusive, UTC */
  deadlineFrom?: string;
  deadlineTo?: string;
  /** Amounts in `currency` (never converted). */
  budgetMin?: number;
  budgetMax?: number;
  /** ISO 4217 that budgetMin, budgetMax and sort=budget-desc refer to. Default EUR. */
  currency?: CurrencyCode;
  sort?: CallSort;
  page?: number;
  pageSize?: number;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

/** GET /v1/opportunities, GET /v1/opportunities/{id} (tenders) */
export interface Opportunity {
  id: string;
  slug: string;
  noticeId: string;
  title: string;
  originalTitle?: string;
  originalLanguage?: string;
  buyerId: string;
  buyerName: string;
  country: CountryCode;
  cpv: string;
  cpvDivision: string;
  procedure: string;
  deadline: IsoDateTime;
  publishedAt: IsoDateTime;
  estimatedValue: Money | null;
  status: CallStatus;
  amended: boolean;
  versionCount: number;
  source: SourceAttribution;
}

export interface OpportunityFilters {
  q?: string;
  country?: CountryCode[];
  cpv?: string[];
  deadlineFrom?: string;
  deadlineTo?: string;
  valueMin?: number;
  valueMax?: number;
  scope?: Regime[];
  status?: CallStatusFilter;
  amended?: boolean;
  page?: number;
  pageSize?: number;
}

/** GET /v1/opportunities/{id}/versions */
export interface FieldChange {
  field: string;
  label: string;
  before: string | null;
  after: string | null;
}
export interface OpportunityVersion {
  version: number;
  detectedAt: IsoDateTime;
  changes: FieldChange[];
}

/** GET /v1/sources */
export type RunStatus = 'ok' | 'partial' | 'failed' | 'never';
export type SourceType = 'grants' | 'tenders';
export interface SourceHealth {
  id: string;
  name: string;
  country: CountryCode | null;
  type: SourceType;
  url: string | null;
  lastRunAt: IsoDateTime | null;
  status: RunStatus;
  /** Fetched in the last run. */
  records: number;
  /** fetched / expected minimum of that run, capped at 1; null when the source has no floor. */
  coverage: number | null;
  licence: string;
  attribution: string;
}
export interface Health {
  generatedAt: IsoDateTime;
  sources: SourceHealth[];
}

export interface SiteStats {
  openCalls: number;
  sources: number;
  lastUpdate: IsoDateTime;
}
