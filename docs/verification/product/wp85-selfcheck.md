# WP-85 self-check: the supplier map counts the awards of the supplier report (22 October 2026)

Branch `wp-wp85` from `integration` (79a3be7: WP-81 and WP-83 merged). Owner decision of 22 October 2026: "выровняй карту с
отчётом" (align the map with the report). Before, the supplier map (`/v1/suppliers*`, `/suppliers`) counted core-scope notices,
by supplier country and the notice's **main** CPV code, one count per notice, with no date limit (the loader reads from 2023);
the demand answer (`/v1/readiness/demand`, `/v1/readiness/winners`) counted defence-scope notices of the last three years, by
**buyer** country and **any** CPV code of a notice, one count per procurement. So a company in "who to approach" often had no
supplier page (`slug: null`), and the numbers differed. No deploy, no push, no migration, no production read or write, no
secret, no model call.

## 1. One definition, extracted

`backend/dgate/award_set.py` (new) holds the award set, and both modules build on it; neither keeps a copy:

| Part | What it is | Was |
|---|---|---|
| `NOTICES` | `is_defence AND NOT suppressed AND COALESCE(published_at, notice_date) >= %(since)s` | demand's `MATCH` (inline); the map had `CORE_SQL` and no date |
| `since(today)`, `YEARS` | 1,096 days back from today (UTC), rolling | demand's `_answer`; the map's `SINCE = "2023-01-01"` (a label only) |
| `WINNERS` | legal entities: not suppressed, not `individual_reason`, not `excluded_reason`, not superseded | demand's `AWARD_OK`, the map's `SCOPE` (same text twice) |
| `scope()` | `NOTICES AND WINNERS`, then `NOT_PLACSP` (switch off) or `NOT_TWIN` (switch on) | the map's `scope()`; demand's `(%(placsp)s OR NOT m.placsp)` and its own twin self-join |
| `NOT_TWIN` | a row is out when `award_twin_set` names a preferred row that is itself in the set | the map's (over its core scope); demand's (over the answer) |
| `KEY`, `KEY_HASH` | one procurement however many notices publish it | demand's `KEY`; the map counted `opportunity_id` |
| `CPV_MATCH`, `prefix` | any code of the notice under a prefix, an 8-digit code standing for its level (`opp_cpv_heads`, 0099) | demand's; the map used `a.cpv_main LIKE 'p%'` |
| `FROM` | award, notice, organisation (merged), and `t` (the TED notice a national notice names, for `KEY`) | the map's `FROM` without `t` |

`suppliers.py` imports them; `demand.py` imports them (its `MATCH` = `NOTICES` + countries + `CPV_MATCH`; its `aw` CTE is the
answer's notices joined to their award rows under `award_set.scope()`; `QUERY` became `query()`, built per call because the
condition reads the PLACSP switch). `demand._with_page` is gone: every winner has a page. Unit test
`tests/unit/test_wp85_award_set.py` asserts the shared objects and that no copy (`SCOPE`, `NOT_TWIN`, `SINCE`, `AWARD_OK`,
`PLACSP_IDS`) is left in either module.

## 2. The decisions taken

| Question | Decision | Why |
|---|---|---|
| Period | **the last three years, rolling** (1,096 days to today), the demand answer's rule | preferred by the task; "since 2023" would have changed the report's numbers, and the map's "from 2023" was in fact no filter at all |
| Scope | the whole **defence scope** (`is_defence`), not only the core | the demand answer's; a defence body's commodity purchase is demand |
| Count unit | **procurements** (`KEY`): two TED result notices of one procedure are one contract | the demand answer counts so; with notices the counts could never match |
| CPV | any code of the notice; an 8-digit code is its level (34300000 = 343); a value that is not 2 to 8 digits answers 422 | the demand answer's rule. Before, any string was a `LIKE` prefix |
| Countries | `country` stays the supplier's; new `buyerCountry` is the buyer's (the notice's), same forms (code, alpha-3, English name) and the same 422 | the demand answer's countries are the buyer's |
| Which twin stands | decided over the **whole** award set, never by a filter (the map's WP-61 rule); filters narrow the set afterwards | the only way every filter, the profile and the demand answer agree. Consequence, an edge case: a TED+PLACSP pair whose two publications carry different CPV codes is matched by the codes of the one that stands (the numbered row, then TED). Before, the demand answer kept the PLACSP row when the TED row did not match. Test `test_a_twin_pair_is_matched_by_the_codes_of_the_publication_that_stands_for_it` |
| Summary groups | a win is in **every** CPV division its notice has a code in (the divisions add up to more than the total); `awards` = (supplier, procurement) pairs | so `/suppliers?cpv=35` lists what the "35" row counts |
| Profile years and divisions | a procurement in the year and **main** division of its newest notice, so each table adds up to the count | the profile's tables add up as before |

The TED award loader still reads TED result notices of the core scope only (`awards.candidates`, unchanged): TED winners of
non-core defence notices are in neither the map nor the report. Widening the loader is a separate decision (open, section 7).

## 3. Alignment and where it is proved

| Claim | Evidence |
|---|---|
| Every winner named in "who to approach" has a supplier page; the winners page links the same pages | `test_wp80_approach.py::test_every_named_winner_has_a_supplier_page_with_the_same_count_for_the_same_filters` (switch on and off): every `slug` set and 200, Rheinmetall (no core-scope notice, `slug: null` before) linked |
| The map with the answer's codes and buyer countries gives each winner the answer's `contracts`; per country the `topWinners` counts | same test: `/v1/suppliers?cpv=34300000&buyerCountry=ES,DE` = `{slug: contracts}` of `approach`; per country `buyerCountry=ES` / `DE` = `topWinners[].awards`; `/v1/readiness/winners` slugs = the list's |
| A profile counts every contract of the set (outside these codes too) | same test: Mera's profile = its contracts + its 35000000 notice |
| At scale, on synthetic data near production size | `perf.py`: 300 winners of `/v1/readiness/winners` (3 pages) against the map's first 500 under the same filters: **0 mismatches**, none without a slug, total winners 3,484 = map total 3,484 |
| Defence scope outside the core is on the map; a civil notice is not | `test_supplier_map.py::test_a_defence_scope_notice_outside_the_core_scope_is_on_the_map_and_a_civil_one_is_not` (rewrites `test_a_notice_outside_the_core_scope_is_not_on_the_map`) |
| The window | `test_supplier_map.py::test_the_map_counts_the_last_three_years` (a notice a day before `since` leaves the profile; `summary.since`), unit `test_the_window_is_three_years_back_from_today` |
| Any CPV code, 8-digit codes by level, buyer country beside supplier country, 422s, summary groups by every code | `test_supplier_map.py::test_the_cpv_filter_reads_every_code_of_a_notice_and_the_buyer_country_is_its_own_filter` |
| Procurements, not notices | `test_placsp_award_twins.py::test_two_ted_result_notices_and_the_numbered_placsp_folder_are_one_award`: TED alone now 1 (was 2: two result notices of one procedure) |
| The one-pass summary says what plain separate statements say | `test_placsp_award_twins.py::test_the_summary_in_one_pass_says_what_the_five_statements_said`, its reference rewritten to the new rule (award set, pairs, every division; a row without a CPV is now a notice without codes) |
| The stored twin pairs and the view give the same map | `test_the_stored_pairs_are_the_view_...`: the monkeypatch moved to `award_set.NOT_TWIN` |

Rewritten tests (old scope encoded; none deleted or skipped): `test_a_notice_outside_the_core_scope_is_not_on_the_map`,
`test_the_supplier_page_is_linked_only_where_the_supplier_map_has_one` (now the alignment test above),
the "TED alone, as before" line of `test_two_ted_result_notices_...`, `old_summary_parts`, the `cpv_main = NULL` row of
`test_the_summary_in_one_pass_...`. e2e: labels `Country code` -> `Supplier's country` (`suppliers.spec.ts`, `wp57.spec.ts`),
`Notices per year` -> `Contracts per year`, the profile's value block counts contracts (`wp81.spec.ts`). New: `e2e/wp85.spec.ts`.

## 4. Copy

- `/suppliers`, "What this map covers" (`lib/supplier-sources.coverageText`): "... in the defence-relevant scope, published in the
  last three years. These are the same contracts the supplier report counts in “who to approach”, so a company named there has a
  page here. A contract published in several notices is counted once." The sentence "Before eForms ... so 2023 is thin" is gone
  (the window starts in late October 2023). The aggregate: wins are "a count of contracts"; "A contract is in every CPV division
  its notice has a code in, so the divisions add up to more than the total." The product help: "any CPV code starting with one of
  them" (was "whose main CPV code starts with"). Form: "Supplier's country, for example DE" and "Buyer's country, for example ES",
  with a line saying which is which. Empty state and meta description: "published in the last three years".
- Profile: "Contracts won, last three years"; intro "... of the defence-relevant scope, published in the last three years: the
  same contracts the supplier report counts in “who to approach”. A contract published in several notices is counted once." The
  sentence the task quotes ("There is no ranking, no share and no contract total") was already fixed by WP-81 ("There is no ranking
  and no share; a value appears only on a notice that names one winner, and Contract values sums those values per currency"),
  kept. Tables "Contracts per year", "Main CPV division", buyers' column "Contracts"; the value block counts contracts.
- API `coverage` strings: "published in the last three years" (was "from 2023").
- Docstrings: `award_set.py` (new), `suppliers.py`, `demand.py`; `api.py`'s router comment; `docs/design/API_CONTRACT.md` (a WP-85
  paragraph in the supplier map section; `approach.slug` always set).

## 5. Budget (5 s API)

Local only (no production access in this run), `D:\DEFENCEGATE TESTS\wp85\probe\perf.py`, throwaway database `perf` in
`dgate-wp85`: 330,000 defence-scope notices over 3.5 years (60,000 with winners: 20,000 TED, 40,000 PLACSP), 200,000 civil notices,
66,666 award rows, 11,494 winner organisations (skewed), 2-3 CPV codes a notice, procedure identifiers on a third, 6,000 twin
pairs, PLACSP switch on, list cache off. Production for comparison: about 390,000 defence-scope notices (migration 0099), about
10,000 TED award rows and 35,000-55,000 PLACSP award rows expected (WP-60/61). Five runs each, median (range):

| Call | base 79a3be7 | wp-wp85 |
|---|---|---|
| `/v1/suppliers`, no filter, page 1 | 0.119 s (8,483 suppliers) | 0.152 s (11,116) |
| page 25 (offset 480) | 0.111 s | 0.145 s |
| `q=winner company 7` | 1.595 s | 1.509 s |
| `cpv=343` | 0.092 s (main code) | 0.258 s (any code) |
| `cpv=35100000&buyerCountry=ES,DE,FR` | (no such filter) | 0.104 s |
| `/v1/suppliers/summary` | 0.133 s | 0.391 s |
| profile, largest supplier (2,596 award rows) | 0.191 s | 0.234 s |
| demand 35100000, ES DE FR (25,000 notices, near the cap) | 0.599 s | 0.550 s |
| winners page 5 | 0.379 s | 0.352 s |

The summary's first form took 1.1-1.35 s: `count(DISTINCT (org, key))` over a record sorts three times slower than over one
bigint; it now counts `pair`, a 64-bit hash of (organisation, procurement) (0.39 s; `ponytail:` comment on the collision
ceiling). The summary stays in the list cache (30 minutes), the list in it for 5 minutes; no new infrastructure, no snapshot
needed at these times. WP-80 measured production at 1.5-3x these local times on a loaded server: the slowest call here (the
name search, unchanged) stays under 5 s. **To confirm after deploy** (read-only): `/v1/suppliers/summary` and one profile with
`DGATE_LIST_CACHE_SECONDS=0`.

## 6. Test runs

Local, `D:\DEFENCEGATE TESTS\wp85`, own venv (uv, Python 3.11), throwaway Postgres 17 container `dgate-wp85` on 55485
(database `dgate` for the suites, `perf` for section 5), TZ=UTC, web mock env of `web.yml`, E2E_PORT 3085, Playwright 4 workers.

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit (`pytest`) | **3271 passed**, 1215 deselected (19.9 s) |
| integration (`pytest -m integration`) | **1215 passed**, 0 failed (8 min 56 s), final code |
| `tsc --noEmit` | exit 0 |
| `npm run check` (`scripts/run-checks.mjs`) | all ok |
| `next build` (mock) | exit 0 |
| Playwright, 4 workers, desktop + 375 px | **531 passed, 47 skipped** (the fake-API group, as in WP-80/81), 0 failed (2.0 min), incl. new `wp85.spec.ts` (3 x 2) |

The web suite ran on the final web code. The backend's last change (the summary's `pair` count, the twin-codes test) came after
the first full backend run (1214 passed); the runs in the table are the second, on the final code.

## 7. Limits and open points

- **Open decision: the TED loader reads core-scope result notices only** (`awards.candidates`). The map and the report now count
  the same awards, but TED winners of non-core defence notices (listed-buyer purchases) are in neither. Widening the loader is
  more TED API calls and more rows; not done here (scope).
- The twin edge case (section 2): a pair whose publications carry different codes is matched by the standing one's codes.
- The demo answer (`web/lib/mock/demand.json`, a production snapshot from before WP-85) still has 7 winners with `slug: null`;
  regenerate it from production after deploy (also open from WP-81).
- Ranks change on production: the map grows (defence scope, not only core) and counts procurements, so some suppliers' counts go
  down (several result notices of one procedure) and many go up. Cached pages follow on their own cache times (list 5 min,
  summary 30 min, pages 5 min).
- Budget measured locally on synthetic data; production confirmation after deploy (section 5).
