# WP-106 self-check: tender pages, lists and exports (round 3, 24 October 2026)

Branch `wp-wp106` from `integration` (24e5295). Test copy `D:\DEFENCEGATE TESTS\wp106\`, Postgres 17 on port 55506.

## Final runs (test copy)

| Run | Result |
|---|---|
| ruff | clean |
| backend unit | 3,653 passed (exit 0) |
| backend integration | 1,329 passed (exit 0, 952 s) |
| tsc --noEmit | 0 |
| web lib checks (`scripts/run-checks.mjs`, new `lib/wp106.check.ts`) | all ok |
| next build (mock) | 0 |
| Playwright, whole suite, desktop + mobile-375 | 772 passed, 0 failed (6 skipped by their own conditions); `e2e/wp106.spec.ts` 12 passed |

## Items

### 1. "Who may bid" by legal basis, and "who wins such contracts" (p02, p08)
- Before: the tender page said only "Legal basis Directive 2014/24/EU"; nothing on whether a Portuguese or a Ukrainian company may take part; "More from this buyer" was the only related block.
- Change: panel "Who may bid" on every tender page (`web/lib/who-may-bid.ts`). It paraphrases only the articles of the act the notice states: 2014/24 Art. 18 and 25; 2014/25 Art. 36 and 43; 2014/23 Art. 3; 2004/18 Art. 2 and 5; 2009/81 recital 18 (each Member State decides on third-country operators) and Art. 21 (subcontracting up to 30 % by competition); Ley 9/2017 and Ley 24/2011 named as the Spanish transpositions. Any other basis (national German rules, EU Financial Regulation, none): "The notice states no legal basis we describe here...". Under every line: "What the act says, not advice: the notice and the buyer set the conditions." Link "Who wins such contracts in <country>" to `/suppliers?cpv=<main code to 5 digits>&buyerCountry=<country>`.
- Test: `lib/wp106.check.ts` section 2 (articles present, no advice words, Spanish transpositions read the same, unknown basis -> null); `e2e/wp106.spec.ts` "a tender page says who may bid".
- After: panel present on the demo tender with recital 18 / Article 21 and the link.

### 2. Award rows: winner and value kind in lists; tender <-> award links (p04, p06, p07)
- Before: list cards showed award notices with "Estimated value"; winners only on the notice's own page; the call 121371 did not link to its award 130826 (same procedure identifier `0107af11-...`, checked read-only on production).
- Change: `tenders.list_item_fields` adds to every list item and export row (HTTP requests only, see `serves_meta`) `awardedTo`, `awardedPersons`, `awardValue` (`award_summaries`, four queries per page, the same rules as `awarded`; an integration test holds the two equal), the subject and the main code's title. Cards show "Awarded to: ..." and the value under its kind ("Awarded value", "Framework ceiling"). The change list's award rows say winners and value. Tender page: panel "Other notices of this procedure" (`procedure_stages`, same eForms procedure identifier, oldest first).
- Test: `tests/integration/test_wp106.py` (list item == own page, export rows, stages both ways, change row); `lib/wp106.check.ts` section 3.

### 3. Sort by value and by code; All newest first (p02, p04, p07)
- Before: sorts were deadline and published only; `status=all` ran the rest oldest deadline first (2017 under the open notices).
- Change: `sort=value-desc` (per currency: EUR first, then each other currency by itself, largest first, placeholder amounts with "none"; never converted) and `sort=cpv-asc` (main code), each over an index of migration `0118_wp106_list_sorts.sql`. `status=all` with no sort (`open-first`, the web default for All): open soonest first, then the rest newest deadline first; `deadline-asc` keeps the old order when asked for. The sort menu offers per status only what applies. The export applies the same orders (`listOrder`), the demo API too.
- Tests: `tests/unit/test_wp106.py` (orders and their index expressions), `test_wp106.py` (value/code/All orders), `test_wp52.py` and `test_wp98.py` updated to the new All order with the old one asserted under `sort=deadline-asc`; `wp52b.check.ts` default for All updated; `wp106.check.ts` section 5; e2e sort menu and value order.

### 4. CSV: winner column, one value-kind vocabulary, date filter for large exports, "Too many exports" (p06, p07)
- Before: no winner column; value kinds `total`/`estimated`/`lot sum` against the supplier file's `contract`/`framework ceiling`/`estimate`; p07 saved the 429 text as a CSV.
- Change: columns `winners`, `winner_countries` appended after `confidence` (order of the others unchanged). `value_kind` in one vocabulary with the supplier file: an award row carries the award's value and kind (contract / framework ceiling / estimate), a notice's own value is `estimate` (`estimate (sum of lots)`, `estimate (first lot)`), an award total not classified stays `not stated`. Publication-date range: WP-100 had year links; added a from/to form for a cut result. "Too many exports" was already HTTP 429 (`busy()`); the root cause of a saved error body was the `download` attribute on the CSV links: removed from the tenders/funding, market and supplier CSV links, so a 429/503 is shown, a 200 still downloads (content-disposition attachment).
- Tests: `wp106.check.ts` section 4 and source checks; `wp100.check.ts` vocabulary assertions updated to the shared words; `routes.spec.ts` header tail updated to the two new columns.

### 5. Subject and lots in lists (p03, p06; p02 269322)
- Before: subject only on the notice page; 37631 had none because the NATO stock number (13 digits) read as a phone number; 269322 showed "Modification de la date limite...".
- Change: subject in list items and cards (when it adds to the title). `commercial_subject` takes out lone digit runs of 7+ (part, order, stock numbers) and returns nothing for a description that only states a change (fr/de/es/it/nl/pl/en words); an international phone number (`+` digits) still gives nothing.
- Not done: the lot titles of 37631. The stored payload has `lot_count` but no lot titles (checked read-only); they need a change to the TED mapping and a re-fetch from TED, which this package may not run.
- Tests: `test_wp106.py`, `tests/unit/test_wp106.py`; `test_wp90.py` updated (the list now serves the subject, read the same way).

### 6. CPV labels (34330000, 24615000) (p03, p04)
- Before: cards printed no name and the page "Within: Transport equipment..." for codes outside the 366-code selection.
- Change: the API sends `cpvTitles` from the full CPV 2008 vocabulary it already holds (`cpv_labels.DATA`): all codes on the page, the main code in lists. Web prefers it.
- Test: unit `test_cpv_titles_come_from_the_full_vocabulary`, integration list item, `wp106.check.ts` source check.

### 7. "Closing soon" within 7 days; weekday wording (p01, p02, p04, p06)
- Before: tender chip at 30 days; "Closes this week" for Wednesday read on Saturday.
- Change: `TENDER_SOON_DAYS = 7` for tenders (calls keep 30 days, the API's "closing soon" list); urgent labels in days: "Closes today / tomorrow / in N days".
- Test: `wp106.check.ts` section 1; `ui.check.ts` label assertion updated to "Closes in 2 days".

### 8. Digest CPV filter; calendar CPV field and full country list (p04, p09)
- Change: `/v1/digest?cpv=` narrows the tender sections (`weekly_digest.with_cpv`: the week's events of /changes filtered by the list's own CPV reading); calls unchanged and the page says so; the filter travels in the page, the weeks, the Atom feed (own id) and "the list has the rest". Calendar: a CPV field in the form, and every buyer country listed (the list had narrowed to the chosen ones).
- Tests: `test_wp106.py::test_the_digest_narrows_its_tender_sections_to_cpv_codes`; `wp106.check.ts` section 6; e2e calendar; `wp87.spec.ts` now reads the cpv field (it was a hidden input).

### 9. Changes period beyond 14 days (p03)
- Measured read-only on production: the 14-day window takes 5.9 s, a 30-day window hits the 5 s statement timeout. So no longer rolling window; the page now offers a "Period" choice: the last 14 days, this week so far and every archive week (the API's existing `week`). The legend shows only the kinds listed.
- Tests: e2e `wp106.spec.ts` change-list test; `wp52b.spec.ts` now checks the selected week in the select (it was a hidden input).

### 10. Phone overflow (p01, p03, p07, p09)
- `/tenders` 396 px: a long status pill now wraps (`StatusPill`, card pill wrapper no longer `shrink-0`). Results page 413/425 px reproduced in e2e: the cause was unbreakable references in the rule source notes (`components/readiness/rules.tsx`), now `overflow-wrap:anywhere`. Supplier notices table: the value is repeated under the title on a phone. CSV button: before the results on a phone (tenders, buyers and funding lists).
- Test: e2e phone tests (tenders list, tender page, results page with sections open: width <= 375; CSV above the first card).

### 11. Home page cold 9-14 s (p03, p06, p07, p09)
- Measured on production, read-only: Caddy log of 24 Oct, 439 GET / with p50 0.02 s, p95 0.10 s, max 0.6 s; the RSC prefetches a home load starts p95 <= 0.16 s. A cold browser (Playwright, fresh profile) from the laptop: DOMContentLoaded 0.8-2.4 s, network idle 2.1-3.7 s, 35 requests, largest chunk 371 kB. The persona loads (11:38 UTC) reached the server 7 s after the client started: ten persona browsers ran at once on one machine. No server-side cause; no code change. Open: if wanted, a timing from an unloaded machine.

### 12. Print stylesheet for call pages and roadmap (p09)
- Change (`globals.css`, print): forms, buttons, selects, menus, search, "Can I apply?" and the related lists hidden; call page content at 72 %, roadmap at 62 %.
- After (demo build): funding call 2 A4 pages (was 3 with this CSS's first step; production report 10); roadmap of the 8-step Spanish demo profile 7 -> 4 pages, nothing left out. 1-2 pages for the roadmap would need dropping content (issuers, notes, sources): not done.
- Test: e2e print tests (no form/button/menu visible in print, page counts <= 2 and <= 4).

### 13. "See all 1 companies" (p07)
- Change: singular noun on the search page ("See the 1 company that won contracts").

## Files outside this package's area (smallest change, listed as the brief asks)
- `backend/dgate/changes.py` (WP-103): award rows carry `list_item_fields` (HTTP only), one statement.
- `web/app/(public)/search/page.tsx` (WP-101): the singular noun only.
- `web/components/readiness/rules.tsx` (WP-107): `overflow-wrap:anywhere` on the source note and rule title.
- `web/components/funding/call-list-template.tsx`, `web/app/(public)/funding/[slug]/page.tsx` (WP-102): CSV tools moved above results on a phone; `print:hidden` on partners and related calls.
- `web/app/(public)/suppliers/[slug]/page.tsx`, `web/app/(public)/market/page.tsx` (WP-105): `download` attribute removed from the CSV link; phone value under the title.
- `web/app/(public)/readiness/roadmap/page.tsx` (WP-107): a `data-roadmap-print` wrapper.
- `backend/dgate/tenders.py`: new functions only (`procedure_stages`, `award_summaries`, `latest_descriptions`, `list_item_fields`, `cpv_titles`, orders); the q handling and status logic untouched; `commercial_subject` extended.

## Production
- Migration `0118_wp106_list_sorts.sql` (two indexes, ANALYZE) runs with the deploy (migrate service). No data writes, no ops module.
- The worker's list snapshots pick up the new list fields at their next refresh.
- Saved searches (accounts, closed) accept only `deadline-asc`/`published-desc` as sorts (`accounts.py`); not widened here.
