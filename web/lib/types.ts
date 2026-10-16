// Domain types. They follow docs/design/API_CONTRACT.md (/v1/funding, /v1/tenders, /v1/buyers, /v1/sources),
// which is authoritative.

/** Funder countries we collect. 'EU' = an EU programme. */
export type CountryCode = 'EU' | 'PL' | 'SE' | 'FR' | 'ES' | 'FI' | 'DE' | 'IT' | 'NL';
/** ISO 4217 as the source states it. Amounts are never converted. */
export type CurrencyCode = string;
export type ProgrammeCode = 'EDF' | 'EDIP' | 'HORIZON' | 'DIGITAL' | 'CEF' | 'NATIONAL';
export type Regime = 'defence' | 'dual-use';
export type CallStatus = 'open' | 'forthcoming' | 'closed';
/** Deadline presentation state, derived in lib/deadline.ts — never stored. 'none' = no stated deadline. */
export type DeadlineState = 'normal' | 'soon' | 'urgent' | 'closed' | 'none';
/** UI status pill values. 'upcoming' = a forthcoming call ("Opens soon"). */
export type StatusKind = 'open' | 'upcoming' | 'pending' | 'soon' | 'closed' | 'amended' | 'unknown';

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
  /**
   * A call: = lastSeenAt. A tender: when the notice last changed AT THE SOURCE, as we saw it (the newest version
   * that is not one of our own re-readings), never the time of our reprocessing.
   */
  retrievedAt: IsoDateTime;
  /** A tender: when the source's newest collection run finished (we last looked); absent for a call. */
  checkedAt?: IsoDateTime | null;
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
  /** Who pays: the issuing body of a national call, otherwise the European Commission (the portal's operator). */
  funder: string;
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
  /**
   * The source's own word for the status. It differs from `status` when the dates settle it: a call the source still
   * lists as forthcoming whose opening day has passed and whose deadline is ahead is served open.
   */
  sourceStatus?: string | null;
  openingDate: IsoDateTime | null;
  /** null: no stated deadline (a standing call). Never "closed". */
  deadline: IsoDateTime | null;
  /** The source gave a day, not a time of day: print the date only. Absent on API builds that do not send it. */
  deadlineIsDate?: boolean;
  /** Continuous or several cut-offs: `deadline` is the latest cut-off and an open call past it is still open. */
  rolling?: boolean;
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
  /** Detail only: who may apply, in the source's words where it gives them. Empty: the source says nothing. */
  whoCanApply?: EligibilityItem[];
  /** Detail only: the official documents the source links from the call. */
  documents?: CallDocument[];
}

export interface CallDocument {
  label: string;
  url: string;
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

/** `/v1/funding` with a search text: the words searched and the synonyms searched as well. */
export interface SearchInfo {
  terms: string[];
  alsoSearched: string[];
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  search?: SearchInfo | null;
  /** `/v1/tenders` and `/v1/funding`: `updatedAt` is when the newest successful or partial collection run of the list's sources finished (UTC), null before any. Absent on older API builds. */
  meta?: { updatedAt?: string | null } | null;
}

/** GET /v1/tenders (list), GET /v1/tenders/{slug} (detail). Contract: docs/design/API_CONTRACT.md. */
export type TenderStatus = 'open' | 'closed';
/** core: the notice itself is defence; supply: only the buyer is a defence body, or a single signal from the wrong kind of buyer (`qualifiedBy`). */
export type TenderScope = 'core' | 'supply';
export interface Tender {
  /** Numeric id as a string. */
  id: string;
  /** "<id>-<words>"; only the leading integer is looked up by the API. */
  slug: string;
  /** The source's own notice number, e.g. "123456-2026". */
  noticeId: string;
  /** English where the source gives one, otherwise the source language. */
  title: string;
  /** ISO 639-1 of `title`. */
  titleLanguage: string | null;
  /** The other language, when both exist. */
  originalTitle: string | null;
  originalLanguage: string | null;
  buyerId: string | null;
  buyerSlug: string | null;
  buyerName: string;
  /** ISO-2 of the buyer. */
  country: string | null;
  /** The main CPV code. */
  cpv: string | null;
  cpvCodes: string[];
  /** As the source states it. */
  procedure: string | null;
  /** e.g. "32009L0081" (Directive 2009/81/EC). */
  legalBasis: string | null;
  scope: TenderScope;
  /** null: none stated. A date-only deadline arrives as 00:00 UTC. */
  deadline: IsoDateTime | null;
  publishedAt: IsoDateTime | null;
  estimatedValue: Money | null;
  /** As of now: a passed deadline is closed. */
  status: TenderStatus;
  /** The effective status: open, expired, awarded, cancelled, forthcoming, unknown. Read through lib/tender-status.ts. */
  statusNative: string | null;
  /** The source gives the deadline as a date only. Absent on API builds that do not send it. */
  deadlineIsDate?: boolean;
  /** Things that look wrong in the source (e.g. 'deadline-before-publication'). Unknown codes are ignored. */
  anomalies?: string[];
  /** The buyer's name as resolved to one organisation record; `buyerName` is as published. */
  buyerCanonicalName?: string | null;
  /** What the estimated value is, as the API words it. Shown as given. */
  valueKind?: string | null;
  /** 'ted_twin': the notice states no value and `estimatedValue` is its TED twin's (say so). Absent or null: its own. */
  valueFrom?: string | null;
  /** 'ted_twin': the notice states no procedure and `procedure` is its TED twin's (say so). Absent or null: its own. */
  procedureFrom?: string | null;
  /** 'ted_twin': the national deadline is more than 90 days from its TED twin's and the twin's is shown. */
  deadlineFrom?: string | null;
  /** false: the source states no publication date; the site says "not stated" and the row stays listed. */
  publishedKnown?: boolean;
  /** The date and kind of the notice the record was last read from, where the source states them. Never a publication date. */
  noticeDate?: IsoDateTime | null;
  noticeKind?: string | null;
  /** false: the notice states no deadline, so `status` is a judgement ("deadline not stated"). Absent on older API builds. */
  deadlineKnown?: boolean;
  lotCount?: number | null;
  /** The API's own name for the lot count. */
  lots?: number | null;
  /** What kind of body the buyer is: defence, security, fire_rescue, health, education, municipal, other. */
  buyerClass?: string | null;
  /** Classified as dual-use rather than defence. */
  dualUse?: boolean;
  /**
   * What qualified the notice: `legal_basis`, `military_cpv` (a military product code; `militaryCpv` lists the codes
   * that are), `buyer` (only its buyer being on the defence list keeps it); or, for a notice filed in `supply` with a
   * single signal from the wrong kind of buyer, `directive_civil_buyer` (the directive alone, from a civil buyer) or
   * `security_buyer_cpv` (a military code alone, from a security body). Absent on an older API build.
   */
  qualifiedBy?: string[];
  militaryCpv?: string[];
  /** More than one version observed. */
  amended: boolean;
  versionCount: number;
  securityClearance: boolean;
  subcontracting: boolean;
  /** The same notice in other sources. `source` is the source's name or id (the contract does not say which). `id` and `noticeId` are the other notice's. */
  sameNotice: { source: string; url: string | null; id?: string; noticeId?: string }[];
  /** retrievedAt = when the source last changed the notice as we saw it; checkedAt = when we last collected that source. */
  source: SourceAttribution;
}

export type TenderStatusFilter = 'open' | 'closed' | 'all';
export type TenderScopeFilter = 'core' | 'supply' | 'all';
export type TenderSort = 'deadline-asc' | 'deadline-desc' | 'published-desc';
export interface TenderFilters {
  q?: string;
  country?: string[];
  status?: TenderStatusFilter;
  scope?: TenderScopeFilter;
  /** `defence`: only notices that say defence themselves (not kept in only by a listed buyer). */
  goods?: 'defence';
  /** CPV code prefixes (2 to 8 digits), at most 20. */
  cpv?: string[];
  /** Organisation id. Set by code (the buyer page), never read from the URL. */
  buyer?: string;
  /** YYYY-MM-DD, inclusive, UTC */
  deadlineFrom?: string;
  deadlineTo?: string;
  /** Estimated value in `currency` (never converted). */
  valueMin?: number;
  valueMax?: number;
  currency?: CurrencyCode;
  sort?: TenderSort;
  page?: number;
  pageSize?: number;
}

/** GET /v1/tenders/{slug}/versions, newest first. */
export interface FieldChange {
  field: string;
  label: string;
  before: string | null;
  after: string | null;
}
export interface TenderVersion {
  /** The archive's own row number: it has gaps. Show `sequence`. */
  version: number;
  /** 1 for the notice as first seen, then one per listed change. Absent on API builds that do not send it. */
  sequence?: number;
  /** When we first saw this version. */
  detectedAt: IsoDateTime;
  changes: FieldChange[];
}

/**
 * GET /v1/changes: what changed in the last 14 days. One entry per notice per UTC day. `new`: first collected in
 * the window; `amended`: its deadline, value, status or procedure changed, as the archive observed it (a bulk
 * re-reading of our own is never one). `changes` is empty for `new`.
 */
export type ChangeKind = 'new' | 'amended';
export interface Change {
  /** "<notice id>-<YYYYMMDD>": stable, so a feed reader does not show an entry twice. */
  id: string;
  kind: ChangeKind;
  /** The UTC day it was observed, YYYY-MM-DD. */
  day: string;
  /** The latest observation of that day. */
  detectedAt: IsoDateTime;
  changes: FieldChange[];
  tender: Tender;
}
export interface ChangePage {
  items: Change[];
  total: number;
  page: number;
  pageSize: number;
  windowDays: number;
  windowFrom: IsoDateTime;
  windowTo: IsoDateTime;
  counts: { new: number; amended: number };
  /** Funding calls first collected in the window or whose dates the source moved; page 1 only. Absent on older API builds. */
  funding?: FundingChange[];
  /** How many such calls there are in all, whatever the page. */
  fundingTotal?: number;
  meta?: { updatedAt?: string | null } | null;
}
/** A funding call that is new in the window (`call-new`) or whose closing or opening date the source moved (`call-amended`). */
export type FundingChangeKind = 'call-new' | 'call-amended';
export interface FundingChange {
  /** "call-<call id>-<YYYYMMDD>": one per call per UTC day. */
  id: string;
  kind: FundingChangeKind;
  day: string;
  detectedAt: IsoDateTime;
  /** Empty for `call-new`. `before` and `after` are ISO days. */
  changes: FieldChange[];
  call: Call;
}
/** `scope` absent: defence notices and supplies to defence buyers together. */
export interface ChangeFilters {
  country?: string[];
  scope?: TenderScopeFilter;
  goods?: 'defence';
  page?: number;
  pageSize?: number;
}

/** GET /v1/buyers (list), GET /v1/buyers/{slug} (detail). */
export interface Buyer {
  id: string;
  /** "<id>-<words>" */
  slug: string;
  name: string;
  country: string | null;
  /** Core-scope notices. */
  tenderCount: number;
  /** Of those, open now. */
  openCount: number;
  lastPublishedAt: IsoDateTime | null;
  /** On the curated list of defence bodies. */
  isDefenceBuyer: boolean;
}

/** GET /v1/stats/market: counts of core-scope notices published. Never spend, never market size. */
export interface MarketMonth { month: string; count: number; ted: number; partial: boolean }
export interface MarketStats {
  asOf: IsoDateTime;
  scope: 'core';
  unit: 'notices published';
  /** The 12-month window of every figure but `months`, as dates. */
  windowFrom: string;
  windowTo: string;
  /** Sources that contributed core notices in the window. */
  sourceCount: number;
  /** 36 calendar months, oldest first; the last may be incomplete. */
  months: MarketMonth[];
  countries: { total: number; items: { country: string; count: number }[]; other: number };
  sources: { id: string; name: string; count: number }[];
  amendments: { notices: number; amended: number; share: number | null };
  responseWindow: { notices: number; median: number | null; p25: number | null; p75: number | null };
  cpvGroups: { group: string; count: number }[];
  basis: Record<string, string>;
}

/** GET /v1/buyers/{slug}/profile: the buyer's own core-scope notices, counted. */
export interface BuyerProfile {
  buyerId: string;
  asOf: IsoDateTime;
  tenderCount: number;
  openNow: number;
  perYear: { year: number; count: number }[];
  cpvGroups: { group: string; count: number }[];
  responseWindow: { notices: number; median: number | null; p25: number | null; p75: number | null };
  amendments: { notices: number; amended: number; share: number | null };
  sources: { id: string; name: string; count: number }[];
  basis: Record<string, string>;
}

export type BuyerSort = 'tenders' | 'name';
export interface BuyerFilters {
  q?: string;
  country?: string[];
  hasOpen?: boolean;
  sort?: BuyerSort;
  page?: number;
  pageSize?: number;
}

/** GET /v1/sources */
export type RunStatus = 'ok' | 'partial' | 'failed' | 'never';
export type SourceType = 'grants' | 'tenders';
export interface SourceHealth {
  id: string;
  name: string;
  country: string | null;
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
  /** What we hold of this source: the span of publication dates and how many records. Absent from an older API. */
  heldFrom?: string | null;
  heldTo?: string | null;
  heldCount?: number | null;
  /** Of a tender source: the usual notices per month (median) and the months, `YYYY-MM`, well below it. */
  monthlyMedian?: number | null;
  gapMonths?: string[] | null;
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

/* ---- Accounts: docs/design/ACCOUNT_CONTRACT.md (binding). The browser never calls these; lib/account.ts does. ---- */

export type Role = 'supplier' | 'prime' | 'consultant' | 'grant_writer' | 'other';
export type Track = 'tenders' | 'funding';
/** core: defence only; all: include dual-use and supply notices. */
export type ProfileScope = 'core' | 'all';
export type Cadence = 'instant' | 'daily' | 'weekly' | 'off';

/** Free-text profile fields do not exist on purpose (data minimisation). */
export interface Profile {
  role: Role | null;
  tracks: Track[];
  /** ISO 3166-1 alpha-2, at most 20. */
  countries: string[];
  scope: ProfileScope;
  cadence: Cadence;
}

/** GET /v1/account/me */
export interface Me {
  id: string;
  email: string;
  createdAt: IsoDateTime;
  profile: Profile;
  onboarded: boolean;
  lastVisitAt: IsoDateTime | null;
  /** False when the account accepted an older version of the terms or the privacy notice (or none). */
  termsCurrent: boolean;
}

/** GET /v1/account/sessions */
export interface AccountSession {
  id: string;
  createdAt: IsoDateTime;
  lastSeenAt: IsoDateTime;
  current: boolean;
}

export type SearchKind = 'tender' | 'call';
/** The query parameters of GET /v1/tenders or GET /v1/funding: the site's own URL keys. */
export type SearchFilters = Record<string, string | number | boolean | string[]>;
export interface SavedSearch {
  id: string;
  /** 1..80 characters. */
  name: string;
  kind: SearchKind;
  filters: SearchFilters;
  cadence: Cadence;
  createdAt: IsoDateTime;
  matchCount: number;
  /** Matches published since the account's lastVisitAt. */
  newCount: number;
  lastMatchAt: IsoDateTime | null;
}

export type ShortlistStatus = 'watching' | 'evaluating' | 'bidding' | 'submitted' | 'dropped';
export type ShortlistKind = 'tender' | 'call';
export interface ShortlistItem {
  kind: ShortlistKind;
  /** Tender id or funding call id. */
  ref: string;
  status: ShortlistStatus;
  /** At most 500 characters. */
  note: string;
  createdAt: IsoDateTime;
  updatedAt: IsoDateTime;
  /** The public object; null when it no longer exists. */
  item: Tender | Call | null;
}

export type FollowKind = 'buyer' | 'programme';
export interface Follow {
  kind: FollowKind;
  /** Buyer id, or the programme code as in Call.programme. */
  ref: string;
  createdAt: IsoDateTime;
  item: Buyer | { code: string; name: string; openCount: number } | null;
}

/** POST /v1/account/state */
export interface StateKey { type: 'shortlist' | 'follow'; kind: string; ref: string }
export interface StateItem extends StateKey { saved: boolean; status?: ShortlistStatus }

/** GET /v1/account/dashboard */
export interface DashboardMatch {
  search: { id: string; name: string; kind: SearchKind };
  newCount: number;
  totalCount: number;
  /** Up to 5, newest first. */
  items: (Tender | Call)[];
}
export interface DashboardClosing { kind: SearchKind; item: Tender | Call; source: 'shortlist' | 'search' }
export interface DashboardChange { kind: SearchKind; item: Tender | Call; observedAt: IsoDateTime; changes: FieldChange[] }
export interface DashboardFollowing { kind: FollowKind; ref: string; name: string; openCount: number; latestAt: IsoDateTime | null }
export interface DashboardPulse {
  asOf: IsoDateTime;
  tendersPublished30d: number;
  tendersPublishedPrev30d: number;
  openTenders: number;
  closingWithin14d: number;
  /** Share (0..1) of notices with an amendment in the last 30 days. */
  amendedShare30d: number;
  /** Publication to deadline, notices published in the last 90 days. */
  medianWindowDays: number | null;
}
export interface Dashboard {
  lastVisitAt: IsoDateTime | null;
  matches: DashboardMatch[];
  closingSoon: DashboardClosing[];
  changes: DashboardChange[];
  following: DashboardFollowing[];
  shortlist: { counts: Partial<Record<ShortlistStatus, number>>; items: ShortlistItem[] };
  pulse: DashboardPulse | null;
}
