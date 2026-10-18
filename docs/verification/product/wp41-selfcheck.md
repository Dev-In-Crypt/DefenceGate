# WP-41 self-check: networks data fixes (18 October 2026)

Branch `wp-wp41` (from `integration` at `70fa80e`), test database letters `u` and `u2`, migrations 0086 and 0087. Written by the
implementer for the verifier. Everything ran on the server (`/root/dev-u`); production was only read (`SELECT` in a
read-only transaction with a 30 s timeout through the Postgres container, and file reads of the private raw store through the
worker container). No language model was called. Third parties: about 70 requests to the CORDIS SPARQL service (one a
second, the connector's User-Agent, robots.txt read first) and 9 CORDIS project pages (`/project/rcn/<n>`; `/data/` and
`/search` were not requested); nothing else.

The source of every defect is `docs/verification/product/verify2-networks.md`. Verdicts first, evidence after.

## Verdict per defect

| Id | Verdict | What was done |
|---|---|---|
| N1 coordinator amount = project total or off | **Partly fixed; the rest is the age of the open data (owner)** | Cause found, below. The 18 coordinators that carry the whole project (ERC grants paid in full to two hosts) are withheld; a host with linked third parties keeps its figure with the note `gross_of_third_parties`; the 33 projects whose amounts exceed their total are withheld (391 amounts, EUR 889.8 M of 141.2 bn). JOANNEUM and Granada differ because the open data is older than the CORDIS page: not a loader defect |
| N2 third parties stored as EUR 0 | **Fixed** | A third party shown at 0 is `NULL` with the note `linked_third_party` (13,701 rows). The amount itself is not in the open data |
| N3 1,749 H2020 / Horizon Europe nulls | **Not fixable from SPARQL; needs the owner** | The service holds no payment for those roles (their grants have no payment and no funding amount). `NULL` stays, with the note `no_payment_stated` (9,997 CORDIS rows in all). Two ways to the amounts are in `docs/sources/cordis.md` |
| N4 CSIC under Italy | **Fixed** | Not a multi-site case: the record is contradictory (address Trento IT, site name "... Madrid ES", VAT ES). Country by vote of the three signals. 1 organisation of 72,534 is moved (CSIC), 1 has sites in several countries (EurOcean) |
| N5 duplicates of large institutions | **Fixed (merge where a key proves it, a display family where only the names are alike)** | 760 groups / 961 rows merged (37 groups held a project on both sides: the directory duplicates); 57 families / 60 variants in the directory, 40 biggest read by hand |
| N6 wrapped and glued EDF names | **Fixed; 36 members recovered without a model** | Quote check on letters only; glued names respaced; `ops/edf_recover` |
| N7 individuals | Not touched (another package) | |
| N8 partner area | **Fixed** | Call 106 SMERO; 3 EDIP calls get their EDF category; the rest say they are generic |
| N9 Horizon topic form | **Fixed** | |
| N10 supplier small-group suppression | **Not in this package's list; needs the owner** | |
| N11 RENK AG / RENK GmbH | **Fixed** | Different legal forms are different bodies; the cascade keeps them apart and `ops/split_legal_forms` repairs the stored suppliers |
| N12 stale name | **Mechanism fixed; no effect yet** | The open data still prints the old name (SANSIRRO); it acts when the service catches up. 13 respellings are correctly not treated as renames |

## N1 to N3: what the SPARQL fields are (read, not guessed)

For a project the service has `hasTotalCost` and, through its `Grant`, `hasFundingAmount` (the EU contribution); a role
(`OrganisationRole`) has `isRecipientOf` a `GrantPayment` with `hasPaymentAmount` / `value`. That payment is the only money on
a participation. The role has no other amount property and no link from a third party to the beneficiary it is linked to.

The CORDIS page prints per participant the **net EU contribution**, "the sum of money that the participant receives, deducted
by the EU contribution to its linked third party" (the page's own definition). Read side by side on ERC 695618 (rcn 204887):

| | open data (SPARQL) | CORDIS page |
|---|---|---|
| Universite de Lorraine, host | payment 2,810,229 (= the project total) | net EU contribution 2,248,040 |
| CNRS, third party | payment 0 | 562,189 |

So the loader read the right property. The property is the **gross** payment: it includes the share of linked third parties,
who are shown at 0. That explains the coordinator-equals-total rows (Lorraine, HIRIS 213934: 1,500,000 = the project total,
third party Zodiac Data Systems at 0), the 3TR row of IRCCS Ca' Granda (6 third parties in the project) and the 13,701 zeros. It does
not explain JOANNEUM (238600) and Granada (241820): there the **service is older than the page** (Granada's own project total in
the service is 165,312.96, the page says 182,596.14; the JOANNEUM amounts differ in the pattern of an amendment that moved
EUR 190,950.12 between participants), and VTT in CONNECT-NM (264821) is not explained at all (303,600 against 618,177.95). The 1,749
nulls: the service has no payment for the role (probe of 273305, 274592, 277703, 274757: the grant has zero payments and no
funding amount; 236264 has payments for the others and none for the CNR).

What was built:

* `participation.contribution` means "EUR the service pays to this participant, gross of its linked third parties". `NULL` is
  unknown, never zero. `contribution_note` (a closed list, `CHECK` in migration 0086, column comments, `docs/sources/cordis.md`,
  `docs/design/API_CONTRACT.md`) says why: `no_payment_stated`, `linked_third_party`, `exceeds_project_total`,
  `source_states_none` (EDF), or the caveat `gross_of_third_parties` on a stated amount. `0` is a stated 0 (an associated
  partner is not funded).
* `networks.settle_amounts` (pure) applies the project rule; the loader and the repair use the same function.
* The repair needs no reload and no network: `python -m dgate.ops.repair_contributions [--yes]` re-derives the notes from
  the stored rows and the projects' EU contribution (the stored figure of a withheld amount is in `contribution_stated`, so it comes
  back if a project total is corrected).

Measured on the production rows (382,153 active CORDIS participations, the exact function, offline): plain 288,331;
`gross_of_third_parties` 69,733; `linked_third_party` 13,701 (= the verifier's 13,701); `no_payment_stated` 9,997;
`exceeds_project_total` 391 amounts in 33 projects, 18 of them a coordinator carrying the whole project (= the verifier's 18),
EUR 889,772,136 withheld from a sum of 141,198,678,777 (0.63 %). 278 of the 391 are in five projects (110, 95, 35, 19 and 19 amounts: rcn 264878, 242744, 236381, 269101, 236380). A flat 2 % is allowed on top of 1 EUR per
participant: without it a project with 148 participants and a 0.2 % excess lost every amount. The 33 against the verifier's 37:
four projects are within 2 %.

## N4: the country

Of 72,534 organisations, **1** has sites in two countries (FUNDACAO EUROCEAN: Lisboa PT and 's-Gravenhage NL, two VAT numbers; kept
as `several`, country NL as before, `country_sites {NL,PT}`) and **1** has a site whose name contradicts its address (CSIC,
PIC 999991722: address "Belenzani 19, 38122 Trento, IT", site name "... CIENTIFICAS Madrid ES", VAT ESQ2818002D). 191
organisations have more than one site, all in one country. 48 organisations have a VAT prefix that differs from the stored
country; the vote leaves 47 of them as they are (the prefix alone is one voice; most are Mexican tax numbers and `UK`).
`cordis.seat_country`: all agree or only the address speaks: the address; name and VAT agree against it: that country
(`country_basis = 'vote'`); several countries: the first and the list. One voice against the address changes nothing.
The live check of the repair (15 requests, 43 s, against a dump of the organisation table): `{'basis_vote': 1, 'basis_several': 1,
'names_to_refresh': 0 after the respelling rule}` and one country change, CSIC `IT -> ES`. The aliases of the row move with
it. CSIC (418756) and the Spanish row without a PIC (32392: 5 projects, same key) then fall in one `org_dedupe` group.

## N5: merge and families

**Merge (`ops/org_dedupe`).** Two rows of one country with the same key (`key_of`: accents, case, hyphens, ampersands, legal forms
stripped) or, for keys of 12 characters or more, the same key without spaces, merged with `db.merge_organisations` (reversible:
the alias keeps `prev_organisation_id`; nothing deleted), method `name_key` 0.95 or `name_key_spaces` 0.90. Vetoes: two
PICs, registration numbers or VAT numbers; two legal-form classes (RENK); a row removed on request. **Only groups that touch a project
participant**: the first dry run over all organisations found 19,775 groups / 23,976 rows, 16,838 groups blocked by differing
registration numbers: that is the procurement buyers whose hyphen variants the buyer list shows as families, and a mass merge of
them was not the task. The focus gives **760 groups, 961 rows** (664 `name_key`, 297 `name_key_spaces`), left alone: 1,260 for
different registration numbers (buyer rows beside a CORDIS row), 179 for different PICs, 23 for spacing on a short key. In
**37 groups both sides hold projects** (78 rows): these are the duplicates the directory showed. Hand check of 15 of the 37 (random,
seed 41): **15 of 15 the same body** (Beyond Semiconductor, Zanasi Alessandro SRL, ELRA, Robert Koch-Institut, ONERA, C3S, E4 Computer
Engineering, TNO, NEDINSCO, LEITAT, Stratiotiki Scholi Evelpidon, Prisma Electronics, ISD, Fraunhofer (5 rows), ENS Paris-Saclay).
The glued rows of the verifier land in groups: `universiteduluxembourg` into 72059, `universidadpolitecnicademadrid` into 35666;
`forsvaretsforskningsinstitutt` (426802) has no spaced twin and stays, with its display name respaced by `edf_recover`.

**Families (`ops/org_families`, `dgate/org_family.py`, table `organisation_family_member`, migration 0087).** The mechanism of
`buyer_family_member` for organisations: display only, a star around the row with most projects, every variant has its own stored
pair with the head (a chain A~B~C never joins A and C), method and confidence stored (`name_variant` = the cascade's trigram
similarity, `same_name` 0.80 = one name under several PICs). Vetoes: other country; two PICs (for a trigram pair), two
registration numbers or VAT numbers; two legal forms; a name under 6 characters. The directory card of the head counts the projects of
its variants and says "Includes N name variants"; the head's profile counts them too (so card and profile agree; `nameVariants`,
`variantOf` in the API); a variant has no card of its own and keeps its profile. Measured: 4,550 open pairs, 3,817 after
following the merges, **3,639 have a row outside the directory** (a buyer-only row), 178 inside: **66 accepted, 81 vetoed for two PICs, 21
VAT, 2 registration numbers, 8 legal form**. Result **57 families, 60 variants**; the 40 biggest, each read: `wp41-families-top40.md`
(**40 of 40 yes**). The verifier's numbers: Fraunhofer 2,727 + 8 + 1 + 1 is one card of 2,737 (4 rows merged, the "FOERDERUNG" spelling a
variant), INSERM 1,003 + 1, TNO 934 + 3 + 2 one card of 939, Politecnico di Torino 584 + 1. "AP-HP, 6 rows": those six are buyer rows
(no participation), so no card changes; `same_name` is built and tested (one name, two PICs).

## N6: EDF members

The first reading dropped 35 names (the quote check compared words with spaces) and the answer left out 8 more rows; 31 of 283
sheets. Now: the check compares letters only; a glued name is stored with the spacing of one plain-text line (only for names that show
the signs: a word of 15 letters or more, or a capital inside a word; the plain text prints "SAS" as "SA S" on some sheets, which
the first version of this rule would have copied); the rows of the table the answer lacks are read without a model
(`table_entries`) from the text still in the raw store. Run against the 283 landed texts and the stored facts (offline): **36
members recovered on 27 sheets** (ARCHER, EMISSARY, MARTE, ACTUS, NG-MIMA, ESOCA, RESILIENCE-R-2023, LACE, ...), **no sheet is left
short of the number of names it lost**. After recovery the table has as many rows as the sheet has participants on **278 of 283
sheets** (253 before); the five others are table rows the reader cannot pair (NEUMANN: the reader finds 36 rows, 37 are stored: the
model had one more). Hand check of 20 random sheets (seed 41): **19 of 20 yes** (table rows = participants, one coordinator mark =
one coordinator); the 20th is NEUMANN. 24 stored glued names would be respaced (all improvements; "HelzelMesstechnik GmbH", "UNIVERSITEDULUXEMBOURG",
"PrismaElectronics ABEE", ...). Names that need a model: none by the stored counts; a name whose break falls inside a word
("PLIROF ORIAS") is recovered with the break and resolved by the fold key (the merge joins it to its twin). A model re-read would cost
about USD 0.0015 a sheet (0.42 USD for 283), and only after the stored row is removed or `PROMPT_VERSION` raised.

## N8 to N12

* **N8** the category is the last category token of the code (`edf_factsheets.category_of`): call 106 is SMERO (it was DIS), call 93
  AIRDEF; the stored project `EDF-2023-DA-DS-AIRDEF-EATMI` was filed under DS (`edf_recover` refiles it). A test per call for all
  **40** EDF-prefixed calls (`tests/unit/test_wp41_partners.py`). EDIP: `...-AMDS` (air and missile defence) is compared with AIRDEF,
  `...-GNPS` with GROUND and NAVAL, `...-C5ISRS` with C4ISR and SPACE, said in `area.rule` as our reading of the title; the other nine EDIP calls (108,
  109, 113 to 118, 193) have no counterpart in the EDF's categories and say so (`area.generic`, a `note`): the same list for every
  such topic was the verifier's finding, and it cannot be fixed by a better rule, only labelled.
* **N9** `topic=HORIZON-CL3-2023-DRS` now matches the stored `HORIZON_HORIZON-CL3-2023-DRS-...` and the call code; a topic that matches
  nothing says so in `limits`; the EDF-factsheet limit is shown only for EDF queries.
* **N11** RENK: `Renk Aktiengesellschaft` and `RENK GmbH` have one key and two legal-form classes. The cascade (aliases, exact name)
  skips an organisation that has only been called by another class and makes a new one with a `legal_form_conflict` review row. The
  stored supplier is repaired by `ops/split_legal_forms` unless the notices state the same registration number for both forms (the register
  says one body). "Maybe 1 more of 4,186": the tool lists them on the dry run; I could not run it on production here.
* **N12** the display name follows a **rename** (a different key), not a respelling (13 of 72,534 differ in accents or punctuation:
  "Fundación" is not improved by "FUNDACION"); the old name stays an alias. SANSIRRO / QUS TECH cannot be shown today: the open data copy still prints
  SANSIRRO.

## Hostile review of my own diff

I read every changed file again and ran the checks against the live service and the production dumps. **12 findings, 12 fixed**, 9 pinned
by a test that fails without the fix:

1. **The new organisation query was refused by the live service (HTTP 500)**: `(MIN(?vat) AS ?vat) ... (GROUP_CONCAT(?vat) AS ?vats)`
   reads a variable an earlier expression has renamed. The stand-in service cannot see this; found only by running the real query. A text test now pins
   the rule for all three queries.
2. The display name would have replaced 13 accented names with CORDIS's unaccented ones: rename means a different key (test).
3. A project with 148 participants and a 0.2 % excess lost every amount: a 2 % allowance (test).
4. A first dry run of the merge found 19,775 groups / 23,976 rows, mostly procurement buyers: restricted to groups that touch a project participant (test).
5. The EDF rows would have kept a `NULL` note for good (the monthly job does not read fresh files again): the repair marks them (test).
6. `edf_recover` could write a project under a key the loader had not given it: the key is checked.
7. The respacing rule copied the plain text's own faults ("SA S"): applied only to names that show glue (test).
8. The merge loaded 430,000 organisations as rows (about 600 MB): two passes, buckets only (about 100 MB).
9. `_settle_organisation` carried an unused parameter.
10. Two existing CORDIS tests had amounts that exceed their project's total (a fixture inconsistency the new rule rightly refuses): the totals were raised in
    the fixtures, the assertions are unchanged. One WP-32 test and one unit test used `...-CPA-AMDS` as the example of an EDIP topic with no
    category; it now has one, so they use `...-CPA-CDS`.
11. `Renk G.m.b.H.` has another key than `Renk GmbH` (the key strips only the written forms); a pre-existing limit of `key_of`, not widened here.
12. Test numbers like `DE811111111` are rejected as junk by `normalise_identifier`; the tests use realistic digits.

## Tests

* `tests/unit/test_wp41_money.py` (34), `test_wp41_edf.py` (11), `test_wp41_families.py` (43), `test_wp41_partners.py` (44): amounts and notes,
  the country vote, the SPARQL alias rule, the quote check and recovery, the merge plan and the vetoes, the family stars, all 40 calls.
* `tests/integration/test_wp41_money_country.py` (13) and `test_wp41_networks.py` (12): the loader's amounts and notes, the repair
  equal to the loader and idempotent, the country moved with its aliases, the targeted country repair reading only the organisations, the
  merge (head, method, confidence, alias memory, review closed, directory counted once, idempotent), the family in the directory, on the card
  and on the profile (card = profile), the legal-form guard in the cascade and the supplier split, the gaps route, the EDF recovery with a real
  PDF text, the refiling of a category.
* Ruff clean. Unit suite (default marker): all pass, including the web-fixture tests once `web/` and `infra/` are present on the server
  (the first run failed five tests only because the test copy had no `web/` directory). Integration: the files that touch the changed
  code (`test_network_api`, `test_networks_*`, `test_wp32`, `test_wp41_*`, `test_supplier_map`) pass; the full integration run is
  recorded in the report. `tsc --noEmit` of `web/` is clean (the `node_modules` of another implementer's copy, mounted read-only).

## Not checked, not met

* **The full integration suite on the final tree**: see the report; the host is shared with several other full runs.
* The new directory refresh SQL (two indexed joins added to the 33 s job) and the profile's extra queries were not timed on production-sized
  data: the new table does not exist in production, and a copy of `participation` did not fit the scratch budget. The profile adds
  one query on a table of about 60 rows; the directory list adds one column.
* `ops/split_legal_forms` and `ops/org_dedupe` were run on fixtures and, for the merge plan, offline on a full dump of production; their
  `--yes` runs on production are the orchestrator's.
* The CORDIS monthly CSV package (which has the net figures) was not looked at: `/data/` is disallowed.
* N3 and the stale pages (JOANNEUM, Granada, VTT) cannot be corrected from the open data.
* Playwright specs: none written for the card line (one line of text); `tsc` only.
