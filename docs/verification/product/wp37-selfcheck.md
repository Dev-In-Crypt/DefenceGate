# WP-37 self-check: supplier map from award notices (18 October 2026)

Implementer's own check, before the independent verifier. Branch `wp-wp37` (from `integration`), test database
`agent_q`, test copy `/root/dev-q`. Feasibility, with every number and its method:
`docs/design/SUPPLIER_MAP_FEASIBILITY.md`.

## Acceptance criteria

| Criterion (brief) | Result | Evidence |
|---|---|---|
| Feasibility numbers measured | **met** | the feasibility document: 46,007 result notices fetched, 30,632 naming a winner, **4,807 unique suppliers (4,666 European) in the core scope**, 2,427 European under the narrowest definition; also M3 (no-go), the other award sources, GLEIF |
| Go/no-go rule applied | **met, GO** | 4,807 against 2,000; per year 1,761 (2024), 2,266 (2025), 2,228 (2026 to 18 Oct); the pages say that 2023 is thin because the API states no winner as data before eForms |
| Tables for award and supplier (organisation + the WP-26 cascade, no other resolution) | **met** | migration 0078 `award`, `award_notice`; suppliers are `organisation` rows found or made by `dgate.resolution.resolve`; the loader adds a guard for namesakes and attaches a registration number, both after the cascade |
| Loader with the pipeline rule (land, normalise, archive); idempotent | **met, with one deviation** | the winners are not in the raw store (the daily pull never asked for them: `TED_FIELDS`), so the loader asks TED by publication number, **lands** the answer (`ted_awards/` bundles, `raw_ingest` rows), **normalises** (`read_award`) and **archives** (`award`). Idempotent: tests, and on the live run below the second run had 0 candidates and made no request |
| No natural persons: skip and count | **met as far as a rule on names can be** | `person_reason`; counted in `award_notice.skipped_person` and in the summary; a person's name never reaches an organisation, an alias, an award or the raw store (tested); measured rates below. **Not a guarantee** |
| API `GET /v1/suppliers?country=&cpv=&q=` and `/v1/suppliers/{slug}` (wins by CPV and year, buyers, values) | **met** | `dgate/suppliers.py`; contract in `docs/design/API_CONTRACT.md`; 14 integration tests |
| Pages `/suppliers`, `/suppliers/[slug]` | **met, not seen in a browser** | `web/app/(public)/suppliers/`; `tsc --noEmit` clean and `npm run check` (12 checks) passes in `node:22-alpine`; the Playwright spec `web/e2e/suppliers.spec.ts` is written and **not run** (no browser on the server; CI runs it) |
| Public aggregate by CPV and country | **met** | `/v1/suppliers/summary`, shown on `/suppliers`; a group of fewer than 3 suppliers is not published (tested) |
| Supplier-level detail only if the facts are published by the buyer in the notice | **met** | see "Mosaic effect" |
| Coverage statement on the pages | **met** | both pages and the API (`coverage`): TED holds only part of European defence spending (a 2025 ECIPE brief puts it at about a tenth; **not re-checked by us**, and the page says so); the map is the open segment |
| 15 supplier profiles checked by hand against the notices | **met** (15 of 15) | below |
| Endpoint timings | **met** | below |
| Database growth under 500 MB | **met** | about 10 MB for the whole load |
| Production load commands and disk estimates in the report | **met** | the report |

## Tests added

- `backend/tests/unit/test_awards.py` (62 tests): the tenderer block against the zipped winner fields (the trap), a
  tenderer that did not win, lists that do not line up, no winner field, 18 persons and 18 companies by name and
  country, nothing of a person in the winner list, the counts or the landed record, the first military CPV as the
  main code, 12 spellings of one number and 4 different numbers, the `awards` command, only publication numbers in a
  TED query.
- `backend/tests/integration/test_supplier_map.py` (14 tests): the loader end to end against Postgres with a stand-in
  for the TED search API (organisations, aliases, awards, the person absent from the database and from the landed
  record; a second run asks about nothing and writes nothing); only core-scope result notices are asked for; a notice
  with no winner is read once; a notice TED does not return is asked again; two companies of one name with different
  numbers are two suppliers and one open review row, and the second again by its number joins the second; list
  filters and paging; a profile (a value only where one supplier won; no sum, share or rank field); one number
  written two ways is shown once; 404 and 410; a notice removed on request leaves the profile; a notice outside the
  core scope is not on the map; the aggregate publishes no group under 3 and no supplier name; three suppliers of one
  country make a cell.
- Mutation check (before the last two additions): with the person rule switched off, 4 integration and 19 unit tests
  failed.
- Web: `web/e2e/suppliers.spec.ts` (4 tests, not run here).
- Whole suite on the server, final tree (apart from the one-line Caddyfile change after it): `ruff check .` clean, unit and
  integration suites together `EXIT=0` (`/root/q_full_suite2.log`, test database `agent_q`).

## Live run against production data (scratch database)

A read-only export of the 7,596 core-scope result notices that production holds (the loader's exact candidate set:
TED, core scope, result subtypes, from 2023, not suppressed) was loaded into a scratch database
(`agent_q_scratch`), and the real loader was run against the live TED API. Production was only read.

| Measure | Value |
|---|---|
| Candidates / requests / run time | 7,596 notices, 76 requests, 196 s (one 429 from TED was retried by the retry ladder) |
| New awards / supplier organisations | 9,826 / 4,187 (4,178 new organisations) |
| How suppliers were found | alias 5,454, exact name 4,125, national number 200, new organisation for a namesake 53 |
| Winners left out | natural persons 223 (103 by name, 120 trading names); no country 0 |
| Notices | loaded 6,481, no winner named 981, nothing keepable (only persons) 134 |
| Second run | 0 candidates, no request, no row |
| Size | `award` 2.3 MB, `award_notice` 1.2 MB, new organisations and aliases about 6 MB: **about 10 MB** |

**What an earlier replay of recorded answers found that the unit tests did not** (the reason for running on real
data): a first version split an organisation whenever a notice stated a registration number different from the one
held, and made 225 new organisations; of 40 read, most were one company's VAT and register numbers, a leading zero, a
prefix or a typo. `numbers_conflict` now requires one kind of number (digit count or letter prefix), neither number the
start of the other and at least two characters of difference; the cascade's order (an alias before a number) is
corrected by looking up the body that holds the number first. 53 namesake splits remain; their review rows
(`id_conflict`) wait for a person, nothing is merged.

## Natural persons, measured

Core scope, 5,997 distinct (name, country) pairs (details in the feasibility document, section 3): 184 skipped
(3.1 %); of 45 skipped names read by hand 30 were persons or sole proprietorships (67 %) and 15 were companies; of 45
names kept without any legal-form word 3 were persons (about 0.8 % of all suppliers leak). Three rounds of the rule
were driven by these samples, and the last two fixes (Polish given names, a person at the start of a name) were not
re-measured on a fresh sample. The rule cannot see an all-capital sole trader, a person with a company-like word in
the name, or a person registered with a business number.

## Endpoint timings and plans

Scratch database above (9,826 awards, 4,187 suppliers); `TestClient` including serialisation, list cache off, 3 runs;
the API role's budget is 5 s.

| Request | ms |
|---|---|
| `/v1/suppliers` (default) | 118 to 142 |
| `?q=rheinmetall` / `?q=airbus defence` | 401 to 415 / 391 to 431 |
| `?country=DE` / `?cpv=35` | 100 to 113 / 92 to 146 |
| `?sort=name&page=40` | 126 to 129 (1,082 before the page was cut ahead of the shown-spelling lookup) |
| `?pageSize=100` | 181 to 204 |
| `/v1/suppliers/summary` | 217 to 302 |
| `/v1/suppliers/{slug}` (75 wins, 29.8 KB / 1 win) | 83 to 91 / 56 to 58 |

`EXPLAIN ANALYZE`: list page 40 84 ms, summary groups 32 ms, summary cells 43 ms, profile notices 4.7 ms. The name
search (`q`) is the slowest because it folds the stated names of every award; it stays near 0.4 s at this size and the
list is cached five minutes. Production itself was not queried for these (the tables do not exist there yet).

## 15 profiles read against the notices

Chosen at random (seed 37) in the scratch database; for each, the profile's name, country, number, years, CPV and
value were read against a fresh TED answer for its notices: is the supplier among the *winners* of the notice, with
that country, and does a tenderer that lost stay out. All 15 yes.

| Supplier (country) | Wins | Read against TED | Verdict |
|---|---|---|---|
| Microsoft Deutschland GmbH (DE) | 2 | sole winner of 516691-2026 (44.8 M EUR) and 355471-2024 (no value stated); the number was shown twice, spelt with two kinds of space (fixed afterwards: shown once) | yes |
| SAFE Sicherheitsunternehmen in Sachsen GmbH (DE) | 6 | sole winner of both notices read | yes |
| Motorsport in Motion B.V. (NL) | 1 | sole winner of 166784-2025, 650,000 EUR | yes |
| De Zeeman Pro NV (BE) | 2 | "DE ZEEMAN PRO" and "De Zeeman Pro NV" are one organisation; sole winner of both | yes |
| Noske-Kaeser Germany GmbH (DE) | 2 | sole winner of both | yes |
| Comptoir Métallurgique de Bretagne (FR) | 1 | sole winner of 423862-2024, 15 M EUR | yes |
| Sodarca (PT) | 1 | one of 2 winners of 682062-2025; no value shown (two winners) | yes |
| Onyx Méditerranée (FR) | 1 | one of 9 winners of 116190-2025 | yes |
| Sierra Modellsport (RO) | 1 | one of 3 winners of 687373-2024 | yes |
| Industry62 OÜ (EE) | 1 | one of 18 winners of 507191-2024 | yes |
| NETFORMERS Sp. z o.o. (PL) | 1 | sole winner of 289041-2026, 1,330,646.48 PLN (the notice's own currency) | yes |
| S3 Solutions (FR) | 3 | one of 4 and of 10 winners in the two notices read | yes |
| Optimum-Tymińska i s-ka sp. z o.o. (PL) | 1 | one of 2 winners of 521883-2026 | yes |
| Aeromaritime Systembau GmbH (DE) | 1 | sole winner of 747634-2024, 5.08 M EUR | yes |
| Surcom International B.V. (NL) | 3 | sole winner of 561422-2026 (3.05 M EUR) and 436610-2026 (13.1 M SEK) | yes |

An earlier sample of 15 on the replay (a consortium partner whose name carries the notice's "partner konsorcjum"
suffix; a name with a typo in one notice that still joined its organisation by number) also read yes. This reads the
pipeline against TED's answers; it does not read the TED web pages.

## Mosaic effect: the reasoning

Each fact on a supplier page is a fact a buyer published in a result notice: name, country, buyer, date, CPV, and the
value of a notice that names one winner. A buyer that withholds a winner publishes no winner field, and the map cannot
show what the buyer did not publish. What is new is the *collection*: "who has supplied what to whom, in Europe" is a
picture nobody published. The map therefore (1) shows supplier-level detail only as the notice states it, with the
link to the notice; (2) publishes aggregates only for groups of at least 3 suppliers (tested: no group under 3, no
supplier name in the aggregate); (3) states no ranking, share, total value per supplier, or "sole source" label
(tested: no such field in the profile; the e2e spec checks the phrases are absent); (4) shows at most the latest 50
notices of a supplier; (5) honours `suppression` for an organisation or a notice (tested; 410); (6) says on every page
that it is the open segment. Residual risk, for the owner and the lawyer: the profile page of a company is itself a
dossier of public facts, and it is indexable (it is not in the sitemap, which lists `/suppliers` only). Whether supplier
pages should be indexable, and how a ministry's request to remove its notices in bulk is handled, are decisions outside
this work.

## Could not check, or not done

- Playwright specs not run; pages not seen in a browser; the 375 px layout is by construction (tables in
  `overflow-x-auto`, wrapping text), not by look.
- The live run used a scratch database loaded from a read-only export, not production itself: the first run on
  production is the orchestrator's (commands in the report).
- The person rule was tuned on the sample it was measured on; the last two fixes were not re-measured.
- A corrected result notice is not re-read (a notice is read once); no `--refresh`.
- Trigram candidates (stage 3) are off for the load (`candidates: False`; 4,178 new organisations at about 40 ms each);
  `python -m dgate.pipeline resolution-candidates --all` queues them later.
- No Level 2 GLEIF parent data or LEI enrichment (decision: enrichment only, not built).
- The other award sources (BOAMP names, e-Zamówienia contractors with NIP, BKMS XML) are not loaded.
- Names that carry a consortium role ("... - partner konsorcjum") are shown as published.

## Hostile review of the diff: what it found

Eleven findings, all fixed: (1) `winner-country` is not in the order of `winner-name` (81 % agreement): the tenderer
block is read instead (99.0 %); (2) a plain number inequality split 225 organisations: `numbers_conflict`, 53 left;
(3) the cascade tries an alias before a registration number, so a company stating its own number could be filed under
a namesake: the holder of the number is looked up first; (4) the raw record would have landed the names of natural
persons: blanked in place before landing; (5) the shown name of a supplier was arbitrary (the first spelling seen,
often capitals): now the commonest, mixed case first; (6) the list at page 40 took 1.08 s: the spelling is asked for the
page's 20 rows only (0.13 s); (7) the public page gave the ECIPE figure as fact: now "not re-checked"; (8) publication
numbers were put into a TED query unchecked: only `\d{1,9}-\d{4}` goes in; (9) the person rule flagged Estonian
"Aktsiaselts", Hungarian and Polish long legal forms, ministries: markers added after reading the samples; (10) one
registration number spelt two ways was shown twice on a profile; (11) `conftest.TABLES` did not truncate the new
tables, and a first integration test used numbers (`111111111`) that the identifier check rejects as junk.

## Cleanup

Removed: `/root/wp37_scratch` (36 MB: the study's notices, scripts and outputs), `/root/dev-q-old`, `/root/*_q.tgz`,
the first scratch database. At the end of the work also `/root/wp37_scratch2` (the export, the raw store of the live
run), `/root/scratch_live.py`, `/root/q_verify.py`, `/root/export_core.sql`, `/root/run_q_scratch.sh` and database
`agent_q_scratch`. Kept for the verifier until the merge (named in `docs/DELETION_CANDIDATES.md`): `/root/dev-q`,
`/root/run_q.sh`, `/root/q_full_suite2.log`, database `agent_q`. The study's own numbers can be reproduced only by
repeating it (about 250 TED requests).
