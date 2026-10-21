# CORDIS (`cordis`): research projects, organisations and participations

Read on 17 October 2026. Connector: `backend/dgate/sources/cordis.py`; loader `backend/dgate/networks.py`
(`run_cordis`); command `python -m dgate.pipeline cordis`; monthly worker job `cordis_monthly` (day 5).

## The finding that shapes the connector: the bulk files are not ours to fetch

The appendix (Part III) names the data.europa.eu packages for Horizon Europe, Horizon 2020 and FP7. Their
distributions (read from `https://data.europa.eu/api/hub/search/datasets/<id>`) all point at
`https://cordis.europa.eu/data/cordis-<PROGRAMME>projects-{csv,json,xml,xlsx}.zip`, for example
`cordis-h2020projects-csv.zip`, `cordis-HORIZONprojects-csv.zip`, `cordis-fp7projects-csv.zip`.

`https://cordis.europa.eu/robots.txt` says, for every agent (read 17 October 2026):

    Disallow: /data/        Disallow: /search        Disallow: /publication/        Disallow: /booklet/ ...

The brief for this work says to honour robots.txt, so **no file under `/data/` is requested, by the code or by
the author of this work**, and no bulk-file parser was written for a format that could not be inspected.
What is open is CORDIS's own SPARQL service, documented on `https://cordis.europa.eu/about/services` and
`/datalab/sparql-endpoint`: `GET https://cordis.europa.eu/datalab/sparql?query=...` with
`Accept: application/sparql-results+json`, anonymous, not disallowed (`/datalab` is not in robots.txt). The
connector reads robots.txt first and refuses to run if the SPARQL path is ever disallowed (tested).

If the owner wants the monthly CSV package instead (it may be fresher, see "Coverage" below), the download has to be
a decision of the owner (a browser download is what a person would do); an importer for the files would then be a
small addition reading the same `OrgRecord`, `ProjectRecord` and `RoleRecord` shapes.

## The twelve questions (technical appendix Part V)

| # | Question | Answer |
|---|---|---|
| 1 | Official open data page, publisher | CORDIS, Publications Office of the EU for the Commission's research directorates. Datasets `cordish2020projects`, `cordis-eu-research-projects-under-horizon-europe-2021-2027`, `cordisfp7projects` on data.europa.eu |
| 2 | API, bulk, feed | Bulk zips (CSV, JSON, XML, XLSX) under `/data/` (robots-disallowed, see above); a SPARQL endpoint; RSS. SPARQL is used |
| 3 | Registration | None for SPARQL. (A "data extraction" API exists behind an EU Login account: not used.) |
| 4 | Format, specification | SPARQL 1.1 JSON results. Vocabulary at `http://data.europa.eu/s66#` (classes `Project`, `Organisation`, `OrganisationRole`, `GrantPayment`, `Grant`, `MonetaryAmount`, `Site`, `PostalAddress`). No published specification was found beyond the service page; the shapes used here were read by querying (below) |
| 5 | History | FP7 (2007) to Horizon Europe. Earliest project start date in the service: 2001-01-01 (a few older records); FP7 and later are the bulk |
| 6 | Update frequency, lag | The data.europa.eu description says monthly. The SPARQL copy lags: latest project start date 2025-11-01, and Horizon Europe grant numbers stop in the 1012xxxxx range (see "Coverage") |
| 7 | Licence | Every distribution carries licence `COM_REUSE`, "European Commission reuse notice" (Commission Decision 2011/833/EU, `http://data.europa.eu/eli/dec/2011/833/oj`); `https://cordis.europa.eu/about/legal` states that the Commission's reuse policy is implemented by that decision. The decision permits reuse, commercial reuse included, with attribution and without distortion. Same licence as the `eu_portal` source. Attribution stored in `source.attribution` |
| 8 | Rate limits | None stated for SPARQL. Observed: at most 10,000 rows per answer (a `LIMIT 50000` returned 10,000); an answer takes 0.2 to 10 s. The connector asks for 2,000 to 5,000 rows, one request at a time, at most one a second |
| 9 | How updates are represented | Overwrite: the service shows the current state only. The loader updates the project in place, marks a participant who is gone `active = false`, and the monthly `consortium_snapshot` records the composition |
| 10 | Retention limit | None seen |
| 11 | Separate datasets | Horizon Europe, Horizon 2020 and FP7 are three datasets on data.europa.eu but one graph in SPARQL; the framework is read from the topic prefix (`HORIZON_`, `H2020_`, `FP7_`), then the call prefix, then the grant number and the start year |
| 12 | Personal data | The queries select organisation, project and participation fields only: no person, no contact, no abstract, no keyword, no result. Legal names of organisations are stored as published; a sole trader's own name can be one (not measurable from the data; listed in `docs/DATA_PROTECTION.md`) |

## Shapes read (17 October 2026)

Counts from `SELECT COUNT(DISTINCT ?x) WHERE { ?x a e:<Class> }`: **80,208 projects, 72,534 organisations,
398,584 participations** (`OrganisationRole`), 422,007 payments.

* A participation has `isInvolvedIn` (the project), `isRoleOf` (the organisation), `roleLabel` (coordinator 75,997,
  participant 284,739, associatedPartner 15,298, thirdParty 14,750, partner 7,589, internationalPartner 211) and,
  through `isRecipientOf` / `hasPaymentAmount` / `value`, an amount in euro. 3,115 have no payment; 70 have two
  (summed). All 669,411 amounts are EUR.
* An organisation has `identifier` (**the PIC**, 72,219 of 72,534; no PIC is shared), `legalName`, `vatNumber`
  (42,912), `rcn`, and a country through `hasSite / hasAddress / addressCountry`. CORDIS writes the Commission's
  country codes: `UK` and `EL` are mapped to `GB` and `GR`. 13 organisations have no country and are skipped (counted).
* A project has `rcn` (the unique record number: **the key**), `identifier` (the grant agreement number), `title`,
  `startDate`, `endDate`, `duration`, `projectStatus` (CLOSED 53,768; SIGNED 24,471; TERMINATED 1,952), `hasTotalCost`
  and, through its grant, `hasFundingAmount` (the EU contribution), `hasFundingSchemeCall`, `hasFundingSchemeTopic`.
* **The grant number is not unique**: four records share 101197076, three share 101217617, and so on. It is stored
  and indexed, not made a key.
* ERC and MSCA records state a total cost of 0; the loader stores that as "not stated".
* Organisations and roles are joined by the service's own identifier inside one run, not by `rcn` or PIC (a PIC is
  missing for 315 organisations, an `rcn` for 57). 16,091 roles point at 1,021 organisation identifiers that the
  service does not define at all (no triple: no name, country or PIC; the role label carries a name only): they are
  counted (`roles_unlinked`) and not stored.
* Framework by topic prefix: H2020 35,361 projects, HORIZON 17,580, FP7 15,556, no topic about 11,700 (read from the
  call or the dates, see the code).

Paging: keyset on `STR(?x)` with `GROUP BY ?x ORDER BY STR(?x) LIMIT n`, so a row is never half an entity and no page
repeats or skips. Each answer is checked against the service's own count (`COUNT(DISTINCT ?x)`): a pass that read less
than 99.5 % of it fails the run and nothing is marked inactive.

## Coverage, honestly

The SPARQL copy is older than the monthly package may be. Horizon Europe: 17,580 projects with a topic in the service,
latest start date 2025-11-01; the grant numbers 101121253 (a 2023 project) and the EDF grant numbers are not found.
Horizon 2020 and FP7 are complete for practical purposes (H2020 35,361 projects). The product shows "as published
by CORDIS, copy of <date>"; a gap in recent Horizon Europe starts is a known limit, measured on 17 October 2026, and
is the one reason to ask the owner for the monthly package.

EDF projects are **not** in CORDIS (grant numbers 101224281 and 101304876 do not exist there): see `edf_factsheets.md`.

## What a full load did (17 October 2026, scratch copy of production)

35 minutes, 551,237 rows read, 67,113 organisations created and 5,404 matched to organisations the buyer side already
held (by alias or exact name, same country), 80,208 projects, 382,155 participations, +142 MB in the database for
CORDIS alone (362 bytes a project, 165 bytes a participation, 432 bytes a new organisation), +33 MB in the raw store.
A second pass, with every organisation found by PIC, takes 12 minutes. 16,064 participations (4 %) belong to 1,021
organisation identifiers that the service does not define (no name, country or PIC): they are counted in
`roles_unlinked` and not stored. 276 organisations met twice in one project are merged into one participation
(coordinator wins, amounts added).

## Scope decision (measured)

All three frameworks are loaded: FP7 23,914 projects, Horizon 2020 37,137, Horizon Europe 18,211, 946 with no
programme at all (no topic, call, grant number or start date; they have no participants either). The cost of FP7 is
a quarter of the bytes, so there is no case for leaving it out; a subset would need a stated rule and none is applied.
`--programme` keeps one or two frameworks if the owner wants less (organisations are always all read).

## How the source appears on the site

The source is seeded **inactive** (migration 0060) and its first finished run switches it on. `/v1/health` lists every
active source and calls one that never ran `unhealthy`; a monthly source with a weekday floor would also be called
stale after 36 hours. The floor of this source is therefore a plain setting (`DGATE_FLOOR_CORDIS`, 400,000 rows)
and not an entry of the daily floor table. Its kind is `grant`, as for the other funding sources.

## What an amount means, what a null means (WP-41, 18 October 2026)

Found by reading the SPARQL fields of a handful of projects and the same projects' CORDIS pages (nine project pages,
`/project/rcn/<n>`, which robots.txt allows; `/data/` and `/search` were not requested; about 30 SPARQL requests, one a
second, the connector's User-Agent):

* The only money on a participation is the **grant payment of its role** (`isRecipientOf` / `hasPaymentAmount` / `value`).
  There is no "net" amount and no link from a third party to the beneficiary it is linked to (role properties: `order`,
  `roleLabel`, `isBeneficiaryOf`, `isInvolvedIn`, dates; nothing else).
* The CORDIS page prints, per participant, the **net EU contribution**: "the sum of money that the participant receives,
  deducted by the EU contribution to its linked third party" (the page's own definition). The open data pays the
  beneficiary the gross and shows its third parties at 0. Example, ERC 695618: payment to the Universite de Lorraine
  2,810,229 (= the project total), CNRS (third party) 0; the page: Lorraine 2,248,040, CNRS 562,189. This is the cause of
  the coordinator-equals-project-total cases and of the 13,701 third-party rows stored as 0 (8 of 10 read on the pages had an
  amount). The loader now stores a third party at 0 as unknown (`NULL`, note `linked_third_party`) and a participant of a
  project that has third parties with the note `gross_of_third_parties`.
* Where the service holds **no payment at all** for a role (the grant has no payment and no funding amount: recent Horizon
  Europe grants, 273305, 274592, 277703, 274757; and single roles such as the CNR in 236264) the amount is unknown: `NULL`,
  note `no_payment_stated`. The 1,749 H2020 / Horizon Europe participant rows with a null amount are of this kind; CORDIS shows
  an amount on the page for 10 of 12 read. **Not fixable from SPARQL.** Options for the owner: the monthly CSV package
  (`organization.csv` has `ecContribution` and `netEcContribution`; a person downloads it in a browser, as for the German
  portals), or a targeted read of about 1,000 project pages (about 20 minutes at one a second, robots.txt allows `/project/`; a
  new HTML reader to build and keep).
* The open data is **older than the pages**: JOANNEUM (238600) 1,652,264.59 and Granada (241820) 165,312.96 were amended on
  the site (1,823,370.98 and 182,596.14; the service's own project total of 241820 is the old figure too). Not a loader
  defect; the age of the copy is the limit (`Coverage`, above).
* A project whose participants' amounts add up to **more than its EU contribution** (33 projects on 17 October: ERC grants
  that moved between two hosts and are paid to both in full, grants amended after the payment was recorded) cannot be
  right in every row and the data does not say which. Every positive amount of such a project is withheld (`NULL`, note
  `exceeds_project_total`), the figure as stated is kept in `participation.contribution_stated`. One euro per participant (CORDIS
  rounds) and 2 per cent of the project total (an amendment moves a few thousand euro) are not an excess. 391 amounts, EUR 889.8 M
  of 141.2 bn, 18 of them a coordinator carrying the whole project; 278 of the 391 are in five projects.

`participation.contribution` is therefore "EUR the service pays to this participant, gross of its linked third parties,
`NULL` = unknown"; the column comment and migration 0086 say the same, `contribution_note` is a closed list. The directory
and profile sums skip `NULL`. Repair of rows already stored, without a reload: `python -m dgate.ops.repair_contributions
[--yes]` (reads the stored rows, no network; the loader applies the same function).

## Country and name of an organisation (WP-41)

The organisation record has a country only through its sites (`hasSite` / `hasAddress` / `addressCountry`). Of 72,534
organisations **one** has sites in two countries (FUNDACAO EUROCEAN, Lisboa PT and 's-Gravenhage NL, with two VAT numbers),
and **one** has a site whose name contradicts its address: PIC 999991722 (CSIC) has the address "Belenzani 19, 38122
Trento, IT" under the site name "... CIENTIFICAS Madrid ES" and VAT ESQ2818002D; the project pages (participation
addresses) show Spain. It is not a multi-site problem: the record is contradictory, and the first load took the address.
`cordis.seat_country` decides from the three signals the record gives (address, the country its site name ends with,
the prefix of its VAT number): all agree or only the address speaks, the address; the name and the VAT number agree
against the address, that country (`organisation.country_basis = 'vote'`); sites in several countries, the first one and the
list (`'several'`, `country_sites`). One signal against the address changes nothing (CrowdHelix: address IE, VAT IE, site
name "London UK"). The repair needs 15 requests: `python -m dgate.pipeline cordis-countries [--yes]`.

The display name follows the name CORDIS prints now (`_settle_organisation`); the earlier name stays an alias (it was
recorded when the organisation first met it). The service's copy lags the site: SANSIRRO GMBH (PIC 422890) is printed
QUS TECH GMBH on the site and is still SANSIRRO in the service, so the mechanism will act when the service catches up.


## A payment read twice (WP-43, 18 October 2026)

The roles query sums a role's payment (`SUM(?amt)` grouped by the role). The other patterns multiply the rows it sums over:
a role that points to two organisation nodes, or to two projects, was read once per combination, so its payment came out
doubled. 207 of the 398,584 roles are such (on 18 October); in 168 of them one node is a bare reference (a URI with no
description at all) beside the real organisation, in the others both are described. The biggest effect is on one body:
CEA (PIC 888898201) carries a bare duplicate node in many projects (ENEN2plus: 92,035 stored for the 46,017.50 the
open data holds; a 549 million euro project listed 118 million for CEA instead of 59 million). `cordis.role_record` now divides
the sum by `orgs` x `projects` (`COUNT(DISTINCT ?o)`, `COUNT(DISTINCT ?p)` of the query), and the organisation of the role is
the node with a description (`real_org`) when there is one. Measured on the live service: the query costs 8.7 s a page
instead of 5.9 s. `python -m dgate.ops.repair_role_multiples [--yes]` corrects the rows already stored (one request).

16,012 roles (4.0 per cent) point only to a bare node: the service names no organisation for them, so they cannot be loaded
(for example a 121,500 euro participant of SLAFNET). They are the `roles_unlinked` of the load report.

A figure on a CORDIS project page that differs from the open data is not this: MedMaD (172,750.08), RECOMBINE (41,400)
and E-TANDEM (240,750) are what the service states; the page was amended later. A participation that ended is shown at
0 on the page; the open data holds no end of participation, so the stored amount stays.

## The bulk packages (WP-70, 21 October 2026)

**Decision.** The owner authorised on 21 October 2026 the download of free public data that improves the product. The
three CSV packages below were downloaded once each, from the server, one file at a time, with the connector's
User-Agent. `robots.txt` still disallows `/data/` for every agent (read again on 21 October 2026), so the download is an
operator's command (`--download`), never a scheduled job: no worker entry calls it.

**Where the URLs come from.** `dgate.ops.cordis_bulk.bulk_urls` reads the data.europa.eu dataset pages
(`https://data.europa.eu/api/hub/search/datasets/<id>`, ids `cordisfp7projects`, `cordish2020projects`,
`cordis-eu-research-projects-under-horizon-europe-2021-2027`) and keeps the distribution whose download URL is the
projects CSV package. Read on 21 October 2026:

| Package | URL | Bytes | Last-Modified | sha256 (first 16) |
|---|---|---|---|---|
| FP7 | `https://cordis.europa.eu/data/cordis-fp7projects-csv.zip` | 32,953,397 | 2 January 2025 | `886ee47973584971` |
| Horizon 2020 | `https://cordis.europa.eu/data/cordis-h2020projects-csv.zip` | 55,246,902 | 8 October 2026 | `7c00e367edbb2216` |
| Horizon Europe | `https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip` | 37,509,664 | 8 October 2026 | `b9919057b77e897a` |

**Licence.** Every distribution carries `COM_REUSE`, labelled by data.europa.eu "European Commission reuse notice"
(`http://data.europa.eu/eli/dec/2011/833/oj`). CORDIS's legal notice (`https://cordis.europa.eu/about/legal`, read 21
October 2026): "The Commission's reuse policy is implemented by Commission Decision 2011/833/EU". The same notice
licenses CORDIS's editorial content under CC BY 4.0 (credit, changes indicated); the attribution stays
"Source: CORDIS, European Commission", and a changed amount keeps the reason in `contribution_note`.

**Shape.** Each zip holds `project.csv` and `organization.csv` (and others not read), `;`-separated, quoted, UTF-8 with a
byte-order mark. `organization.csv` has one row per participant and project: `projectID` (the grant number),
`organisationID` (the PIC), `role` (`coordinator`, `participant`, `thirdParty`, `partner`, `associatedPartner`,
`internationalPartner`), `ecContribution` (the gross EU contribution, as the SPARQL payment: a third party is 0 there),
`netEcContribution` (net of linked third parties, what the project page prints; empty for FP7), `country` (`UK`, `EL`),
and name, address, URL and a link to a contact form. **No contact person is in the files**; the module reads only
`projectID`, `organisationID`, `role`, `ecContribution` and `country` and nothing else is held. `project.csv` gives the
record number (`rcn`) of each grant number. Rows: FP7 140,064 (472 without a PIC, 1 shifted by a stray quote: skipped),
H2020 179,046, Horizon Europe 148,155. Reading all three, streamed: 14 s, 54 MB of memory.

**What it changed and why** (rules in the docstring of `dgate/ops/cordis_bulk.py`, tested in
`tests/unit/test_cordis_bulk.py` and `tests/integration/test_wp70_cordis_bulk.py`):

* `no_payment_stated` amounts get `ecContribution` (the gross figure, the meaning of the column). 18 of 18 sampled rows
  equal the figure on the CORDIS project page.
* an amount that is an exact multiple (x2, x3) of `ecContribution` becomes that figure (the WP-43 defect, rows the
  one-request repair could not match).
* any other difference is **kept** and counted (`differs_kept`): the bulk is a later copy and the project pages show
  amendments (WP-41), but the rule "the newer file wins" was not given and is the owner's to decide. Neither is the
  switch of the column to the net figure.
* a fill that would push its project over the EU contribution (and so withhold amounts shown today) is dropped.
* countries are compared only: `organisation.country` is NOT NULL, so no stored participant is without one.

Production dry run, 21 October 2026: see `docs/verification/product/wp70-selfcheck.md`.
