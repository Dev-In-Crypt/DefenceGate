# WP-37 self-check: supplier map from award notices (18 October 2026)

Implementer's own check, before the independent verifier. Branch `wp-wp37` (from `integration`), test database
`agent_q`, test copy `/root/dev-q`, scratch database `agent_q_scratch` (removed at the end, see the last section).
Feasibility, with every number and its method: `docs/design/SUPPLIER_MAP_FEASIBILITY.md`.

## Acceptance criteria

| Criterion (brief) | Result | Evidence |
|---|---|---|
| Feasibility numbers measured | **met** | the feasibility document: 46,007 result notices fetched, 30,632 naming a winner, **4,807 unique suppliers (4,666 European) in the core scope**, 2,427 European under the narrowest definition; go/no-go rule (2,000) passes under all of them. Also M3 (no-go), the other award sources, GLEIF |
| Go/no-go rule applied | **met, GO** | 4,807 against 2,000; per year 1,761 (2024), 2,266 (2025), 2,228 (2026 to 18 Oct); said on the page that 2023 is thin because the API states no winner as data before eForms |
| Tables for award and supplier (organisation + the WP-26 cascade, no other resolution) | **met** | migration 0078 `award`, `award_notice`; suppliers are `organisation` rows made by `dgate.resolution.resolve` (the loader adds only a guard for namesakes and attaches a registration number, both after the cascade) |
| Loader from the raw store with the pipeline rule: land, normalise, archive; idempotent | **met, with one deviation** | the winners are not in the raw store (the daily pull never asked for them: `TED_FIELDS`), so the loader asks TED by publication number, **lands** the answer (`ted_awards/` bundles, `raw_ingest` rows), **normalises** (`read_award`) and **archives** (`award`). Idempotent: unit and integration tests; on the real-data replay a second run had 0 candidates and made 0 requests |
| No natural persons: skip and count | **met as far as a rule on names can be** | `person_reason`; counted in `award_notice.skipped_person` and the summary; the person's name never reaches an organisation, an alias, an award or the raw store (tested); measured rates below. **Not a guarantee** |
| API `GET /v1/suppliers?country=&cpv=&q=` and `/v1/suppliers/{slug}` (wins by CPV and year, buyers, values) | **met** | `dgate/suppliers.py`; contract in `docs/design/API_CONTRACT.md`; 13 integration tests |
| Pages `/suppliers`, `/suppliers/[slug]` | **met, not seen in a browser** | `web/app/(public)/suppliers/`; `tsc --noEmit` clean, `npm run check` (12 checks) passes in `node:22-alpine`; the Playwright spec `web/e2e/suppliers.spec.ts` was written but **not run** (no browser on the server; CI runs it) |
| Public aggregate by CPV and country | **met** | `/v1/suppliers/summary`, shown on `/suppliers`; groups of fewer than 3 suppliers are not published (tested) |
| Supplier-level detail only if the facts are published by the buyer in the notice | **met** | see "Mosaic effect" |
| Coverage statement on the pages | **met** | both pages and the API (`coverage`): TED holds only part of European defence spending (a 2025 ECIPE brief puts it at about a tenth; **we have not re-checked that figure**, the page says so), the map is the open segment |
| 15 supplier profiles checked by hand against the notices | **met** (15 of 15) | below |
| Endpoint timings | **met** | below |
| Database growth under 500 MB | **met** | about 13 MB for the whole load |
| Production load commands and disk estimates in the report | **met** | the report |

## Tests added

- `backend/tests/unit/test_awards.py` (62 tests): the tenderer block against the zipped winner fields (the trap), a
  tenderer that did not win, lists that do not line up, no winner field, 18 persons and 18 companies by name and
  country, nothing of a person in the winner list, the counts or the landed record, the first military CPV as the
  main code, 12 spellings of one number and 4 different numbers, the `awards` command, only publication numbers in a
  TED query.
- `backend/tests/integration/test_supplier_map.py` (13 tests): the loader end to end against Postgres with a stand-in for
  the TED search API (organisations, aliases, awards, the person absent from the database and from the landed
  record, a second run asks about nothing and writes nothing), only core-scope result notices are asked for,
  a notice with no winner is read once, a notice TED does not return is asked again, two companies of one name with
  different numbers are two suppliers and one open review row, list filters and paging, a profile (a value only where
  one supplier won; no sum, share or rank field), 404 and 410, a notice removed on request leaves the profile, a
  notice outside the core scope is not on the map, the aggregate publishes no group under 3 and no supplier name,
  three suppliers of one country make a cell.
- Mutation check: with the person rule switched off (`person_reason` returning None) 4 integration and 19 unit
  tests fail.
- Web: `web/e2e/suppliers.spec.ts` (4 tests, not run here).
- Whole suite on the server (ruff, unit, integration) on the final tree: see the last line of this file.

## Real-data run (read-only on production data; scratch database)

The 46,007 recorded TED answers (the real winner fields, fetched for the feasibility study) were replayed through the
real loader into a scratch database loaded with 8,883 core-scope result notices (built from the same answers and the
stored classification flags; **not** a copy of production: titles, values and currencies are approximated, which does
not touch the winners). No further request went to TED.

| Measure | Value |
|---|---|
| Candidates / requests | 7,515 notices in 76 requests (production has 7,596 candidates: 76 requests, as the replay) |
| Run time of the loader (replay, server under load) | 66 to 132 s |
| New awards / supplier organisations | 9,824 / 4,188 (4,177 new organisations) |
| How suppliers were found | alias 5,543, exact name 4,122, national number 110, new organisation for a namesake 55 |
| Winners left out | natural persons 223 (103 by name, 120 trading names), no country 0 |
| Notices | loaded 6,479, no winner named 902, only persons or nothing keepable 134 |
| Second run | 0 candidates, 0 requests, 0 rows |
| Size | `award` 2.3 MB, `award_notice` 1.3 MB, organisations and aliases about 10 MB: **about 13 MB** |

**What the replay found that the unit tests did not** (the reason for the run): a first version split an organisation
whenever a notice stated a registration number different from the one held, and made 225 new organisations; of 40
read, most were one company's VAT and register numbers, a leading zero, a prefix or a typo. `numbers_conflict` now
requires one kind of number (digit count or letter prefix), neither number the start of the other and at least two
characters of difference: 55 namesake splits remain. The open review rows (`id_conflict`) are for a person; nothing
is merged.

## Natural persons, measured

Core scope, 5,997 distinct (name, country) pairs (details in the feasibility document, section 3): 184 skipped
(3.1 %); of 45 skipped names read by hand 30 were persons or sole proprietorships (67 %) and 15 were companies;
of 45 names kept without any legal-form word 3 were persons (about 0.8 % of all suppliers leak). Three
rounds of the rule were driven by these samples, and the last two fixes (Polish given names, a person at the start of
a name) were not re-measured on a fresh sample. The rule cannot see an all-capital sole trader, a person with a
company-like word in the name, or a person registered with a business number.

## Endpoint timings and plans

Scratch database with 9,824 awards, 4,188 suppliers; `TestClient` including serialisation, list cache off, 3 runs;
the API role's budget is 5 s.

| Request | ms |
|---|---|
| `/v1/suppliers` (default) | 103 to 122 |
| `?q=rheinmetall` / `?q=airbus defence` | 415 to 480 / 393 to 450 |
| `?country=DE` / `?cpv=35` | 84 to 122 / 86 to 98 |
| `?sort=name&page=40` | 102 to 143 (1,082 before the page was cut before the shown spelling is looked up) |
| `?pageSize=100` | 186 to 210 |
| `/v1/suppliers/summary` | 190 to 232 |
| `/v1/suppliers/{slug}` (75 wins, 22.8 KB / 1 win) | 75 to 98 / 70 to 87 |

`EXPLAIN ANALYZE`: list page 40 114 ms, summary groups 52 ms, summary cells 49 ms, profile notices 2.7 ms. The
name search (`q`) is the slowest because it folds the stated names of every award; it stays under 0.5 s at this size
and is cached five minutes. Not measured on production data in production (the tables do not exist there yet).

## 15 profiles read against the recorded notices

For each supplier chosen at random (seed 37) the profile's name, country, number, years and CPV were read against the
API answer of its notices: is the supplier among the *winners* of the notice, with that country, and did a tenderer
that lost stay out. Verdict yes for all 15.

| Supplier (country) | Wins | Read against the notice | Verdict |
|---|---|---|---|
| HES-TDL Szolgáltató Kft (HU) | 1 | sole winner of 516409-2026 | yes |
| BOCANCI.COM (RO) | 15 | one of 8 winners of 635854-2026 and of 5 of 465841-2026; no value shown (several winners) | yes |
| RAMET s.r.o. (CZ) | 1 | sole winner of 162064-2025 | yes |
| Uni-Safe A/S (DK) | 1 | sole winner of 557982-2024 | yes |
| ST&T Kądziela, Zawadzki sp. j. (PL) | 2 | partner of a consortium in two notices; the name carries the notice's "partner konsorcjum" suffix | yes (name cosmetic) |
| NORVEKS SPORTS LV (LV) | 1 | winner of 421414-2024, named twice (two lots), counted once | yes |
| Loihde Trust Oy (FI) | 2 | winner of both; Certego Oy, a losing tenderer in 449311-2025, is not a winner | yes |
| OREDUI (FR) | 1 | one of 9 winners of 116190-2025 | yes |
| SIERRA MODELLSPORT (RO) | 1 | one of 3 winners of 687373-2024 | yes |
| SWISS Defence AG (CH) | 1 | sole winner of 506655-2024 (Dutch buyer) | yes |
| NETFORMERS Sp. z o.o. (PL) | 1 | sole winner of 289041-2026 | yes |
| LVCIM (FR) | 1 | sole winner of 612887-2026 | yes |
| Thales Edisoft Portugal (PT) | 2 | sole winner of both, values shown | yes |
| Thales Deutschland GmbH (DE) | 1 | sole winner of 745503-2024 (main CPV 71356000, the first code of the notice) | yes |
| UAB "ARVEKA" (LT) | 4 | one of 4 winners; the two Latvian-buyer notices spell it "ARVEKA" and "ĀRVEKA" and share one organisation (same number) | yes |

This reads the pipeline against TED's own answers; it does not read the TED web pages. Currencies in the scratch
database are approximated (every value shown as EUR), so the HES-TDL value (314,960,628) is probably forint: in
production the notice's own currency is stored.

## Mosaic effect: the reasoning

Each fact on a supplier page is a fact a buyer published in a result notice: name, country, buyer, date, CPV, and
the value of a notice that names one winner. A buyer that withholds a winner publishes no winner field, and the map
cannot show what the buyer did not publish. What is new is the *collection*: "who has supplied what to whom, in
Europe" is a picture nobody published. The map therefore (1) shows supplier-level detail only as the notice states it, with
the link to the notice; (2) publishes aggregates only for groups of at least 3 suppliers (checked by test: no group
under 3, no supplier name in the aggregate); (3) states no ranking, share, total value per supplier, or "sole
source" label (checked by test: no such field in the profile; the e2e spec checks the phrases are absent); (4) shows at
most the latest 50 notices of a supplier; (5) honours
`suppression` for an organisation or a notice (tested; 410); (6) says on every page that it is the open segment.
Residual risk, for the owner and the lawyer: the profile page of a company is itself a dossier of public facts, and it
is indexable (it is not in the sitemap, which lists `/suppliers` only). Whether supplier pages should be indexable, and
whether a ministry should be able to have its notices removed in bulk, is a decision outside this work.

## Could not check, or not done

- Playwright specs not run. Pages not seen in a browser; 375 px layout is by construction (tables in
  `overflow-x-auto`, wrapping), not by look.
- The loader was not run against the live TED API with the real database (production is read-only for this work): the
  replay used recorded real answers; the first live run is the orchestrator's (commands in the report).
- The person rule was tuned on the sample it was measured on; the last two fixes were not re-measured.
- A corrected result notice is not re-read (a notice is read once); `--refresh` not built.
- `resolution-candidates` (trigram candidates, stage 3) was switched off for the load (`candidates: False`): 4,177 new
  organisations would add about 40 ms each; `python -m dgate.pipeline resolution-candidates --all` queues them later.
- No Level 2 GLEIF parent data, no LEI enrichment (decision: enrichment only, not built).
- The other award sources (BOAMP names, e-Zamówienia contractors with NIP, BKMS XML) are not loaded.

## Hostile review of the diff: what it found

Ten findings, all fixed: (1) `winner-country` is not in the order of `winner-name` (81 % agreement): reading the
tenderer block (99.0 %); (2) a plain number inequality split 225 organisations: `numbers_conflict`, 55 left;
(3) the raw record would have landed the names of natural persons: blanked in place before landing; (4) the shown
name of a supplier was arbitrary (the first spelling seen, often capitals): the commonest, mixed case first;
(5) the list at page 40 took 1.08 s: the spelling is asked for the page's 20 rows only (0.14 s); (6) the public
page gave the ECIPE figure as fact: now "not re-checked"; (7) publication numbers were put into a TED query
without a check: only `\d{1,9}-\d{4}` goes in; (8) `RemovedOnRequest` had no supplier wording; (9) the person
rule flagged Estonian "Aktsiaselts", Hungarian and Polish long legal forms, ministries: markers added after reading
the samples; (10) `conftest.TABLES` did not truncate the new tables. Not fixed, listed above: the consortium
suffix in a name, a correction not re-read.

## Cleanup

Scratch removed at the end: `/root/wp37_scratch` (fetched notices 15 MB, scripts, outputs, the replay's raw store),
`/root/scratch_load.py`, `/root/q_verify.py`, `/root/*_q.tgz`, database `agent_q_scratch`, `/root/run_q_scratch.sh`.
Kept for the verifier until the merge (named in `docs/DELETION_CANDIDATES.md`): `/root/dev-q`, `/root/dev-q-old`,
`/root/run_q.sh`, database `agent_q`.
