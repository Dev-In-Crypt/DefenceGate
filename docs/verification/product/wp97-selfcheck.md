# WP-97 self-check: the supplier report for every country and for services (persona round of 23 October 2026, B)

Branch `wp-wp97` from `integration` (9693f6a, WP-94/95/96 in). Input: `D:\DEFENCEGATE TESTS\ux-oct23\SUMMARY.md` section B and the
evidence of p01-es-auto, p03-de-machining, p04-pl-ammo, p06-nl-logistics (problems.csv, dumps, screenshots). No deploy, no push, no
production read or write, no procurement portal called. Not touched: the WP-88 copy rule (one sentence before content, the rest
collapsed), the WP-93 verdict logic, the WP-95 value logic (buyer amounts reuse `suppliers.value_of`, `best`, `value_totals`).
No Spanish translation; commercial information only (no technical data of any product).

## 1. Own country first, words by country and kind of codes

- `lib/demand.ts` `ownFirst`: the company's country first in "Who buys" (results table and report sections), in the primes and the
  new dealers group; "Open now" first on the results page and in the report (`r-open` is the report's first section).
- `lib/cpv.ts` `codeKind`: services (most codes in CPV divisions 50-98), automotive (the set, or 341/342/343/3542), machining,
  ammunition, other goods. `components/readiness/approach.tsx` `INTRO`: one sentence per kind. The Indra/elDiario paragraph only for
  `country === 'ES'` and automotive codes (`spanishAutomotive`); the Murcia CAETRA guides only for a Spanish company (report `Support`);
  the Spanish regional grants were already Spain-only.
- Home: the "I make parts" button goes to `/readiness/supplier` (it opened the Spain automotive page for every visitor).

## 2. Country routes

- `lib/country-routes.ts`: Germany and Poland lines, every fact from a source already in the repository:
  BAAINBw and the federal notice service (oeffentlichevergabe.de, operator Beschaffungsamt des BMI: `docs/sources/de_national.md`,
  BAAINBw seen in the day files), BAFA export licences (AWV § 8 and § 11, AWG § 13: rule DE-EXPORT-BAFA of `seeds/requirements.json`),
  GHB admission applied for by the contracting party and free of charge (BMWE FAQ, rules DE-GHB-*), Agencja Uzbrojenia and the
  Regional Logistics Bases (our buyer data, `seeds/defence_buyers.csv`), e-Zamówienia (`dgate/sources/ezamowienia.py`). What no source
  in the repository settles says "Not covered yet for <country>: ... Check with <body>": NCAGE office (NSPA), AQAP in Germany (the buyer
  named in the tender, for the Bundeswehr BAAINBw), Polish weapons/ammunition/explosives licences and industrial security certificate
  (the buyer, e.g. Agencja Uzbrojenia), Polish military export authority. Other countries get one "Not covered yet" line and the NCAGE
  line. No issuer, cost or time is invented (`lib/wp97.check.ts` holds every external link to a file of the repository and no figure).
- Shown on the roadmap, in the report's step plan and on `/requirements?country=XX`. With a country other than Spain chosen, the
  Spanish route's requirements (RID, PECAL, REOCE, HSEM, HSES: `profile.requirementCountry`) are hidden on `/requirements`, with a
  line and a link to Spain's.
- NCAGE: one sentence (`readiness.ncageText`) on the requirements page, the roadmap step, the report's "Issued by" (it printed
  "National codification bureau (NCB) of the country") and the route line.

## 3. Services path

- `/check`: a third card "Supply services to the armed forces" -> `/readiness/supplier?offer=services`.
- Supplier profile: "Do you sell products or services?" (the wizard's `offering`, same answer); services: "What you provide",
  `SERVICE_PROCESSES` (logistics, transport, fuel, facility, catering, maintenance and repair, training, IT services); certificates
  VCA, ISO 14001, ISO 45001, ISO 50001 added (ISO/IEC 27001 was there); no rule reads them.
- `lib/cpv.ts` `CODE_SETS`: automotive (unchanged), precision machining and aerospace parts, ammunition and explosives (3533, 3534,
  2461x), services (60000000, 63100000, 09100000, 79993000, 90900000, 55500000, 50100000, 80600000, 72000000: vehicle repair 501 and
  defence training 806 rather than whole divisions 50 and 80, which match too many notices for one map). Every code is in the CPV
  2008 vocabulary (check).

## 4. Primes and dealers

`backend/dgate/demand.py` `PRIMES`, added with the page read on 23 October 2026:

| Group | Source |
|---|---|
| URO Vehículos Especiales | company page https://urovesa.com/en/ (VAMTAC, "More than 20 years of service in the Spanish Armed Forces") |
| Iveco Defence Vehicles (Leonardo) | Leonardo press release 30 July 2025 https://www.leonardo.com/en/press-release-detail/-/detail/30-07-2025-ldo-iveco-defence |
| Escribano Mechanical & Engineering | EDR Magazine, FEINDEF 2025 https://www.edrmagazine.eu/feindef-2025-escribano-unveils-two-new-turrets-the-guardian-30-t-and-the-guardian-2-0-pro-and-a-mock-up (escribano.com is a parked domain; the FEINDEF exhibitor page answered 403 to automated reading) |
| Rheinmetall Expal Munitions | already marked by "rheinmetall" (SIPRI); Rheinmetall's subsidiary page confirms it is wholly owned since 1 August 2023 |
| GDELS-Santa Bárbara, Navantia, Indra | already on the list (FEINDEF, SIPRI, elDiario.es) |

Civil namesakes stay unmarked ("Iveco España", "Talleres URO"). `distributor_of`: a winner whose name says Recambios, Repuestos,
Neumáticos, Ferretería, Tyres/Tires/Reifen, Euromaster, Distribución(es), Suministros industriales is listed under "Competitors and
distributors" (not a customer), never among the direct suppliers or in the results' short list. `ponytail:` name words, no register.

## 5. Open now and buyer amounts

- `demand.open_now`: per country of the answer, the `/tenders` default view's conditions (`tenders._tender_filters`, status open,
  scope relevant) and collapse rules, counted with `_count_up_to` to 200 in 400 ms per country (past the cap "at least 200"; out of
  time no count, the link only), with `href=/tenders?country=XX&cpv=<the answer's prefixes>`. Integration test: equals
  `GET /v1/tenders?country=ES&cpv=343&status=open` `total`. A country outside the five gets the link without a count.
- `demand.buyer_values`: per listed buyer family (top 10 per country), the contract values of its award rows under the codes,
  `value_of` per row, `best` per procurement and winner, `value_totals(...)["byCurrency"]` (contract values only, never ceilings or
  estimates, per currency). Shown as "Awarded: EUR ... over N contracts" under each buyer.

## 6. Short printable report

"Print the short version (5 to 10 pages)" and "Print the full report". Short: open now, ten direct suppliers of the own country and
five primes, buyers with amounts (own country ten, others three), the step plan with the national route; no appendix, no explainer,
no per-country winners or notice lists, no source quotes. Grants: each printed in full once, later steps name it with a pointer;
"Check the current call" once. The report now asks the programmes the roadmap asks (no PIC for a supplier that does not want EU
funding).

Page counts (A4, Chromium PDF of the e2e, demo demand answer): ES automotive short 10 (full 33), DE machining short 6, NL services short 5.

## 7. Missing answers

- Follow-up questions are asked once their parent is "yes" or "I am not sure" (they were hidden after "not sure"): the persona's three
  "referenced but missing" questions (PECAL nine months, PECAL prior contract, classified storage) now exist on the page for her answers.
- `askedAt(field, supplier, profile)`: a question's own field (`#q-<field>`); while hidden, the field that shows it (recursively).
  The check walks every Spanish and German question for five profiles and asserts the anchor is a question the page shows.
- `notSure`: "I am not sure" is listed apart ("the rule stays open"), not counted as missing (results cards and the report's appendix).
- `/readiness/results?from=supplier` (the supplier page's save): title and crumbs "Your supplier report", "Change my answers" -> the
  supplier profile.

## Tests (local, `D:\DEFENCEGATE TESTS\wp97`, Postgres container dgate-wp97 on 55497, E2E_PORT 3097)

- ruff: clean. Unit: see the run below. Integration (full): see the run below.
- New: `tests/unit/test_wp97_approach.py`; WP-97 cases in `tests/integration/test_wp80_approach.py` (dealer flag, buyer amount =
  contract values only, open count = tender list total); `web/lib/wp97.check.ts`; `web/e2e/wp97.spec.ts` (five scenarios, desktop
  and 375 px). Fixtures `assess-{es-auto97,de-mach97,pl-ammo97,nl-svc97}[-routes].json` computed by `readiness.api.assess_payload`
  over the seed for the persona profiles.
- Changed expectations (the WP-97 behaviour, not weakened): wp65/68/73 results URL `?from=supplier`; wp67 the report's request carries
  the routes; wp68 the home link; wp73/wp68 links to the question not its block; wp73 an HSEM "not sure" is listed apart; wp80 the
  report's first section `r-open` and dealers apart; wp89 the code-set status text and dealers; wp91 the NCAGE sentence;
  `test_wp80_primes` Escribano is now a marked group.
- Screenshots: `docs/verification/product/wp97/`.

## Open decisions

1. Production timing of the two new statements (buyer values, five open counts) is not measured: the open counts are time-boxed
   (5 x 400 ms worst case), the buyer values statement is not; measure on the server before deploy.
2. The services set uses 501 and 806 instead of whole divisions 50 and 80; whether the services set as a whole stays under the
   30,000-notice cap on production is unmeasured (else the map says "too broad").
3. Dealers by name words only; JPG ("reconstrucción y recambios") falls into it. Excluding codes (tyres 3435) in the profile was not built.
4. Germany/Poland: NCAGE offices, AQAP authority in Germany, Polish licensing and export authorities need primary research before
   they can replace the "Not covered yet" lines.
5. The Indra source line stays elDiario.es (shown with Indra as a winner to any country); a company page could replace it.
