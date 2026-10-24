# WP-104 self-check: entities (persona round of 24 October 2026)

Branch `wp-wp104` (from `integration` 24e5295). Test copy `D:\DEFENCEGATE TESTS\wp104\` (own venv, Postgres 17 on port 55504).
Production read only: SELECTs through the postgres container and dry runs of the changed modules (loaded in memory in the
worker container, `SET TRANSACTION READ ONLY`, nothing written), 24 October 2026 about 12:40 to 15:30 UTC.

The owner's rule applied throughout: companies with different registration numbers, or recorded with a different number,
are different companies; a merge needs evidence (one identifier, the same company in the source) and is stored with its
method and confidence, with an undo path.

## 1. /buyers/9770: the Polish Ministry of National Defence under the Cyberspace Resources Centre (the cause)

**Before.** `organisation` 9770 *centrum zasobow cyberprzestrzeni sil zbrojnych* (PL) is not merged with anything: no row has
`merged_into = 9770`, its aliases are its own name only. The ministry is in its **buyer family**:
`buyer_family_member (org_id 13000 'ministerstwo obrony narodowej', head_org_id 9770, method twin_notice, confidence 0.85,
created 2026-10-23 18:24)`. The buyer page shows the family, so the centre carried the ministry's notices (catering,
training: "4,023 tenders").

**Cause.** The WP-96 twin rule (`ops/buyer_families.twin_groups`) moves a buyer row into the family of the buyer of the TED
notices its national copies point at. It counted only the copies whose TED twin is under *another* row
(`twin_pairs` had `o.buyer_org_id <> t.buyer_org_id`), so any number of them, however few, moved the row. The ministry has
135 Baza Konkurencyjności/e-Zamówienia copies (`pl_atlas`, `stated_ted_ref`) of TED notices: 107 are its own TED notices,
28 are TED notices the centre published (IT and telecom purchases: "Dostawa sprzętu informatycznego", 718194-2025;
"Świadczenie usługi telefonii komórkowej", 145866-2024 ...), where the national bulletin names the ministry, the legal
entity, as the buyer. 28 against 0 counted moved the whole ministry (990 notices) under the centre. No organisation merge
was involved; the "merge" is this display-layer family row.

**Change.** `twin_pairs` returns the pairs whose two rows are one row too (a copy of the row's own TED notice is a vote to
stay), and `twin_groups` moves a row only when more than half of its twinned copies point at one other buyer.
`ops.buyer_families` prints every row it would set or remove before it writes (`--changes` prints only those).

**Undo path.** The family table is rebuilt by its rules; the run removes the row. The worker's daily job runs it too
(`worker.py`), so after the deploy the next daily run also removes it.

**Test.** `tests/unit/test_wp104.py::test_a_buyer_whose_copies_mostly_are_its_own_ted_notices_stays_itself`,
`tests/integration/test_wp104.py::test_the_ministry_is_taken_out_of_its_cyberspace_centres_family` (the stored wrong row is
reported as `remove`, written away, the centre's page counts its own 3 open notices only, a second run writes nothing).

**After (production dry run).** `remove 13000 -> 9770 twin_notice 0.85 [copies: own 107, others 28]`. The same rule takes 26
other twin rows out (listed in the appendix); most are like this one (a ministry under one of its units: `ministere des armees
-> minarm sga sid sid med sd-ac`, own 6 / others 2; the Public Procurement Office under the Military Gendarmerie, own 0 but
its 6 copies split 3 and 3 between two buyers; an administrative court under the police logistics centre) or ties of one copy each.
A few were right by name and are now kept by a name rule instead (the Land Forces Academy with and without its patron:
new `_PL_PATRON` spelling). Ties stay apart: a wrong family is worse than none (`buyer_family` module rule).

## 2. Buyer families (display layer, `buyer_family.py`)

| Item | Before (production) | Change | After (dry run) |
|---|---|---|---|
| NAVARM | `navarm` 241281 (1 notice), `direzione degli armamenti navali - navarm` 257932, `ministero della difesa direzione degli armamenti navali` 39770 (25), the SGD/DNA long names (68799, 68 ...) all separate | rule `it_navarm` (`armamenti navali`, `navarm`) | one family, head 68799 (20 rows set; TERRARM 28, ARMAEREO 13, NL 12, PT army 14, PT air force 17, BAAINBw 2) |
| DAT 91425 / 91363 | 91425 *ministero della difesa sgd-dna direzione degli armamenti terrestri* (96) and 91363 (15) separate, 30 more spellings | rule `it_terrarm` (`armamenti terrestri`, `terrarm`) | one family, head 91425 |
| DAA 42679 / 200153 | 42679 (101) and 200153 (23) separate, 20 more spellings | rule `it_armaereo` (`armamenti aeronautici`, `armaereo`) | one family, head 42679 |
| NL MoD English | *netherlands ministry of defence* (3), *dutch ...* (2), *the netherlands ministry of defence modnl*, *ministery of defence*, *nld/nl ministry of defence*, *royal netherlands air force logistic centre woensdrecht* (24), *royal netherlands navy/air force* outside the family | `nl_defensie` reads the country in front, the misspelling and the armed services in English | all in the ministry's family (head 215). *department of defense* (whose?) left alone |
| BAAINBw variants | 246716 *bundesamt fur bundesamt fur ausrustung ...*, 239304 *bundesamt fur informationstechnik ausrustung und nutzung ...* separate | `baainbw` rule takes the doubled start and the swapped words | both in 196's family |
| Hochbauamt "vertreten durch" | *Bundesrepublik Deutschland vertreten durch das BMVg dieses vertreten durch ... Staatliche Hochbauamt Ulm/Schwäbisch Hall* (121 and 39 notices) separate from the Hochbauamt | DE spelling: the office the last "(end)vertreten durch" names (two words or more), "Staatliche" = "Staatliches"; the rules read this spelled name too; a family is headed by a row without "vertreten" where one exists | Ulm family head 92202 *staatliches hochbauamt ulm* (members 344, 32228, 85325, 88904); Schwäbisch Hall head 107866; the same for Freiburg, Karlsruhe, Heidelberg, Staatliches Baumanagement Niedersachsen, GMSH, Logistikzentrum Baden-Württemberg, BBR, Beschaffungsamt des BMI ... (appendix) |
| PT Exército / Força Aérea | army: 62149 *estado-maior do exercito* (683), the logistics command (31947, 41), the Repartição, *estado portugues - mdn - exercito portugues* separate; air force: 102440 (760) with only 120583, *mdn forca aerea dat*, *forca aerea direcao de abastecimento e transportes*, CLAFA, academy separate | rules `pt_exercito` (`exercito`), `pt_forca_aerea` (`forca aerea`, `fap`) | army family head 62149, air force family head 102440. The Navy (Marinha) was not reported and is left as it is |
| JW 4724 | one buyer row (8654) on production; the report named it 'Jednostka Wojskowa 4724' for one winner and 'Skarb państwa - Jednostka Wojskowa 4724' for another | `demand.py` (`apb`): a buyer in a winner's "wins most from" line is named as the answer's buyer list names it (its commonest spelling over all notices of the answer), not per winner | one name per buyer in one answer; also fixes BAAINBw "...und Nutzung" / "...Nutzung der Bundeswehr" in those lines |

Tests: `tests/unit/test_wp104.py` (`test_the_three_italian_armament_directorates_are_one_buyer_each`,
`test_dutch_ministry_english_variants_join_the_ministry`, `test_german_office_variants_and_represented_offices_are_one_buyer`,
`test_a_family_of_spellings_is_headed_by_its_plain_name`, `test_portuguese_army_and_air_force_units_are_one_buyer_each`),
`tests/integration/test_wp104.py::test_a_buyer_is_named_alike_in_every_winners_lines`.

Dry run on production with all of it: 844 groups, 1,597 members; **175 rows set, 28 removed** (exact list in the appendix).

## 3. Supplier merges (`ops/supplier_dedupe.py`)

**Before.** `python -m dgate.ops.supplier_dedupe` on production (dry run): 11,313 winners, **0 groups**; left alone
`different_company_numbers 66, different_legal_forms 17`. One conflicting number anywhere in a set of rows a rule links kept
the whole set apart.

**Change.**
* Joins are made numbers first, names second, and only where no part has a conflict among the parts it would be joined to.
  A conflict keeps apart the rows it concerns; a row without a number that two conflicting companies could be is joined to
  neither (Rheinmetall Electronics).
* `company_number_division` (0.95): one company number, and one name is the other's followed by a division word
  (division, divisione, divisão, divisie, Geschäftsbereich, Sparte). A name that merely begins with another is never enough.
* One number in two countries joins only under one name key, and only where the country is decided (`group_country`: the
  country the legal form allows, else the one with more than half of the award rows; a tie decides nothing). The head is a
  row of that country. The other row's award rows move to it first, recorded in `organisation_country_fix` (basis
  `company_number_twin`); the row keeps the country its notices stated (`db.merge_organisations(allow_other_country=True)`,
  which never moves a number across countries). `--undo-batch FROM TO` undoes the merges and then the country corrections
  of the same window.
* Keys: the Spanish state-company mark (S.M.E., SME) and the misspelt *Società per Azione* are legal-form tokens
  (`resolution/names.py`); an Italian name's leading *Società* is dropped where the name states S.p.A./S.r.l. (`core_key`).
* The report prints every pair it would merge (`pair HEAD <- MEMBER method confidence`).
* Owner decisions of 24 October (second commit):
  * `stated_number_prefix` (0.90): a row with no number of its own whose award rows state a number the other row
    holds, and whose name begins with the other's (Navantia Sistemas). Never when the rest of the name brings a legal
    form or a partnership word (UTE, Sp. J, Sp. K, S.L. ... SL UTE) or a joining sign or word the other name lacks
    (-, &, +, /, comma, y/e/i/und/and/et/en): the dry run without that guard took joint ventures and partnerships
    (JUMABEDA ... UTE, SERANCO S.A.U.- PRACE S.A., CLAYMORE Sp. z o.o. Sp. J, STAR SAN DUO ... Sp. K., Seyntex-Sioen),
    which stay apart.
  * `curated_source_review` (0.90): `REVIEWED` in `ops/supplier_dedupe.py`, rows a person read in the source, found by
    the company row's number and the other rows' folded names (rows of those names holding a number are never taken),
    with the evidence stored in `organisation_merge_candidate.evidence`. Entry: Works 11 Sp. z o.o.
  * Both methods are in `METHODS`, so `--undo-batch` undoes them.
  * Award rows: a merge never moves an award row (`award.organisation_id` stays; the supplier map reads
    `COALESCE(merged_into, id)`), so the `(opportunity_id, organisation_id)` key is never touched where both names are
    winners of one notice (753670-2023, 629838-2023): both rows stay, the procurement counts once for the company
    (`count(DISTINCT key)`), and undo needs nothing more than clearing `merged_into`. Tested.

**Tests.** `tests/unit/test_wp104.py` (`test_a_conflicting_row_no_longer_keeps_a_shared_number_apart`,
`test_a_row_without_a_number_between_two_numbers_joins_neither`,
`test_one_number_in_two_countries_is_one_company_where_a_country_is_decided`,
`test_divisions_typos_and_the_state_company_mark_are_the_company`, `test_keys_of_the_state_company_mark_and_the_misspelt_form`,
`test_a_row_without_its_own_number_joins_the_row_its_stated_number_names_under_its_name`,
`test_the_reviewed_works_11_variants_join_the_company_row`, `test_pilatus_constructions_aeronautiques_is_listed_in_the_pilatus_group`);
`tests/integration/test_wp104.py::test_reviewed_variants_and_a_stated_number_merge_with_their_evidence_and_undo` (both names
winners of one notice: both award rows stay, the company's count is 2 procurements, evidence stored, undo);
`tests/integration/test_wp104.py::test_shared_numbers_merge_across_a_conflict_and_a_wrong_country_with_undo` (merge, the
award rows' country, the fix record, idempotent, undo puts back merges and countries). The WP-96 tests stay as they were and pass.

**After (production dry run with the new code, owner decisions included): 42 groups, 52 rows** (exact pairs in Appendix B).
Left alone:
`different_company_numbers 67, different_legal_forms 17, spacing_on_a_short_key 7`.

The persona items:

| Item | Production evidence | Result |
|---|---|---|
| Heckler & Koch x2 (x5 rows; merge of 428135 confirmed by the owner) | 427567 *Heckler Koch GmbH* (27 awards, HRB 481250, N0047964B), 431166 (N0047964B), 427723 (N0047964B), 428135 *Heckler und Koch* (DE232899163 in TED; N0047964B in a PLACSP notice), 433974 *HECKLER AND KOCH GMBH.* (PLACSP code 0000CGC00430 only) | 431166, 427723, 428135 merged into 427567 (`company_number` 0.97: N0047964B, the Spanish tax number of the company, stated for each). 433974 stays (another number). 428135 is also recorded with DE232899163 (a VAT number; 427567's own is a register number, another kind): merge confirmed by the owner |
| Rheinmetall Electronics GmbH x3 | 426698 DE811127845 (32 awards), 428360 DE119356818 (4; the same number is stated for Rheinmetall Project Solutions GmbH, so probably a group VAT number), 430165 DE251121155 (1) | **not merged**: three numbers; the owner decided to keep the three rows separate |
| Leonardo variants and divisions | 426671 Leonardo S.p.A. (00401990585 / 00881841001) | merged into it: 437203 *Leonardo, Società per Azione* (00881841001, `company_number`), 430393 *... Aircraft Division* and 431219 *... Divisione Sistemi di Difesa* (00881841001, `company_number_division`), 439305 *SOCIETA LEONARDO S.P.A.* (`name_key`). *Leonardo Spa_149684* (0006001333) stays: another number |
| Leonardo group, group total | group view listed 6 companies; PZL-Świdnik (427593) and Leonardo Belgium (431099) outside; no total | `ops/company_groups`: PZL-Świdnik (with or without the parent's name) and Leonardo Belgium added; `/v1/suppliers?group=` returns `groupTotals` (the companies' contract sums per currency, never converted) and the page shows "Group total of contract values: ..." under the group note (its copy no longer says nothing is added up) |
| Pilatus (check) | 428700 *pilatus aircraft ltd* CH (16 awards, 15030004652 stated in TED 28855-2025), 439344 *PILATUS AIRCRAFT LIMITED* BG (3 awards, Bulgarian notices, 15030004652), 429359 *PILATUS Constructions Aéronautiques SA* CH (1 award, no number) | 439344 merged into 428700 (one number, one name; its award rows to CH). 429359 stays: no number and another legal form; owner decision: kept separate (its stated name is not Pilatus Aircraft Ltd's, no number) and listed with the others in a new curated company group `pilatus` (display only; source: Pilatus Aircraft Ltd's company information) |
| Navantia SA Sme | 427121 *NAVANTIA SA, SME* (204 awards, A84076397), 420165 *NAVANTIA S.A.* (54, A84076397) | merged (`company_number`), head 427121. The display keeps "SME" in capitals (web `display-name.ts`: it is the state-company mark S.M.E., not a size label): "Navantia SA, SME". *NAVANTIA SISTEMAS* 429848 (both its award rows state A84076397, no number of its own): merged into 427121 (`stated_number_prefix` 0.90), owner decision |
| Elbit C4I & Cyber x3 | one Israeli row 411947 (514046283, two spellings of one row) and one Spanish row 431178 (A79201430, a Spanish company number) | not merged: two numbers, two companies |
| BSS Holland BV / B.V. | one row (428058, 34310311) | no duplicate row; the two spellings are the names as published, printed where a page shows the stated name |
| Thales Nederland x2 | one row (409486); "1 contract" in the report is the count under the report's codes, 5+ on /companies all codes | no duplicate row |
| Works 11 / Works (check) | 428445 *WORKS 11 Sp. z o.o.* (19, NIP 6462895170); 439434 *Works Sp. z o.o.* and 439544 *WORKSS - 11 Sp. z o.o.* stand as second winners in the same notices as Works 11 (753670-2023, 629838-2023), 439885 *Works11 Sp. z o. o.* (315699-2023); none of the three has a number | owner decision from the source: 439885, 439544, 439434 merged into 428445 (`curated_source_review` 0.90). Evidence: 'Works11 Sp. z o. o.' TED 315699-2023; 'WORKSS - 11 Sp. z o.o.' TED 629838-2023, which also lists 'WORKS 11- Sp. z o.o.'; 'Works Sp. z o.o.' TED 753670-2023, buyer JW 2305 (where Works 11 has 9 wins), which also lists 'Works 11 Sp. z o.o.' |

## 4. Display names (web `lib/display-name.ts`)

| Item | Before | Change | After |
|---|---|---|---|
| "Did Sds" (tender 269424, Direction d'Infrastructure de la Défense Saint-Denis) | "DID SDS" title-cased | a name of at most three words of at most four letters, all capitals, is a row of abbreviations and is not cased | "DID SDS" |
| "Navantia SA Sme" | "NAVANTIA SA, SME" -> "Navantia SA, Sme" | SME in the names' known abbreviations | "Navantia SA, SME" |

Test: `web/lib/wp104.check.ts` (also: a shouted name and a title are still cased as before).

## 5. Runs in the test copy

All in `D:\DEFENCEGATE TESTS\wp104\` against the worktree's code (`sync.ps1`, `backend-run.ps1`, `web-run.ps1`):

| Run | Result |
|---|---|
| ruff | clean |
| unit (`pytest`) | 3,658 passed (second commit; 3,655 at the first) |
| integration (`pytest -m integration`, Postgres 17 on 55504) | 1,326 passed (second commit, 14 min; 1,325 at the first) |
| web `tsc --noEmit` | clean |
| web lib checks (`node scripts/run-checks.mjs`, 52 files, `wp104.check.ts` new) | all ok |
| `next build` (mock) | ok |
| Playwright `e2e/wp104.spec.ts`, `e2e/wp96.spec.ts`, `e2e/suppliers.spec.ts` (desktop and mobile-375) | 26 passed (first commit; the second changes no web file) |

## 6. Files touched outside the package's own files

* `backend/dgate/demand.py` (WP-105's): the `apb` CTE names a buyer as `b` does (one line of SQL); test in `test_wp104.py`.
* `backend/dgate/suppliers.py` (WP-105's report parts; this is the list endpoint): `groupTotals` on `SupplierPage` and its
  query when `group` is asked.
* `backend/dgate/db.py`: `merge_organisations(allow_other_country=...)`, default unchanged.
* `web/app/(public)/suppliers/page.tsx`, `web/lib/api.ts`, `web/lib/mock/suppliers.ts`, `web/lib/value-totals.ts`: the group
  total; the group note's copy changed from "nothing is merged or added up across them" to "nothing is merged across them"
  (made true), and `web/e2e/wp96.spec.ts` asserts the new wording (same assertion otherwise).
* `web/lib/display-name.ts` (shared display helper).

## 7. Ops to run on production (orchestrator; each reports by default)

1. After the deploy: `python -m dgate.ops.buyer_families --changes` (expect about 175 set / 28 removed, including
   `remove 13000 -> 9770`), then `--yes`. The daily worker run would do the same.
2. `python -m dgate.ops.supplier_dedupe` (expect 42 groups, 52 rows, every pair printed as `pair HEAD <- MEMBER`), then
   `--yes`; keep the printed `--undo-batch FROM TO` line. Undo: `python -m dgate.ops.supplier_dedupe --undo-batch FROM TO --yes`
   (merges and the country corrections of that window).
3. `python -m dgate.ops.company_groups` then `--yes` (after step 2; PZL-Świdnik and Leonardo Belgium join the Leonardo
   group, the new Pilatus group lists Pilatus Aircraft Ltd and Pilatus Constructions Aéronautiques SA; dry run before the
   merges: 69 members, 12 to write).
4. The list caches refresh on their own (supplier list 5 minutes; the value orders at the next award load or within 4 hours).

## 8. Open items

* Owner decisions of 24 October applied (second commit): Rheinmetall Electronics stays three rows; Heckler & Koch 428135
  merged; Navantia Sistemas and the Works 11 variants merged; Pilatus Constructions Aéronautiques SA separate, in the
  Pilatus group.
* `stated_number_prefix` also merges, on production, 9 more rows of the same shape (IBM Deutschland's Flensburg branch,
  ETRA AIR, KenBIT Polska, Aerotechnika M & T, BARPIMO Coatings, Novelec Ebro, Continental Tyres, TKT Servicios, Ingloba):
  listed in Appendix B for review before `--yes`.
* Search finding NAVARM / TERRARM / ARMAEREO by abbreviation is WP-101's (the families now hold the rows).
* The Portuguese Navy (Marinha) units were not reported and are left as they are.

## Appendix A. Buyer families: every row the write changes (production dry run, 24 October 2026)

`member -> head method confidence (stored before)` | names (country, normalised name, first 70 characters). `[copies: own N, others M]` on a twin row: its national copies of its own TED notices and of other buyers'.

```
  set        438 ->  204949 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das bundesamt fur bauwesen ') -> ('', 'bundesrepublik deutschland vertreten durch das bundesministerium der v')
  set      11468 ->    9369 spelling_variant 0.9  (new) | ('', 'zespol szkol centrum ksztalcenia rolniczego im ks dr jana dzierzona w ') -> ('', 'zespol szkol centrum ksztalcenia rolniczego im ziemi dobrzynskiej w na')
  set      13325 ->    9369 spelling_variant 0.9  (new) | ('', 'zespol szkol centrum ksztalcenia rolniczego im wladyslawa stanislawa r') -> ('', 'zespol szkol centrum ksztalcenia rolniczego im ziemi dobrzynskiej w na')
  set      13578 ->     262 spelling_variant 0.9  (new) | ('', 'warminsko-mazurski oddzial strazy granicznej') -> ('', 'warminsko-mazurski oddzial strazy granicznej im gen bryg stefana pasla')
  set      18533 ->   21448 spelling_variant 0.9  (stored -> 21448 twin_notice) | ('PL', 'karpacki oddzial strazy granicznej imienia 1 pulku strzelcow podhalans') -> ('PL', 'karpacki oddzial strazy granicznej imienia 1 pulku strzelcow podhalans')   [copies: own 0, others 1]
  set      19085 ->    9369 spelling_variant 0.9  (new) | ('', 'zespol szkol centrum ksztalcenia rolniczego im michala drzymaly w brzo') -> ('', 'zespol szkol centrum ksztalcenia rolniczego im ziemi dobrzynskiej w na')
  set      22258 ->    9369 spelling_variant 0.9  (new) | ('', 'zespol szkol centrum ksztalcenia rolniczego im mjr pil wladyslawa szcz') -> ('', 'zespol szkol centrum ksztalcenia rolniczego im ziemi dobrzynskiej w na')
  set      25653 ->   25005 spelling_variant 0.9  (new) | ('', 'zespol szkol nr 2 im jana pawla ii w miechowie') -> ('', 'zespol szkol nr 2 im jaroslawa iwaszkiewicza-ckziu w katowicach')
  set      28605 ->  229666 spelling_variant 0.9  (new) | ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium des i') -> ('DE', 'beschafffungsamt des bmi')
  set      30148 ->   30146 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland endvertreten durch gebaudemanagement schles') -> ('', 'land schleswig-holstein endvertreten durch gebaudemanagement schleswig')
  set      31947 ->   62149 rule:pt_exercito 0.9  (new) | ('PT', 'ministerio da defesa nacional exercito portugues comando logistica') -> ('', 'estado-maior do exercito')
  set      32228 ->   92202 spelling_variant 0.9  (new) | ('DE', 'bundesrepublik deutschland vertreten durch das bmvg dieses vertreten d') -> ('DE', 'staatliches hochbauamt ulm')
  set      35089 ->  118723 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das bmvg dieses vertreten d') -> ('DE', 'staatliches hochbauamt freiburg')
  set      35753 ->     215 rule:nl_defensie 0.9  (new) | ('', 'royal netherlands air force logistic centre woensdrecht') -> ('NL', 'ministerie van defensie')
  set      36094 ->  247441 spelling_variant 0.9  (new) | ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium der v') -> ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium der v')
  set      39293 ->   62149 rule:pt_exercito 0.9  (new) | ('PT', 'ministerio da defesa nacional exercito portugues comando da logistica') -> ('', 'estado-maior do exercito')
  set      39770 ->   68799 rule:it_navarm 0.9  (new) | ('', 'ministero della difesa direzione degli armamenti navali') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set      41046 ->   68799 rule:it_navarm 0.9  (new) | ('IT', 'ministero della difesa segretariato generale della difesa e direzione ') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set      41294 ->   62149 rule:pt_exercito 0.9  (new) | ('PT', 'ministerio da defesa nacional exercito portugues cmd da logistica') -> ('', 'estado-maior do exercito')
  set      45363 ->   37123 spelling_variant 0.9  (new) | ('', 'land baden-wurttemberg vertreten durch das logistikzentrum baden-wurtt') -> ('', 'logistikzentrum baden-wurttemberg')
  set      46908 ->  107866 spelling_variant 0.9  (new) | ('DE', 'bundesrepublik deutschland vertreten durch das bmvg dieses vertreten d') -> ('DE', 'staatliches hochbauamt schwabisch hall')
  set      48484 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('PT', 'ministerio da defesa nacional forca aerea dat') -> ('PT', 'estado maior da forca aerea')
  set      48663 ->     430 spelling_variant 0.9  (new) | ('', 'bundesanstalt fur immobilienaufgaben vertreten durch die oberfinanzdir') -> ('DE', 'staatliches hochbauamt heidelberg')
  set      48704 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('', 'ministerio da defesa nacional forca aerea clafa dmsa') -> ('PT', 'estado maior da forca aerea')
  set      50950 ->   30146 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch gebaudemanagement schleswig') -> ('', 'land schleswig-holstein endvertreten durch gebaudemanagement schleswig')
  set      54864 ->   42679 rule:it_armaereo 0.9  (new) | ('', 'ministero della difesa segretario generale della difesa dna direzione ') -> ('IT', 'ministero della difesa sgd dna direzione degli armamenti aeronautici e')
  set      58656 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('', 'ministerio da defesa nacional comando da logistica da forca aerea') -> ('PT', 'estado maior da forca aerea')
  set      62884 ->  118723 spelling_variant 0.9  (new) | ('DE', 'bundesrepublik deutschland vertreten durch das bmub dieses vertreten d') -> ('DE', 'staatliches hochbauamt freiburg')
  set      62929 ->  305301 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das bundesministerium fur v') -> ('', 'bundesanstalt fur landwirtschaft und ernahrung ble')
  set      65390 ->   30171 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland diese vertreten durch das bundesministerium') -> ('', 'betrieb fur bau und liegenschaften mecklenburg-vorpommern')
  set      67103 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('', 'ministerio da defesa nacional estado-maior da forca aerea') -> ('PT', 'estado maior da forca aerea')
  set      71499 ->   68799 rule:it_navarm 0.9  (new) | ('', 'ministero della difesa segretariato generale della diesa e direzione n') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set      71737 ->   62149 rule:pt_exercito 0.9  (new) | ('', 'estado-maior do exercito reparticao de concursos e contratos da') -> ('', 'estado-maior do exercito')
  set      75750 ->  107866 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das bmub dieses vertreten d') -> ('DE', 'staatliches hochbauamt schwabisch hall')
  set      79380 ->   30146 spelling_variant 0.9  (new) | ('', 'ministerium fur inneres und bundesangelegenheiten des landes sh- lande') -> ('', 'land schleswig-holstein endvertreten durch gebaudemanagement schleswig')
  set      82261 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('', 'forca aerea clafa direcao de comunicacoes e sistemas de informacao') -> ('PT', 'estado maior da forca aerea')
  set      83241 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('', 'ministerio da defesa nacional forca aerea direcao de abastecimento e') -> ('PT', 'estado maior da forca aerea')
  set      85325 ->   92202 spelling_variant 0.9  (new) | ('', 'bundesanstalt fur immobilienaufgaben vertreten durch die oberfinanzdir') -> ('DE', 'staatliches hochbauamt ulm')
  set      87251 ->   68799 rule:it_navarm 0.9  (stored -> 41046 spelling_variant) | ('IT', 'ministero della difesa - segretariato generale della difesa e direzion') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set      87647 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('', 'ministerio da defesa nacional - fap - clafa - dmsa') -> ('PT', 'estado maior da forca aerea')
  set      88785 ->   68799 rule:it_navarm 0.9  (new) | ('', 'ministero della difesa segretariato generale della difesa e direzione ') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set      88904 ->   92202 spelling_variant 0.9  (stored -> 32228 spelling_variant) | ('DE', 'bundesrepublik deutschland vertreten durch das bmvg dieses vertreten d') -> ('DE', 'staatliches hochbauamt ulm')
  set      90214 ->   62149 rule:pt_exercito 0.9  (stored -> 31947 spelling_variant) | ('PT', 'ministerio da defesa nacional - exercito portugues - comando logistica') -> ('', 'estado-maior do exercito')
  set      90532 ->   68799 rule:it_navarm 0.9  (stored -> 68799 spelling_variant) | ('IT', 'ministero della difesa segretariato generale della difesa e direzione ') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set      90730 ->   91425 rule:it_terrarm 0.9  (new) | ('IT', 'ministero difesa segretariato generale e direzione nazionale armamenti') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set      91363 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'ministero della difesa segretariato generale e direzione nazionale deg') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set      91541 ->   91425 rule:it_terrarm 0.9  (new) | ('IT', 'direzione degli armamenti terrestri') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set      91542 ->   91425 rule:it_terrarm 0.9  (stored -> 90730 spelling_variant) | ('IT', 'ministero difesa - segretariato generale e direzione nazionale armamen') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set      91543 ->   91425 rule:it_terrarm 0.9  (new) | ('IT', 'segretariato generale della difesa e direzione nazionale degli armamen') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set      91544 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'ministero della difesa segretariato generale della difesa e direzione ') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set      91545 ->   91425 rule:it_terrarm 0.9  (new) | ('IT', 'ministero della difesa direzione armamenti terrestri') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set      91546 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'segretariato generale della difesa e direzione nazionale armamenti dir') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set      91547 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'segretariato generale e direzione nazionale degli armamenti direzione ') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set      91548 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'segretariato generale della difesa e direzione nazionale armamenti dir') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set      91549 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'ministero della difesa direzione armamenti terrestri 9a divisione') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set      91710 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'ministero della difesa direzione degli armamenti terrestri') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set      91717 ->   68799 rule:it_navarm 0.9  (stored -> 68799 spelling_variant) | ('IT', 'ministero della difesa - segretariato generale della difesa e direzion') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set      91944 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'min difesa direzione armamenti terrestri 9 divisione') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set      93386 ->   62149 rule:pt_exercito 0.9  (stored -> 41294 spelling_variant) | ('PT', 'ministerio da defesa nacional - exercito portugues - cmd da logistica') -> ('', 'estado-maior do exercito')
  set      93517 ->   30146 spelling_variant 0.9  (new) | ('', 'ministerium fur inneres landliche raume und integration des landes sch') -> ('', 'land schleswig-holstein endvertreten durch gebaudemanagement schleswig')
  set      94760 ->  102440 rule:pt_forca_aerea 0.9  (stored -> 48484 spelling_variant) | ('PT', 'ministerio da defesa nacional - forca aerea - dat') -> ('PT', 'estado maior da forca aerea')
  set      94894 ->   62149 rule:pt_exercito 0.9  (new) | ('PT', 'estado portugues - ministerio da defesa nacional - exercito portugues') -> ('', 'estado-maior do exercito')
  set      97078 ->  107866 spelling_variant 0.9  (stored -> 46908 spelling_variant) | ('DE', 'bundesrepublik deutschland vertreten durch das bmvg dieses vertreten d') -> ('DE', 'staatliches hochbauamt schwabisch hall')
  set      97234 ->   62149 rule:pt_exercito 0.9  (stored -> 94894 identical_name) | ('PT', 'estado portugues ministerio da defesa nacional exercito portugues') -> ('', 'estado-maior do exercito')
  set      97854 ->  118723 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das bundesministerium fur u') -> ('DE', 'staatliches hochbauamt freiburg')
  set      98346 ->   62149 rule:pt_exercito 0.9  (stored -> 39293 spelling_variant) | ('PT', 'ministerio da defesa nacional - exercito portugues - comando da logist') -> ('', 'estado-maior do exercito')
  set      99439 ->  102440 rule:pt_forca_aerea 0.9  (stored -> 48484 spelling_variant) | ('PT', 'ministerio da defesa nacional -- forca aerea -- dat') -> ('PT', 'estado maior da forca aerea')
  set      99440 ->   62149 rule:pt_exercito 0.9  (stored -> 94894 spelling_variant) | ('PT', 'estado portugues -- ministerio da defesa nacional -- exercito portugue') -> ('', 'estado-maior do exercito')
  set     100089 ->   62149 rule:pt_exercito 0.9  (stored -> 101831 spelling_variant) | ('PT', 'estado -- maior do exercito -- direcao de aquisicoes -- comando da log') -> ('', 'estado-maior do exercito')
  set     100936 ->   62149 rule:pt_exercito 0.9  (stored -> 101831 identical_name) | ('PT', 'estado maior do exercito direcao de aquisicoes comando da logistica') -> ('', 'estado-maior do exercito')
  set     101831 ->   62149 rule:pt_exercito 0.9  (new) | ('PT', 'estado-maior do exercito direcao de aquisicoes comando da logistica') -> ('', 'estado-maior do exercito')
  set     102056 ->  118723 spelling_variant 0.9  (stored -> 62884 spelling_variant) | ('DE', 'bundesrepublik deutschland vertreten durch das bmub dieses vertreten d') -> ('DE', 'staatliches hochbauamt freiburg')
  set     102248 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('', 'forca aerea direcao de abastecimento e transportes') -> ('PT', 'estado maior da forca aerea')
  set     102320 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('', 'ministerio da defesa nacional forca aerea academia da forca aerea') -> ('PT', 'estado maior da forca aerea')
  set     102457 ->  118723 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das bundesministerium fur u') -> ('DE', 'staatliches hochbauamt freiburg')
  set     103972 ->   62149 rule:pt_exercito 0.9  (new) | ('', 'estado-maior do exercito direccao de aquisicoes comando da logistica') -> ('', 'estado-maior do exercito')
  set     104147 ->     215 rule:nl_defensie 0.9  (new) | ('', 'the netherlands ministry of defence') -> ('NL', 'ministerie van defensie')
  set     104649 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('', 'ministerio da defesa nacional forca aerea') -> ('PT', 'estado maior da forca aerea')
  set     105113 ->   68799 rule:it_navarm 0.9  (new) | ('', 'ministero della difesa segretariato generale della difesa direzione de') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set     114985 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('', 'forca aerea direcao de manutencao de sistemas de armas') -> ('PT', 'estado maior da forca aerea')
  set     116699 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('', 'forca aerea') -> ('PT', 'estado maior da forca aerea')
  set     117347 ->  118723 spelling_variant 0.9  (stored -> 128295 spelling_variant) | ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium des i') -> ('DE', 'staatliches hochbauamt freiburg')
  set     118811 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('', 'ministerio da defesa nacional forca aerea academia') -> ('PT', 'estado maior da forca aerea')
  set     120583 ->  102440 rule:pt_forca_aerea 0.9  (stored -> 102440 shared_tax_id) | ('PT', 'forca aerea portuguesa') -> ('PT', 'estado maior da forca aerea')
  set     120772 ->   91425 rule:it_terrarm 0.9  (stored -> 91425 identical_name) | ('IT', 'ministero della difesa sgd dna direzione degli armamenti terrestri') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     121007 ->   68799 rule:it_navarm 0.9  (stored -> 68799 spelling_variant) | ('IT', 'ministero della difesa segretariato generale della difesa e direzione ') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set     122488 ->  102440 rule:pt_forca_aerea 0.9  (new) | ('', 'ministerio da defesa nacional forca aerea direcao de abastecimento e t') -> ('PT', 'estado maior da forca aerea')
  set     122728 ->  247441 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das bundesministerium der v') -> ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium der v')
  set     124886 ->   42679 rule:it_armaereo 0.9  (new) | ('', 'ministero della difesa - direzione degli armamenti aeronautici e per l') -> ('IT', 'ministero della difesa sgd dna direzione degli armamenti aeronautici e')
  set     127049 ->   42679 rule:it_armaereo 0.9  (stored -> 42679 spelling_variant) | ('IT', 'ministero della difesa - sgd dna - direzione degli armamenti aeronauti') -> ('IT', 'ministero della difesa sgd dna direzione degli armamenti aeronautici e')
  set     128295 ->  118723 spelling_variant 0.9  (new) | ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium des i') -> ('DE', 'staatliches hochbauamt freiburg')
  set     128711 ->     215 rule:nl_defensie 0.9  (new) | ('', 'netherlands ministry of defence') -> ('NL', 'ministerie van defensie')
  set     135129 ->  247441 spelling_variant 0.9  (stored -> 36094 spelling_variant) | ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium der v') -> ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium der v')
  set     135438 ->     215 rule:nl_defensie 0.9  (new) | ('', 'ministery of defence') -> ('NL', 'ministerie van defensie')
  set     139456 ->  101007 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das bmvbs dieses vertreten ') -> ('DE', 'staatliches hochbauamt karlsruhe')
  set     139544 ->   42679 rule:it_armaereo 0.9  (stored -> 42679 spelling_variant) | ('IT', 'ministero della difesa - sgd dna- direzione degli armamenti aeronautic') -> ('IT', 'ministero della difesa sgd dna direzione degli armamenti aeronautici e')
  set     143029 ->   48480 spelling_variant 0.9  (new) | ('', 'die bundesrepublik deutschland vertreten durch das bundesministerium d') -> ('', 'landesbetrieb bau- und liegenschaftsmanagement sachsen-anhalt')
  set     146078 ->  145645 spelling_variant 0.9  (new) | ('', 'staatliche bau- und liegenschaftsamt rostock die bundesrepublik deutsc') -> ('DE', 'staatliches bau- und liegenschaftsamt rostock die bundesrepublik deuts')
  set     155635 ->  118723 spelling_variant 0.9  (stored -> 128295 spelling_variant) | ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium des i') -> ('DE', 'staatliches hochbauamt freiburg')
  set     158326 ->   30146 spelling_variant 0.9  (new) | ('', 'ministerium fur inneres landliche raume integration und gleichstellung') -> ('', 'land schleswig-holstein endvertreten durch gebaudemanagement schleswig')
  set     164848 ->   30146 spelling_variant 0.9  (new) | ('', 'ministerium fur inneres landliche raume integration und gleichstellung') -> ('', 'land schleswig-holstein endvertreten durch gebaudemanagement schleswig')
  set     165834 ->   11467 spelling_variant 0.9  (new) | ('', 'instytut rybactwa srodladowego im stanislawa sakowicza w olsztynie') -> ('', 'instytut rybactwa srodladowego im stanislawa sakowicza - panstwowy ins')
  set     173828 ->  118723 spelling_variant 0.9  (new) | ('DE', 'bundesrepublik deutschland vertreten durch das bmi dieses vertreten du') -> ('DE', 'staatliches hochbauamt freiburg')
  set     175815 ->   29911 spelling_variant 0.9  (new) | ('DE', 'land niedersachsen vertreten durch das staatliche baumanagement nieder') -> ('DE', 'bundesrepublik deutschland vertreten durch das staatliche baumanagemen')
  set     178167 ->   68799 rule:it_navarm 0.9  (stored -> 68799 spelling_variant) | ('IT', 'ministero della difesa -segretariato generale della difesa e direzione') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set     179282 ->  194521 spelling_variant 0.9  (new) | ('', 'land baden-wurttemberg vertreten durch das ministerium des inneren fur') -> ('', 'ministerium des inneren fur digitalisierung und kommunen baden-wurttem')
  set     179642 ->   91425 rule:it_terrarm 0.9  (stored -> 91543 spelling_variant) | ('IT', 'segretariato generale della difesa e direzione nazionale degli armamen') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     181115 ->  177481 spelling_variant 0.9  (new) | ('', 'auswartiges amt vertreten durch das bundesamt fur auswartige angelegen') -> ('DE', 'bundesamt fur auswartige angelegenheiten')
  set     181508 ->   91425 rule:it_terrarm 0.9  (stored -> 91545 spelling_variant) | ('IT', 'ministero della difesa - direzione armamenti terrestri') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     181709 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'ministero difesa -sgd- dna direzione armamenti terrestri') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     182122 ->   91425 rule:it_terrarm 0.9  (stored -> 91425 spelling_variant) | ('IT', 'ministero della difesa - sgd-dna direzione degli armamenti terrestri') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     184555 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'direzione armamenti terrestri') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     186332 ->  247441 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch bundesministerium d verteid') -> ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium der v')
  set     187378 ->  118723 spelling_variant 0.9  (stored -> 173828 spelling_variant) | ('DE', 'bundesrepublik deutschland vertreten durch das bmi dieses vertreten du') -> ('DE', 'staatliches hochbauamt freiburg')
  set     188162 ->     215 rule:nl_defensie 0.9  (new) | ('', 'nl ministry of defence') -> ('NL', 'ministerie van defensie')
  set     188922 ->  247441 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch bundesministerium d verteid') -> ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium der v')
  set     191944 ->  249503 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das bundesministerium der v') -> ('DE', 'staatl hochbauamt stuttgart')
  set     192434 ->   42646 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das staatliche baumanagemen') -> ('', 'staatliches baumanagement luneburger heide')
  set     194309 ->   29911 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das staatliches baumanageme') -> ('DE', 'bundesrepublik deutschland vertreten durch das staatliche baumanagemen')
  set     194789 ->  247441 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten d bundesministerium d verteidigun') -> ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium der v')
  set     197974 ->   48480 spelling_variant 0.9  (new) | ('', 'die bundesrepublik deutschland vertreten durch das bundesministerium d') -> ('', 'landesbetrieb bau- und liegenschaftsmanagement sachsen-anhalt')
  set     198716 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'ministero della difesa - segretariato generale della difesa e direzion') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     198788 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'ministero della difesa - segretariato generale della difesa e direzion') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     199149 ->     215 rule:nl_defensie 0.9  (new) | ('', 'ministery van defence') -> ('NL', 'ministerie van defensie')
  set     199178 ->  177481 spelling_variant 0.9  (new) | ('', 'auswartiges amt vertreten durch bundesamt fur auswartige angelegenheit') -> ('DE', 'bundesamt fur auswartige angelegenheiten')
  set     199301 ->     391 spelling_variant 0.9  (new) | ('DE', 'land nordrhein-westfalen vertreten durch das innenministerium des land') -> ('DE', 'landesamt fur zentrale polizeiliche dienste nordrhein-westfalen')
  set     199730 ->   35061 spelling_variant 0.9  (new) | ('', 'die bundesrepublik deutschland vertreten durch das bundesministerium d') -> ('', 'staatliches bauamt traunstein')
  set     200153 ->   42679 rule:it_armaereo 0.9  (new) | ('', 'ministero della difesa - segretariato generale della difesa dna - dire') -> ('IT', 'ministero della difesa sgd dna direzione degli armamenti aeronautici e')
  set     200633 ->     330 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch amt fur bundesbau diese ver') -> ('DE', 'bundesamt fur infrastruktur umweltschutz und dienstleistungen der bund')
  set     208078 ->   68799 rule:it_navarm 0.9  (new) | ('', 'ministero della difesa - segretariato generale della difesa e direzion') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set     208225 ->     391 spelling_variant 0.9  (stored -> 199301 spelling_variant) | ('DE', 'land nordrhein-westfalen vertreten durch das innenministerium des land') -> ('DE', 'landesamt fur zentrale polizeiliche dienste nordrhein-westfalen')
  set     211141 ->     215 rule:nl_defensie 0.9  (new) | ('', 'nld ministry of defence') -> ('NL', 'ministerie van defensie')
  set     213001 ->     215 rule:nl_defensie 0.9  (new) | ('', 'the netherlands ministery of defence') -> ('NL', 'ministerie van defensie')
  set     216331 ->   30146 spelling_variant 0.9  (stored -> 224694 twin_notice) | ('DE', 'land schleswig-holstein vertreten durch das ministerium fur inneres ko') -> ('', 'land schleswig-holstein endvertreten durch gebaudemanagement schleswig')   [copies: own 1, others 1]
  set     217321 ->     215 rule:nl_defensie 0.9  (new) | ('', 'royal netherlands air force') -> ('NL', 'ministerie van defensie')
  set     224694 ->   30146 spelling_variant 0.9  (new) | ('DE', 'land schleswig-holstein vertreten durch das landespolizeiamt schleswig') -> ('', 'land schleswig-holstein endvertreten durch gebaudemanagement schleswig')
  set     231242 ->   68799 rule:it_navarm 0.9  (stored -> 68799 spelling_variant) | ('IT', 'ministero della difesa - segretariato generale della difesa e direzion') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set     231335 ->   42679 rule:it_armaereo 0.9  (new) | ('', 'ministero della difesa - segretariato generale della difesa - direzion') -> ('IT', 'ministero della difesa sgd dna direzione degli armamenti aeronautici e')
  set     231416 ->  247441 spelling_variant 0.9  (new) | ('DE', 'bundesrepublik deutschland vertreten durch d bundesministerium d verte') -> ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium der v')
  set     232616 ->   68799 rule:it_navarm 0.9  (new) | ('', 'ministero della difesa - segretariato generale della difesa e direzion') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set     232670 ->   42679 rule:it_armaereo 0.9  (new) | ('', 'segretariato generale della difesa e direzione nazionale degli armamen') -> ('IT', 'ministero della difesa sgd dna direzione degli armamenti aeronautici e')
  set     234815 ->   42679 rule:it_armaereo 0.9  (new) | ('', 'direzione armamenti aeronautici') -> ('IT', 'ministero della difesa sgd dna direzione degli armamenti aeronautici e')
  set     234942 ->   68799 rule:it_navarm 0.9  (new) | ('', 'segretariato generale della difesa e direzione nazionale degli armamen') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set     236235 ->     215 rule:nl_defensie 0.9  (new) | ('', 'dutch ministry of defence') -> ('NL', 'ministerie van defensie')
  set     237282 ->     215 rule:nl_defensie 0.9  (new) | ('', 'the netherlands ministry of defence modnl') -> ('NL', 'ministerie van defensie')
  set     238476 ->  135530 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das bundesministerium der v') -> ('DE', 'bundesministerium der verteidigung')
  set     238625 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'ministero della difesa segretariato generale della difesa e direzione ') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     239304 ->     196 rule:baainbw 0.9  (new) | ('', 'bundesamt fur informationstechnik ausrustung und nutzung der bundesweh') -> ('DE', 'bundesamt fur ausrustung informationstechnik und nutzung der bundesweh')
  set     239364 ->   42679 rule:it_armaereo 0.9  (new) | ('', 'direzione armamenti aeronautici e per l aeronavigabilita') -> ('IT', 'ministero della difesa sgd dna direzione degli armamenti aeronautici e')
  set     241281 ->   68799 rule:it_navarm 0.9  (new) | ('', 'navarm') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set     241792 ->   68799 rule:it_navarm 0.9  (new) | ('', 'ministero della difesa segretariato generale della difesa e direzione ') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set     243607 ->   68799 rule:it_navarm 0.9  (new) | ('', 'direzione nazionale degli armamenti - direzione nazionale degli armame') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set     243613 ->   42679 rule:it_armaereo 0.9  (new) | ('', 'direzione degli armamenti aeronautici e per l aeronavigabilita armaere') -> ('IT', 'ministero della difesa sgd dna direzione degli armamenti aeronautici e')
  set     243734 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'ministero della difesa direzione nazionale degli armamenti direzione d') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     246716 ->     196 rule:baainbw 0.9  (new) | ('', 'bundesamt fur bundesamt fur ausrustung informationstechnik und nutzung') -> ('DE', 'bundesamt fur ausrustung informationstechnik und nutzung der bundesweh')
  set     247389 ->   42679 rule:it_armaereo 0.9  (new) | ('', 'direzione degli armamenti aeronautici e per l aeronavigabilita') -> ('IT', 'ministero della difesa sgd dna direzione degli armamenti aeronautici e')
  set     250496 ->  247441 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das bmvg vertreten durch da') -> ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium der v')
  set     254147 ->   42679 rule:it_armaereo 0.9  (new) | ('', 'ministero della difesa direzione nazionale armamenti direzione degli a') -> ('IT', 'ministero della difesa sgd dna direzione degli armamenti aeronautici e')
  set     254189 ->   42679 rule:it_armaereo 0.9  (new) | ('', 'ministero della difesa direzione nazionale armamenti direzione degli a') -> ('IT', 'ministero della difesa sgd dna direzione degli armamenti aeronautici e')
  set     255135 ->   68799 rule:it_navarm 0.9  (new) | ('', 'ministero della difesa - direzione nazionale degli armamenti - direzio') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set     257088 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'direzione nazionale degli armamenti terrestri') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     257393 ->   68799 rule:it_navarm 0.9  (new) | ('', 'ministero della difesa direzione nazionale degli armamenti navali') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set     257932 ->   68799 rule:it_navarm 0.9  (new) | ('', 'direzione degli armamenti navali - navarm') -> ('IT', 'ministero della difesa segretariato generale della difesa e direzione ')
  set     261832 ->     215 rule:nl_defensie 0.9  (new) | ('', 'royal netherlands navy') -> ('NL', 'ministerie van defensie')
  set     263673 ->   91425 rule:it_terrarm 0.9  (new) | ('', 'direzione armamenti terrestri terrarm') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     283830 ->   29911 spelling_variant 0.9  (stored -> 175815 identical_name) | ('DE', 'land niedersachsen vertreten durch das staatliche baumanagement nieder') -> ('DE', 'bundesrepublik deutschland vertreten durch das staatliche baumanagemen')
  set     311116 ->   91425 rule:it_terrarm 0.9  (stored -> 91541 identical_name) | ('IT', 'direzione degli armamenti terrestri') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     319013 ->  253236 twin_notice 0.85  (new) | ('', 'minarm sga drh-md defense mobilite') -> ('FR', 'ministere des armees et des anciens combattants sga drh-md defense mob')   [copies: own 0, others 1]
  set     326214 ->   91425 rule:it_terrarm 0.9  (stored -> 91541 identical_name) | ('IT', 'direzione degli armamenti terrestri') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     326340 ->   91425 rule:it_terrarm 0.9  (stored -> 91541 identical_name) | ('IT', 'direzione degli armamenti terrestri') -> ('IT', 'ministero della difesa sgd-dna direzione degli armamenti terrestri')
  set     335478 ->   25005 spelling_variant 0.9  (new) | ('', 'zespol szkol nr 2 im ksiecia pawla karola sanguszki w lubartowie') -> ('', 'zespol szkol nr 2 im jaroslawa iwaszkiewicza-ckziu w katowicach')
  set     339933 ->     137 spelling_variant 0.9  (new) | ('PL', 'akademia wojsk ladowych imienia generala tadeusza kosciuszki') -> ('PL', 'akademia wojsk ladowych')
  set     349608 ->  229666 spelling_variant 0.9  (stored -> 28605 identical_name) | ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium des i') -> ('DE', 'beschafffungsamt des bmi')
  set     349638 ->  247441 spelling_variant 0.9  (stored -> 231416 spelling_variant) | ('DE', 'bundesrepublik deutschland vertreten durch d bundesministerium d verte') -> ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium der v')
  set     439042 ->  247441 spelling_variant 0.9  (new) | ('', 'bundesrepublik deutschland vertreten durch das bundesministerium der v') -> ('DE', 'bundesrepublik deutschland vertreten durch das bundesministerium der v')
  remove     137 ->  339933 twin_notice 0.85 | ('PL', 'akademia wojsk ladowych') -> ('PL', 'akademia wojsk ladowych imienia generala tadeusza kosciuszki')   [copies: own 357, others 2]
  remove     323 ->  243945 twin_notice 0.85 | ('FR', 'sid atlantique') -> ('FR', 'minarm sga dcsid sid atl ministere des armees secretariat general pour')   [copies: own 14, others 8]
  remove     421 ->   28697 twin_notice 0.85 | ('ES', 'direccion de adquisiciones del mando de apoyo logistico del ejercito d') -> ('ES', 'direccion de adquisiciones del mando de apoyo logistico del ejercito d')   [copies: own 163, others 8]
  remove     440 ->    7096 twin_notice 0.85 | ('PL', 'urzad zamowien publicznych') -> ('PL', 'oddzial zabezpieczenia zandarmerii wojskowej')   [copies: own 0, others 6]
  remove    2009 ->   28646 twin_notice 0.85 | ('ES', 'xunta de goberno do concello de santiago de compostela') -> ('ES', 'xunta de goberno del ayuntamiento de santiago de compostela')   [copies: own 1, others 1]
  remove    9020 ->  180754 twin_notice 0.85 | ('PL', '4 wojskowy oddzial gospodarczy') -> ('PL', '4 wojskowy oddzial gopodarczy')   [copies: own 242, others 1]
  remove   13000 ->    9770 twin_notice 0.85 | ('PL', 'ministerstwo obrony narodowej') -> ('PL', 'centrum zasobow cyberprzestrzeni sil zbrojnych')   [copies: own 107, others 28]
  remove   13533 ->   22034 twin_notice 0.85 | ('PL', 'jednostka wojskowa nr 3964') -> ('PL', 'wojskowe centrum edukacji obywatelskiej')   [copies: own 56, others 1]
  remove   28574 ->  249183 twin_notice 0.85 | ('FR', 'ministere des armees') -> ('FR', 'minarm sga sid sid med sd-ac')   [copies: own 6, others 2]
  remove   29911 ->  175815 twin_notice 0.85 | ('DE', 'bundesrepublik deutschland vertreten durch das staatliche baumanagemen') -> ('DE', 'land niedersachsen vertreten durch das staatliche baumanagement nieder')   [copies: own 174, others 19]
  remove   32929 ->  238712 twin_notice 0.85 | ('FR', 'esid de brest') -> ('FR', 'minarm sga dcsid sid atlantique ministere des armees secretariat gener')   [copies: own 13, others 2]
  remove   33524 ->  225437 twin_notice 0.85 | ('FR', 'dirisi') -> ('FR', 'dirisi brest')   [copies: own 26, others 1]
  remove   41850 ->  196061 twin_notice 0.85 | ('DE', 'bayerisches landeskriminalamt') -> ('DE', 'bayerisches landeskriminalamt blka')   [copies: own 2, others 2]
  remove   55183 ->   41113 twin_notice 0.85 | ('DE', 'stadt leipzig branddirektion') -> ('DE', 'stadt leipzig')   [copies: own 1, others 1]
  remove  132828 ->  256128 twin_notice 0.85 | ('FR', 'service interarmees des munitions') -> ('FR', 'simu')   [copies: own 2, others 2]
  remove  145645 ->  147151 shared_tax_id 0.9 | ('DE', 'staatliches bau- und liegenschaftsamt rostock die bundesrepublik deuts') -> ('DE', 'staatliches bau- und liegenschaftsamt rostock')
  remove  167694 ->   21992 twin_notice 0.85 | ('FR', 'depafi') -> ('FR', 'ministere de l interieur')   [copies: own 6, others 1]
  remove  216183 ->     391 twin_notice 0.85 | ('DE', 'landesamt fur zentrale polizeiliche dienste nrw lzpd') -> ('DE', 'landesamt fur zentrale polizeiliche dienste nordrhein-westfalen')   [copies: own 1, others 1]
  remove  219918 ->  218362 twin_notice 0.85 | ('FR', 'tribunal administratif de paris') -> ('FR', 'etablissement central logistique de la police nationale')   [copies: own 0, others 3]
  remove  220398 ->   34117 twin_notice 0.85 | ('FR', 'pfc rambouillet') -> ('FR', 'mindef air siae')   [copies: own 0, others 2]
  remove  222333 ->  181271 twin_notice 0.85 | ('FR', 'centre de soutien technique et administratif') -> ('FR', 'csta')   [copies: own 6, others 3]
  remove  222592 ->  247764 twin_notice 0.85 | ('FR', 'dapsa') -> ('FR', 'direction des approvisionnements en produit de sante des armees')   [copies: own 2, others 2]
  remove  233067 ->   56480 twin_notice 0.85 | ('FR', 'dga information strategique') -> ('FR', 'dga intelligence technique economique')   [copies: own 3, others 4]
  remove  243648 ->  225340 twin_notice 0.85 | ('FR', 'sous-direction de la prefiguration de l agence ministerielle de gestio') -> ('FR', 'sous-direction de la prefiguration de l agence ministerielle de gestio')   [copies: own 1, others 1]
  remove  244125 ->     330 twin_notice 0.85 | ('DE', 'bundesamt fur infrastruktur umweltschutz und dienstleistungen') -> ('DE', 'bundesamt fur infrastruktur umweltschutz und dienstleistungen der bund')   [copies: own 25, others 8]
  remove  247036 ->   34117 twin_notice 0.85 | ('FR', 'sga shd') -> ('FR', 'mindef air siae')   [copies: own 7, others 4]
  remove  253236 ->   34117 twin_notice 0.85 | ('FR', 'ministere des armees et des anciens combattants sga drh-md defense mob') -> ('FR', 'mindef air siae')   [copies: own 2, others 2]
  remove  283707 ->  129049 twin_notice 0.85 | ('ES', 'departament d interior i seguretat publica') -> ('ES', 'departanmeto de interior')   [copies: own 1, others 1]
```

## Appendix B. Supplier merges: every pair the write merges (production dry run, 24 October 2026)

`head` then `<- member country awards name numbers method confidence`; `(award rows to XX)`: the member's award rows move to the company's country first.

```
winners 11313 groups 42 rows 52 left {'spacing_on_a_short_key': 7, 'different_company_numbers': 67, 'different_legal_forms': 17}
head 426671 IT awards 25 'LEONARDO - SOCIETA PER AZIONI' numbers ['00401990585', '00881841001', '401990585'] country IT
   <- 437203 IT awards 2 'Leonardo, Societá per Azione' ['00881841001'] company_number 0.97
   <- 430393 IT awards 1 'Leonardo S.p.A. – Aircraft Division' ['00881841001'] company_number_division 0.95
   <- 431219 IT awards 1 'Leonardo S.p.A. Divisione Sistemi di Difesa' ['00881841001'] company_number_division 0.95
   <- 439305 IT awards 1 'SOCIETA LEONARDO S.P.A.' [] name_key 0.95
head 427567 DE awards 27 'Heckler Koch GmbH' numbers ['000N0047964B', '481250', 'HRB481250', 'N0047964B'] country DE
   <- 428135 DE awards 9 'Heckler und Koch' ['232899163', 'N0047964B'] company_number 0.97
   <- 431166 DE awards 8 'HECKLER & KOCH GMBH' ['N0047964B'] company_number 0.97
   <- 427723 DE awards 4 'Heckler and Koch GmbH' ['000N0047964BN0047964B', 'N0047964B'] company_number 0.97
head 428445 PL awards 19 'WORKS 11 Sp. z o.o.' numbers ['6462895170'] country PL
   <- 439434 PL awards 1 'Works Sp. z o.o.' [] curated_source_review 0.9
   <- 439544 PL awards 1 'WORKSS - 11 Sp. z o.o.' [] curated_source_review 0.9
   <- 439885 PL awards 1 'Works11 Sp. z o. o.' [] curated_source_review 0.9
head 427121 ES awards 204 'NAVANTIA SA, SME' numbers ['A84076397'] country ES
   <- 420165 ES awards 54 'NAVANTIA S.A.' ['A84076397', 'B84076397'] company_number 0.97
   <- 429848 ES awards 2 'NAVANTIA SISTEMAS' ['A84076397'] stated_number_prefix 0.9
head 429483 ES awards 20 'EQUIPAMIENTOS SDAL S.L.' numbers ['B81993222'] country ES
   <- 430059 ES awards 15 'Equiamientos SDAL SL' ['B81993222'] company_number 0.97
   <- 438118 ES awards 2 'EQUIPAMIENTO SDAL SL' ['B81993222'] company_number 0.97
head 432464 ES awards 2 'Iturri SA, El Siglo 1870 SL, Integral Thermal Shield SL, Climb Wear SL' numbers ['U88593124'] country ES
   <- 432477 ES awards 1 'Iturri SA, El Siglo 1870 SL, IntegralThermal Shield SL y Climb Wear SL' ['U88593124'] company_number 0.97
   <- 432540 ES awards 1 'Iturri SA, El Siglo 1870SL, Integral Thermal Shield SL y Climb Wear SL' ['U88593124'] company_number 0.97
head 402125 DE awards 9 'IBM DEUTSCHLAND GMBH' numbers ['145178813'] country DE
   <- 430409 DE awards 1 'IBM Deutschland GmbH Niederl. Flensburg' ['145178813'] stated_number_prefix 0.9
head 403968 ES awards 7 'ETRA AIR SL' numbers ['B67918383'] country ES
   <- 438962 ES awards 1 'ETRA AIR SL (ETRAIR)' ['B67918383'] stated_number_prefix 0.9
head 405287 DE awards 14 'THALES DEUTSCHLAND GMBH' numbers ['122269850', '301675630', '812331104'] country DE
   <- 428200 DE awards 10 'Thales Deutschland' ['122269850'] company_number 0.97
head 411427 DK awards 5 'TERMA AS' numbers ['41881828', '49776268'] country DK
   <- 429668 NO awards 1 'Terma A/S' ['41881828'] company_number 0.97  (award rows to DK)
head 420715 NO awards 5 'NAMMO RAUFOSS AS' numbers ['980038300', '9911951888'] country NO
   <- 440010 FI awards 1 'Nammo Raufoss AS' ['980038300'] company_number 0.97  (award rows to NO)
head 425662 IL awards 2 'RAFAEL ADVANCED DEFENCE SYSTEMS LTD' numbers ['514416973', '520042185'] country IL
   <- 430604 IL awards 1 'Rafael Advanced Defence Systems Ltd.' [] name_key 0.95
head 426685 IT awards 2 'ELETTRONICA SPA' numbers [] country IT
   <- 439473 IT awards 1 'SOCIETA ELETTRONICA SPA' [] name_key 0.95
head 426744 FR awards 16 'SAFRAN ELECTRONICS & DEFENSE' numbers ['039480107911', '480107911', 'CRS480107911'] country FR
   <- 435712 ES awards 2 'SAFRAN ELECTRONICS & DEFENSE' ['480107911', 'FR039480107911'] company_number 0.97  (award rows to FR)
head 427614 LT awards 22 'UAB DEFENSA' numbers ['300005349'] country LT
   <- 430988 LV awards 1 'UAB DEFENSA' ['300005349'] company_number 0.97  (award rows to LT)
head 427615 EE awards 9 'Baltic Fox OÜ' numbers ['101269588', '11535997'] country EE
   <- 430850 LV awards 1 'Baltic Fox OU' ['11535997'] company_number 0.97  (award rows to EE)
head 427734 FR awards 6 'Helisim SAS' numbers ['0000CGC00178', '34421646365', '421646365'] country FR
   <- 434264 ES awards 1 'HELISIM SAS' ['421646365'] company_number 0.97  (award rows to FR)
head 427735 IT awards 2 'ANSETT AVIATION ITALIA' numbers ['009412790967', '09412790967'] country IT
   <- 433456 ES awards 1 'ANSETT AVIATION ITALIA' ['09412790967'] company_number 0.97  (award rows to IT)
head 428275 IT awards 18 'Fiocchi Munizioni S.p.A.' numbers ['0000CGC00504', '000810220137', '00810220137', 'N0057381F'] country IT
   <- 433479 ES awards 9 'FIOCCHI MUNIZIONI SPA' ['IT000810220137', 'N0057381F'] company_number 0.97  (award rows to IT)
head 428293 GB awards 1 'ARMTRAC' numbers ['787570476'] country GB
   <- 437184 UK awards 1 'ARMTRAC' ['787570476'] company_number 0.97  (award rows to GB)
head 428526 PT awards 15 'Vanguard Marine Lda.' numbers ['0000CGC80191', '508451396'] country PT
   <- 434042 ES awards 2 'Vanguard Marine Lda.' ['508451396'] company_number 0.97  (award rows to PT)
head 428566 EE awards 5 'Eurosec OÜ' numbers ['11606119'] country EE
   <- 431207 LV awards 1 'EUROSEC OÜ' ['11606119'] company_number 0.97  (award rows to EE)
head 428700 CH awards 16 'pilatus aircraft ltd' numbers ['105943984', '15030004652', '4131284801574', 'A19716885'] country CH
   <- 439344 BG awards 3 'PILATUS AIRCRAFT LIMITED' ['15030004652'] company_number 0.97  (award rows to CH)
head 429101 IL awards 2 'AERONAUTICS' numbers ['512551425'] country IL
   <- 433157 ES awards 1 'AERONAUTICS LTD' ['512551425'] company_number 0.97  (award rows to IL)
head 429252 PL awards 5 'KenBIT Sp. z o.o.' numbers ['0000884493'] country PL
   <- 430349 PL awards 1 'KenBIT Polska Sp. z o.o.' ['0000884493'] stated_number_prefix 0.9
head 429473 HU awards 1 'AEROTECHNIKA M & T Zrt.' numbers ['12013786241'] country HU
   <- 430557 HU awards 1 'Aerotechnika M & T Budapest Repüléstechnikai Szolgáltató Zrt.' ['12013786241'] stated_number_prefix 0.9
head 429896 EE awards 5 'eqqus Ltd OÜ' numbers ['10717064'] country EE
   <- 430736 LV awards 3 'Eqqus Ltd. OU' ['10717064', 'EE10717064'] company_number 0.97  (award rows to EE)
head 429994 PL awards 2 'SZCZĘŚNIAK Pojazdy Specjalne Sp. z o.o.' numbers ['241073251', '5472099801'] country PL
   <- 430406 SE awards 1 'SZCZESNIAK POJAZDY SPECJALNE SP. Z O.O.' ['241073251'] company_number 0.97  (award rows to PL)
head 430537 ES awards 18 'Guardian Homeland Security S.A' numbers ['A84650720'] country ES
   <- 432581 IL awards 1 'Guardian Homeland Security S.A' ['A84650720'] company_number 0.97  (award rows to ES)
head 431248 FI awards 3 'Nammo Lapua Oy' numbers ['14911323'] country FI
   <- 431123 SE awards 1 'Nammo Lapua Oy' ['14911323'] company_number 0.97  (award rows to FI)
head 431253 SK awards 1 'MSM EXPORT, s.r.o.' numbers ['48006122'] country SK
   <- 430368 LV awards 2 'MSM EXPORT s.r.o.' ['48006122'] company_number 0.97  (award rows to SK)
head 432487 ES awards 5 'HEWLETT PACKARD SERVICIOS ESPAÑA, S.L.U.' numbers ['B82591470'] country ES
   <- 432629 ES awards 1 'HEWLETT PAKARD SERVICIOS ESPAÑA, S.L.U.' ['B82591470'] company_number 0.97
head 432858 ES awards 3 'fabios e hijos' numbers ['B14514194'] country ES
   <- 437645 CO awards 1 'fabios e hijos' ['B14514194'] company_number 0.97  (award rows to ES)
head 433638 ES awards 1 'BARPIMO SA' numbers ['A26004960'] country ES
   <- 435555 ES awards 1 'BARPIMO COATINGS S.A.' ['A26004960'] stated_number_prefix 0.9
head 433949 ES awards 1 'novelec' numbers ['B99423824'] country ES
   <- 436894 ES awards 1 'NOVELEC EBRO S.L.' ['B99423824'] stated_number_prefix 0.9
head 434378 ES awards 1 'CONTINENTAL' numbers ['B83916056'] country ES
   <- 436401 ES awards 1 'CONTINENTAL TYRES SL' ['B83916056'] stated_number_prefix 0.9
head 434743 ES awards 4 'SIEMENS, S.A.' numbers ['A28006377'] country ES
   <- 436502 ES awards 2 'SIEMENS, S.A., DIVISION SMART INFRAESTRUCTURE' ['A28006377'] company_number_division 0.95
head 435586 ES awards 1 'INSTALACIONES TÉCNICAS CONTRERAS S.L. (ITECO S.L.)' numbers ['B18676734'] country ES
   <- 436129 GD awards 1 'INSTALACIONES TÉCNICAS CONTRERAS S.L. (ITECO S.L.)' ['B18676734'] company_number 0.97  (award rows to ES)
head 435848 ES awards 2 'TKT Servicios Informáticos' numbers ['B90011198'] country ES
   <- 434726 ES awards 1 'TKT SERVICIOS' ['B90011198'] stated_number_prefix 0.9
head 437680 ES awards 2 'INGLOBA SEGURIDAD S.A' numbers ['A86376803'] country ES
   <- 438704 ES awards 1 'Ingloba,S.A.' ['A86376803'] stated_number_prefix 0.9
head 439476 IT awards 2 'TECNODIFE SRL' numbers [] country IT
   <- 439306 IT awards 1 'SOCIETA TECNODIFE SRL' [] name_key 0.95
head 439608 IT awards 1 'Società ORIZZONTE SISTEMI NAVALI S.p.A' numbers [] country IT
   <- 439652 IT awards 1 'Orizzonte Sistemi Navali S.p.A.' [] name_key 0.95
```

## Appendix C. Company groups (production dry run before the merges, 24 October 2026)

```
rheinmetall: 26 companies  (Rheinmetall AG, annual report: list of shareholdings (https://www.rheinmetall.com/en/investor-relations))
      420406  RHEINMETALL WAFFE MUNITION GMBH
      426698  RHEINMETALL ELECTRONICS GMBH
      426763  RHEINMETALL TECHNICAL PUBLICATIONS GMBH
      426931  Rheinmetall Italia S.p.A.
      427038  Rheinmetall Protection Systems GmbH
      427143  RHEINMETALL PROJECT SOLUTIONS GMBH
      427233  RHEINMETALL DEFENCE NEDERLAND B.V
      427234  RHEINMETALL LANDSYSTEME GMBH
      427709  Rheinmetall Soldier Electronics GmbH
      428000  Rheinmetall MAN Military Vehicles GmbH
      428184  RHEINMETALL EXPAL MUNITIONS, S.A.U.
      428360  Rheinmetall Electronics GmbH
      429167  Rheinmetall Air Defence AG
      429387  Rheinmetall Waffe Munition Schweiz AG
      429399  RheinmetallMAN Military Vehicles GmbH
      429709  Rheinmetall Polska Sp. z. o.o.
      430165  Rheinmetall Electronics GmbH
      430309  Rheinmetall Technical Publications GmbH Ndl. Penzberg
      430367  RHEINMETALL EXPAL MUNITION, S.A.
      430412  Rheinmetall Project Solutions GmbH
      430474  Rheinmetall Waffe Munition ARGES GmbH
      430524  Rheinmetall Canada Inc.
      430559  RHEINMETALL DENEL MUNITION (PTY) LTD
      433669  RHEINMETALL DENERL MUNITION (Pty) Ltd
      439727  RHEINMETALL WAFFE MUNITION GmbH
      439987  Rheinmetall Canada Inc
leonardo: 9 companies  (Leonardo S.p.A., integrated annual report: consolidated companies (https://www.leonardo.com/en/investors))
      382508  LEONARDO UK LTD
      412040  LEONARDO GERMANY GMBH
      426671  LEONARDO - SOCIETA PER AZIONI
      427593  LEONARDO PZL-ŚWIDNIK S.A.
      429964  LEONARDO UK LTD
      430205  Leonardo Electronics Division
      431099  Leonardo Belgium S.A.
      431221  Leonardo Spa_149684
      437203  Leonardo, Societá per Azione
saab: 9 companies  (Saab AB, annual report: group companies (https://www.saab.com/investors))
      394573  SAAB AB
      426792  SAAB DYNAMICS AB
      426991  Saab Barracuda AB
      427436  SAAB DEUTSCHLAND GMBH
      428303  Saab Finland Oy
      430383  SAAB GRINTEK DEFENCE LTD
      430385  Saab Danmark A/S
      431338  Saab Barracuda AS
      439291  Saab Deutschland GmbH
pilatus: 3 companies  (Pilatus Aircraft Ltd (Pilatus Flugzeugwerke AG), Stans: company information (https://www.pilatus-aircraft.com))
      428700  pilatus aircraft ltd
      429359  PILATUS Constructions Aéronautiques SA
      439344  PILATUS AIRCRAFT LIMITED
pgz: 22 companies  (Polska Grupa Zbrojeniowa S.A.: companies of the PGZ group (https://www.pgzsa.pl))
       27452  wojskowe zaklady lacznosci nr 2
      426930  PIT-RADWAR S.A.
      427332  HUTA STALOWA WOLA S.A.
      427687  MESKO S.A.
      427706  Fabryka Broni "ŁUCZNIK" - Radom Sp. z o. o.
      427707  Rosomak Spółka Akcyjna
      427827  Zakłady Mechaniczne "TARNÓW" S.A.
      427971  Wojskowe Zakłady Łączności Nr 1 S.A.
      428046  WOJSKOWE ZAKŁADY LOTNICZE NR 1 S.A., ul. Dubois 119, 93-465 Łódź
      428125  Wojskowe Zakłady Elektroniczne S.A.
      428222  PIT - RADWAR SP.A.
      428272  WOJSKOWE ZAKŁADY UZBROJENIA SPÓŁKA AKCYJNA
      428376  PGZ Stocznia Wojenna Sp. z o.o.
      430628  Wojskowe Zakłady Lotnicze Nr2 S.A.
      430717  HUTA STALOWA WOLA S.A.
      439309  Wojskowe Zakłady Motoryzacyjne S. A.
      439456  Wojskowe Zakłady Elektroniczne S.A. oraz PIT - RADWAR S.A.
      439602  Wojskowe Zakłady Łączności Nr 1 w Zegrzu
      439688  Wojskowe Zakłady Lotnicze Nr2 S.A.
      439833  WOJSKOWE ZAKŁADY LOTNICZE NR 1 SA
      439861  ROSOMAK Spółka Akcyjna ul. Powstańców 5/7 41-100 Siemianowice Śląskie
      439954  Mesko Spółka Skcyjna
{'members': 69, 'written': 0, 'removed': 0, 'to_write': 12, 'to_remove': 0}  (dry run: nothing written, add --yes)
```
