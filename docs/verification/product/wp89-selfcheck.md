# WP-89 self-check: the supplier path (UX audit of 22 October 2026, section 4)

Branch `wp-wp89` from `integration` (da59587: WP-86, WP-87 and WP-88 merged). Persona Marta: a Spanish automotive parts maker in the
Comunitat Valenciana, no defence experience (audit dumps and screenshots in `D:\DEFENCEGATE TESTS\ux-oct22\supplier\`). Owner priorities:
usability, completeness, correctness; no Spanish translation now. Not changed: WP-87's numbers logic (every count below reuses the award
set and the tender list's CPV reading), WP-88's copy rules (one sentence before content, the rest collapsed, attribution lines visible).
No migration, no deploy, no push, no production read or write, no secret, no model call.

## 1. What changed, item by item

| # | Audit finding | Change | Test |
|---|---|---|---|
| 1 | "Who to approach" showed eight German primes; the Spanish winners only in the report or behind "All 365 winners" | `approachGroups()` (`lib/demand.ts`): the named winners in three groups, each most contracts first: the direct suppliers of the company's own country, the primes (those of its country first: Indra before Saab), the others. Results page: two columns, "Direct suppliers in Spain" (5) and "Large primes" (5), the "All N winners" button kept. Report: "Direct suppliers in Spain" first, then "Prime contractors and large defence groups among them", then "The other named winners, in other countries". Without a home winner the first column is "Direct suppliers" of every country. | `wp89.check.ts` §1; `wp80.spec.ts` (rewritten), `wp89.spec.ts` results |
| 2 | CPV search: "castings" found casting machines, "machined" nothing, "machining" machining centres | 13 curated entries in `lib/data/product-keywords.json` (the existing keyword-map pattern, no model): vehicle parts, castings, forgings, machined/turned/CNC parts, stampings/pressings, rubber parts/seals/gaskets/hoses, plastic parts, wiring harnesses, filters, seats, glass/windscreens/mirrors, paint/coatings, fasteners/springs. Codes and titles verbatim from the CPV 2008 file; where the CPV has no code for the product as such (castings, forgings, machined parts, stampings) the entry names the part codes it is bought under and its note says so, and names the machines' code. `cpvSearch` keeps the entry's order (castings: 44470000 Cast-iron products first) and lists machine codes (group 426, titles naming a machine, machinery, machining or presses: `isMachineCode`) after the products. The note shows under the matches. Button "Automotive supplier: suggested codes" adds `AUTOMOTIVE_SET` (10 official codes) to the chosen ones, never past 15, each removable. The supplier map's product search reads the same words. | `wp89.check.ts` §2, `cpv.check`, `wp57.check` (unchanged, pass); `wp89.spec.ts` CPV search |
| 3 | /buyers and /market had no CPV filter | Backend: `tenders.cpv_prefixes()` (2 to 8 digits, a check digit dropped, else 422) and `CPV_HEADS` (the GIN index of migration 0099, the tender list's prefix reading). `/v1/buyers?cpv=`: the buyer families with at least one counted (core) notice under the codes, a semi-join; the counts stay all of their notices (said in the hint and the footnote). `/v1/stats/market?cpv=`: every figure narrowed (scope and months), echoed as `cpv`, cache key includes it. Web: a CPV field in the buyer filters and on /market (kept in "Try again" and in the country links to /tenders), `ignoredFilters` names an unreadable code. The site search's buyers group: `search._defaults(list_buyers)["cpv"]` is None, so its "see all" still equals the list's default. | `test_wp89.py` (buyers, market, search defaults); `wp89.check.ts` §3; `wp89.spec.ts` /buyers and /market |
| 4 | Results: EDF/EDIP/SAFE above the Spanish MoD path; "19 answers are missing"; roadmap "PIC … Needed now" vs report "only if you apply for EU funding"; answers asked via /readiness?step= | A supplier's results (`hasSupplier`) lead with the supply routes, Spanish Ministry of Defence first, then NATO and NSPA; the EU programmes follow collapsed under "If you also want EU funding (4 programmes)", open when it said yes. New question on the supplier page, block "If you also want EU funding (optional)" (`supplier.euFunding`, stored, not sent); with yes it asks there the questions the EU programmes read (legal form, executive management, control, component share, restricted components, UA/EEA components, Ukrainian partner, SAFE role, PIC; the wizard's option lists shared). `wantsEuFunding()`: yes/no as answered; unanswered or not sure, a supplier-page-only profile is a supplier first. The roadmap of a supplier that does not want EU funding asks the engine for the supply routes only (`programmes: ["ES-MOD", "NATO-SUPPLY"]`, an existing API field): no PIC step, with a line and a link to add EU funding. Every missing answer of a card links to the supplier page for a supplier (`askedAt(field, true)`: EU fields → `#sp-eu`, classified work, exports and the export authorisation to their blocks, the Spanish route's questions as before); the readiness check keeps its own steps. The report's appendix lists the routes first. Generated fixture `assess-/request-es-sup-civil-routes.json` (`python -m dgate.readiness.export`, covered by its `--check` test). | `wp89.check.ts` §4 (also: every missing answer of the audit-like partial profile links to the supplier page); `wp89.spec.ts` results, roadmap, EU questions |
| 5 | NCAGE "free of charge" / "Not stated in a primary source" / "Free"; RID cost unstated in mixed words; Valencian company shown Murcia, Aragón, Galicia, Extremadura grants | `costStatement()` / `timeStatement()` (`lib/readiness.ts`): one statement per requirement, the source's own words, else the range, else **"Not stated by the source"** (`NOT_STATED`), used by the report, the roadmap, the requirement list and pages and a call's readiness block. NCAGE reads "Free of charge (NSPA)" everywhere (NSPA: "In accordance with NATO policy, the assignment and update to the NCAGE are free of charge"); RID "Not stated by the source" for cost and time everywhere. The report prints a vendor range with its label where the roadmap does. Regional grants (`regionalGrants()`): with the region chosen, its own programmes only; none of its own while another region's covers the step → "No programme of Comunitat Valenciana in our sources pays for this step. Ask your regional development agency whether it has one; the programmes of other regions are for companies established there." No agency is named: no primary source in the repository names IVACE or the Cámara de Valencia (`docs/research/ANGLE1_SPAIN_LANDSCAPE_2026-10-22.md` only mentions an unverified AVIA study). A closed call carries a "Closed" tag (`isClosed`). Without a region chosen, every programme is listed as before. | `wp89.check.ts` §5, `wp67.check.ts` (rewritten for the one statement), `readiness.check.ts`; `wp67.spec.ts` (rewritten), `wp89.spec.ts` report, Galicia, requirement pages |
| 6 | Supplier card 311 (all codes) vs 44 in the report (her codes) | The report's and the results' winner links carry the profile's codes and the report's countries (`supplierHref`). `GET /v1/suppliers/{slug}?cpv=&buyerCountry=` returns `underCodes {cpv, buyerCountries, contracts}`: the contracts under the codes and countries counted as `/v1/suppliers?cpv=&buyerCountry=` (and so "who to approach") count them; the page shows "44 of them under your CPV codes, in Spain, Germany, …, as in your supplier report" under the total. Without codes nothing changes; an unreadable list falls back to the total. | `test_wp89.py` (equals the list's count); `wp89.check.ts` §6; `wp89.spec.ts` supplier page |
| 7 | PDF 59 pages, the methodology paragraph 38 times; closed contract values looked empty | The sums' scope and rules once, under the list in "How we count" (`data-value-rules`), not under each company (`Winner rules={false}`). The "Contract values" summary line carries the total: "Contract values: EUR 1,512,500 over 1 contract; 48 of 49 contracts state none" / "no stated value" (`totalLine`), here and on the supplier page; the details stay collapsible. Print only: a company's values print as that line; the demand map prints each winner with its newest notice and no "At the source" address (one line says so, once); tighter rows. | `wp81.spec.ts`, `wp87.spec.ts`, `wp66.spec.ts` (rewritten for the summary and the print); `wp89.spec.ts` report (pages) |

## 2. The printed report

Same profile (Marta's, from the audit's `state.json`), same demo data (`lib/mock/demand.json`, production's answer of 22 October), A4,
`page.pdf`: **46 pages before → 29 after** (`wp89/before-report-pages.txt`, `wp89/after-report-pages.txt`; PDFs in
`D:\DEFENCEGATE TESTS\wp89\shots\`, not committed). On production the audit counted 59 for this profile with 38 named winners; by the same
cuts an estimated 35 to 38. What was cut on paper only: the per-company rules paragraph (now once), the per-company value details (the summary
line prints), two of three notices per winner in the demand map (every winner stays named in "Who to approach"), the source addresses of
those notices (their numbers print), the other regions' grants.

## 3. Tests

Local, `D:\DEFENCEGATE TESTS\wp89` (own venv, Python 3.11; Postgres 17 container `dgate-wp89` on 55489; TZ=UTC; web mock env of
`web.yml`; E2E_PORT 3089; Playwright 4 workers), final code:

| Check | Result | Time |
|---|---|---|
| ruff | All checks passed | |
| unit (`pytest`) | **3283 passed**, 1235 deselected | 33 s |
| integration (`pytest -m integration`) | **1235 passed**, 0 failed (3 new in `test_wp89.py`) | 12 min 22 s |
| `tsc --noEmit` | exit 0 | 4 s |
| `npm run check` (`scripts/run-checks.mjs`, 41 files with the new `wp89.check.ts`) | all ok | 100 s |
| `next build` (mock) | exit 0 | 59 s |
| Playwright, desktop + 375 px | **636 passed, 56 skipped** (the fake-API group and width-specific tests, as before), 0 failed | 2 min 20 s |

Two earlier runs saw one `wp87.spec.ts` calendar.ics test fail with `read ECONNRESET` from the local server under load; it passed alone
and in the two final full runs (not related to this change).

Rewritten (owner-approved changes of visible text or order; none deleted or skipped): `wp67.spec.ts` (the report states the roadmap's cost
words, not "Not stated in a primary source"), `wp67.check.ts` (same), `readiness.check.ts` ("Not stated by the source"), `wp80.spec.ts`
(home-country winners first, primes of the own country first, two columns on the results page, links carry the codes), `wp81.spec.ts` (the
summary line's total; the rules once under the list), `wp87.spec.ts` (summary text starts "Contract values"), `wp66.spec.ts` (a notice's
source link is hidden in print).

New: `backend/tests/integration/test_wp89.py`, `web/lib/wp89.check.ts`, `web/e2e/wp89.spec.ts` (9 tests × 2 widths), fixtures
`assess-/request-es-sup-civil-routes.json` (generated by the engine).

Screenshots, `docs/verification/product/wp89/` (desktop 1280, demo data, Marta's profile; `before-*` from `integration` da59587, `after-*`
from this branch, `shots.cjs`): `results-who-to-approach`, `results-fold`, `results-programmes`, `report-fold`, `report-print-preview`,
`cpv-castings`, `buyers-cpv`, `market-cpv` (before: the CPV parameter is ignored and has no field).

## 4. Open decisions for the owner

- **Cost on the report (changes WP-67's rule).** The report used to print a figure only where the requirement's source is primary, so it
  said "Not stated in a primary source" where the roadmap said "Free". It now prints the requirement's one statement, the same as the
  roadmap and the requirement pages (NCAGE "Free of charge (NSPA)", PIC "Free"; a vendor range with its "vendor range" label for a non-Spanish
  AQAP step). If the report should stay primary-only, the roadmap and the requirement pages would have to drop the NSPA statement too.
- **"Wants EU funding" when unanswered.** A profile that only used the supplier page is treated as a supplier first (routes first, EU
  collapsed, no PIC on the roadmap); one that finished the readiness check is treated as wanting EU funding. Confirm the default.
- **Regional agency.** No primary source in the repository names IVACE or the Cámara de Valencia, so the sentence says "your regional
  development agency". A sourced name per region can be added to `lib/es-support.ts` (held to the research file by `wp80.check.ts`).
- **What prints.** On paper the demand map shows each winner's newest notice only and no source addresses; the per-company value details
  print as their summary line. Say if any of it must be on paper.
- **/buyers with a CPV code** lists the buyers with at least one tender under it and keeps their total counts; a count under the codes per
  buyer (and an order by it) is possible but needs the collapse rules per request (the 5 s budget): not built.
- **Synonym codes.** For castings, forgings, machined parts and stampings the CPV has no product code; the entries point to the part codes
  (34320000, 34330000, 35421000, engine parts, shafts). Checked against the vocabulary, not against archive notices of those products.
- Spanish labels: not done (owner: not now).
