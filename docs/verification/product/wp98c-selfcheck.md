# WP-98c self-check: supplier value orders and feed prewarm (production timings after the WP-98b deploy)

Branch `wp-wp98c` from `integration` (b480e8e: WP-98b and WP-100 in). Input: the coordinator's production timings after deploy
b480e8e: `/suppliers?sort=value-EUR` 503 at 5.8 s cold, 4.1 s warm; `/changes.atom` 5.1 s cold (a 502 on the first request
after the earlier deploy), about 1.0 s cached. No deploy, no push, no production read or write. Search code (WP-98) not touched.

## 1. Supplier value orders

- **First try, dropped.** A table of every award row's value (`value_of` stored per row) changed nothing on the synthetic set:
  0.60 s with the per-row valuing, 0.64 s from the table. The time is the second pass over the whole award set (every
  supplier's sums for the order), not the valuing. Not committed.
- **What is in.** `suppliers.compute_value_order()`: every supplier's contract-value sums per currency, largest first: the rows
  `contract_values_sql` gives (WP-95 contract values only, a unit price in no sum: the sums the list cards and the profile
  show). Two orders, the whole set and TED's rows, stored in `list_snapshot` (`supplier-values:set`, `supplier-values:ted`) with
  the PLACSP switch they were computed under. Written after every award load (`awards.refresh_award_twins`, which every load
  path calls, in a savepoint: a failure leaves the older orders and never the load), every four hours (`ops/warm_lists`) and at
  the worker's start when missing (`warm_lists.run_first`). `/v1/suppliers?sort=value-XXX` without a filter reads it (kept five
  minutes in memory); with a filter, or none stored, too old (8 h) or computed under the other switch, it sums live as before
  (a filter narrows the pass: 0.16 to 0.18 s on the synthetic set).
- **Older than the last award load.** The page carries `valuesAsOf` and `valuesBehind` (an `award_notice.read_at` after it);
  /suppliers then says "Ordered by the contract values as summed on …; contracts read since then join the order at the next
  update (each company's own values below are current)". The cards' own values are always summed now.
- **Truth.** `test_wp98c.py`: the stored order equals the live one, item for item; every stored sum equals the profile's
  `values.byCurrency` for that supplier and currency; the TED order holds TED's values only; a marker in the stored body is what
  the list shows; a filter, a 9-hour-old order and one computed under the other switch are summed live; an award load after
  the order sets `valuesBehind`.

## 2. Feed prewarm

- **API.** The Atom feed's first page reads the API's first two pages of 200 (`FEED_PAGE_SIZE`, `FEED_PAGE_ENTRIES` 400).
  `warm_lists` now keeps them (`FEED_PAGE_SIZE`, `FEED_API_PAGES`; `wp98c.check.ts` holds them to web/lib/api.ts), and the list
  cache read a page over 100 without its snapshot at all (`cache_list` returned before the snapshot read): it now reads the
  snapshot for any size and keeps only the small pages in memory. The worker's start writes these pages and the value orders
  when missing or older than four hours (`worker.warm_first_views`, its own thread, seconds), so a deploy's first reader has them.
- **Web.** `instrumentation.ts` starts `lib/feed-warm.ts` on a server that reads the API: 5 s and 30 s after start, then every
  4 minutes (under the feed's five fresh minutes), the server asks its own `/changes.atom`, `/funding.ics`,
  `/calendar.ics?kind=funding`, `/calendar.ics?kind=tenders` and `/digest.atom`, one after the other, and logs what did not
  answer 200. WP-100's stale-while-revalidate kept the last page in memory only, so a restarted server had nothing: the
  unfiltered feed's pages are now also written to disk (`last-good`, at most 6 h old), so a cold start serves the last page
  while it builds, and a build that fails serves it instead of a 502. `DG_WARM_FEEDS=0` turns the warmer off.

## 3. Timings (cold, production-sized synthetic archive)

Laptop, test container, database `dgate_perf` (350,000 notices, 105,000 defence, 63,636 award rows, 18,398 suppliers), list
cache off, median of 3 (`D:\DEFENCEGATE TESTS\wp98b\perf98c.log`):

| Request | As deployed (summed live) | Stored order |
|---|---|---|
| `/v1/suppliers` (default order, for reference) | 0.19 s | 0.19 s |
| `?sort=value-EUR` | 0.60 s | **0.28 s** |
| `?sort=value-PLN` | 0.59 s | **0.25 s** |
| `?source=ted&sort=value-EUR` | 0.59 s | **0.23 s** |
| `?cpv=3581,181&sort=value-EUR` (live either way) | 0.16 s | 0.18 s |
| `?buyerCountry=ES&sort=value-EUR` (live either way) | 0.16 s | 0.16 s |
| Writing both orders with the twin pairs (`refresh_award_twins`) | | 2.17 s |
| Worker start, first views (4 feed pages) | | 1.36 s |

The value order now costs the default list plus about 0.1 s (unnesting the stored ids). Production ran the live order at 5.8 s
cold against 0.60 s here (about ten times the laptop); by the same ratio the stored order is about 2.5 to 3 s cold and the
default list's cost on production bounds it.

End to end, a local API on that database and `next start` with `DG_API_URL` set (`demo-*.log`):

- API process just started: `/v1/changes?pageSize=200&page=1` 0.15 s (snapshot), `/v1/suppliers?sort=value-EUR` 0.61 s.
- Web just started: the warmer asked `/v1/changes` pages 1 and 2 of 200 and the funding lists within its first round, no
  failure logged; then `/changes.atom` 0.15 s, `/funding.ics` 0.03 s, `/calendar.ics?kind=funding` 0.05 s,
  `/suppliers?sort=value-EUR` (page render) 1.64 s.
- API stopped, web restarted: `/changes.atom` 200 in 0.09 s from the page on disk (a 502 before).
- The synthetic archive has no version history, so the change window's live cost (5.1 s on production) is not reproduced here;
  the snapshot read path is what is measured.

## 4. Tests

Local, `D:\DEFENCEGATE TESTS\wp98b` (own venv; Postgres 17 container `dgate-wp98c` on 55488, removed at the end; TZ=UTC; web
mock env; E2E_PORT 3188), final code:

| Check | Result | Time |
|---|---|---|
| ruff | All checks passed | |
| unit | **3566 passed** | 26 s |
| integration | **1300 passed**, 0 failed (5 new in `test_wp98c.py`) | 11 min 18 s |
| `tsc --noEmit` | exit 0 | 11 s |
| lib checks (with `wp98c.check.ts`) | all ok | 123 s |
| `next build` (mock) | exit 0 | 37 s |
| Playwright, desktop + 375 px, 4 workers | **743 passed, 57 skipped, 0 failed** | 156 s |

New: `backend/tests/integration/test_wp98c.py` (5 tests), `web/lib/wp98c.check.ts`. No test deleted, skipped or weakened.

## 5. Open points

- The stored order lags a merge or a removal on request by up to four hours (like the twin pairs); a removed supplier never
  shows (the list's own filters run live), only its place in the order is old.
- The production ratio is an estimate; please time `/suppliers?sort=value-EUR` cold after the next deploy (the worker's start
  writes the orders within seconds; until then the live sum answers as before).
- Next.js prints "Failed to copy traced files ... dg-last-good" on Windows builds (the temp folder path); it was there before
  (WP-97's build log) and is a warning only.
