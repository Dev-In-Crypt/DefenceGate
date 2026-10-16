# Frontend <-> API contract (funding hub)

Decided with the owner on 12 October 2026. The design's `web/lib/types.ts` was
modelled on a guess of `/v1/*`; this is what the backend really serves. The frontend
adapts `types.ts`, `api.ts`, `filters.ts` and the pages to this document; the backend
implements it in `backend/dgate/funding.py`. The existing `/v1/calls`, `/v1/opportunities`
and `/v1/health` are not changed.

## Owner decisions that shape it

1. **Money is never converted.** A budget is shown in the currency the source states.
   The budget filter takes a currency (default EUR) and matches amounts in that currency
   only; calls in another currency are not compared with it.
2. **A call that has not opened yet is a status of its own**, `forthcoming`, shown as
   "Opens soon". The design had only open and closed.
3. **Titles.** The English title is the heading where the source publishes one (EU
   programmes, Vinnova). Otherwise the heading is the source-language title with a
   language label. Whichever language is not the heading goes beneath it, smaller, with
   a `lang` attribute. Nothing is translated by us.
4. **The source is shown with every fact**: name, link, retrieval time, licence,
   attribution.

## Endpoints (all GET, JSON, anonymous)

### `/v1/funding`

Query parameters (all optional; names are the design's URL keys):

| param | values | meaning |
|---|---|---|
| `q` | text | word search (16 Oct 2026): accents and hyphens folded (`counter-drone` = `counter drone`), every word must match a whole word (up to 3 letters), the start of a word (4 letters) or part of a word (5 or more); the identifiers match by the start of their words; `drone`, `uas`, `uav`, `unmanned`, `rpas` are synonyms, as are `logistics`/`supply`/`mobility` and `ai`/`artificial intelligence` (`backend/dgate/textsearch.py`). Over title, original title, issuer, call ID, topic ID |
| `programme` | `EDF,EDIP,HORIZON,DIGITAL,CEF,NATIONAL` | OR within; any other value is a 422 (was: ignored) |
| `regime` | `defence,dual-use` | OR within; any other value is a 422 (was: ignored) |
| `country` | `EU,PL,SE,FR,ES,FI,DE,IT,NL` | funder country; `EU` = EU programme |
| `status` | `open` (default) `forthcoming` `closing-soon` `closed` `all` | `closing-soon` = open with deadline within 30 days |
| `from`, `to` | `YYYY-MM-DD` | deadline range, inclusive, UTC |
| `min`, `max` | number | budget range, in `currency` |
| `currency` | ISO 4217, default `EUR` | the currency `min`, `max` and `sort=budget-desc` refer to |
| `sort` | `deadline-asc` (default, but `deadline-desc` when `status=closed`) `deadline-desc` `budget-desc` | closed calls always last; calls without a deadline after those with one |
| `page`, `pageSize` | 1.., pageSize <= 500 | |

Response: `{ "items": [Call], "total": int, "page": int, "pageSize": int, "meta": {...}, "search": { "terms": [str], "alsoSearched": [str] } | null }`.
`search` is null without `q`; `alsoSearched` lists the synonyms searched beyond the typed words.

`sort=budget-desc` lists calls whose budget is in `currency` first, largest first, then
the rest by deadline. It never orders across currencies.

### `/v1/funding/{slug}`

One `Call`, plus `conditionsText`. `404` for an unknown slug. The slug is
`<id>-<words>`; only the leading integer is looked up, so a changed title does not break
a link. The frontend should redirect to the canonical slug when the words differ.

### `/v1/funding/slugs`

`[{ "slug": str, "updatedAt": IsoDateTime }]` for every call, for the sitemap.

### `/v1/sources`

The design's `Health`: `{ "generatedAt": IsoDateTime, "sources": [SourceHealth] }`.

## Types

```ts
type CountryCode = 'EU'|'PL'|'SE'|'FR'|'ES'|'FI'|'DE'|'IT'|'NL';   // funder countries we collect
type CurrencyCode = string;                                      // ISO 4217 as the source states it
type ProgrammeCode = 'EDF'|'EDIP'|'HORIZON'|'DIGITAL'|'NATIONAL';
type Regime = 'defence'|'dual-use';
type CallStatus = 'open'|'forthcoming'|'closed';

interface Call {
  id: string;                  // numeric id as a string
  slug: string;                // "<id>-<words>"
  programme: ProgrammeCode;    // every national source is NATIONAL
  programmeName: string;       // "Horizon Europe", "Vinnova calls in the civil-military ..."
  callId: string | null;       // EU call identifier; null for national sources
  topicId: string;             // EU topic code, or the source's own identifier
  title: string;               // the heading (English where the source publishes one)
  titleLanguage: string;       // ISO 639-1 of `title`: "en", "pl", "es", ...
  originalTitle: string | null;       // the other language, when the source gives both
  originalLanguage: string | null;    // ISO 639-1 of `originalTitle`
  regime: Regime;
  funderCountry: CountryCode;  // 'EU' for an EU programme
  issuer: string | null;       // the body that issues a national call
  status: CallStatus;
  openingDate: IsoDateTime | null;
  deadline: IsoDateTime | null;       // null: no stated deadline (a standing call)
  budget: { amount: number; currency: CurrencyCode } | null;
  budgetScope: 'call' | 'topic' | null;   // 'call': the pot several topics share
  actionType: string | null;
  fundingRate: string | null;  // not collected yet; always null
  scope: string[];             // keywords the source publishes; may be empty
  eligibility: { label: string; value: string }[];   // structured rows only
  publishedAt: IsoDateTime | null;    // the source's own date for the call, where it states one
  firstSeenAt: IsoDateTime;
  lastSeenAt: IsoDateTime;     // when we last saw the source list it
  source: SourceAttribution;
}

interface SourceAttribution {
  sourceId: string;            // source.code
  sourceName: string;
  url: string | null;          // the original record
  retrievedAt: IsoDateTime;    // = lastSeenAt
  licence: string;
  attribution: string;
}

interface SourceHealth {
  id: string; name: string; country: CountryCode | null; type: 'grants'|'tenders';
  url: string | null; lastRunAt: IsoDateTime | null;
  status: 'ok'|'partial'|'failed'|'never';
  records: number;             // fetched in the last run
  coverage: number | null;     // fetched / expected minimum of that run, capped at 1; null when no floor
  licence: string; attribution: string;
}
```

`conditionsText` (detail only): the source's own conditions text, in the source's
language, unedited. Show it as published, under a label that says so, or not at all;
it is not prose of ours.

## Rules the frontend must keep

- A null `deadline` is "No fixed deadline", never a date and never "Closed".
- `forthcoming` has its own pill ("Opens soon") and its own filter; it is not "open".
- Never convert or sum amounts across currencies. Show `CUR amount` as given.
- `titleLanguage != 'en'` means the heading is not English: label it.
- Countries are shown as code + name.

---

# Tenders and buyers (added 12 October 2026)

The funding contract's sibling for procurement notices (`opportunity`) and the bodies
that publish them (`organisation`). Same rules: anonymous GET, JSON, camelCase, amounts
never converted, no personal data, every record carries its `source`.

## Endpoints

### `/v1/tenders`
Query (all optional): `q` (title, buyer or notice number), `country` (comma ISO-2),
`cpv` (comma prefixes, at most 20), `status` (`open` default | `closed` | `all`),
`scope` (`relevant` default since 16 October 2026: `core` and `supply` together | `core`: the notice itself is defence | `supply`: only the buyer is a
defence body, or one of the two groups of 14 October 2026 | `all`; see "Changes of 16 October 2026"), `goods` (`defence`: of the chosen scope, only notices that say defence themselves, i.e. `legal_basis` or `military_cpv` in `qualifiedBy`, not kept by a listed buyer alone; absent by default; the same parameter on `/v1/changes`), `buyer` (organisation id), `from` / `to` (deadline, `YYYY-MM-DD`
UTC), `min` / `max` (estimated value) with `currency` (ISO 4217, default `EUR`: a range
selects that one currency), `sort` (`deadline-asc` default | `published-desc`), `page`
(1..1000), `pageSize` (1..250, default 20).
Returns `{ items: Tender[], total, page, pageSize, meta }`. A national notice whose TED twin is
in the same result is shown once (the TED one); `sameNotice` lists the other copies.

### `/v1/tenders/{slug}`
`<id>-<words>`, resolved by the leading integer. Returns `Tender`; 404 otherwise.

### `/v1/tenders/{slug}/versions`
The archive: `TenderVersion[]`, newest first. 404 for an unknown notice.

### `/v1/tenders/export`

One page of a CSV export (15 October 2026). The same filters as `/v1/tenders` (`q`, `country`, `cpv`,
`status`, `scope`, `goods`, `buyer`, `from`, `to`, `min`, `max`, `currency`), the same collapse rules, no
`sort`, `page` or `pageSize`. Rows come newest id first, `limit` at a time (default 500, at most 2,000);
`cursor` is the previous response's `nextCursor` (digits only). There is no total: the page costs a keyed
scan that stops after `limit + 1` rows, so it is the same at any depth. `nextCursor` is null on the last
page (a page that ends the result exactly has none). Rows may repeat or be missed if the data changes
between calls; a caller de-duplicates by `id`. Not cached.

### `/v1/tenders/slugs`
`[{ slug, updatedAt }]` for the sitemap: open notices and those published in the last
12 months, core scope only, at most 5,000.

### `/v1/buyers`
Query: `q` (name), `country` (comma ISO-2), `hasOpen` (`true`: only buyers with an open
tender), `sort` (`tenders` default | `name`), `page`, `pageSize` (1..100, default 20).
Returns `{ items: Buyer[], total, page, pageSize }`. Only buyers with at least one
core-scope notice are listed.

### `/v1/buyers/{slug}`
`<id>-<words>`. Returns `Buyer`; 404 otherwise. Its tenders are `/v1/tenders?buyer=<id>`.

### `/v1/buyers/slugs`
`[{ slug, updatedAt }]`: buyers with an open tender, at most 2,000.

## Types

```ts
interface Tender {
  id: string;                        // numeric id as a string
  slug: string;                      // "<id>-<words>"
  noticeId: string;                  // the source's own number, e.g. "123456-2026"
  title: string;                     // English where the source gives one, else the source language
  titleLanguage: string | null;      // ISO 639-1 of `title`
  originalTitle: string | null;      // the other language, when both exist
  originalLanguage: string | null;
  buyerId: string | null;
  buyerSlug: string | null;
  buyerName: string;
  country: CountryCode | null;       // ISO-2 of the buyer
  cpv: string | null;                // the main CPV code
  cpvCodes: string[];
  procedure: string | null;          // as the source states it
  legalBasis: string | null;         // e.g. "32009L0081" (Directive 2009/81/EC)
  scope: 'core' | 'supply';          // core: the notice itself is defence; supply: only the buyer is
  deadline: IsoDateTime | null;      // null: none stated
  publishedAt: IsoDateTime | null;
  publishedKnown: boolean;           // false: the source states no publication date
  noticeDate: IsoDateTime | null;    // the date of the notice the record was last read from, where stated
  noticeKind: 'call' | 'prior' | 'award' | 'formalisation' | 'cancellation' | 'update' | null;
  firstSeenAt: IsoDateTime | null;   // when we first collected it ("new since" compares this, never publishedAt)
  estimatedValue: { amount: number; currency: string } | null;
  status: 'open' | 'closed';         // as of now (a passed deadline is closed)
  statusNative: string | null;       // the source's own word: open, awarded, cancelled, unknown
  amended: boolean;                  // more than one version observed
  versionCount: number;
  securityClearance: boolean;
  subcontracting: boolean;
  sameNotice: { source: string; url: string | null }[];
  source: SourceAttribution;         // retrievedAt = when we last observed the notice
}

interface TenderVersion {
  version: number;
  detectedAt: IsoDateTime;           // when we first saw this version
  changes: { field: string; label: string; before: string | null; after: string | null }[];
}

interface Buyer {
  id: string;
  slug: string;                      // "<id>-<words>"
  name: string;
  country: CountryCode | null;
  tenderCount: number;               // core-scope notices
  openCount: number;                 // of those, open now
  lastPublishedAt: IsoDateTime | null;
  isDefenceBuyer: boolean;           // on the curated list of defence bodies
}
```

## Rules the frontend must keep (in addition to the funding ones)

- `scope: 'supply'` is "Supplies to a defence buyer", not "defence notice"; say so.
- `status: 'closed'` with `statusNative: 'awarded'` reads "Awarded", not just "Closed".
- Show `buyerName` as a link to `/buyers/<buyerSlug>` when `buyerSlug` is set.
- A tender's date-only deadline from TED is `00:00 UTC`: show the date, not a time.

## Clarifications after the first frontend build (12 October 2026)

- `Tender.country` and `Buyer.country` are plain ISO-2 strings, not the nine funder
  codes: buyers are in about 40 countries (DE, PL, FR, CZ, ES, RO, IT, GB, ...).
- `sameNotice[].source` is the source id (`ted`, `nl_tenderned`, ...); map it to a name
  with `/v1/sources`.
- `statusNative` is the effective status as of now: `open`, `expired` (open when
  published, deadline since passed), `awarded`, `cancelled` or `unknown`. `status` is
  `open` only for `open`.
- `status=all` with `sort=deadline-asc` lists open first, then closed; within each,
  earliest deadline first and no deadline last.
- A deadline stored with a time is compared with the clock (closed from that instant). A
  date-only deadline from a source that gives no time is `00:00 UTC` and reads closed
  from that instant, a day early in the source's own terms; the page shows the date and
  says nothing finer.
- `TenderVersion.changes[].before/after` are display strings: `deadline_at` as
  `YYYY-MM-DD HH:MM UTC`, `cpv_codes` joined with commas, text cut at 300 characters.
- `Buyer` has no `source`: its counts are over notices from several sources.


## Changes of 12 October 2026 (data quality work)

All additive; nothing was removed from a response.

**Tenders** (`GET /v1/tenders`, `/v1/tenders/{slug}`)
- `status` is `open` only for a notice that can still be acted on. `statusNative` carries the
  lifecycle word: `open`, `expired` (shown as Closed), `awarded`, `cancelled`, `forthcoming`
  (shown as Planned), `unknown` (never shown as open). For TED it comes from the notice type
  (`cn-*` open, `can-*` and `veat` awarded or cancelled, `pin-*` forthcoming).
- `scope` stays `core` or `supply`. `core` is the 2009/81/EC legal basis or a military CPV;
  a listed defence buyer on its own is `supply`. New: `buyerClass` (`defence`, `security`,
  `municipal`, `health`, `education`, `fire_rescue`, `other`) and `dualUse` (a military CPV
  from a body that buys for itself, demoted from `core`; reachable with `scope=all`).
- `publishedAt` is the publication date (TED `publication-date`, not the dispatch date).
- `noticeDate` and `noticeKind` (15 October 2026, PLACSP; null for sources that state none)
  are the date and the kind of the notice the record was last read from. They are never a
  publication date: a Spanish folder whose stored entry is an award has `publishedAt` null,
  `publishedKnown` false, and `noticeKind: "award"` with its date, which the site words as
  "Award notice dated 12 Sep 2026". Where an earlier entry of the same folder was the call,
  `publishedAt` is the call's date (kept, not replaced by the award's). `sort=published-desc`
  orders by `publishedAt`, else `noticeDate`.
- `estimatedValue` is accompanied by `valueKind` (`total`, `estimated`, `lot_sum`,
  `first_lot`); `lots` is the lot count where the notice lists lots.
- `buyerName` is the notice's own spelling; `buyerCanonicalName` is the organisation's.
- `procedure` is a word (`Open procedure`, `Restricted procedure`, ...) or null: bare codes
  (`16`, `BZP 1.1.1`) are not shown.
- `anomalies`: `deadline-before-publication`, `deadline-more-than-3y`.
- `sort=deadline-desc` is accepted. `status=closed` lists the newest deadlines first.
- A BOAMP rectificatif is not listed beside the notice it corrects when that notice is held,
  and of several TED re-publications of one procedure with the same status only the newest
  matching the filters is listed.
- `/v1/tenders/{slug}/versions`: each version has `sequence` (1, 2, ... of the visible
  versions) next to `version` (the archive number, with gaps where re-reads were annotated).
  Values are display strings (`10 Sep 2026`, `Awarded`, `1,200,000 EUR`); deadlines are UTC.
  Versions written by bulk corrections (note kind `remapped`) are not amendments.

**Funding** (`GET /v1/funding`, `/v1/funding/{slug}`)
- `deadlineIsDate`: the source gave a date without a time; the stored deadline is the end of
  that calendar day in the source's time zone. `rolling`: open although the last cut-off has
  passed (continuous or multiple cut-off programmes). `anomalies` as for tenders.
- `publishedAt` is filled for EU portal, AID and NCBR calls. A CEF military-mobility topic is
  in scope as dual-use.

**Accounts** are internal (`docs/design/ACCOUNT_CONTRACT.md`).

## Changes of 13 October 2026 (verification round, read side)

All additive. A response gained fields; none was removed or renamed.

**Lists** (`GET /v1/tenders`, `GET /v1/funding`)
- `meta.updatedAt` (`IsoDateTime | null`, UTC): when the newest successful or partial
  collection run of the list's sources finished (tenders: the procurement sources, funding: the
  grant sources; failed runs do not count). It is the freshness of the data, not the time of
  the response, and is read from `ingest_run` at most every five minutes. `null` before any
  run. Use it for "Last update"; `generatedAt` of `/v1/sources` is the render time.

**Tenders** (`GET /v1/tenders`, `/v1/tenders/{slug}`)
- `deadlineKnown` (`boolean`): `false` when the notice states no deadline. Its `status` is
  then a judgement, not a stated fact: label it "Deadline not stated" rather than showing
  nothing. A notice with no deadline stays open for 365 days after publication, unless
  its procedure is over (next point).
- A notice with no deadline of its own is **not** served as open when its procedure is over:
  the TED notice it was forwarded as is awarded, cancelled, closed or past its deadline; or
  another notice of the same procedure is an award or a cancellation published on or after it;
  or a rectificatif names it. It then has `status: closed` and `statusNative: expired`, and
  leaves `status=open` lists and counts (buyer `openCount`, profile `openNow`). A notice that
  states its own deadline is never judged by its twin. On 13 October 2026 this removed 79 of
  416 notices (all French) from the default list.
- `valueFrom` (`'ted_twin' | null`): `'ted_twin'` when the notice itself states no value and
  `estimatedValue` is the value of the TED notice it is the same procurement as; `valueKind`
  then describes that figure. Never written to the stored notice. Not used when the twin's
  value is the first lot of several (`valueKind: first_lot`), is a placeholder (1 or less), or
  has no currency; and, where the link was made by procedure identifier or by the heuristic,
  only when the twin has the notice's own status (a call's value is not shown on its award).
  A value the notice states itself always wins.
- A value of 1 or less (0, 0.01, 1: TED's way of saying "not known") is never shown as
  `estimatedValue`, and a `min`/`max` range does not match it: `max=100000` no longer returns
  notices that show "not stated". The range matches the notice's own stored value only, not
  `valueFrom: 'ted_twin'`.
- `sameNotice[]` entries also carry `id` (the other notice's id, as a string) and `noticeId`,
  so a page can leave a notice's twin out of "more from this buyer".

**Status of other endpoints.** `/v1/opportunities` applies the same status rule
(`status` there is the effective status; `status=expired` includes a superseded notice).

## Changes of 14 October 2026 (site QA round 2, WP-7)

- `Tender.source.retrievedAt` is when the SOURCE last changed the notice, as we saw it: the
  newest version that is an amendment (not a `reread`, `out_of_order` or `remapped` version,
  and not one that only moved the publication date). It was the newest observation of any
  kind, which is our own reprocessing. New: `source.checkedAt`, when the source's newest
  successful or partial collection run finished (null for a call).
- New `Tender.qualifiedBy` (`legal_basis`, `military_cpv`, `buyer`) and `Tender.militaryCpv`
  (the notice's codes that are military). `buyer` means the notice would be demoted as dual-use
  without its buyer being on the defence list; a page must not call that a military product code.
- `Buyer.openCount` applies the list's own status rule and collapse (a national notice and its
  TED twin, a rectificatif and its parent, a re-publication count once): it equals the `total`
  of `/v1/tenders?buyer=<id>&status=open`. `tenderCount` still counts every core notice.
- `Buyer`/`Tender` names: a trailing `_<digits>` after a letter (the Irish eTenders buyer id
  TED carries) is dropped when served; the stored name is unchanged.
- `/v1/funding`: a call stored `forthcoming` whose deadline has passed is `closed` (it never
  opened), so `status=forthcoming` and the web agree. A rolling call is unchanged.
- `SourceHealth.monthlyMedian` and `gapMonths` (`YYYY-MM`): of a tender source, the usual
  notices per month (median of the whole months between its first and last) and the months
  with fewer than half of that. Absent where the read did not finish in the API's budget.

## Changes of 14 October 2026 (WP-8, owner decision on the scope of `core`)

- Two groups of notice leave `core` and are served as scope `supply` (never deleted; found by `q`,
  `scope=supply` and `scope=all`). `Tender.qualifiedBy` names them with one of two new values
  in place of the signal it was found through:
  - `directive_civil_buyer`: the 2009/81/EC legal basis is the only defence signal and `buyerClass`
    is known and is neither `defence` nor `security`. Label: "Filed under the defence procurement
    directive by a civil buyer".
  - `security_buyer_cpv`: a military CPV is the only signal (not demoted as dual-use) and
    `buyerClass` is `security`. `militaryCpv` still lists the codes. Label: "Security-body purchase
    of a military-type product code".
  A listed buyer, a link to a defence notice of another source, or the legal basis together with a
  military CPV keeps a notice in `core`; a notice whose buyer class is not yet known is never moved.
  `scope` stays `core` or `supply`; `supply` therefore also holds these two groups.
- Forsvarsbygg (Norwegian Defence Estates Agency) is a defence buyer: its notices are `supply`
  through the buyer signal, `core` only with the legal basis or a military CPV as for any buyer.

## Changes of 15 October 2026 (WP-10: what changed)

### `/v1/changes`
The real changes of the last 14 days, newest first. Query (all optional): `country` (comma ISO-2,
at most 20), `scope` (`core` | `supply` | `all`; absent: `core` and `supply` together, which is the
only default that differs from `/v1/tenders`), `page` (1..100), `pageSize` (1..200, default 50; a
page over 100 is not kept in the answer cache). Answers are kept five minutes; the limiter charges
three tokens a request (`hardening.request_cost`).

Returns `{ items: Change[], total, page, pageSize, windowDays, windowFrom, windowTo, counts, meta }`
with `counts = { new, amended }` over the whole window (not the page) and `windowDays` always 14.

`Change` = `{ id, kind, day, detectedAt, changes, tender }`:

- `id`: `<notice id>-<YYYYMMDD>`, stable. One entry per notice per UTC day.
- `kind`: `new` (first collected in the window, published no earlier than 7 days before it, so a
  history load is not news) or `amended`. A notice first seen and amended the same day is one `new`
  entry; one first seen earlier and amended is `amended`.
- `day`: the UTC day observed. `detectedAt`: the latest observation of that day.
- `changes`: `FieldChange[]`, empty for `new`. Only `status`, `deadline_at`, `value_amount`,
  `value_currency` and `procedure_type` are listed (an allow-list). Several amendments of one day
  are merged: the line runs from the day's first `before` to its last `after`, and a line that
  returned to where it began is dropped.
- `tender`: the same `Tender` as `/v1/tenders` (current state, nothing personal).

What is **not** an amendment: a version annotated `reread`, `out_of_order`, `remapped` or
`correction` in `opportunity_version_note`; one that moved only the publication date or the CPV
codes; a line whose two sides read the same. Our own re-derivations therefore never appear. A
national notice listed under its TED twin in `/v1/tenders` is listed once here too.

The archive began on 8 September 2026: a change made earlier is not shown, and a change is dated
the day we observed it, which may be later than the day the buyer made it. Index: migration 0046
(`oppver_observed`, partial on `observed_at` for versions after the first).

### Site routes built on it
`/changes` (page, filters `country` and `scope` in the URL; filtered and paged views are noindex) and
`/changes.atom` (Atom 1.0, newest 100 entries, same filters). Each entry's `id` is
`tag:<host>,2026:change:<Change.id>`, `updated` is `detectedAt`, the feed answers `ETag` and
`Last-Modified` and 304 on `If-None-Match` / `If-Modified-Since`, and carries titles, buyers,
countries and the old and new values only. `/changes` is in the sitemap without its filters.

## Changes of 16 October 2026 (WP-19, funding frictions of `docs/verification/ux/ux-funding.md`)

All additive, except the first point, which corrects a status.

- `/v1/funding` `status`: a call the source lists `forthcoming` whose `openingDate` has come (UTC
  day) and whose `deadline` is ahead is `open` (F1). It is in `status=open`, `closing-soon`, the
  calendar and the `.ics`, and no longer in `forthcoming`. A forthcoming call with no deadline
  stays forthcoming. `Call.sourceStatus` (`string | null`) is the source's own word.
- `Call.funder` (`string`): the issuing body of a national call, the programme name where a
  national source names no issuer, otherwise `European Commission` (the operator of the portal EU
  calls are read from) (F6). `programmeName` stays the programme in full.
- `/v1/funding/{slug}` also has `whoCanApply` (`{label, value}[]`: the eligible-countries and
  other-eligibility sections of the source's own conditions, and the applicants/beneficiaries of
  a national call; empty when the source says nothing) and `documents` (`{label, url}[]`: the
  documents the conditions link, https on `europa.eu` hosts only), both withdrawn with
  `conditionsText` when the source's `commercial_ok` is not true (F2, F9).
- `/v1/changes` also has `funding` (page 1 only, at most 50): `{id, kind: 'call-new' |
  'call-amended', day, detectedAt, changes: FieldChange[], call: Call}`, and `fundingTotal` (all of
  them, whatever the page); `counts` keeps its two numbers.
  `call-new`: first collected in the window and not closed; `call-amended`: the source moved the
  closing or opening date (table `call_change`, migration 0053; a day re-expressed is not a
  move). The tender `items`, `total` and `counts.new`/`amended` are unchanged; `scope` and
  `goods` filters switch `funding` off, `country` filters by funder country (F5).


## Changes of 16 October 2026 (WP-20, UX walk-throughs; owner decision on the default scope)

- **Default scope.** `/v1/tenders`, `/v1/tenders/export` and `/v1/changes` default to `scope=relevant`: `core`
  and `supply` together (`SCOPE_SQL['relevant']`, the two do not overlap). `core`, `supply` and `all` keep their
  meaning; `all` still holds the notices that are only dual-use. `Tender.scope` is still `core` or `supply`.
  The site's own default (list, CSV, calendar, home counters, saved searches without a `scope`, `/changes`) is
  `relevant`; a URL or saved search that carries `scope=` keeps its meaning. `/v1/opportunities` is unchanged
  (`core` default). Cost of the default list on production (`EXPLAIN ANALYZE`, 16 October, first page, open):
  320 ms execution time warm, a parallel sequential scan where `core` alone uses the
  `opp_core_published_v2` index; no new index was needed.
- **`GET /v1/tenders/scope-counts`** with the filters of `/v1/tenders` except `scope`, `sort`, `page`: `{relevant,
  core, supply}`, each the total the list would show under that scope with the list's own collapse rules.
  Cached like the lists. The site prints them next to the scope choices and on the home page.
- **History is not news.** A version written by a history load, a replay, a re-qualification or a backfill is
  annotated `history` (migration 0054; `db.historical_load`). `/v1/changes`, the Atom feed, the digests and
  every amendment count (`Tender.amended`, the market and buyer "with an amendment" shares) leave it out.
  `TenderVersion.historic` is true for such a version: the tender page lists it ("Read by DefenceGate on ..."),
  `detectedAt` is when we read it. `Tender.versionCount` still counts it. A notice is `new` only if it was
  published inside the window (two days of slack, was seven). `python -m dgate.ops.tag_history` annotates the
  versions written before; it reports unless told `--yes`.
- **Version lines.** A change of `source_url` inside the same site is not a line; a move to another site is one
  line naming the two sites, not the two addresses.
- **Search.** `q` of `/v1/tenders` and of `/v1/buyers`: every word must begin a word of the title or buyer name,
  accents and punctuation folded both ways (`dg_fold`, migration 0054: "Ausrüstung" = "Ausrustung", "off-road" =
  "off road"); at most six words; the notice number is matched as typed. Trigram indexes on the folded titles.
- **`GET /v1/stats/market`** takes `year` (2017 to the current year; the calendar year, to today when current) and
  `country` (ISO-2); the response carries `year` and `country`, `windowFrom`/`windowTo` are the year's, and the
  `months` series is that year's twelve months. Without them: unchanged (rolling 12 months, 36-month series).
- **`GET /v1/sources`**: `valueStatedCount` (tender sources): how many of the held notices state a value (a
  placeholder amount does not count). The site says "Not stated by the buyer in N % of notices from this source".
- CSV of tenders (site): the `sort` parameter is honoured; the file is rectangular: columns `scope`, `why_listed`,
  `versions` and `result_truncated` (`true` on every row when the result was cut at the limit, which then holds the
  most recently added notices, in the order chosen); no note row in the data.
