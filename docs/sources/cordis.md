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
