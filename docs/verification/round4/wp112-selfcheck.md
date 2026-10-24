# WP-112 self-check: supplier report, supplier pages, market (round 4, persona re-check of 24 October 2026)

Branch `wp-wp112` (from `integration` e0d73b7). Findings: `D:\DEFENCEGATE TESTS\ux-oct24b\NOTES.md` (p01, p02, p03, p04, p06, p07)
and the persona folders there. Test copy `D:\DEFENCEGATE TESTS\wp112\`, Postgres `dgate-wp112` on 55512 (removed at the end). No
migration was needed (0124 unused). Production was read only: a handful of SELECTs and single API reads inside `dgate-api-1` /
`dgate-worker-1`, one public page fetch each for the Spain landing and the URO page.

## 1. "Too many requests" in two report sections; grey skeletons on the results page (p02)

Before: `shots/sup-report.txt` (p02): "Who to approach" and "Who buys what you make" both "Too many requests" 3 s after the results page.

Cause, found in three parts:
- The rate limit is per visitor address (`hardening.RateLimit`, 120 tokens, 2 a second; the demand map costs 5, the check 3). Ten auditors
  ran from one address, and every page they opened charged that one bucket (the header search alone costs 15). A refused request is told
  to wait 1-3 s (`Retry-After` = the tokens missing / 2), and the report retried **once**: in a busy shared bucket the second try lost
  again. The same address also explains the URO page without its "under your codes" line (item 7): its read with the codes was refused and
  the page fell back silently.
- The 10-minute tab cache was hit only when the results page's demand request had **finished**. That request takes 1.7 s on an idle server
  (machining codes, measured 16:57 UTC, load 1.1) and several seconds under load; a visitor who clicked "My supplier report" before it
  answered aborted it (the hook's AbortController) and the report asked again: two charges for one answer.
- The report's readiness call differs from the results page's for a supplier that wants no EU funding (only the supply routes): a second
  assess is needed there (its roadmap differs) and stays.

Change (`web/lib/answer-cache.ts`, `web/components/readiness/use-readiness.ts`):
- `shared(kind, key, run)`: one request in flight per answer, shared by every page of the tab; it is no longer aborted when the page is
  left, it is kept (`remember`) when it lands, and the report waits for it. A failed request is forgotten (a retry asks again).
- `fetchPatiently`: a 429 is waited out after each `Retry-After` as long as `PATIENCE_SECONDS` (30) of wall time since the first request
  are not used up, the requests' own time included, so a slow and busy API together never hold a section past ~30 s plus one request
  (p03: a report that had not finished after 60 s).
- Results page and report: while the demand answer is on its way, a visible status line ("Finding who wins these contracts: counting three
  years of defence notices under your codes in seven countries. This usually takes 5 to 15 seconds; if the server is busy, the page waits
  and asks again on its own.") above the skeleton (`Computing` in `demand.tsx`).

Not changed: the prices of the calls (they are what the work costs) and the per-address bucket (a shared office address is the side to err
on). Tests: `web/lib/wp112.check.ts` section 1 (two 429s waited out; patience in time; one request for two pages; a failure forgotten);
`web/e2e/wp112.spec.ts` "the results page says what it computes, and the report opened before the answer asks no second time" (demand
delayed 2.5 s, the click before it lands: one demand request, no "Too many requests").

## 2. Primes for the wrong trade; the Indra source five times (p02, p03, p06)

Before: p02 (uniforms/tents): Rheinmetall Electronics (1 contract, no value) and URO among the primes; primes at the same buyers Indra
308, Navantia 153, Rheinmetall Landsysteme 48. p06 (logistics): Indra, Navantia, Airbus ES after Thales; "Indra's 2026 supplier
selection for automotive firms (elDiario.es)" five times.

Checked on production: Rheinmetall Electronics won TED notice 118983 (IdZ-ES soldier system) with main code 18000000, the profile's own
code: a real match. URO's contract is PLACSP 390929, a supply contract of 23 codes from protective clothing to food, main code 18143000:
a catch-all notice. p06's Indra, Navantia and Airbus winners are real winners under the profile's IT services (72) and vehicle repair
(501) codes.

Change (`backend/dgate/demand.py`):
- A notice "names the trade" when its main (first) code is under one of the codes and it lists at most `CATCH_ALL_CODES` (20) codes
  (`trade` in the answer's statement). A winner without such a contract is ranked after those with one, is not listed past the first 30
  as a prime would be, and is marked `byOtherCodeOnly`; the answer counts them (`approach.byOtherCodeOnly`). The per-country top winners
  rank the same way. The report lists them apart: "Matched by an additional code only" (O-rings of a pipeline notice, URO's lot of a mixed
  supply contract).
- The primes at the same buyers count only contracts of the same trade (`trades`: the codes' divisions, in division 35 its group; vehicles
  34 and military vehicles 354 are one trade): a uniform maker no longer sees the shipyard and the radar maker.
- Indra is not in the SIPRI Top 100 of 2024 (the fact sheet's annex table, `fs_2512_top_100_2024.pdf`, read 24 October 2026: Navantia
  rank 88, no Indra), so its mark rests on the elDiario.es report alone, which is about vehicle makers' suppliers. `ONLY_FOR`: Indra is
  marked for codes under 34 or 354 only. Every other group is marked as before.
- The source line of a prime is printed once per group in a list (`firstOfGroup`), not under each member.

Tests: `tests/unit/test_wp112.py` (Indra by codes, a UTE of Indra and Thales falls to Thales, `trades`); `tests/integration/test_wp112.py`
(the additional-code and catch-all winners after a one-contract winner of the trade, counted; the Indra mark for IT and vehicle codes);
`tests/integration/test_wp105.py` primes-at-buyers updated to the rule: Indra's other contracts there are military-vehicle parts now, and a
radar prime at the same buyer must not be listed (stricter than before); `wp112.check.ts` section 2; `wp112.spec.ts` (side group, source
lines 2 for 3 primes).

## 3. Source captions (p03, p04, p06)

Before: `/companies?country=PL&cpv=353`, `/suppliers?buyerCountry=NL&cpv=60`, German companies: "Origen de los datos: Ministerio de
Hacienda (PLACSP)" and the "TED and PLACSP" source choice. `/market?country=PL&cpv=353,2461`: "Poland: TED + e-Zamówienia" over a count of
three sources (Atlas Przetargów 5.2 %).

Change: `/v1/suppliers` says whether one of the page's companies has a PLACSP win under the filters (`placsp`); the list's credit line,
the source choice and the "TED only" link follow it (an older answer without the field keeps the map's credit). The supplier page and the
buyer's top suppliers already credit by their own rows; their dates now say whose records they are ("this company's award results there
as last updated on 2026-10-07", item 9). `/market` words its coverage line from the sources its count holds (`countedLine`): "Poland: TED +
e-Zamówienia + Atlas Przetargów (a one-off load of its archive of past notices)". Tests: integration `test_the_supplier_list_credits_placsp_only_for_a_page_with_its_wins`;
`wp112.check.ts` 4; `wp112.spec.ts` (PL page: TED credit only; ES page: PLACSP credit).

## 4. Market (p01, p04, p06)

- Scope switch: `/v1/stats/market?scope=relevant` counts all defence (the tender list's default), with a country or codes only (422 for the
  whole market: the 36-month series of that scope has no index of its own and could spend the 5 s budget cold). The page has "What is
  counted" (Military goods and works / All defence), names the scope in its sentence and figures, and links the tender list in the same
  scope; its basis text says what is counted. Test: integration `test_the_market_counts_all_defence_on_request...` (0 core vs 3 relevant
  transport notices for NL/60; 422 without a filter).
- Groups: with codes asked, the CPV groups are those under the codes (as the money table already was): the jewellery, luggage and sports
  codes of the matched notices are not listed under ammunition codes. Every 3-digit group has its official title now
  (`web/lib/data/cpv-groups.json`, 317 titles taken from the full vocabulary file; "374 Sports goods and equipment", "246 Explosives").
  `ui.check.ts`: 452 now has its own title (the division fallback was for a title we did not hold).
- Spain's directive share: checked, not stale any more. Production: all 2,861 Spanish defence notices that name Ley 24/2011 have
  `sig_legal_basis` true; the live landing `/readiness/spain-automotive` reads "Spain: 705 procurements ...; under Directive 2009/81/EC: 213
  of 705 (30 %)" (24 Oct, 16:5x UTC). The 5 % of the audit was the page's hourly cache from before the re-classification. No recompute needed.

## 5. Sums explained (p06, p07)

Before: Seko Benelux "EUR 15,867,768 over 1 contract" for three contracts (two framework ceilings, 21 M and 8.4 M, not said); buyer page
"EUR 24.3 M over 2 contracts" in a row of 3; Leonardo "10 + 2 SEK + 4 no value" of 18 (2 frameworks, 54 M BGN, unsaid).

Change (`web/lib/value-totals.ts`): the summary line of every "Contract values" block accounts for every contract and says that ceilings
are not added: "EUR 10,000,000 over 10 contracts; SEK 5,000,000 over 2 contracts; of the 18 contracts, 2 with a framework ceiling only, 4
with no value for this company alone (ceilings, estimates and unit prices are not added)". The company list and the buyer's top-supplier
cells add "; N more with a framework ceiling, an estimate or no value of their own (not added)" (`restNote`). The different figures of
Seko Benelux on different pages are different scopes (all codes at the buyer: 24.3 M over 2; under CPV 60: 15.9 M over 1); each line now
says what it leaves out. Tests: `wp112.check.ts` 3 (the Leonardo and Seko cases); `wp81.check.ts`, `wp98b.check.ts` expectations updated to
the new, fuller words (the old ones asserted the incomplete line).

## 6. Supplier CSV (p07)

`/v1/suppliers/{slug}/contracts` names the supplier as its page does (the spelling most notices use, mixed case first: "Leonardo
S.p.A.", not the stored "LEONARDO - SOCIETA PER AZIONI") and carries its registration numbers; the CSV has a `company_number` column
after `supplier`. Shared code: `suppliers._stated` (the page and the file use the same statement). Tests: integration
`test_the_supplier_file_carries_the_page_name_and_its_numbers`; `wp112.check.ts` 5.

## 7. Codes on the report path (p01, p02, p06)

- URO page without "N of them under your codes": the API answers it (production: 33 of URO's contracts under the ten automotive prefixes,
  0.48 s); the page's read with the codes was refused (the shared address, item 1) and the page fell back to the plain profile without a
  word. Now the fallback says "How many are under your CPV codes could not be read just now; reload the page in a minute." (a 422 for
  unreadable codes stays silent, as before).
- The army's top suppliers led by a vehicle maker: the report's buyer links carried no codes. Every buyer link of the report (who buys,
  wins most from) now carries the profile's codes as prefixes (`buyerHref`); production check: Estado-Maior do Exército under the textile
  codes lists Lucro Exponencial, OUM, Vitor Xavier (3 contracts), without them URO first (19).
- Services results heading: "Who buys what you sell" for a services company (`providesServices`).
- FR/NL winners under automotive codes: France's test benches are CPV 34328100 "Test benches", which the official vocabulary files under
  343 (vehicle parts): a match by the vocabulary, kept. NL's O-rings come from a pipeline notice (main 44160000) with 34312500 as an
  additional code: now ranked last and marked (item 2).

## 8. ASAP and the ammunition call (p04)

- ASAP ended / EDIP replaced it: no primary source held (EUR-Lex refused the automated read of Regulation (EU) 2023/1525, both the TXT
  and HTML forms); left as it is, per the brief.
- Call 118 "What it funds": checked against the topic document in the raw store (`eu_portal/2026/10/02/run-topics-0000.jsonl.gz#0`,
  EDF-EDIP-USI-2026-LS-IRA-MAB): "production/integration of sensing and effector modules" and "scale-up of UA systems and ready-to-use
  production lines" are the call's own words (UA is Ukraine in this topic: "delivery in UA"). Kept.

## 9. Phone and dates (p02)

- The buyer-country filter of /tenders and /buyers: the chosen countries first, then by English name (`countryOrder`); Portugal is no
  longer below twenty countries ordered by volume.
- Torfal: 2026-10-07 is the newest PLACSP record behind Torfal's own wins, 23 Oct the newest of the whole map; the page now says "this
  company's award results there as last updated on 2026-10-07".

## Added from the coordinator (p03)

- `/requirements?country=DE`: ISO 9001 and EN 9100 said "Appears in the rules of Spanish defence supplier (MoD)". Another country's own
  route is left out of that line; where only such a route names it: "No rule we hold for Germany names it; we hold it from the rules of
  Spanish defence supplier (MoD) only." No German or NATO basis is put in its place (none held). `appearsLine` in `lib/readiness.ts`.
- Report slower than 60 s (machining): measured on production after the auditors' peak (16:57 UTC, load 1.1): demand 1.74 s, winners page
  0.49 s for the machining codes with home DE. The minute-long wait was the retry path under 429s and 10 s proxy timeouts; now bounded
  (item 1).
- `/companies` with German companies: item 3.

## Files outside the package

`web/components/tenders/filter-bars.tsx` and `web/lib/taxonomy.ts` (`countryOrder`, item 9), `web/app/(public)/requirements/page.tsx` and
`web/lib/readiness.ts` (`appearsLine`), `web/components/market/buyer-suppliers.tsx` (`restNote`), `web/lib/cpv.ts` and
`web/lib/data/cpv-groups.json` (group titles), `web/lib/ui.check.ts`, `wp81.check.ts`, `wp98b.check.ts` (expectations of changed words),
`backend/tests/integration/test_wp105.py` (primes at buyers by trade), `backend/tests/integration/test_wp89.py` (the market's groups under the codes asked: 343 only, and 343 and 354 without codes), `web/e2e/wp66.spec.ts` (buyer link with the codes), `web/e2e/wp98b.spec.ts` (the fuller list value line), `web/e2e/wp100.spec.ts` (the `company_number` column), `web/lib/mock/demand.json` and `web/lib/mock/suppliers.ts`
(the new fields).

## Ops on production

None. No data is written; the answers change with the code. The market's and the lists' caches renew within the hour.

## Results

- Backend (test copy, Postgres 17 on 55512): ruff clean; unit 3,775 passed; integration 1,365 passed (the one failure of the first run, `test_wp89::test_the_market_takes_a_cpv_filter`, was the old group rule; updated, its file re-run green).
- Web: `tsc --noEmit` clean; `node scripts/run-checks.mjs` all green (`wp112.check.ts` new); `next build` green; Playwright full suite 816 passed, 61 skipped, 1 failed: `digest.spec.ts` conditional request (304 expected, 200 under four workers on a shared machine), green on its own re-run (15 passed); WP-112 spec green on desktop and 375 px.
- `wp112.spec.ts`: the company-list credit is shown only for a page without PLACSP wins (the demo map holds no PLACSP source); the per-page rule is tested on the API.
