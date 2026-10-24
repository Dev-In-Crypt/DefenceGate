# WP-101 self-check: search (round 3, persona round of 24 October 2026)

Branch `wp-wp101` (from `integration` 24e5295). Package: `search.py`, `search_terms.py`, the q-handling of `tenders.py`, the
web search page and the tenders list error state, the CPV picker and supplier product words. Findings: `D:\DEFENCEGATE TESTS\ux-oct24\SUMMARY.md`
(WP-101) and the persona folders p01, p03, p04, p05, p06, p07, p10.

## Root cause of the 503s (production, read-only, 24 October 2026, 12:40-13:30 UTC, load 0.2-0.6)

Measured inside `dgate-api-1` with the API role (`statement_timeout` 5 s, every transaction `READ ONLY`), the list function
called as the API calls it, each statement timed; the slowest one explained with `EXPLAIN (ANALYZE, BUFFERS)` (25 s limit).

| request (production, before) | time | answer |
|---|---|---|
| `/v1/tenders?q=Drehteile Frästeile` | 7.0 s | **QueryCanceled (503)**: the page query 5.0 s (cancelled), its count 1.2 s (gave up) |
| same, `EXPLAIN ANALYZE` of the page query without the limit | **12.6 s** (20.4 s on a second run) | 14 rows |
| `/v1/tenders?q=fuel&status=all` | 3.6 s | "at least 21" (the count ran out of time: a floor, not the count) |
| `/v1/tenders?q=brandstof&status=all` | 4.6 s | "at least 21" |
| `/v1/tenders?q=cyber&status=all` | 8.1 s (page query 4.7 s, a hair under the 5 s limit) | "at least 203" |
| `/v1/tenders?q=warehousing&status=all` | 2.0 s | 164 |
| `/v1/tenders?q=220199-2026` (Open) | 0.3 s | 0: the notice is awarded |
| `/v1/search?q=Regionalna Baza Logistyczna` | 4.5 s | **every part "slow"**: the tender part used 4.5 s of the 4.5 s budget |
| `/v1/search?q=Ersatzteile` | 4.6 s | tenders "at least 6" (list: 11), funding, buyers, suppliers, organisations "slow" |
| `/v1/search?q=Ministère de la Défense` | 5.5 s | tenders "at least 6", the other four "slow" |
| `/v1/search?q=Ministerie van Defensie` | 4.2 s | tenders "at least 6", funding and buyers "slow" |
| the other parts alone (buyers, suppliers, funding, organisations for those words) | 0.02-1.6 s each | fine: they were starved by the tender part |

The plan of the Drehteile Frästeile page query (timings of every case: `D:\DEFENCEGATE TESTS\wp101\perf\prod-before.txt`):
a `Parallel Bitmap Heap Scan` over the trigram indexes found ~20,000 candidates in 0.8 s, then spent 4.7-20 s re-checking them
(`Rows Removed by Index Recheck: 2617`, `by Filter: 1805` per worker): every candidate is re-checked against the whole condition,
and each of its ~50 terms (two words, each a slot of the 17-term spare-parts group, over two titles and the buyer name, in the
index re-check and again in the filter) computed `dg_fold(title)` again. Measured on production over 5,000 notices:
one `dg_fold` costs 0.08-0.13 ms (the `translate` of 90 accented letters), the old re-check of one slot over one title 0.40 ms a row,
the same slot over the already folded text 0.02 ms a row (20 times less); `dgate_cpv_heads` 0.04 ms a row against 0.001 ms for
stored heads. So the cost was the fold per term, not the number of matches, and it grew with every word and synonym.

## Items

### 1. Multi-word q 503 (Drehteile Frästeile, always), q + status=all 503 (warehousing, brandstof, fuel, Schwingarm, cyber)

- Before: above (12.6 s, 503 every time; status=all 3.6-8.1 s with counts that gave up).
- Change: migration `0113_tender_search_text.sql`: `opportunity_search`, one row per notice with `dg_fold` of both titles and of the
  buyer name (NULL while the buyer is withheld), `dgate_cpv_heads` of the codes and the notice number, written by an AFTER INSERT /
  AFTER UPDATE trigger on `opportunity` (only when one of those columns changes), backfilled by the migration, trigram and GIN indexes.
  `tenders._tender_filters` writes the search as `EXISTS (SELECT 1 FROM opportunity_search ts WHERE ts.id = o.id AND ...)`: the same
  LIKE / regular expression / code-overlap conditions as before, over the stored text, so a re-check folds nothing. Correlated on
  `o.id`, so the collapse rules (`collapse_clauses` rewrites `o.` for the twin) read the twin's own row.
  `search_terms.expand`: a run of terms of one group is one slot ("Drehteile Frästeile" = any term of the spare-parts group, or both
  words): (G or D) and (G or F) is G or (D and F), the same notices at half the work. The typed words are never listed as "also
  searched". `MAX_ALTERNATIVES` 24 -> 40 (the groups grew, item 4). The web demo's `lib/search-terms.ts` reads the same way.
- Same rows: the old and the new WHERE run side by side over the synthetic archive (`perf\compare.py`, old code from `integration`):
  Ersatzteile, Drehteile Frästeile, fardamento, drone, Bundeswehr, spare parts: identical sets except one more notice for the
  spare-parts words, which the new term CNC finds through its CPV code 42621100 "CNC lathe" (item 4). Nothing the old search found is lost.
- Tests: `tests/unit/test_wp101.py` (one slot, the SQL reads `opportunity_search` and never `dg_fold(`/`dgate_cpv_heads(`, the
  collapse rule follows the twin), `tests/integration/test_wp101.py` (the trigger keeps the folded texts through insert, amendment and
  withholding, every notice has its row; two words of one group find what either finds, in Open and All).
  `tests/unit/test_wp98.py::test_the_search_sql_of_a_group_is_a_few_regular_expressions_over_the_titles`: the two column names in its
  assertions follow the new table (`ts.title_en`, `ts.buyer_name`); what it asserts (a product term never reads the buyer, the typed
  word does, every placeholder has its value) is unchanged.
- After: production cannot be timed before the deploy (no writes there). On the production-sized synthetic archive (357,000 notices,
  `D:\DEFENCEGATE TESTS\wp101\perf\gen.py`, laptop, cold list caches, 5 s statement timeout; `before.json` with the `integration`
  code, `after2.json` with this branch, second run of each):

  | request (synthetic, 357,000 notices) | before | after |
  |---|---|---|
  | `/v1/tenders?q=Drehteile Frästeile` | 2.34 s | 0.61 s |
  | `... &status=all` | 6.38 s, "at least 541" | 1.86 s, 10,342 or more (the rest counted to the cap) |
  | `/v1/tenders?q=fuel&status=all` | 3.72 s, "at least 149" | 0.88 s, 10,149 or more |
  | `/v1/tenders?q=brandstof&status=all` | 4.61 s, "at least 349" | 0.88 s, 10,149 or more |
  | `/v1/tenders?q=Ersatzteile&status=all` | 6.20 s, "at least 341" | 2.00 s, 10,342 or more |
  | `/v1/tenders?q=fardamento&status=all` | 4.89 s | 1.09 s |
  | `/v1/tenders?q=drone&status=all` | 2.42 s | 0.52 s |
  | `/v1/tenders?q=Bundeswehr&status=all` | 1.59 s, "at least 264" | 0.33 s, 4,961 exact |
  | `/v1/tenders/scope-counts?q=fuel&status=all` | **503** (1.25 s) | 200, 1.31 s |
  | `/v1/search?q=Ersatzteile` | 4.55 s, suppliers and organisations "slow" | 2.09 s, every part answered |
  | `/v1/search?q=uniforms` | 4.53 s, two parts "slow" | 3.11 s, every part answered |
  | `/v1/search?q=Drehteile Frästeile` | 4.23 s, two parts "slow" | 2.09 s, every part answered |

  The laptop is about three times the 2-core server, and the synthetic titles are shorter (the folds cost less there), so the
  production gain is larger than these ratios: on production the fold per term was the whole cost (12.6 s for 14 rows), and the
  re-check over stored text costs a twentieth of it (measured above). To be confirmed on production after the deploy with the probe
  `perf\probe.py` (read-only), the same cases as the "before" table.
- Counts: bounded and honest as before (`SMALL_CAP` 200 / `TOTAL_CAP` 10,000 in their time boxes; "at least" only when a count stopped,
  never below what was read). The floors the old counts gave because they ran out of time ("at least 149" for 10,149) are now
  the real counts or the 10,000 cap.

### 2. Header search timeouts (Regionalna Baza Logistyczna, PGZ, Ministerie van Defensie, Ministère de la Défense, Ersatzteile, uniforms)

- Before: the parts run one after the other in one 4.5 s budget, and the tender part (the folds of item 1, three words of a buyer name
  over every title and buyer name) used it up: on production every other part said "slow". Alone, the other parts took 0.02-1.6 s.
- Change: item 1 (the tender part reads stored text). `search.opens_on` (item 5). No change to the budget.
- Test: `tests/integration/test_wp101.py::test_the_global_search_counts_the_tenders_as_the_list`.
- After: synthetic table above: every part answers. PGZ already answered on production (1.8 s).

### 3. A 503 shown as "No tenders match"; it must be an error with retry

- Before: p05's own capture of the 503 (`p05-fr-cyber\t_cyber_eu_1440.txt`, HTTP 503) shows "We could not load tenders"; the "No tenders
  match" capture (`t_cyber_fr_1440.txt`) is an HTTP 200 for `q=cyber&country=FR` with no open French notice, a true empty list. What
  was wrong: "Try again" called `reset()` only, which re-renders the error the server sent; it never read the list again.
- Change: `web/app/(public)/tenders/(list)/error.tsx`: Try again is `router.refresh()` and `reset()` in a transition (the button is
  away while it runs). The demo data fail for one search (`lib/mock/tenders.ts DEMO_UNAVAILABLE`) so the state can be tested; with
  the API the site never reads that file. Fewer 503s: item 1.
- Test: `web/e2e/wp101.spec.ts` (the error heading, no "No tenders match", the search kept, Try again reads again).

### 4. Product words in tender search, CPV picker and supplier product filter

- Before: harness, wiring, stamping, castings, Zerspanung, CNC: 0 tenders or no group; the CPV picker: "No code matches" for Drehteile,
  Frästeile, Zerspanung; cyber 203 against cybersecurity 3; `explosives` missed AU's detonating cord (CPV 24615000, PL, 690087-2026);
  `/suppliers?product=ammunition` read the finder's 3533 only and missed 35300000 (Mesko's 2026 award), `product=cyber` found no code.
- Change: `data/search-terms.json` (both copies): spare parts + Zerspanung, CNC, Präzisionsteile, mecanizado, usinage ...;
  ammunition + detonators, detonating cord, lont, zapalniki, Zünder, Sprengschnur ...; new groups wiring (31611, 31612, 35422),
  stampings, castings, cyber (4873, 4876, 7221273, 728) with their words in EN/DE/FR/ES/PL/NL/IT/PT. `web/lib/data/product-keywords.json`
  (picker and supplier filter): Drehteile, Frästeile, Zerspanung, Präzisionsteile, CNC-Teile ... under machined parts; wiring, Kabelbaum
  ... under wiring harness; German/Spanish words for stampings and castings; detonating cord under detonators; `ammo`/`ammunition`
  read as 353 and 2461 (the tender list's ammunition group); a cyber entry (48730000, 48731000, 48732000, 48760000, 72212730, 72150000,
  72800000, with a note that IT services in general are 72 and software 48). Every code and title from the CPV 2008 codelist we hold.
- Tests: unit `test_the_product_words_of_the_personas_have_a_group`, `test_cyber_typed_any_way_finds_the_same_notices`; integration
  `test_the_product_words_of_the_personas` (harness/Kabelbaum find a Spanish and a Polish wiring notice, cyber/cybersecurity a French
  and a German one, explosives the detonating cord); `web/lib/wp101.check.ts` (picker and filter); `e2e/wp101.spec.ts` (supplier filter).
  Changed because the requirement changed: `web/lib/cpv.check.ts` pinned `ammo` -> 3533 and "ammunition" -> the finder's titles; it
  now pins `ammo` and `ammunition` -> 353, 2461 (still covering 3533) and runs its title-search assertions on "ammunition for warfare";
  `e2e/ux.spec.ts` U9 expects "“ammunition” is read as ... 35300000" instead of "matches N codes of the finder ... 3533".

### 5. Notice id search across statuses (220199-2026)

- Before: production `q=220199-2026` (Open, the default) 0 rows; the notice is awarded.
- Change: `tenders.NOTICE_NUMBER` (TED `220199-2026`, `2026/S 203-724451`): the global search reads such a search in every status
  (`search.opens_on`), its "see all" opens `/tenders?q=...&status=all`, and `/tenders?q=<number>` without a status chosen opens on All
  (a redirect; a status chosen is kept). Web: `lib/search-terms.ts NOTICE_NUMBER`, `tenderListQuery`.
- Tests: unit `test_a_notice_number_is_looked_for_in_every_status`, integration `test_a_notice_number_is_found_in_every_status`,
  `wp101.check.ts`, `e2e/wp101.spec.ts`.

### 6. Buyer abbreviations (RBLog, AU, WOG, JW, NAVARM, TERRARM, ARMAEREO)

- Before: not in the map (only BAAINBw, DMO, DGA, JAE MALE, FMV).
- Change: `search-terms.json buyers`: RBLog = Regionalna Baza Logistyczna, AU = Agencja Uzbrojenia, WOG = Wojskowy Oddział Gospodarczy,
  JW = Jednostka Wojskowa, NAVARM / TERRARM / ARMAEREO = Armamenti Navali / Terrestri / Aeronautici (and the abbreviation itself, as
  production's own names carry it: "direzione degli armamenti navali - navarm"). The names were checked against production's buyer
  names (read-only).
- Tests: unit `test_the_abbreviations_of_polish_and_italian_buyers`, `wp101.check.ts`.

### 7. Counts consistent ("at least 6" vs 11 vs 28; "at least 12" then 21)

- Before: the global search's tender part and the list counted the same way but ran out of time at different points ("at least 6"
  in the search, "at least 11" in the list, 28 real).
- Change: none to the counting (it was bounded and honest); item 1 makes the counts finish inside their time boxes.
- Test: `test_the_global_search_counts_the_tenders_as_the_list` (12 = 12, exact, in both).
- After: synthetic table: the totals are exact or the 10,000 cap. A count that still stops in time says "at least" and is never
  below the rows read.

## Files outside the package's list

- `backend/migrations/0113_tender_search_text.sql` (new, the WP-101 number).
- `web/lib/mock/tenders.ts` (demo data: `DEMO_UNAVAILABLE`, for the error-state test only).
- `web/lib/data/product-keywords.json`, `web/lib/cpv.check.ts`, `web/e2e/ux.spec.ts` (item 4).

## Production (orchestrator)

- Deploy runs migration 0113: the backfill folds ~394,000 notices (estimated 2-4 minutes on the 2-core host: 0.08 ms per fold, three
  folds and the code heads per notice) and builds five indexes (~0.3-0.4 GB on disk, 6.5 GB free). The trigger takes a lock on
  `opportunity` until the migration commits: reads (the API) go on, a load that writes notices waits. Run it when no load is running.
- No ops module: the table is derived and the migration fills it; nothing on production is rewritten.
- Afterwards, the read-only probe (`perf\probe.py` through `docker exec dgate-api-1`) for the "before" cases above.

## Personal data

`opportunity_search` repeats fields `opportunity` already holds (titles, the buyer body's name, codes, the notice number), folded;
no contact field, nothing new, a withheld buyer's name not at all. `docs/DATA_PROTECTION.md` lists no new kind of data for it.
