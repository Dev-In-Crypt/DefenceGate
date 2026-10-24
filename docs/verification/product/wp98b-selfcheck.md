# WP-98b self-check: presets, buyer and supplier orders, coverage notes (persona round of 23 October 2026, C items 5-7)

Branch `wp-wp98b` from `integration` (58d6bd9, WP-97 in). Input: `D:\DEFENCEGATE TESTS\ux-oct23\SUMMARY.md` section C items 5, 6
and 7, and the evidence of p02-pt-textile, p03-de-machining, p04-pl-ammo, p06-nl-logistics and p07-it-analyst (problems.csv). No
deploy, no push, no production read or write, no portal called. Not touched: search (WP-98: `search.py`, `/search`, the `q` code of
`_tender_filters`), the WP-88 copy rules, the WP-93 verdicts, the WP-95 value logic (`value_of`, `best`, `value_totals` are reused,
not changed), the WP-97 report logic.

## 1. What changed, item by item

| # | Persona finding | Change | Test |
|---|---|---|---|
| 5a | p02: "Uniforms and protective gear" was 3581 + 181; boots (188), garments (182/183), textile articles (395), protective clothing (35113400) outside | `CPV_PRESETS` (`web/lib/analyst.ts`) "Uniforms, footwear and protective gear": 35810000, 18100000, 18200000, 18300000, 18800000, 35113400, 39500000 (prefixes 3581, 181, 182, 183, 188, 351134, 395). 395 holds carpets and hospital linen too: taken whole, as the task says, since a notice coded 39500000 itself is under no narrower prefix. | `wp98b.check.ts` §5, `wp98b.spec.ts` presets |
| 5b | p04: the ammunition preset (353) missed fuses, detonators, primers, pyrotechnics (2461x) | "Ammunition, weapons, explosives and pyrotechnics": 35300000 + 24610000 (prefixes 353, 2461: prepared explosives, propellants, pyrotechnics, fuses/caps/igniters/detonators). Replaces "Ammunition and weapons" (353 is in it). | same |
| 5c | p03: no preset for machined / spare parts | "Machined parts and spare parts": 35421000, 35521000, 35641000 (mechanical spare parts of military vehicles, warships, aircraft), 34320000, 34330000, 34913000 (vehicle and other spare parts), 35340000 (parts of firearms and ammunition), 44530000 (fasteners). The CPV has no code for machined parts as such (WP-89 note), so these are the part codes they are bought under. | same |
| 5d | p06: presets only for military goods | A second row "Services": Transport and logistics (60100000, 63100000, 63520000, 63700000), Fuel (09100000), Facility management and cleaning (79993000, 90900000), Catering (55500000), Vehicle repair and maintenance (50100000), Training (80600000), IT services (72000000). Goods and services are two labelled rows (`PRESET_GROUPS`). | same |
| 5e | every code checked | `wp98b.check.ts`: every preset code is in the CPV 2008 vocabulary (`lib/data/cpv-full.json`), at most 20 prefixes, a preset is recognised in any order; titles of the key codes asserted verbatim. `wp90.check.ts` keeps its vocabulary loop over every preset; its label list now covers the first four (the others are WP-98b's, held in `wp98b.check.ts`). | `wp90.check.ts`, `wp98b.check.ts` |
| 5f | p03: deadline chips hidden in the collapsed "Deadline between" | The "Next 7 / 14 / 30 days" presets sit above the folded date range, always in sight; a second click on the active one takes it off. | `wp98b.spec.ts` (no `details [data-deadline-presets]`), `wp90.spec.ts` unchanged and passing |
| 5g | p02: on a phone the panel stayed open after Apply, first result at 2,717 px | `FilterPanel` (`components/funding/filter-panel.tsx`): below lg, a submit (Apply, Enter) folds the panel and scrolls to `#results`, focus moved there without a second scroll; the live form sends the filters as before. The filters as chips above the results below lg (`components/tenders/filter-chips.tsx`, `filterChips()` in `lib/analyst.ts`): one per filter (search words, preset name or CPV codes, main code only, excluded codes, each country, status, scope, defence goods, deadline, value), each linking to the list without it; the defaults are no chip. FilterPanel is shared, so /funding's panel folds after Apply too (same layout, the call list has `#results`). | `wp98b.check.ts` chips; `wp98b.spec.ts` phone (panel hidden, `#results-heading` in the viewport, chip removes its filter) |
| 6a | p02: /buyers?cpv= ranked by all tenders (MINARM/DGA #2 for uniforms) | `GET /v1/buyers?cpv=`: `cpvCount` per buyer family, the notices of the counted set under the codes, each once as the tender list shows it (`collapse_clauses` over the same filters, same family, `tenders.under_codes`); `sort=cpv` orders by it. The WP-89 two-step form is kept: the families are read first, on their own, and the list's query takes them as `ANY(ids)`; the order is a join to `unnest(ids, counts)`. The collapse is bounded: past 2.5 s (`UNDER_CODES_MS`, a savepoint with its own `statement_timeout`, restored after) the plain count is given and the page says `cpvCountCollapsed: false`; the footnote then says a notice published twice may count twice. Web: with a CPV filter the default order is "Most tenders under these codes first" (`defaultBuyerSort`, kept out of the address), the card shows "Under these codes" before "Tenders in archive". | `test_wp98b.py` (order, counts, a national copy counted once, the slow path), `wp98b.check.ts` §6, `wp98b.spec.ts` buyers |
| 6b | p02: the supplier list showed no amounts | `GET /v1/suppliers`: `contractValues` per supplier, the contract values of the wins the filters select per currency (`contract_values_sql`: each procurement once, valued as `best` picks its row, contract values only, a unit price in no sum: the SQL of `value_totals`' `byCurrency`, held equal to the profile by a test). `sort=value-XXX` orders by the sum in one currency, largest first, none in it last; never converted. Web: a line per card, "Contract values: EUR 1,243,802 over 2 of 6 contracts; PLN …", and one order per site currency ("Contract values in EUR, largest first", …). The order help says what a value order is and is not. Rate cost +2 for a value order (`hardening.request_cost`). | `test_wp98b.py` (equals the profile; EUR and PLN orders; 422 on a bad currency), `wp98b.check.ts`, `wp98b.spec.ts` suppliers |
| 7a | p02, p06, p07: no word that a country is TED only | One constant, `NATIONAL_COVERAGE` (`web/lib/coverage-copy.ts`): the countries whose own portal or feed we read (DE, ES, FR, NL, PL) with the portal, its start where it matters and a note; every other country is "TED only". `wp98b.check.ts` holds its countries equal to the `source` rows of `backend/migrations` (kind `tender`, a country, less the one-off Atlas load and the award results), and holds that only PLACSP's award results are read. `coverageLine()`: "Portugal: TED only; the national portal is not collected", "Italy: TED only; …", "Spain: TED + PLACSP, awards too", "Netherlands: TED + TenderNed (since January 2026); in practice chiefly one buyer, the Ministry of Defence", "Germany: TED + the federal notice service (since 25 October 2023); state and municipal portals are not collected"; for the supplier map "France: winners from TED only; BOAMP's award notices are not read". `CoverageNote` shows one line per chosen country (at most six) with a link to /data, above the results of /tenders, /buyers, /suppliers (buyer's country, else the supplier's) and /market, so above an empty result too. | `wp98b.check.ts` §7, `wp98b.spec.ts` coverage |
| 7b | p07: Spanish winners fill /suppliers; no fair comparison | `GET /v1/suppliers?source=ted`: the winners of TED's own result notices (`award_set.BASE` and TED rows, no twin rule needed, TED-copy values only). Web: a "Sources" choice (TED and PLACSP / TED only) when PLACSP is on the map, and with a country chosen a line "Comparing countries? Show TED's winners only". | `test_wp98b.py` (madzeal: 6 wins, 4 in TED, no TED contract value), `wp98b.spec.ts` |

Docs: `docs/design/API_CONTRACT.md` "Changes of 24 October 2026"; `backend/dgate/suppliers.py` module note, rule (3) now reads that
the list can be ordered by contract value when the visitor chooses it (see open decisions).

## 2. Timings (the 5 s budget)

No production access in this run (production reads were refused by the session's permission rules), so measured on the laptop
against a synthetic archive of production's size in the test container (database `dgate_perf`, deleted with the container):
350,000 notices, 105,000 defence, 63,636 award rows, 6,000 buyers, 20,000 suppliers; random CPV pairs from 40 codes, TED twins and
procedure identifiers on part of the rows. Cold (list cache off), median of 3 (`perf.log` in `D:\DEFENCEGATE TESTS\wp98b`):

| Request | Median | Max |
|---|---|---|
| `/v1/buyers` (no CPV) | 0.36 s | 1.80 s (first, cold) |
| `/v1/buyers?cpv=<uniforms preset>` sort tenders / cpv | 1.79 s / 1.62 s | 1.89 s |
| `/v1/buyers?cpv=353,2461` sort tenders / cpv | 0.78 s / 0.69 s | 0.79 s |
| `/v1/buyers?cpv=343` sort tenders / cpv | 0.83 s / 0.86 s | 0.93 s |
| `/v1/buyers?cpv=35` sort tenders / cpv | 1.51 s / 2.44 s | 2.70 s |
| `/v1/suppliers` (default) | 0.45 s | 0.48 s |
| `/v1/suppliers?sort=value-EUR` / `value-PLN` | 1.67 s / 1.77 s | 1.84 s |
| `/v1/suppliers?source=ted` / with `sort=value-EUR` | 0.43 s / 1.67 s | 1.80 s |
| `/v1/suppliers?cpv=3581,181&sort=value-EUR` | 0.42 s | 0.48 s |

The step itself (`under_codes`): division 35 (52,501 notices under the code, more than production has) 1.67 s collapsed, the
uniforms preset 0.61 s, 343 0.26 s; the WP-89 step it replaces took 0.01 to 0.05 s. The server is slower than the laptop (the WP-52
note: the collapse of 68,000 core notices took 8 s idle there), which is why the collapse is bounded at 2.5 s with the plain count
behind it, instead of trusting the laptop's numbers. Every answer is kept 5 minutes (`cache_list`).

## 3. Tests

Local, `D:\DEFENCEGATE TESTS\wp98b` (own venv, Python 3.11; Postgres 17 container `dgate-wp98b` on 55488, removed at the end;
TZ=UTC; web mock env of `web.yml`; E2E_PORT 3188; Playwright 4 workers), final code:

| Check | Result | Time |
|---|---|---|
| ruff | All checks passed | |
| unit (`pytest`) | **3564 passed**, 1293 deselected | 31 s |
| integration (`pytest -m integration`) | **1293 passed**, 0 failed (5 new in `test_wp98b.py`) | 14 min 6 s |
| `tsc --noEmit` | exit 0 | 3 s |
| `npm run check` (all `lib/*.check.ts`, with the new `wp98b.check.ts`) | all ok | 135 s |
| `next build` (mock) | exit 0 | 66 s |
| Playwright, desktop + 375 px, 4 workers | final code: **726 passed, 57 skipped, 1 failed**: `funding.spec.ts` calendar.ics `read ECONNRESET` from the local server under load (the flake WP-89 recorded); `funding.spec.ts` alone right after: 19 passed. The full run before the last change (the scroll fix below) was 727 passed, 0 failed. | 185 s |

A first full run, made while the integration suite ran beside it, failed `wp49` "a radio applies at once" (3 s poll), `digest.atom`
304 and a `wp80` report order; all three passed alone (39 passed) and in every later full run. The phone test found the scroll ran
before the fold and the new list were laid out (the chips ended above the viewport, the browser's scroll anchoring); the scroll now
waits for both, and the test asserts the first chip is in view.

New: `backend/tests/integration/test_wp98b.py` (5 tests), `web/lib/wp98b.check.ts`, `web/e2e/wp98b.spec.ts` (5 tests × 2 widths, the
phone test skipped on desktop). Changed: `wp90.check.ts` (its label list now the first four presets; the vocabulary loop over all of
them unchanged). No test deleted, skipped or weakened.

Screenshots, `docs/verification/product/wp98b/` (demo data, `WP98B_SHOTS`): `tenders-presets` (1280, 375), `tenders-chips` (375),
`tenders-pt-coverage` (1280, 375), `buyers-cpv-order` (1280, 375), `suppliers-values` (1280, 375).

## 4. Open decisions for the owner

- **A value order on the supplier list.** `suppliers.py` said the map "states no ranking of suppliers by contract value" (the
  mosaic rule, WP-37; WP-81 lifted it for sums only). The task asks for the value column with a sort, so the list can now be ordered
  by the sum in one currency when the visitor chooses it; the default stays the number of wins and the help says many contracts
  state no value. To withdraw it: drop `VALUE_SORTS` from the order choice on `/suppliers` (the column stays).
- **395 in the uniforms preset** includes carpets and linen; 3952 (made-up textile articles) alone would miss a notice coded
  39500000. Say if the narrower set is preferred.
- **The Netherlands line** says TenderNed "since January 2026, in practice chiefly one buyer, the Ministry of Defence"
  (docs/sources/nl_tenderned.md: Defensie's 435 of 2026 and the directive notices; the 2026 backfill not run). The /market chart's
  step at January 2026 (p06) is not marked on the chart: only the line above it says so.
- **Buyer counts under the codes on production.** Measured on synthetic data only; if the server gives the plain count often
  (`cpvCountCollapsed: false`), the collapse can be precomputed by the worker like `buyer-base`.
- **/funding's filter panel** folds after Apply on a phone as well (one shared component); it was not asked but is the same
  behaviour the audit asks for (E: "Filters collapse after Apply").
