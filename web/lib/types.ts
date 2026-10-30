// Domain types. They follow docs/design/API_CONTRACT.md (/v1/funding, /v1/tenders, /v1/buyers, /v1/sources),
// which is authoritative.
import type { ValueSum, ValueTotals } from './value-totals';

/** Funder countries we collect. 'EU' = an EU programme. */
export type CountryCode = 'EU' | 'PL' | 'SE' | 'FR' | 'ES' | 'FI' | 'DE' | 'IT' | 'NL';
/** ISO 4217 as the source states it. Amounts are never converted. */
export type CurrencyCode = string;
/** WP-91: 'EDIP-USI' is a topic of EDIP's Ukraine Support Instrument, which the portal files under the EDF (the API reads it from the topic code). */
export type ProgrammeCode = 'EDF' | 'EDIP' | 'EDIP-USI' | 'HORIZON' | 'DIGITAL' | 'CEF' | 'NATIONAL';
/** WP-91: who may apply, as the API reads it from the rules and the stored call data; null where nothing we hold says. */
export type WhoMayApply = 'companies' | 'public' | 'designated';
/** The values of the filter `who` (WP-99: a call open only to designated bodies is in neither). */
export type WhoFilter = 'companies' | 'public' | 'research';
export type Regime = 'defence' | 'dual-use';
/** WP-132: `unlisted`: the source stopped listing a call it last called open or forthcoming (`lastSeenAt` is when it last listed it). */
export type CallStatus = 'open' | 'forthcoming' | 'closed' | 'unlisted';
/** Deadline presentation state, derived in lib/deadline.ts — never stored. 'none' = no stated deadline. */
export type DeadlineState = 'normal' | 'soon' | 'urgent' | 'closed' | 'none';
/** UI status pill values. 'upcoming' = a forthcoming call ("Opens soon"). */
export type StatusKind = 'open' | 'upcoming' | 'pending' | 'soon' | 'closed' | 'amended' | 'unknown' | 'unlisted';

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
  /** WP-145: the call document says Ukrainian entities cannot receive funding under this call (an EDIP call). Absent on older API builds. */
  ukraineNoFunding?: boolean;
  /** WP-91: `companies` (a company can take part), `public` (only public bodies may apply); null or absent where nothing we hold says. */
  whoMayApply?: WhoMayApply | null;
  /** WP-109: whether a university or a research organisation may apply; null or absent where nothing we hold says. */
  researchMayApply?: boolean | null;
  /** WP-92: true where the call's own eligibility facts say it is reserved for SMEs; null or absent otherwise. */
  smeOnly?: boolean | null;
  /** WP-92, detail only: what the call funds, at most three commercial sentences of the topic description's Objective / Expected outcome. Null: none passed the filter. */
  fundsSummary?: string | null;
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
  /** Detail only (WP-132): the scope rule no longer takes the call (WP-109): its page says so and is not indexed. */
  outOfScope?: boolean;
  /**
   * Detail only (WP-137): the call's own limits beside who may apply: where an applicant must be established (`established`, Art. 22.5
   * of the Horizon Europe Regulation) and the exclusion of entities controlled from elsewhere (`control`), each with the call's sentence.
   */
  whoMayApplyLimits?: WhoLimit[];
}

export type WhoLimit = { kind: 'established' | 'control' | string; quote: string; note: string };

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
  /**
   * WP-91: the engine's outcome of each establishment rule for one country of each group (EU, EEA_EFTA, UA, OTHER), with only the
   * country and the kind of action known (`asks`: the answers a rule still needs). Absent where no rules are encoded.
   */
  byCountry?: Record<'EU' | 'EEA_EFTA' | 'UA' | 'OTHER', RuleOutcome[]>;
  /** WP-91: the rules on who may apply, for a company or research body (`not_met`: a company cannot apply to this call). */
  forCompany?: RuleOutcome[];
}

/** One rule's outcome in the summary of a call (see `RulesApply.byCountry`). */
export interface RuleOutcome { rule: string; title: string; outcome: 'met' | 'not_met' | 'conditional' | 'unknown' | 'to_obtain' | 'info'; asks: string[]; reason: string }

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
  /** WP-93: `call_page`, the rules an agency's page states (an AID call), served without its words. */
  basis?: 'call_document' | 'work_programme' | 'call_page';
  sources?: EligibilitySourceInfo[];
  facts: Record<string, { value: unknown; note?: string | null; quote: string; confidence: number; scope?: 'call_document' | 'general' | 'topic' | 'programme' }>;
}

export interface CallDocument {
  label: string;
  url: string;
}

export type CallStatusFilter = 'open' | 'forthcoming' | 'open-forthcoming' | 'closing-soon' | 'closed' | 'all';
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
  /** WP-145: only calls whose document says Ukrainian entities cannot receive funding under them (`ukraineNoFunding`). */
  uaNoFunding?: boolean;
  /** WP-91: who may apply (`whoMayApply`): a call nothing we hold speaks for is in neither. */
  who?: WhoFilter;
  page?: number;
  pageSize?: number;
}

/** WP-110: a code the search words name (backend tenders.cpv_hints); `prefix` is what the list's CPV filter takes. */
export interface CpvHint { code: string; title: string; prefix: string }

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
  /** WP-98, `/v1/tenders`: the terms of other languages the words were also read as (lib/search-terms.ts), and their product groups. */
  alsoSearched?: string[];
  searchGroups?: { id: string; label: string; cpv: string[] }[];
  /** WP-110, `/v1/tenders`: "Did you mean CPV 31611000 Wiring sets?": codes the words name, with their official titles. */
  cpvHints?: CpvHint[];
  /** `/v1/suppliers`: always false since WP-81 (a group of fewer than three suppliers was withheld before). */
  withheld?: boolean;
  search?: SearchInfo | null;
  /** `/v1/funding`: calls with cascade funding among those that match every filter but this one. Absent on older API builds. */
  cascadeTotal?: number | null;
  /** `/v1/funding`: calls open to Ukrainian participants among those that match every filter but this one. Absent on older API builds. */
  ukraineTotal?: number | null;
  /** `/v1/funding` (WP-145b): calls whose document says Ukrainian entities cannot receive funding, among those that match every filter but this one. Absent on older API builds. */
  uaNoFundingTotal?: number | null;
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
  confidence?: {
    level: 'high' | 'medium' | 'low'; basis: string[];
    /** WP-95: the level in words, by what it rests on ("Clearly defence", "Defence buyer, ordinary purchase", ...). Absent on older APIs. */
    label?: string | null;
  } | null;
  /** More than one version observed. */
  amended: boolean;
  versionCount: number;
  securityClearance: boolean;
  subcontracting: boolean;
  /** The same notice in other sources. `source` is the source's name or id (the contract does not say which). `id` and `noticeId` are the other notice's. */
  sameNotice: { source: string; url: string | null; id?: string; noticeId?: string }[];
  /** WP-135, the notice's own page only: the slug of the copy the lists show, when this notice is the other copy of a Polish notice (bulletin and mirror). */
  copyOf?: string | null;
  /** retrievedAt = when the source last changed the notice as we saw it; checkedAt = when we last collected that source. */
  source: SourceAttribution;
  /** WP-90, the notice's own page only: the first sentence of its description when it reads as a commercial subject (no specification, no contact). */
  subject?: string | null;
  /** WP-90: the address of the procurement documents, where a source states it as such (Germany's Bekanntmachungsservice, BT-15). */
  documentsUrl?: string | null;
  /** WP-95: the other buyers of a joint procurement, as the notice names them after `buyerName`. */
  otherBuyers?: string[];
  /** WP-95, the notice's own page only: the legal-entity winners (a supplier page link where there is one); natural persons are counted, never named. */
  awardedTo?: AwardedTo[];
  awardedPersons?: number;
  /** WP-95: what the award states and what kind of amount it is. WP-106: on list items and export rows too, with `awardedTo`. WP-103: `setAside`, a figure the notice states that its own estimate contradicts (the kind is then `estimate`). */
  awardValue?: { amount: number; currency: string; kind: ValueKind; setAside?: number | null; /** WP-108: `lots` or `procedure`; absent for the estimate of WP-103 */ setAsideReason?: 'lots' | 'procedure' | null } | null;
  /** WP-103: whether the notice was read for its winners; false: an award whose winners DefenceGate has not read yet. Absent on older APIs. */
  winnersRead?: boolean;
  /** WP-106, the notice's own page: the other notices of its procedure (the call of an award, the award of a call), oldest first. */
  stages?: ProcedureStage[];
  /** WP-106: the official CPV titles of the codes (on the page all of them, in a list the main code's), from the full vocabulary. */
  cpvTitles?: Record<string, string>;
}

/** WP-106: another notice of the same procedure. `status` is its stored one: awarded, cancelled, forthcoming, else a call. */
export interface ProcedureStage { id: string; slug: string; noticeId: string; status: string | null; publishedAt: IsoDateTime | null }

/** WP-95: what an amount is: the contract awarded, a framework agreement's ceiling, or the buyer's estimate. */
export type ValueKind = 'contract' | 'framework' | 'estimate';
export interface AwardedTo {
  name: string;
  slug: string | null;
  country: string | null;
  valueAmount?: number | null;
  valueCurrency?: string | null;
  valueKind?: ValueKind | null;
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
export type TenderSort = 'core-first' | 'deadline-asc' | 'deadline-desc' | 'published-desc'
  /** WP-106: `open-first` the default of All (the open notices, then the newest deadline first); by value (per currency) and by main code. */
  | 'open-first' | 'value-desc' | 'cpv-asc';
export interface TenderFilters {
  q?: string;
  country?: string[];
  status?: TenderStatusFilter;
  scope?: TenderScopeFilter;
  /** `defence`: only notices that say defence themselves (not kept in only by a listed buyer). */
  goods?: 'defence';
  /** CPV code prefixes (2 to 8 digits), at most 20. */
  cpv?: string[];
  /** WP-90: `cpv` reads the notice's main code only (the first). Only with `cpv`. */
  cpvMain?: boolean;
  /** WP-90: leave out a notice with any code under these prefixes ("not 3511"). */
  notCpv?: string[];
  /** Organisation id. Set by code (the buyer page), never read from the URL. */
  buyer?: string;
  /** WP-144: one unit of `buyer` (a `BuyerUnit.key`). Set by the buyer page from its own units, only with `buyer`. */
  unit?: string;
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
  /** WP-96: open notices of the same filters that state no deadline (not in `items`; 0 with a date range). */
  withoutDeadline?: number;
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
  /** WP-108: why a correction is one: `remapped` (our corrected reading). */
  reason?: 'remapped' | null;
  /** WP-108: the publication date the source moved in the version that made the notice awarded: said apart, not the buyer's change. */
  redated?: FieldChange[];
  /** When we first saw this version. */
  detectedAt: IsoDateTime;
  changes: FieldChange[];
}

/**
 * GET /v1/changes: what changed in the last 14 days. One entry per notice per UTC day. `new`: first collected in
 * the window; `amended`: its deadline, value, status or procedure changed, as the archive observed it (a bulk
 * re-reading of our own is never one). `changes` is empty for `new`.
 */
export type ChangeKind = 'new' | 'award' | 'amended';
/** WP-90: what /changes can be narrowed to: a kind of entry, or the amendments that moved one thing. */
export type ChangeKindFilter = ChangeKind | 'deadline' | 'value' | 'status';
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
  /** WP-95: how many notices this row stands for (the lots of one notice, one notice from two sources). Absent: 1. */
  repeats?: number;
}
export interface ChangePage {
  items: Change[];
  total: number;
  page: number;
  pageSize: number;
  windowDays: number;
  windowFrom: IsoDateTime;
  windowTo: IsoDateTime;
  /** `awards` (WP-95): new award notices, counted apart from `new`; absent on older APIs. */
  counts: { new: number; amended: number; awards?: number };
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
  /** WP-108: the notice's status now (as `Tender.statusNative`), read when the issue is served: a new notice cancelled since says so. */
  statusNative?: string | null;
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
  /** WP-106: the CPV prefixes the tender sections were narrowed to; absent or empty for the whole issue. */
  cpv?: string[];
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
  kind?: ChangeKindFilter;
  /** WP-87: the tender list's other filters, read by the API as the list reads them. */
  q?: string;
  cpv?: string[];
  /** WP-90: the rest of them, so a subscription is exactly its search: main code only, excluded codes, the list's status (as of now). */
  cpvMain?: boolean;
  notCpv?: string[];
  status?: TenderStatusFilter;
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
  /** Notices of the list's default scope (All defence; WP-96, it was the core scope). */
  tenderCount: number;
  /** Of those, open now. */
  openCount: number;
  /** WP-96: of the open ones, the military goods and works (`scope=core`). Only on the buyer's own page. */
  openCoreCount?: number | null;
  lastPublishedAt: IsoDateTime | null;
  /** On the curated list of defence bodies. */
  isDefenceBuyer: boolean;
  /** Other organisation rows of the same body shown under this buyer (0 when none). */
  nameVariants: number;
  /** WP-111: on the buyer's own page, the names the family's other rows publish under (each once, most notices first). */
  variantNames?: string[];
  /** WP-98b: with a CPV filter, its tenders under the codes (each once, as the tender list shows them); else null. */
  cpvCount?: number | null;
  /** The profile of the same body in the networks layer (/organisations/<slug>), when it took part in funded projects. */
  organisationSlug?: string | null;
  /** WP-144: on the buyer's own page, its units (the names its notices state), most tenders first; none below two. */
  units?: BuyerUnit[];
  /** The scope the counts are of: `relevant` (the default), or WP-144 item 5 `all` for a buyer whose notices are all outside it. */
  scope?: 'relevant' | 'all';
}

/** WP-144: a unit of a buyer: the buyer's name as its notices state it (folded: case, accents, punctuation). */
export interface BuyerUnit {
  /** The value of `unit=` on the tender list. */
  key: string;
  /** Its commonest spelling. */
  name: string;
  /** Its tenders as the tender list shows them with `unit=` (any status, All defence, each once). */
  tenderCount: number;
  /** Of them, the military goods and works. */
  coreCount: number;
}

/** GET /v1/stats/market: counts of core-scope notices published. Never spend, never market size. */
export interface MarketMonth { month: string; count: number; ted: number; partial: boolean }
export interface MarketStats {
  asOf: IsoDateTime;
  /** WP-112: `relevant` (all defence) when asked with a country or codes. */
  scope: 'core' | 'relevant';
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
  /** WP-96: `observedFrom`, since when the archive watched these notices: the share is shown once that is six months back, as on a buyer page. */
  amendments: { notices: number; amended: number; share: number | null; observedFrom?: IsoDateTime | null };
  responseWindow: { notices: number; median: number | null; p25: number | null; p75: number | null };
  cpvGroups: { group: string; count: number }[];
  basis: Record<string, string>;
  /** WP-105: the contract values awarded in the window (the supplier map's contracts), null while none is stored; absent from an older API. */
  money?: MarketMoney | null;
  basisMoney?: string;
}

/** WP-105: one slice of the market's contract values: the sums per currency, out of how many contracts (a contract and its winner). */
export interface MoneyTotals { byCurrency: ValueSum[]; of: number; withoutValue: number }
export interface MarketMoney {
  asOf: IsoDateTime; since: string; until: string; total: MoneyTotals;
  byCountry: (MoneyTotals & { country: string })[];
  byCpvGroup: (MoneyTotals & { group: string })[];
  byBuyer: (MoneyTotals & { slug: string; name: string; country: string | null })[];
}

/** The market page's selectors: a calendar year (the rolling 12 months when absent) and one buyer country. */
export interface MarketFilters {
  year?: number; country?: string; /** WP-89: CPV prefixes, as on /tenders. */ cpv?: string[];
  /** WP-112: `relevant` counts all defence (the tender list's default), with a country or codes only; military goods and works otherwise. */
  scope?: 'relevant';
}

/** GET /v1/buyers/{slug}/profile: the buyer's own core-scope notices, counted. */
/** WP-90, GET /v1/buyers/{slug}/suppliers: who won this buyer's contracts (the supplier map's award set), most first, at most 10. */
export interface BuyerSuppliers {
  /** WP-105: `contractValues`, the contract values of its contracts with this buyer per currency, as its supplier page sums them. */
  items: { slug: string; name: string; country: string | null; awards: number; contractValues?: ValueSum[] }[];
  /** Every supplier and contract of the buyer in the award set, not only the ten listed. */
  suppliers: number;
  contracts: number;
  attribution: string;
  /** WP-105: the CPV prefixes asked (none: every code); the sum over every supplier; contracts and winners in all, and how many state a value. */
  cpv?: string[];
  contractValues?: ValueSum[];
  awardsWithSupplier?: number;
  valued?: number;
}

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

/** WP-98b: `cpv`, most tenders under the CPV filter's codes first (only with a CPV filter). */
export type BuyerSort = 'tenders' | 'name' | 'cpv';
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
  /** WP-114: the data checks in alert, each in the API's fixed sentence; `since` null when not known. Absent on older API builds. */
  alerts?: { control: string; since: IsoDateTime | null; checkedAt: IsoDateTime; message: string }[];
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
  /** WP-155: the name printed on the account's company reports (Consultant), plain text, at most 80 characters. */
  reportName?: string | null;
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
  /** False for an account made by the old sign-in link that has not set a password yet. */
  hasPassword: boolean;
  /** Two-step sign-in (TOTP) is on. */
  totp: boolean;
  /** WP-123: the plan picked on the pricing page before registering, remembered; the plan in force is Free until payment opens. */
  planChoice: import('./plans').PlanChoice | null;
  /** WP-124: the plan in force, from verified payment events only. */
  plan: import('./plans').PlanId;
  /** WP-124: the paid features this account may use (every one while no plan is on sale). */
  features: PaidFeature[];
  /** WP-153: keys of the data API can be issued (DGATE_API_KEYS_OPEN on the API): the account area shows API keys. WP-155: and the
   *  account holds a data licence (granted by the operator; no plan grants it). */
  apiKeys: boolean;
  /** WP-158: a member of a licensed association (the cluster licence): the account area shows its page. */
  association: boolean;
  /** WP-155: saved searches the plan allows, company reports a month (null: no limit). */
  limits: { savedSearches: number; reportsPerMonth: number | null };
  /** WP-157: the team workspace the account is in (null: none); `active` while the plan in force has the workspace (sharing works). */
  workspace?: { role: 'owner' | 'member'; active: boolean } | null;
}

/** WP-158: GET /v1/account/association, the account's own membership. `seats` (counted, never named) for the admin only. */
export interface AssociationView {
  name: string;
  role: 'admin' | 'member';
  plan: 'pro' | 'team';
  memberSince: IsoDateTime;
  /** The licence ends by itself at this moment (the start of the day after its last day, UTC). */
  licensedUntil: IsoDateTime | null;
  digest: { on: boolean; country: string | null; cpv: string[]; lastWeek: string | null };
  seats: { used: number; cap: number } | null;
}

/** WP-153: a key of the data API as the account API lists it (never the key itself, except `key` in the answer that made it). */
export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: ('tenders' | 'archive')[];
  ratePerMinute: number;
  dailyQuota: number;
  createdAt: IsoDateTime;
  expiresAt: IsoDateTime;
  lastUsedAt: IsoDateTime | null;
  revokedAt: IsoDateTime | null;
  requestsToday: number;
}

export interface ApiKeys {
  open: boolean;
  /** WP-155: the account holds the data licence (granted by the operator, no plan grants it). */
  licensed: boolean;
  sources: string[];
  maxKeys: number;
  keys: ApiKey[];
  events: { event: 'created' | 'revoked'; at: IsoDateTime; name: string; prefix: string }[];
}

/** WP-124: the paid features that exist (backend billing.FEATURES; WP-155: the owner's plan split). */
export const PAID_FEATURES = ['saved_searches', 'email_alerts', 'company_report', 'competitors_full', 'signals_full', 'signals_csv', 'consortium_gaps', 'branded_reports',
  'eligibility_export', 'supplier_map_csv',   // WP-156: the two exports
  'team_workspace', 'client_profiles'] as const;   // WP-157: the team workspace and client profiles
export type PaidFeature = (typeof PAID_FEATURES)[number];

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
  /** Null while the search is paused (WP-124). */
  matchCount: number | null;
  /** Matches published since the account's lastVisitAt. */
  newCount: number;
  lastMatchAt: IsoDateTime | null;
  /** WP-124: kept after a downgrade but not run, and no alerts, until the account has a plan with saved searches again. */
  paused?: boolean;
  /** WP-157: the client profile it belongs to (Consultant), and whether this account made it (a teammate's search is shown, not changed). */
  clientId?: string | null;
  mine?: boolean;
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
  /** WP-157: the client profile it belongs to (Consultant). */
  clientId?: string | null;
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
  /** WP-91: of those, the projects whose title shares a topic word of the call (they rank first). Absent on older API builds. */
  topical?: number;
  firstYear: number | null;
  lastYear: number | null;
  /** The newest projects, at most three. */
  evidence: PartnerEvidence[];
}
export interface PartnersAnswer {
  call: { id: string; slug: string; topic: string | null };
  /** Null when the call's code names no area the project data can be compared with. */
  area: {
    kind: string; label: string; rule: string; projects: number; organisations: number; firstYear: number | null; lastYear: number | null; broaderThanCall: boolean;
    /** WP-91: the call title's topic words, the synonyms searched with them, and how many projects of the area share one (they rank first). */
    topicWords?: string[]; topicAlso?: string[]; topicalProjects?: number;
  } | null;
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
  /** WP-110, the site search only: found by this name it was published under, not by its own ("Konsorcjum: MEGMAR ... Leonardo Poland"). */
  matchedAs?: string;
  country: string;
  awardCount: number;
  firstYear: number | null;
  lastYear: number | null;
  /** CPV divisions (two digits) of the notices the supplier won. */
  cpvDivisions: string[];
  /** WP-98b: on the list, the contract values of the wins the filters select, per currency, never converted (WP-95: contract values only). */
  contractValues?: ValueSum[];
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
  /** WP-95: what the value is (contract, framework ceiling, estimate); absent on older APIs. */
  valueKind?: ValueKind | null;
  /** WP-95: the framework agreement this call-off states it is based on. */
  framework?: { source: string; noticeId: string; sourceUrl: string | null; slug?: string | null } | null;
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
  /** WP-96: the curated company group it is listed under (a parent and its subsidiaries, never merged), with its source. */
  group?: { key: string; name: string; source: string; members: number } | null;
  /** WP-111: other winners of the same country under the same name, kept apart because each holds its own company number. */
  namesakes?: { slug: string; name: string; country: string | null; identifiers: string[]; awards: number }[];
  /** WP-111: this company's own numbers, the ones that keep it apart from its namesakes. */
  ownNumbers?: string[];
}
/** WP-100, GET /v1/suppliers/{slug}/contracts: every contract of a supplier (one row per procurement), for its CSV. */
export interface SupplierContract {
  noticeId: string;
  slug: string;
  title: string;
  buyerName: string | null;
  buyerCountry: string | null;
  publishedAt: IsoDateTime | null;
  cpv: string | null;
  winnersInNotice: number;
  valueAmount: number | null;
  valueCurrency: string | null;
  valueKind: ValueKind | null;
  /** In the profile's sum of contract values (a contract value that is not a unit price). */
  inContractSum: boolean;
  frameworkNoticeId: string | null;
  source: string;
  sourceName: string;
  sourceUrl: string | null;
  licence: string;
  attribution: string;
}
export interface SupplierContracts {
  slug: string; name: string; total: number; cap: number; items: SupplierContract[];
  /** WP-112: its registration numbers as its page shows them (absent from an older API). */
  identifiers?: string[];
}
/** WP-152, GET /v1/suppliers/{slug}/competition (backend/dgate/competition.py). A market is one buyer and one CPV class. */
export interface Competitor {
  slug: string; name: string; country: string | null;
  /** Its contracts in the markets it shares with the company. */
  overlap: number;
  markets: number;
  buyers: number;
  /** The company's own contracts in those markets. */
  ours: number;
  /** The same name in the same country: possibly the company itself under another record. */
  sameName: boolean;
  /** The curated group both are listed under. */
  sameGroup: string | null;
}
export interface CompetitionTally { key: string; contracts: number }
export interface CompetitionShare {
  /** A CPV class (4 digits) or a buyer country. */
  key: string;
  contracts: number;
  /** Every contract of the award set there. */
  total: number;
  /** The commonest currency of the contract values there; null when none states one. */
  currency: string | null;
  value?: number | null; valued?: number | null; valueTotal?: number | null; valuedTotal?: number | null;
}
export interface SupplierCompetition {
  /** False while the stored contract rows are being renewed: nothing else is filled. */
  available: boolean;
  asOf?: IsoDateTime | null;
  since?: string | null;
  contracts: number;
  markets: number;
  competitorCount: number;
  competitors: Competitor[];
  byCountry: CompetitionTally[];
  byClass: CompetitionTally[];
  size: { currency: string; median: number; valued: number; otherCurrencies: number } | null;
  withoutValue: number;
  shareByClass: CompetitionShare[];
  shareByCountry: CompetitionShare[];
  /** The paid company report exists (DGATE_COMPANY_REPORT_OPEN). */
  reportOpen: boolean;
  /** WP-155: the slug of the one report open to everyone (while reports are open), and whether this company's is it. */
  sampleReport?: string | null;
  isSample?: boolean;
  /** WP-155: every competitor of the list (the account answer); false: the public answer's first five. */
  full?: boolean;
}

/** WP-98b: `sort` value-XXX orders by the contract values in currency XXX; `source` ted lists TED's winners only. */
export interface SupplierFilters { q?: string; country?: string; buyerCountry?: string; cpv?: string; group?: string; sort?: SupplierSort; source?: 'ted'; page?: number; pageSize?: number }
export type SupplierSort = 'awards' | 'name' | `value-${string}`;
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
