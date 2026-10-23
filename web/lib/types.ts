// Domain types. They follow docs/design/API_CONTRACT.md (/v1/funding, /v1/tenders, /v1/buyers, /v1/sources),
// which is authoritative.
import type { ValueTotals } from './value-totals';

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
  /** A tender: what `retrievedAt` is. `amendment` = the newest change we saw the source make; `first_seen` = no change seen, it is when we first collected the notice. Absent on older API builds. */
  lastChangeKind?: 'amendment' | 'first_seen' | null;
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
  /** Only when `budget` is null: why there is none, from what the source states (never a number of ours). Absent on older API builds. */
  budgetNote?: BudgetNote | null;
  actionType: string | null;
  /** Not collected yet; always null. */
  fundingRate: string | null;
  /** Keywords the source publishes; may be empty. */
  scope: string[];
  /** Structured rows only; may be empty. */
  eligibility: EligibilityItem[];
  /**
   * Financial support to third parties (cascade funding): true or false where a source we hold says so, null where
   * nothing does. Null is "not determined", never "no". Absent on older API builds.
   */
  cascade?: boolean | null;
  /**
   * Open to Ukrainian participants: true or false where a source we hold says so, null where nothing does. Null is
   * "unknown", never "no". Absent on older API builds.
   */
  openToUkraine?: boolean | null;
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
  /** Detail only: the rules read from the call document (verified quotes only), or null when it was not read. */
  documentEligibility?: CallDocumentEligibility | null;
  /**
   * Detail only. `read`: facts are served; `not_read`: the places the rules are written are known (`eligibilitySources`)
   * and none has been read yet; `no_source`: the portal lists nothing we can read.
   */
  eligibilityState?: 'read' | 'not_read' | 'no_source';
  eligibilitySources?: EligibilitySourceInfo[];
  /** Detail only: how `cascade` was decided and the sentence it rests on. Absent when it is not determined. */
  cascadeBasis?: { reason: string; evidence: string | null } | null;
  /** Detail only: the area earlier projects are compared in for partner suggestions ("EDF capability category SPACE"); null when the call has none. */
  partnerArea?: string | null;
  /** Detail only: how `openToUkraine` was decided and the sentence it rests on. Absent when the call has no flag yet. */
  ukraineBasis?: { reason: string; evidence: string | null } | null;
  /** Detail only: the regime the call is under and its headline conditions, each with its source. Absent on older API builds. */
  rulesApply?: RulesApply | null;
}

/** Why a call has no budget figure (GET /v1/funding `budgetNote`). `perProject` is a ceiling the source states per project, not a budget. */
export interface BudgetNote {
  reason: string;
  /** One line for a list card. */
  short: string;
  /** The full sentence for the call page. */
  text: string;
  perProject?: Money | null;
}

/** The "rules that apply" block of a call (GET /v1/funding/{slug} `rulesApply`). */
export interface RulesApply {
  regime: { code: string; name: string; why: string };
  /** False: the regime is named but no rules of it are encoded. */
  encoded: boolean;
  programme?: { code: string; name: string; legalBasis: string | null };
  /** The kind of action of an EDIP call, which decides which rules are listed (who may apply to common procurement), else null. */
  action?: string | null;
  rules: {
    rule: string; title: string; kind: string; requirement: string | null;
    /** A sentence that qualifies the rule for some applicants (Ukraine and the EDF; the exemption of Article 9(9)), or null. */
    caveat?: string | null;
    source: { url: string; ref: string | null; text: string | null; origin: string; verificationStatus: string; lastReviewed: string };
  }[];
  alsoRead: { label: string; ref: string; text: string; url: string } | null;
  notice: string;
}

/** Where some of a call's rules are written: its call document, the work programme's general annexes, or the topic's own text. */
export interface EligibilitySourceInfo {
  scope: 'call_document' | 'general' | 'topic';
  label: string;
  url: string | null;
  extractedAt: IsoDateTime | null;
}

export interface CallDocumentEligibility {
  /** The document the facts were read from; null when they come from the topic's own text only. */
  documentUrl: string | null;
  extractedAt: IsoDateTime;
  /** `work_programme`: the call has no call document, and the facts come from the general annexes and the topic's text. */
  basis?: 'call_document' | 'work_programme';
  sources?: EligibilitySourceInfo[];
  facts: Record<string, { value: unknown; note?: string | null; quote: string; confidence: number; scope?: 'call_document' | 'general' | 'topic' }>;
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
  /** Only calls with cascade funding (financial support to third parties). */
  cascade?: boolean;
  /** Only calls open to Ukrainian participants (the flag is true; unknown is not included). */
  ukraine?: boolean;
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
  /** `/v1/suppliers` and `/v1/tenders`: the list serves no position beyond this (WP-39, WP-52); absent on other lists. */
  maxOffset?: number;
  /** `/v1/tenders`: the count stopped at its cap, so `total` is "at least this many". Absent on older API builds. */
  totalCapped?: boolean;
  /** `/v1/suppliers`: always false since WP-81 (a group of fewer than three suppliers was withheld before). */
  withheld?: boolean;
  search?: SearchInfo | null;
  /** `/v1/funding`: calls with cascade funding among those that match every filter but this one. Absent on older API builds. */
  cascadeTotal?: number | null;
  /** `/v1/funding`: calls open to Ukrainian participants among those that match every filter but this one. Absent on older API builds. */
  ukraineTotal?: number | null;
  /** `/v1/tenders` and `/v1/funding`: `updatedAt` is when the newest successful or partial collection run of the list's sources finished (UTC), null before any. Absent on older API builds. */
  /** `updatedBy` (WP-87): the source whose run that was, named on the page. */
  meta?: { updatedAt?: string | null; updatedBy?: string | null } | null;
  /** `/v1/tenders`: when this page was worked out (a kept page says when it was made). Absent on older API builds. */
  asOf?: IsoDateTime;
  /** Set by lib/api.ts, never by the API: the data service did not answer, and this is its last good answer, received at this time. */
  staleAsOf?: IsoDateTime;
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
  /**
   * How sure we are the notice is defence procurement: `high` (a military product code and a listed defence buyer
   * agree), `medium` (the buyer is a defence body, or the directive and a military code agree) or `low` (one weak
   * signal). `basis` is the reason in plain words. A statement about the group of notices that get the level,
   * measured on a sample (methodology), never about the single notice. Absent on an older API build.
   */
  confidence?: { level: 'high' | 'medium' | 'low'; basis: string[] } | null;
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

/** `planned` (19 October 2026): a prior information notice whose deadline, if it states one, is ahead. `closed` no longer holds them. */
export type TenderStatusFilter = 'open' | 'closed' | 'planned' | 'all';
/** `relevant` (the default since 16 October 2026): core and supply together. See SCOPE_CHOICES in lib/taxonomy.ts. */
export type TenderScopeFilter = 'relevant' | 'core' | 'supply' | 'all';
/** GET /v1/tenders/scope-counts: what each scope choice leads to, for the other filters as given. */
export interface ScopeCounts {
  relevant: number;
  core: number;
  supply: number;
  /** core + supply - relevant: supply notices that are the national copy of a core one (shown once in `relevant`). Absent on older API builds. */
  overlap?: number;
  /** A count stopped at its cap: the figures are "at least". */
  capped?: boolean;
  /** When the counts were worked out. */
  asOf?: IsoDateTime;
}
/** `core-first` (WP-87): the default of the open list, the core notices first, each part soonest deadline first. */
export type TenderSort = 'core-first' | 'deadline-asc' | 'deadline-desc' | 'published-desc';
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

/**
 * GET /v1/tenders/calendar: every open notice that states a deadline, with what a calendar draws and nothing else.
 * `deadline` is the one the notice's page shows (`deadlineFrom: 'ted_twin'` when it is the TED twin's).
 */
export interface CalendarItem {
  id: string;
  slug: string;
  noticeId: string;
  title: string;
  buyerName: string;
  country: string | null;
  deadline: IsoDateTime;
  deadlineFrom?: string | null;
  scope: TenderScope;
  status: TenderStatus;
  statusNative: string | null;
  anomalies?: string[];
  sourceName: string;
}
export interface CalendarPage {
  items: CalendarItem[];
  /** Open notices with a deadline in all; `truncated` when `items` holds fewer (maxItems). */
  total: number;
  truncated: boolean;
  asOf?: IsoDateTime;
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
  /** A history load wrote this version: `detectedAt` is when we read the change, not when it was published. */
  historic?: boolean;
  /** Our own corrected reading of a notice we already held (`remapped`): shown, not counted as the publisher's change. */
  correction?: boolean;
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
  /** `updatedBy` (WP-87): the source whose run that was, named on the page. */
  meta?: { updatedAt?: string | null; updatedBy?: string | null } | null;
  /** See Paginated.staleAsOf. */
  staleAsOf?: IsoDateTime;
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
/**
 * GET /v1/digest: the issue of one ISO week (Monday to Monday, UTC). The counts are the full ones; each list holds at
 * most `sectionLimit` items, newest or soonest first.
 */
export interface DigestTender {
  id: string;
  slug: string;
  kind: ChangeKind;
  day: string;
  title: string;
  buyerName: string;
  country: string | null;
  deadline: IsoDateTime | null;
  estimatedValue: Money | null;
  changes: FieldChange[];
  /** How many notices of the week this row stands for (identical title, buyer, date and kind are listed once). Absent on older issues. */
  repeats?: number;
}
export type DigestCallKind = 'call-new' | 'call-amended' | 'call-opened' | 'call-closing';
export interface DigestCall {
  id: string;
  slug: string;
  kind: DigestCallKind;
  title: string;
  funder: string;
  programmeName: string;
  funderCountry: string;
  status: string;
  openingDate: IsoDateTime | null;
  deadline: IsoDateTime | null;
  deadlineIsDate: boolean;
  cascade: boolean | null;
  /** One line from the facts read from the call's document; null when none were read. */
  eligibility: string | null;
  eligibilityState: 'read' | 'not_read' | 'no_source';
  changes: FieldChange[];
  /** WP-87: defence | dual-use; the API lists the defence calls of a section first. Absent from issues stored before. */
  regime?: Regime | null;
}
export interface DigestCounts {
  tendersNew: number;
  tendersAmended: number;
  callsNew: number;
  callsAmended: number;
  callsOpened: number;
  callsClosing: number;
  cascade: number;
}
export interface Digest {
  /** ISO week, YYYY-Www. */
  week: string;
  weekFrom: IsoDateTime;
  /** Exclusive: the next Monday. */
  weekTo: IsoDateTime;
  closingUntil: IsoDateTime;
  generatedAt: IsoDateTime;
  sectionLimit: number;
  counts: DigestCounts;
  tendersNew: DigestTender[];
  tendersAmended: DigestTender[];
  callsNew: DigestCall[];
  callsAmended: DigestCall[];
  callsOpened: DigestCall[];
  callsClosing: DigestCall[];
  cascadeCalls: DigestCall[];
  /** Open calls with cascade funding today (not the week's). */
  cascadeOpenNow: number;
  country: string | null;
  previousWeek: string | null;
  nextWeek: string | null;
  /** `updatedBy` (WP-87): the source whose run that was, named on the page. */
  meta?: { updatedAt?: string | null; updatedBy?: string | null } | null;
  staleAsOf?: IsoDateTime;
}
export interface DigestWeek {
  week: string;
  weekFrom: IsoDateTime;
  weekTo: IsoDateTime;
  counts: DigestCounts | null;
  computedAt: IsoDateTime | null;
}

/** `scope` absent: defence notices and supplies to defence buyers together. */
export interface ChangeFilters {
  country?: string[];
  scope?: TenderScopeFilter;
  goods?: 'defence';
  /** An ISO week of the digest (`2026-W42`) instead of the last 14 days, and one kind of change in it: where the digest's "the list has the rest" leads. */
  week?: string;
  kind?: ChangeKind;
  /** WP-87: the tender list's other filters, read by the API as the list reads them. */
  q?: string;
  cpv?: string[];
  deadlineFrom?: string;
  deadlineTo?: string;
  valueMin?: number;
  valueMax?: number;
  currency?: CurrencyCode;
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
  /** Other organisation rows of the same body shown under this buyer (0 when none). */
  nameVariants: number;
  /** The profile of the same body in the networks layer (/organisations/<slug>), when it took part in funded projects. */
  organisationSlug?: string | null;
}

/** GET /v1/stats/market: counts of core-scope notices published. Never spend, never market size. */
export interface MarketMonth { month: string; count: number; ted: number; partial: boolean }
export interface MarketStats {
  asOf: IsoDateTime;
  scope: 'core';
  unit: 'notices published';
  /** The window of every figure but `months`, as dates: the rolling 12 months, or the calendar year asked for. */
  windowFrom: string;
  windowTo: string;
  /** The calendar year and the buyer country the figures were asked for; absent or null: the rolling 12 months, all countries. */
  year?: number | null;
  /** WP-89: the CPV prefixes the figures were narrowed to; absent or null: every code. */
  cpv?: string[] | null;
  country?: string | null;
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

/** The market page's selectors: a calendar year (the rolling 12 months when absent) and one buyer country. */
export interface MarketFilters { year?: number; country?: string; /** WP-89: CPV prefixes, as on /tenders. */ cpv?: string[] }

/** GET /v1/buyers/{slug}/profile: the buyer's own core-scope notices, counted. */
export interface BuyerProfile {
  buyerId: string;
  asOf: IsoDateTime;
  tenderCount: number;
  openNow: number;
  perYear: { year: number; count: number }[];
  /** WP-87: notices published before the first year shown, and without a publication date: with them the years add up to `tenderCount`. */
  perYearEarlier?: number;
  perYearUndated?: number;
  cpvGroups: { group: string; count: number }[];
  responseWindow: { notices: number; median: number | null; p25: number | null; p75: number | null };
  /** `observedFrom` (WP-87): when the archive first saw the oldest of these notices; the share is shown once that is six months back. */
  amendments: { notices: number; amended: number; share: number | null; observedFrom?: IsoDateTime | null };
  sources: { id: string; name: string; count: number }[];
  basis: Record<string, string>;
}

export type BuyerSort = 'tenders' | 'name';
export interface BuyerFilters {
  q?: string;
  country?: string[];
  /** WP-89: CPV prefixes: the buyers with a notice under one of them (the tender list's reading). */
  cpv?: string[];
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
  /** Of a tender source: how many of the held notices state an estimated value. */
  valueStatedCount?: number | null;
  /** Of a tender source: false when our connector never reads an estimated value from its notices. Absent on older API builds. */
  valueRead?: boolean | null;
  /** Of a tender source: the usual notices per month (median) and the months, `YYYY-MM`, well below it. */
  monthlyMedian?: number | null;
  gapMonths?: string[] | null;
  /** How often the source is collected (daily, monthly, one-off, on demand), after how many hours a run is late for that, and whether it is. Absent on older API builds. */
  updateFreq?: string | null;
  staleAfterHours?: number | null;
  stale?: boolean | null;
  /** Why a run that is not `ok` is not (a fixed sentence) and its kind. */
  statusReason?: string | null;
  statusReasonKind?: string | null;
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

/** GET /v1/funding/{slug}/partners (WP-32): organisations of earlier projects in the call's area, ranked. */
export interface PartnerEvidence { projectId: string; acronym: string | null; title: string; year: number | null; role: string }
export interface Partner {
  organisationId: string;
  /** "<id>-<words>": the page is /organisations/<slug>. */
  slug: string;
  name: string;
  country: string;
  /** Projects of the area the organisation took part in (a project counted once). */
  projects: number;
  coordinated: number;
  firstYear: number | null;
  lastYear: number | null;
  /** The newest projects, at most three. */
  evidence: PartnerEvidence[];
}
export interface PartnersAnswer {
  call: { id: string; slug: string; topic: string | null };
  /** Null when the call's code names no area the project data can be compared with. */
  area: { kind: string; label: string; rule: string; projects: number; organisations: number; firstYear: number | null; lastYear: number | null; broaderThanCall: boolean } | null;
  partners: Partner[];
  /** Organisations of the whole area by country, before the country filter. */
  countries: { country: string; organisations: number }[];
  /** Organisations in the area (in the chosen country when a filter is set). */
  total: number;
  country: string | null;
  /** The country listed first (the visitor's own), or null. */
  prefer?: string | null;
  note: string | null;
  source?: { readAt: string | null; sources: string[]; licence: string };
}

/** The supplier map (GET /v1/suppliers, docs/design/API_CONTRACT.md): winners named in TED result notices of the defence scope, the last three years: the award set of the demand answer (WP-85). */
export interface SupplierItem {
  id: string;
  slug: string;
  name: string;
  country: string;
  awardCount: number;
  firstYear: number | null;
  lastYear: number | null;
  /** CPV divisions (two digits) of the notices the supplier won. */
  cpvDivisions: string[];
}
export interface SupplierNotice {
  id: string;
  slug: string;
  noticeId: string;
  title: string;
  buyerName: string | null;
  buyerCountry: string | null;
  publishedAt: IsoDateTime | null;
  cpv: string | null;
  /** How many winners the notice names; a value is stated only where this is 1. */
  winnersInNotice: number;
  valueAmount: number | null;
  valueCurrency: string | null;
  /** WP-87: the value is under 1,000: shown as published, probably a unit price, left out of every sum. */
  valueSuspect?: boolean;
  sourceUrl: string | null;
  /** Where the notice shown is from: ted, es_placsp, es_placsp_agg (WP-61; absent from older APIs, read as ted). */
  source?: string;
  /** The same award in the other source, counted once: its publication there, for provenance. */
  alsoPublished?: { source: string; noticeId: string; sourceUrl: string | null }[];
}
/** A source of the supplier map with the attribution its terms ask for (GET /v1/suppliers/summary `sources`). */
export interface SupplierSourceNote {
  code: string;
  name: string;
  attribution: string;
  /** The newest update stamp of what was read from it (PLACSP's terms ask for the date of last update). */
  lastUpdated?: IsoDateTime | null;
}
export interface Supplier extends SupplierItem {
  /**
   * WP-89: of its contracts, those under the CPV codes (and of the buyer countries) the page was asked for: the supplier report's link
   * carries the profile's codes, so the page says "44 of them under your codes" beside the total. Null without codes.
   */
  underCodes?: { cpv: string[]; buyerCountries: string[]; contracts: number } | null;
  /** WP-81: the sum of its notices' values per currency (the values of notices naming it alone), collapsed on the page. */
  values: ValueTotals;
  byYear: { year: number; awards: number }[];
  byCpv: { division: string; awards: number }[];
  buyers: { slug: string; name: string; country: string | null; awards: number }[];
  notices: SupplierNotice[];
  noticeCount: number;
  namesAsStated: string[];
  identifiers: string[];
  attribution: string;
}
export interface SupplierFilters { q?: string; country?: string; buyerCountry?: string; cpv?: string; sort?: 'awards' | 'name'; page?: number; pageSize?: number }
export interface SupplierSummary {
  /** A group of fewer suppliers than this is not published. */
  kMin: number;
  since: string;
  noticesRead: number;
  noticesWithSupplier: number;
  suppliers: number;
  awards: number;
  skippedNaturalPersons: number;
  firstPublished: IsoDateTime | null;
  lastPublished: IsoDateTime | null;
  byCpv: { key: string; suppliers: number; awards: number }[];
  byCountry: { key: string; suppliers: number; awards: number }[];
  cells: { division: string; country: string; suppliers: number; awards: number }[];
  suppressedGroups: number;
  coverage: string;
  /** TED, and PLACSP while its winners are served (WP-61). */
  sources?: SupplierSourceNote[];
}
