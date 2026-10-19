# WP-52 self-check: tenders backend and data correctness (UX audit of 19 October 2026, T2, T3, T8-T18)

Branch `wp-wp52` (from `integration` 4fbdc87). Backend and API contract only; `web/lib/types.ts` got optional fields for the new
API fields and nothing else in `web/` changed (the follow-ups the site needs are listed under "Left"). Tests ran on the server in
`/root/dev-w52` with the database `agent_wp52`: ruff clean and **3,966 tests green** (unit and integration; 3,924 before this work, 42 added in `tests/unit/test_wp52.py` and `tests/integration/test_wp52.py`; the first full run found 8 failures, all mine, fixed below).

## How the numbers below were measured

Production was only read: `EXPLAIN` and short `SELECT`s under `default_transaction_read_only=on` and `statement_timeout`, plus a
`pg_dump`/`COPY` of `opportunity`, `organisation`, `source`, `buyer_family_member` and of the versions of 6,700 notices (the open ones
and those published since 3 October) into a scratch database `w52_scratch` in `dgate-ci-db` (358,000 notices, 800 MB). The scratch copy
reproduces the audit's failures with the old code (q=Bundeswehr 6.2 s, Closed page 4 12.4 s). The server was loaded the whole time
(load average 8 to 13 on 4 cores: the production web, other builders' suites, my own suite), so every figure is pessimistic.
"SQL" is `EXPLAIN (ANALYZE)` execution time of the one query; "endpoint" is the Python function with the page built (twins, buyer
names, versions), the whole of what a request does but the HTTP layer.

| Request | Before (old code, same data) | After |
|---|---|---|
| `/v1/tenders?q=Bundeswehr` (open) | SQL 6.2 s (production `EXPLAIN ANALYZE` 6.7 s, 11,825 buffers read); the API: 503 at 5 s | SQL 0.70 s, endpoint 0.74 s |
| `q=Bundeswehr&country=DE` | SQL 8.0 s; 503 | SQL 0.18 s, endpoint 0.56 s |
| `q=defense` | SQL 3.6 s; 503 | SQL 0.28 s, endpoint 0.28 s |
| `q=Wojskowy&country=PL` | 503 | SQL 0.88 s, endpoint 1.7 s (202 hits) |
| `q=Bundeswehr&from=2026-10-20&to=2026-10-31` | 503 | SQL 0.20 s, endpoint 0.34 s |
| open list, page 1 | SQL 1.6 s | SQL 0.15 s, endpoint 0.44 s (cold 1.2 s) |
| Closed, page 1 | SQL 10.1 s (snapshot hid it) | SQL 42 ms, endpoint 0.45 s |
| Closed, page 4 | SQL 12.4 s; 503 | SQL 75 ms, endpoint 0.28 s |
| Closed, page 57 / page 1000 (offset 9,990) | 503 | endpoint 0.50 s / 1.2 s |
| All, page 6 / page 200 | SQL 12.2 s; 503 | endpoint 0.98 s / 0.56 s |
| Closed + `q=Bundeswehr`, page 1 | not measured | SQL 77 ms; the total is "at least" (see T3), endpoint 1.4 s |
| `/v1/tenders/scope-counts` open / closed | one count per scope, no cap | 0.9 s / 2.2 s (closed is capped) |
| `/v1/tenders/slugs` | production, read-only: 6.6 s (503) | endpoint 1.0 s; from the snapshot a stored answer |
| `/v1/tenders/calendar` (1,449 notices) | did not exist | 1.9 s |
| the buyer aggregate, exact (the worker) | 1.2 to 2 s per request, twins counted twice | 7.7 s in the worker every 4 hours; `/v1/buyers/{slug}` then 0.1 s |
| digest of week 42 built | 30 rows listed, 13 of them one title | 0.8 s; 30 rows standing for 49 notices |

## T2: search is 503 for common words

*Cause.* `status=open` was the expression `EFFECTIVE_STATUS_SQL = 'open'`. The planner could not use it, so it fetched every notice the
search matched, then dropped the closed ones: `Bundeswehr` is in the buyer name of 19,134 notices (a bitmap heap scan of 4,029 blocks per
worker, 11,825 buffers read, 6,387 rows removed by the filter per worker, 246 kept), and the collapse rules re-tested the same
search on the twin sets. Narrowing by country or date did not help because the cost was in the candidates, not in the result.

*Change.* The open filter now carries the redundant conditions `o.status = 'open' AND (o.deadline_at >= now() OR o.deadline_at IS NULL)`
(`tenders.status_conditions`), and a partial index `opp_open_candidates` (2,600 of 357,000 rows) lets the planner start from the open
set (BitmapAnd with the trigram index). The page is read with no window count. The open list is ordered by an expression
(`ORDER_OPEN_DEADLINE`) that no index serves: with the plain `deadline_at ASC` the planner walked `opp_list_deadline_asc` from the oldest
deadline through 350,000 closed notices (2 to 7 s against 0.4 s). Tests: `test_a_search_word_finds_the_open_notices_with_the_status_and_country_filters`,
`test_the_open_list_is_ordered_so_that_no_index_can_walk_the_closed_notices`, `test_the_open_filter_carries_the_conditions_the_planner_can_use`.

## T3: Closed and All cannot be paged past page 3

*Cause.* Pages 1 to 3 came from the worker's snapshot; a live page was `count(*) OVER ()` over 287,634 notices, collapsed and sorted: 12.4 s.

*Change.* (1) The page is `LIMIT/OFFSET` in the order of an index (migration 0091: `opp_list_deadline_asc`, `opp_list_deadline_desc`,
`opp_list_published`, each `WHERE is_defence AND NOT suppressed`, 11, 14 and 11 MB), so a page costs the rows up to it. (2) `MAX_OFFSET = 10,000`:
a page past it has no items and says `maxOffset` (the pattern of `/v1/suppliers`). (3) The total is counted in two steps, each in a 1.2 s
time box (`SELECT set_config('statement_timeout')` inside a savepoint): up to 200, then up to `TOTAL_CAP = 10,000`. `totalCapped: true` means
"at least"; a count that does not finish leaves a lower bound (what was read, plus one more page when the page is full), never an error.
A short last page is exact. (4) The worker stores the exact total in its snapshots (`tenders.EXACT_TOTALS`), and a deeper page of the same
filters repeats it, so Closed says 287,634 on page 1 and on page 400. (5) `status=all` with no sort is the open notices (soonest first)
and then the rest, as two reads, which is the old order. Tests: `test_a_page_past_the_depth_limit_has_no_items_and_says_so`,
`test_a_long_list_counts_up_to_a_cap_and_says_it_stopped`, `test_a_count_that_runs_out_of_time_leaves_a_lower_bound_not_an_error`,
`test_the_count_gives_up_after_its_time_box_and_the_connection_is_usable`, `test_a_deep_page_repeats_the_exact_total_the_worker_stored`,
`test_the_worker_keeps_exact_totals_whatever_the_cap`, `test_all_is_the_open_notices_and_then_the_rest_and_a_page_can_hold_both`.

*Limit that remains.* A search word that matches a fifth of the archive on the Closed or All list (`q=Bundeswehr&status=closed`) shows its
first page in 77 ms but cannot be counted: the match itself, `dg_fold(...) LIKE`, is 0.7 ms a row (13 s for the 19,000 rows, measured with
no collapse at all). The total is then "at least" and `scope-counts` for that view answers 503 (the site shows the labels without numbers).
Pre-folding the three columns into stored columns would remove it; that is an 80 MB table rewrite and was not done.

## T8: "Planned" notices in Closed

*Cause.* `closed` was `effective status <> 'open'`, and a `forthcoming` notice (prior information notice) is not `open`. 6,280 defence
notices are stored `forthcoming`: 6 with a deadline ahead, 31 past, 6,243 with none.

*Change.* A `forthcoming` notice is `planned` until its deadline passes (then `expired`, like any other). `closed` excludes `planned`;
`status=planned` is new; `all` has both; `statusNative` stays `forthcoming` and `status` stays `open | closed`. The first page of Closed on
production data, before: awarded 31 Jul 2027, cancelled 28 Oct, then six Planned notices with a 27 Oct countdown, two that expired today.
After: no Planned notice; the first two rows are still the awarded and the cancelled notice that state a deadline ahead, which are closed
by their own status (left, below). Tests: `test_a_planned_notice_is_neither_open_nor_closed_until_its_deadline_passes`,
`test_the_counts_of_the_statuses_add_up_to_all`, unit `test_a_planned_notice_is_planned_until_its_deadline_passes`.

## T9: the calendar

*Cause.* There is no calendar endpoint: `web/lib/calendar.ts` reads five pages of 100 of `/v1/tenders?status=open&sort=deadline-asc`, the 500
earliest of 1,529; the 500th ends on 28 October.

*Change.* `GET /v1/tenders/calendar?country=&scope=&from=&to=&maxItems=`: every open notice that states a deadline, in one answer, with the
fields a calendar draws and the same deadline the notice page shows (a national deadline 90 days or more from its TED twin's is the twin's).
Measured: November 2026 holds **593** notices (the audit's figure; the list gives 593 for the same range), the whole calendar 1,449, last
deadline 13 June 2040. Tests: `test_the_calendar_holds_every_open_notice_and_not_the_first_five_hundred`,
`test_the_calendar_shows_the_deadline_the_notices_page_shows`. **The site must read it**: see Left.

## T10: changes.atom, the digest

*Cause.* (a) The Atom route asks `/v1/changes` for one page of 100 and says "the last 14 days" (2,311 changes): a web constant
(`FEED_ENTRIES`) and the subtitle. (b) The 13 rows of the digest are 13 different notices (BZP numbers 00483163 to 00483322, "Dzierżawa
stacji transformatorowej 1000 kVA ... postępowanie nr 14/U", one buyer, one day), not one notice repeated. (c) "The tender list has the rest"
leads to a list that has no week filter.

*Change.* (b) `weekly_digest.distinct_events`: notices of one source and buyer with the same title, publication date, kind and changes are
listed once with `repeats` (13); the counts still count every notice (873 new in week 42; 30 rows now stand for 49 notices). (c) `GET
/v1/changes?week=2026-W42&kind=new|amended` lists the events of a digest week (404 outside the archive or for a week not ended): 952 events
for week 42, the issue's 873 + 79. (a) not done here: web.
Tests: `test_the_digest_lists_identical_notices_once_and_counts_them_all`, `test_changes_can_be_asked_for_a_week_and_a_kind`.

## T11: "Last change seen at the source"

*Cause.* `source.retrievedAt` is the newest real version's observation time; a notice with one version has no change, so it is the time we
first collected it (65 % of pages). The label is the site's.

*Change.* `source.lastChangeKind`: `amendment` or `first_seen`. `retrievedAt` is unchanged (the CSV column and the Atom feed read it).
Test: `test_the_source_stamp_says_whether_it_is_a_change_or_our_first_sight`.

## T12: version history against status and published date (notice 235)

*Cause.* Five versions: open (published 31 Aug), the feed stamp moved the date (11 Sep), awarded (29 Sep), then two `remapped` versions, the
second reading the same payload as cancelled and the publication date as 31 Aug. A remapped version is not an amendment and was skipped, but
the lines the earlier entry had drawn from the old reading ("Status: Open to Awarded", "Published: 11 Sep to 29 Sep") were left standing,
so the history ended in a state the notice no longer has.

*Change.* `tenders._fold_remap`: a remapped version corrects the `after` of the latest line of that field, removes a line that now says
nothing, and removes an entry left with no line or only the publication date. Notice 235 on production data now reads: version 1; version 2
(30 Sep): Published 11 Sep to 31 Aug, Status Open to Cancelled; the headline is cancelled, 31 Aug. Tests (unit): `test_the_history_ends_where_the_notice_does`,
`test_a_remap_that_restores_the_old_value_removes_the_line_and_the_entry`, `test_a_remap_of_a_field_no_line_shows_changes_nothing`,
`test_a_real_amendment_after_a_remap_is_measured_from_the_corrected_reading`.
The notice 144917 date flip (28 Sep, 5 Oct, 7 Oct, 28 Sep) is the source's, four real versions, and is shown as it was.

## T13: counts against the list

*Cause.* (a) `scope-counts` was kept in the worker's snapshot for 8 hours for the open view, the list for 5 minutes in memory: the counts
trailed the list by every notice that expired in between (1,541 against 1,529; Germany 248 against 239). (b) 299 + 1,288 is not 1,541
because the union shows the national copy of a core notice once and the two lists each count their own.

*Change.* The open views are no longer kept in the worker's snapshot (`_kept_in_snapshot`; `warm_lists` stops writing them); the counts and
the list use one predicate (`_count`); both say `asOf`; `scope-counts` has `overlap` (core + supply - relevant) and `capped`. Measured on the
scratch copy for six filter sets (none, DE, DE+PL, cpv 35, q=radar, closed): counts equal the totals of the lists they lead to in all six;
open: relevant 1,522 = core 294 + supply 1,274 - overlap 46; Germany 239. Tests: `test_the_counts_beside_the_list_are_the_totals_of_the_lists_they_lead_to`,
`test_a_list_says_when_it_was_worked_out`, `test_the_open_counts_are_read_live_and_the_closed_ones_from_the_snapshot`.

## T14: buyers

*Cause.* (a) The tender card links `buyerSlug` for every organisation; `/v1/buyers/{slug}` exists for families with a core notice. (b) `tenderCount`
counted every core notice (a TED notice and its national copy twice); the list collapses them.

*Change.* (a) `buyerSlug` is null for a buyer with no page (`buyers_with_page`: a core notice settles its own buyer, the others are asked in one
query). Open list on the scratch copy: 1,522 tenders, 387 buyers, **72 buyers (118 tenders) without a page** (the audit: 73 and 119, a notice
expired since); the answer agrees with the aggregate for every buyer. (b) The worker stores the exact aggregate (`aggregate_sql(exact=True)`, key
`buyer-base`); `tenderCount` is then the count of `/v1/tenders?buyer=&status=all&scope=core`, `openCount` of `status=open`, read live. The 12 largest buyers:
BAAINBw 5,366 to **3,329**, HIL 2,990 to 2,174, Ministerstvo obrany 2,908 to 2,450, MINARM/DGA 2,212 to 1,849, Jefatura (Mando de Apoyo) 1,844 to 1,659,
3 Regionalna Baza 1,402 to 1,185, MINDEF Air SIAE 1,341 to 1,157, Ministerie van Defensie 1,091 to 913, Dir. Gestión Económica 986 to 810, 2 Regionalna Baza
799 to 578, Inspektorat Uzbrojenia 772 to 662, Ministrstvo za obrambo 763 to 639: equal to the list in all 12 (and `openCount` too). Until `warm_lists`
has run the API serves the plain count, as before. 15 buyers of the open list were checked one by one (link yes/no against whether the page exists): 15 of 15 agree
(examples: Rejonowy Zarząd Infrastruktury Olsztyn, supply only, no link; Ministère de la Défense, core, link; Bundeswehr-Dienstleistungszentrum Doberlug-Kirchhain,
supply only but its family has a core notice, link). Tests: `test_a_buyer_that_has_only_supply_notices_has_no_link_and_one_with_a_core_notice_has`,
`test_tenders_in_archive_equals_the_buyers_own_list`, `test_open_now_is_read_live_whatever_the_stored_totals_say`.

## T15: the sitemap has no tender and no buyer

*Cause.* `/v1/tenders/slugs` is 6.6 s on production (read-only run of the old query: the max observed version of 5,000 notices); `app/sitemap.ts`
swallows the error. `/v1/buyers/slugs` ran the 2 s aggregate per request.

*Change.* Both are `cache_list` endpoints with a snapshot key (`tender-slugs?`, `buyer-slugs?`); the tender query reads the version table only in the worker's
run (3,644 of the 5,000 notices have several versions; the API's own answer dates a notice by its publication date). `app/sitemap.ts` needs no change: it already reads the
two endpoints. Tests: `test_the_slugs_come_from_the_snapshot_when_there_is_one`, `test_the_slugs_of_the_buyers_are_the_ones_with_an_open_notice_and_a_page`.

## T16 / T18: sources

*T16.* `/v1/sources` adds `updateFreq` (from `source.update_freq`), `staleAfterHours` (daily 72, monthly 960, one-off and on-demand none), `stale`.
CORDIS ran on 17 October 19:10: `stale` stays false until 27 November. `/v1/health` already leaves the monthly sources out (they are not in `floors`).
*T18.* A `partial` run with its minimum met (PLACSP 19,648 against 400: "live feed stale"; EDF: "1 factsheets could not be read") now carries
`statusReason` (a fixed sentence, never the run's own error text) and `statusReasonKind`. Migration 0091 gives 7 source names and 8 attribution lines their accents
(Plataforma de Contratación del Sector Público, Biuletyn Zamówień Publicznych, Atlas Przetargów, Bulletin ... marchés publics, Narodowe Centrum Badań i Rozwoju,
Agence de l'innovation de défense, Datenservice Öffentlicher Einkauf); the codes are untouched. Tests: `test_a_source_is_late_by_its_own_rhythm_and_a_partial_run_says_why`,
`test_the_sources_carry_the_names_their_operators_give_them`, `test_the_reason_never_repeats_the_error_text`.

## T17: a Pyrotechnics tender with a furniture CPV label

*Cause (not a backend fault).* The code is 39225500 and it is the notice's own: TED's English title prefix "Pyrotechnics" is the label of that code (20 of the
notices with that code are alone on it). `web/lib/cpv.ts` `cpvName` falls back to `cpvLabel`, which returns the name of the **division** (39, "Furniture, furnishings,
domestic appliances and cleaning products") when the 8-digit code is not in the 366-code selection of `lib/data/cpv.json` (39225500 is not), and the home card prints it as the code's label.
The fix is in the web: print the division name only as "Division 39: ...", or add the code to the selection. Nothing changed here.

## Existing tests changed (the contract grew; no assertion was removed or loosened)

- `test_tenders_api.py::test_scope_counts_are_the_totals_the_choices_lead_to`: it compared the whole body with `{relevant, core, supply}`; it now compares those three
  numbers and also asserts `capped` is false and `asOf` is present.
- `test_aid_pipeline.py`, `test_ncbr_pipeline.py`: the expected attribution prefix has its accents ("Source : Agence de l'innovation de défense", "Źródło: Narodowe Centrum Badań i Rozwoju").
- `test_warm_lists.py` was not changed: list bodies are stored wrapped (`{"__list__": [...]}`) so that every row of `list_snapshot` is an object, which its `jsonb_set(body, '{total}', ...)` needs.

## Hostile review of my own diff

I read every changed file again after the first full run (8 failures, all mine) and again after the second. **14 issues found, 14 fixed:**

1. The first design counted the Closed list with the list's own SQL; with a search word that is 25 s (hash joins that re-test the search on three twin sets). Fixed: two-step, time-boxed count.
2. A page past the end with a capped count claimed `total >= start`; fixed (`if capped and rows`), test `test_a_deep_page_repeats_the_exact_total_the_worker_stored`.
3. The open list ordered by `deadline_at ASC` was walked through the closed notices by the planner (2 to 7 s); found by timing, fixed (`ORDER_OPEN_DEADLINE`), and the same in the calendar query, found by re-reading.
4. `scope-counts` and `meta` were extended and two existing tests compared whole bodies; `asOf` of the list went to the top level (so `meta == {"updatedAt": None}` holds), the scope-count test was extended, not loosened.
5. `conn.rollback()` after a failed snapshot read discards the caller's transaction: it dropped the follow just written in `test_every_account_flow_works_as_the_least_privileged_role` (the account role may not read `list_snapshot`). Both new snapshot reads and the count time box use savepoints now.
6. List bodies in `list_snapshot` broke `jsonb_set(body, '{total}', ...)` of `test_warm_lists`: they are stored wrapped (`{"__list__": [...]}`).
7. `warm_lists` counted the buyer aggregate twice (`written` 21 against `views` 20); it is a view like the others, and runs before the slugs that read it.
8. The exact buyer aggregate is 8 to 30 s: it cannot be computed in the API's 5 s, so the API serves the plain count until the worker has stored the exact one (the old behaviour, not an error).
9. `/v1/tenders/slugs` read the version table for 3,644 of 5,000 notices (5.6 s on production, the same as before): the worker reads it, the API dates a slug by publication.
10. An open view in the worker's snapshot made the counts trail the list by up to 8 hours: the snapshot is now skipped for `status=open` (a predicate on the request), so old open rows are ignored at once, before `warm_lists` deletes them.
11. `buyers_with_page` counts a buyer family, not the organisation of the notice (`dgate_family_ids`), as `/v1/buyers/{slug}` does; 387 of 387 agree with the aggregate.
12. The digest merge compares source, buyer, title, publication date, kind and the change lines, so two amendments that changed different things are not merged; counts are not changed.
13. `/v1/sources` never returns the run's `error_message` (it can hold an exception text with a host or a key): fixed sentences chosen by kind, test `test_the_reason_never_repeats_the_error_text`.
14. `/v1/changes?week=` validates the ISO week (404, not a 500, for `2026-W99` or a week not ended) and `kind` by pattern (422).

## Production commands (after the deploy; the orchestrator runs them)

1. Deploy `migrate api worker`. Migration 0091 builds 4 indexes (about 38 MB; `CREATE INDEX` holds a write lock on `opportunity` for roughly 3 to 8 s) and updates `source` names.
2. `docker compose ... run --rm --no-deps worker python -m dgate.ops.warm_lists --yes` (also runs in the worker every 4 hours). Writes the exact closed and all views, the sitemap slugs and
   the buyer aggregate (the aggregate alone is 8 to 30 s); deletes the old open scope-count rows. Until it has run: the API answers from the live queries (all inside the budget), buyer counts
   are the plain ones, the slugs are dated by publication.
3. `python -m dgate.ops.build_digest --yes --week 2026-W37` ... `--week 2026-W42` (six weeks, 1 s each): the stored issues are rebuilt with `repeats`.
4. Re-time: `/v1/tenders?q=Bundeswehr`, `?q=defense`, `?q=Wojskowy&country=PL`, `?status=closed&page=4`, `?status=all&page=6&pageSize=10`, `/v1/tenders/calendar?from=2026-11-01&to=2026-11-30` (expect about 593),
   `/v1/tenders/slugs` (5,000), `/v1/buyers/slugs` (about 128), `/v1/buyers/196-...` (`tenderCount` 3,329), `/v1/changes?week=2026-W42`, `/v1/sources`.

## Left

- **Web (not touched; the API fields are in place):** `lib/calendar.ts` should read `/v1/tenders/calendar` (or raise `TENDER_PAGES` to 8 pages of 250) (T9); `changes.atom` `FEED_ENTRIES` and the subtitle,
  and the digest footer link to `/changes?week=...&kind=...` (needs `week`/`kind` on the page) (T10); the list heading and pager for `totalCapped` and `maxOffset`, and the scope labels with `overlap` and
  `asOf` (T3, T13); `source.lastChangeKind` for the label (T11); `/data` reading `stale`, `staleAfterHours` and `statusReason` instead of `STALE_AFTER_DAYS` (T16, T18); the CPV chip fallback (T17); the buyer page
  lists open tenders of scope relevant next to an "Open now" of scope core (D-05, the audit's second half) (T14).
- The first page of Closed still starts with the awarded and the cancelled notice that state a deadline ahead (2 rows): they are closed by status, and an order that puts them last cannot use an index.
- A search word on the Closed or All list cannot be counted (T3, above).
- `/v1/changes` page size stays at 200 (the feed's 100 entries are the web's choice).

## Scratch removed

The scratch database `w52_scratch`, `/root/w52_scratch`, the logs `/root/w52_*.log` and the pytest temp directories are removed. Kept for a re-run, to delete when no longer needed: `/root/dev-w52`,
the database `agent_wp52` in `dgate-ci-db`, `/root/run_w52.sh`.
