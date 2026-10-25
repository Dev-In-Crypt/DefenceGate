# WP-120 self-check: speed and caching

Branch `wp-wp120` (on `integration` at 445c1e5, which carries the orchestrator's compose fix: the worker reads
`DGATE_PLACSP_AWARDS_PUBLIC`, so its supplier value orders and market money are served). Builder brief:
`D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP120.md`. Evidence of the audit: `verify-oct25\system\` and `site\problems.csv`.

## How it was measured

- **Production, before** (read only): curl from the laptop, 3 to 5 s apart (`wp120\perf\site-probe.sh`, `ammo-probe.sh`,
  results `before-site.tsv`, `before-ammo.tsv`, 25 Oct ~12:00 UTC), and the audit's `probe-run.tsv`. The laptop's round trip
  is about 0.27-0.30 s, so a "warm" API answer of 0.30 s is the network. No SQL ran on production: `docker exec` into the
  Postgres container was refused to this run, so there is no production EXPLAIN ANALYZE behind any number here.
- **Before / after on the same data**: the production-sized synthetic archive of WP-98 (`wp98\perf\gen.py`: 357,000 notices,
  95,818 award rows, no production data) in the test Postgres, 5 s statement timeout, in-process `TestClient`; the integration
  code (`git archive integration`) against this branch (`wp120\perf\t120.py`; results `before-nostore.json`,
  `after-final.json`, `before-stored.json`). "Cold" = every in-memory cache emptied (median of three), the database's own
  cache warm; "warm" = the same call again. The synthetic archive is faster than production (fewer twins, a smaller vocabulary
  that makes "ammunition" match 26 % of the notices), so it shows what each change does, not production's absolute times.
- **After on production** can only be measured after the deploy: the commands are at the end.

## Items

### 1. `/v1/suppliers` sorted by contract value (MAJOR)

- Before: 503 at 5.6 s cold (audit); after the orchestrator's compose fix the stored order is served: 1.66 s cold, 0.33 s
  warm, default order 1.78 s cold (laptop, 25 Oct ~12:00). With no stored order the sums were part of the list's one statement,
  which ran past the 5 s timeout.
- Change: with no stored order (worker not run yet, too old, other PLACSP switch) the unfiltered value order is summed by the
  API itself in a planned time box of its own (`suppliers._live_value_order`, 20 s, `tenders.time_boxed`), once per 5 minutes
  for every page and currency (kept in `stats._cache`, the store of the hourly aggregates, which a flood of list pages cannot
  evict; it was in the 120-entry list store). The list statement then joins the order like a stored one. The list itself is
  answered stale for up to 10 more minutes while a background read renews it (item 4).
- Tried and dropped: keeping the per-supplier aggregate in the stored body too. It made the unfiltered list blind to a merge,
  a removal on request, a person flag or the supplier cleaner until the next store (4 integration tests failed: test_wp39 x2,
  test_supplier_map, test_placsp_award_twins). Membership and counts stay live.
- Synthetic: no store, value-EUR cold 1.03 s (one statement under the 5 s timeout) -> 1.12 s (the order in its own 20 s box,
  then the list), and every later page and currency reads the kept order; stored order: about 0.5 s both. Warm 0.03 s. The
  point on production is no 503: the order statement no longer shares the list statement's 5 s.
- Expected on production: as today with the stored order (1.66 s cold, 0.33 s warm); with none stored, one slow first call
  (the sums, about 3.5-4 s, then the list) instead of a 503, and the stale window (item 4) for later expiries.
- Tests: `test_wp120.py::test_with_nothing_stored_the_value_order_is_summed_once_in_its_own_time_box`; the WP-98c tests
  (stored order is the live one, too old / other switch summed now, award load said) pass unchanged.

### 2. Buyer pages (MAJOR)

- Before: p95 4.3 s, 1 in 27 over 5 s, max 9-11.5 s; /buyers/268 262 KB, 1.24 s cold / 0.88 s warm TTFB from the laptop
  (1.69 / 1.39 s total). Its API calls, timed on the host: all 0.03-0.6 s, so the tail is the aggregates expiring under load
  and the size of the page.
- Changes:
  - Lighter page: the first 20 open and 10 planned tenders (soonest deadline first), "Show all" to `?all=1` (up to 100 of
    each, as before; not indexed). The Czech ministry's page held 100 open and 45 planned cards.
  - The buyer aggregate (`buyer_base`, whose live open counts cost 1.06 s on average, 4.2 s at most) is answered up to 25
    minutes past its 5 minutes while one background read renews it (`stats.cached_stale`, at most 2 renewals at once, each
    with its own API connection), and lives in `stats._cache` instead of the list store a flood of pages could evict.
  - `_buyer_names` (the API's costliest statement: 120,000 calls, up to 4.8 s) keeps each buyer's shown name 15 minutes per
    organisation (`stats._name_cache`, 20,000 names; short so a name withheld or removed leaves every page within a quarter
    of an hour).
- Synthetic (largest buyer, 270024): API calls 0.22-0.64 s cold, 0.01-0.08 s warm, unchanged by design (the gain is the
  expiry and the names under load, which a single-user run does not show). Page size: measured after deploy.
- Tests: unit `test_wp120.py` (stale value answered while renewed; a failed renewal keeps the old value),
  `test_wp120.py::test_buyer_names_are_kept_a_while_and_only_with_the_caches_on`, `lib/wp120.check.ts` (page limits and
  `all=1`), `e2e/wp120.spec.ts` (the `?all=1` page is noindex), existing buyer specs (wp52b T14, wp100, wp105).

### 3. Text search with words that expand to many terms

- Before (production, laptop): `status=all&q=ammunition` 7.6 s (audit), 9.8 s and 8.1 s today; its parts: open 2.6 s, closed
  3.5 s, scope counts 503 in 1.6 s (the first count up to 200 did not finish in its 1.2 s box). Traced on the synthetic
  archive: 7 statements per request each re-run the text test (`wp120\perf\stmts.py`).
- Changes:
  - A count budget per list request (`tenders.count_budget`, 2,000 ms for all its counts together; a count with under
    100 ms left is not started and the total is "at least", as when a box runs out). The counts each had 1.2 s, up to seven
    per request (two per part of `all`, `_few`, the "never below Open" count): the counting part is now at most 2 s where it
    could be 8.4 s. This is what bounds production's "ammunition" (its counts ran to their boxes).
  - The candidate set read once per request (`tenders.search_ids`, `searched_once`: the list and its counts, and the scope
    counts' three scopes): the matches (defence, not suppressed, at most 5,000, in a planned time box) and every statement
    tests `o.id = ANY(ids)`; a search over the limits is remembered 5 minutes and takes the per-row EXISTS at once. The set
    lives for the request only (an across-request cache broke `test_list_cache_and_scope`: another query must see a notice
    added a second ago). **Shipped off** (`DGATE_SEARCH_IDS_MS=0`, the default): on the synthetic archive it cost more than
    it saved for every word tried. Measured with it on (800 ms box): ammunition all 1.23 -> 1.69 s, uniform 1.02 -> 1.22 s,
    municion ES 1.67 -> 2.02 s, fuel closed p2 0.56 -> 1.34 s (over the limit, the attempt is paid), drone 0.47 -> 0.36-0.53 s;
    with a 20,000 limit fuel was 0.56 -> 0.92 s. On production the per-row test is far slower (a count up to 200 did not finish
    in 1.2 s), so the read may pay there: switch on with `DGATE_SEARCH_IDS_MS=800` on the API and measure (below).
- Synthetic, shipped state: ammunition all 1.23 -> 1.20 s, uniform 1.02 -> 1.00 s, municion ES 1.67 -> 1.69 s, scope counts
  1.77 -> 1.76 s, fuel closed p2 0.56 -> 0.55 s cold; warm 0.03 s. (The synthetic counts finish inside 2 s, so the budget does
  not bite there; it does where the boxes ran out.)
- Expected on production: `status=all&q=ammunition` 9.8 s -> about 2 s of counting plus its two row reads (open 2.6 s and
  closed 3.5 s whole requests today, each including counts): likely 4-5 s cold, **still over the 3 s target**; open item.
- Tests: `test_wp120.py::test_the_counts_of_one_list_request_share_one_budget`, unit
  `test_no_count_is_started_without_counting_time_left`, `test_wp120.py::test_a_search_read_by_its_matches_lists_what_the_per_row_test_lists`
  (off by default; on: the same items and totals as the per-row test, all / closed / open), `::test_a_slow_match_read_falls_back_and_is_not_tried_again`.

### 4. `/v1/tenders` default, filtered page 2, Planned list, exports

- Before (laptop): default 3.2 s (audit) / 2.6 s cold today, 0.36 s warm; `q=fuel&status=closed&page=2` 5.1 s (site audit);
  Planned 2.6-3.5 s (site), 1.52 s cold today; `/v1/tenders/export` 2.83 s cold and 2.20 s warm (never kept).
- Changes:
  - The tender list, its scope counts, the calendar, the buyer and supplier lists are answered up to 10 minutes past their
    5 minutes while a background read renews them (`cache_list(stale=LIST_STALE_SECONDS)`): the visitor who finds the default
    list expired no longer waits for it. A list never asked, or evicted, is computed as before.
  - The Planned list (no country, pages 1-3, and its scope counts) is stored by the worker with the closed and all lists
    (`ops/warm_lists`).
  - Export pages up to 2,000 notices are kept 5 minutes in a store of their own (`cache_list(large=)`, 8 pages).
  - The filtered page 2 is a text search: item 3.
- Synthetic: export 0.27 s cold / 0.27 s warm -> 0.31 s cold / 0.05 s warm; default list 0.36-0.41 s (unchanged; the gain is
  the expiry); Planned 0.14-0.19 s.
- Tests: `test_wp120.py::test_an_export_page_is_kept_for_five_minutes`, `::test_the_worker_keeps_the_planned_list_without_a_country`,
  unit stale tests; test_warm_lists, test_wp52, test_wp114, test_tender_export pass.

### 5. 304 of calendar.ics and funding.atom

- Before: calendar.ics 304 in 1.36 s (audit) and 1.87 s today, funding.atom 304 in 1.45 s: the body was built to hash it.
- Change: `withCachedEtag` (lib/etag.ts): the built answer is kept per address for its own max-age (an hour), so a revalidation
  or a repeat costs a hash lookup; an error is never kept; at most 40 answers.
- Tests: `lib/wp120.check.ts` (one build for 200, 304 and 200 again; another address another build; an error not kept),
  `e2e/wp120.spec.ts`, `e2e/wp114.spec.ts` (304s), `e2e/wp99.spec.ts` (funding feed).

### 6. changes.atom If-Modified-Since; Cache-Control of a JSON 304

- Before: changes.atom answered its own Last-Modified with 200 and 40 KB (today too); a JSON 304 said `no-store`.
- Root causes: the feed compared the header (whole seconds) with a time with milliseconds; `SecurityHeaders` gave
  `no-store` to anything not 2xx.
- Changes: `notModified(request, etag, lastModified)` in lib/etag.ts compares at the whole second and is used by changes.atom,
  digest.atom and regulation.atom; a 304 gets the 200's `public, max-age=60` (hardening.py).
- Tests: `lib/wp120.check.ts`, `e2e/wp120.spec.ts` (changes.atom and digest.atom 304 to their own Last-Modified),
  `test_wp120.py::test_a_304_repeats_the_cache_control_of_its_200`.

### 7. Statement-timeout log noise

- Before: 30 "canceling statement due to statement timeout" in 2 hours, 26 of them the tender list's own time boxes.
- Change: every planned time box runs through `tenders.time_boxed`: a savepoint with its own `statement_timeout` and
  `application_name = dgate-timebox` (the list counts, the CPV buyer counts, the live supplier order, the match read); a
  parallel helper carries the leader's settings. `infra/docker-compose.yml` adds `log_line_prefix=%m [%p] app=%a ` so the log
  line names it: real timeouts are `grep 'statement timeout' | grep -v app=dgate-timebox`. The prefix takes effect when the
  Postgres container is next recreated (or `ALTER SYSTEM SET log_line_prefix ...; SELECT pg_reload_conf();`, a SIGHUP setting).
  The counts per request are also fewer (item 3's budget), so fewer cancellations.
- Not done: suppressing the ERROR line itself needs `log_min_messages`, a superuser setting. Turning parallel helpers off in
  the boxes was tried and dropped: the counts ran out of their box more often on the synthetic archive.
- Tests: `test_wp120.py::test_a_time_box_is_named_cancels_alone_and_is_undone`.

### 8. Unknown query parameters; "radar" in search and in the organisation list

- Before: `/v1/suppliers?foo=bar`, `/v1/buyers?foo=bar`, `/v1/funding?foo=bar` answered 200 (today: 200 in 2.0 s).
- Change: `known_params` (moved from tenders.py to funding.py, which tenders imports) on the three lists. The site's
  parameters (web/lib/api.ts getSuppliers, buyersQuery, fundingQuery) are all taken.
- Synthetic: 422 in 0.01-0.02 s (no query runs).
- Tests: `test_wp120.py::test_an_unknown_parameter_is_refused` (x3), `::test_the_parameters_the_site_sends_are_taken`.
- "radar": not a bug. The search's organisation part counts the directory as the site opens it, on the defence programmes
  (`search.OPENS_ON`, web/lib/networks.ts DEFENCE_PROGRAMMES), so its "see all" link leads to the same 1; the audit compared it
  with `/v1/organisations?q=radar` without the programme filter (5). The search page already says companies in EU-funded
  projects are those of the defence programmes.

### 9. Companies list on a 429

- Before: a 429 fell to the error boundary ("We could not load the supplier map").
- Change: /suppliers catches the 429 and shows the search's standard wording: "Too many requests from your network just now",
  why (the limit is per internet address, an office shares it), wait a minute, Try again (same filters).
- Tests: `lib/wp120.check.ts` (source check: the demo build has no rate limiter to drive a real 429).

## Indexes

None. No migration (0130 not used): every change is caching, bounding or fewer statements.

## Files touched

Backend: `dgate/tenders.py`, `dgate/suppliers.py`, `dgate/stats.py`, `dgate/listcache.py`, `dgate/funding.py`, `dgate/config.py`,
`dgate/hardening.py`, `dgate/ops/warm_lists.py`; tests `tests/integration/test_wp120.py`, `tests/unit/test_wp120.py`.
Web: `lib/etag.ts`, `app/(public)/{calendar.ics,funding.atom,changes.atom,digest.atom,regulation.atom}/route.ts`,
`app/(public)/buyers/[slug]/page.tsx`, `app/(public)/suppliers/page.tsx`; tests `lib/wp120.check.ts`, `e2e/wp120.spec.ts`.
Infra: `infra/docker-compose.yml` (Postgres `log_line_prefix`). Not touched: award_value.py, org_repair.py, supplier_dedupe.py,
globals.css and the card components (WP-118).

## After deploy (orchestrator)

1. `python -m dgate.ops.warm_lists --yes` (or wait for the worker's round): stores the Planned list.
2. From the laptop, 3 s apart: `bash "D:\DEFENCEGATE TESTS\wp120\perf\site-probe.sh"` and `ammo-probe.sh`; compare with
   `before-site.tsv` / `before-ammo.tsv`.
3. Item 3's candidate read: if `status=all&q=ammunition` (or uniform, municion) stays over 3 s cold, set
   `DGATE_SEARCH_IDS_MS=800` on the API (infra/.env, then recreate api), re-run `ammo-probe.sh`, and keep it only if it is
   faster; ideally with an EXPLAIN ANALYZE of the read (`tenders.search_ids`) first, which this run could not do.
4. Postgres log, a day later: `docker logs dgate-postgres-1 --since 24h 2>&1 | grep 'statement timeout' | grep -vc app=dgate-timebox`
   (needs the new log_line_prefix, i.e. a Postgres recreate or reload).

## Test runs (this copy, `D:\DEFENCEGATE TESTS\wp120`, batched scope)

- ruff: clean. Unit: 3,904 passed, 3 of them new (25 s).
- Integration (the 50 files that exercise suppliers, buyers, funding, the list cache, warm_lists, exports, ETags, scope counts,
  buyer aggregates; `wp120\int-files.txt`): 633 passed, 0 failed (252 s).
- Web: `tsc --noEmit` clean; all lib checks (`node scripts/run-checks.mjs`) passed, `wp120.check.ts` new; `next build` ok;
  Playwright `wp120 wp52b wp100 wp105 wp114 changes digest suppliers wp99`: 99 passed, 11 skipped (mobile duplicates of
  request-only specs), under the web-build lock.
