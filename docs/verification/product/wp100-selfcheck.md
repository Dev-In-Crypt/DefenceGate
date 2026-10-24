# WP-100 self-check: mobile, feeds, exports (persona round of 23 October 2026, E)

Branch `wp-wp100` from `integration` (58d6bd9). Input: `D:\DEFENCEGATE TESTS\ux-oct23\SUMMARY.md` section E minus the phone filter
panel (WP-98b) and the funding feeds (WP-99); evidence of p02-pt-textile, p04-pl-ammo, p07-it-analyst, p09-be-consultant. No deploy,
no push, no production read or write, no procurement portal called. Not touched: the WP-88 copy rule, the WP-95 value logic (the
supplier file reuses `suppliers.value_of`, `best`, `is_suspect`), the list filters UI (WP-98b), search (WP-98), funding (WP-99).

## 1. Phone layout

- Tender page (`app/(public)/tenders/[slug]/page.tsx`): a `d-top` card (deadline badge and "View original at ...") heads the page
  header on a phone, right under the title, before the buyer, award, subject and chips (p02: deadline at 2,043 px and View original at
  4,234 px; p04: deadline below the first screen). A title over 80 characters is cut to four lines below lg (`max-lg:line-clamp-4`),
  the whole of it under "Full title". From lg nothing changes (the side column keeps the deadline and the link).
- Buyer page: the CPV filter, open and planned tenders come before the profile charts and the top suppliers (p04: open tenders at
  ~3,900 px). Same order on desktop (one DOM order, the reading order). "Showing x of y" figures formatted.

## 2. Feeds

- Names: `lib/feed-name.ts` `searchSummary`. Atom title "DefenceGate: radar, DE+PL" (unfiltered: "DefenceGate: what changed");
  calendar `X-WR-CALNAME` "DefenceGate tender deadlines: radar, DE+PL" (unfiltered kind=all stays "DefenceGate deadlines").
- Speed: `lib/api.ts` `getChangesForFeed` read the whole window as 12 API pages one after the other (12.5 s, 1.37 MB, 2,403 entries
  on production, p09). Now the feed is paged (RFC 5005): a page holds 400 entries (two API pages of 200, read at once), `page=N` for
  the older ones, `first`/`previous`/`next` links, the subtitle says how many there are and on which page; a page past the last is a
  404 saying how many pages there are. Cache: fresh 5 minutes per query and page, then the last page built (up to 30 minutes) is served
  while it is built again (one build at a time per key). Filtered feeds go the same way. The subscribe block and /data say 400 a page.
  The API side is unchanged (its window is single-flight and cached five minutes).

## 3. Tenders CSV

- Order: `listOrder` (lib/export-cache.ts) read the list's default sort `core-first` as "newest deadline first" (p09: 30 October at
  the top). It now orders as `list_tenders`: the default view (open, All defence) military goods and works first, each part soonest
  deadline first; `status=all` open first; a sort asked for as before.
- `value_kind` on every row with a value (`lib/export-tables.ts` `csvValueKind`): the notice's own kind as before (TED total,
  estimated, lot sum, first lot); none stated: `estimated` for a call and for any PLACSP notice (the connector reads its valor
  estimado or budget), `not stated` for another source's award notice (BOAMP's figure may be the awarded amount). No new kind is
  stored; WP-95 award kinds are untouched.
- `publishedFrom` / `publishedTo` (YYYY-MM-DD; API `/v1/tenders/export`, the publication date or the notice date) and `cursor`
  (the next part). A cut file sends `Link: <...cursor=...>; rel="next"` and `x-next-part`; every file says its cap in `x-row-cap`
  and `x-row-cap-note`; a malformed value is a 400. The column set is unchanged (`result_truncated` still marks a cut). UI: when a
  result is longer than the cap, the Download CSV box says the Link header and offers one file per publication year (2021 on).

## 4. New exports

- `/suppliers/{slug}/contracts.csv` (API `GET /v1/suppliers/{slug}/contracts`, priced 5 tokens): every contract once (`award_set`
  KEY, the row `best` picks, the one the page's sums read), newest first, at most 5,000: buyer, country, date, CPV, value, currency,
  kind (contract / framework ceiling / estimate), `in_contract_sum`, winners in the notice (co-winners counted, never named),
  framework notice, source name and URL, licence, attribution (from `source`), page URL. A natural person has no page (410/404 as the
  profile). Link on the supplier page under "The notices".
- `/market/export.csv` (same year, country, CPV as /market): one row per month bar (TED and national), country (and the rest), CPV
  group, source; the source's licence and attribution on its row, all contributing sources' on the others (from `/v1/sources`). Link
  under the market figures. Both disallowed in robots.txt like the other exports.

## 5. Calendar page

- "follow the deadlines above" -> "the deadlines this page lists" (the feed box comes first on a phone). Counts formatted (1,449 not
  1449); the feed line says "N deadlines and M opening days and planned deadlines of calls not yet open".

## Tests (local, `D:\DEFENCEGATE TESTS\wp100`, Postgres container dgate-wp100 on 55500, E2E_PORT 3100)

- Final run (24 October 2026, base 58d6bd9): ruff clean; unit 3,564 passed (+2 in `tests/unit/test_wp100.py`, run apart: 2 passed);
  integration 1,290 passed (new: contracts file in `test_supplier_map.py`, publication range in `test_tender_export.py`); tsc clean;
  lib checks all ok (`lib/wp100.check.ts` new); next build ok; Playwright 733 passed, 56 skipped (the fake-API cases, by design),
  1 failed: wp49 "a radio applies at once" on mobile-375 (a 3 s poll on the tenders list, which WP-100 does not touch); rerun:
  the file 3 times 42/42, the test alone 6/6. Timings: unit 24 s, integration 860 s, checks 241 s, build 52 s, Playwright 210 s.
- New: `web/e2e/wp100.spec.ts` (tender first screen at 375 px, buyer order, feed and calendar names, feed paging 404, CSV order,
  value kind, range, cursor, cap header, supplier and market CSV, calendar wording), desktop and 375 px.
- Changed expectations (the WP-100 behaviour, not weakened): `e2e/wp52b-api.spec.ts` "1,449 upcoming deadlines" (was "1449").

## Open decisions

1. Atom timing on production is not measured (no production access in this package): expected ~2 API page reads in parallel cold
   (production measured about 1 s a page) and a cache hit after; measure `/changes.atom` and a filtered feed on the server after deploy.
2. The feed went from one 2,403-entry document to pages of 400: a reader that does not follow `rel="next"` sees the newest 400 only
   (said in the subtitle). Owner may prefer a 7-day window instead.
3. `value_kind` fallback words (`estimated`, `not stated`) are derived in the CSV, not stored; BOAMP's normaliser could record which
   rule gave the value (awarded / estimated / ceiling) with a backfill, if wanted.
4. The CSV button next to "Showing 1-50" on a phone (p09) sits in `list-page.tsx`, the list UI of WP-98b: not done here.
5. The buyer page order change applies to desktop too.
