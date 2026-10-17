# WP-26 self-check: networks data (layer 2, data and resolution)

Branch `wp-wp26`, 17 October 2026. Written by the implementer for the verifier. Everything below was run on the
server (`/root/dev-h`, test database `agent_h`, scratch database `agent_h_scratch`, now deleted); nothing ran on the laptop and
nothing was written to production. No language model API was called: the EDF extraction ran on the real
factsheets with a stand-in that reads the table without a model (see "What could not be checked").

## Verdict per acceptance criterion

| # | Criterion (brief) | Verdict | Evidence |
|---|---|---|---|
| 1 | Migrations 0060-0062: project, participation, consortium_snapshot, resolution_review, resolution_gold; PIC and identifier method on organisation; rows and bytes per project and per participation | **Met** | below, "Rows and bytes" |
| 2 | CORDIS importer, real URLs and shapes, licence, scope on measurement, idempotent, raw landed first | **Met, with one deviation** | The bulk files are robots-disallowed, so the importer reads CORDIS's SPARQL service (open, documented). Counts match the service's own counts; they could **not** be compared with the CSV package counts. "CORDIS" below |
| 3 | EDF factsheet pipeline, URL pattern checked, file names parsed, strict schema, quote check, fake client, no live run | **Met** | "EDF" below. The plan's URL pattern is right for 2024 and 2025 only; four patterns found |
| 4 | Resolution stages 0-3, never an automatic fuzzy merge, method and confidence on every alias and link, Thales SA vs Thales Nederland not merged | **Met** | "Resolution" below; tests `test_networks_resolution.py`, gold pairs of kind `parent_child` |
| 5 | Gold set of 150 pairs (75/75) and `resolution-eval` with precision and recall per stage, precision >= 0.97 where a stage decides alone | **Met** | 172 pairs (88/84); precision 1.000 (38 of 38) for the two deciding stages; recall 0.43 (the gold is made of hard cases); stage 3 proposes with precision 0.80 and never decides. "Gold set" below |
| 6 | Monthly consortium snapshot and `consortium.changed`; worker jobs; job-list test | **Met** | "Snapshots" below; `test_networks_snapshot.py`, `test_worker.py` |
| 7 | Read-only CLI report | **Met** | `python -m dgate.ops.networks_report`; timings below |
| - | Counts match the package counts of the sources | **Partly** | the service's counts, yes (72,534 / 80,208 / 398,495 of 398,584 roles read, the rest explained); the monthly packages cannot be fetched under robots.txt |
| - | Second run creates zero rows | **Met** | real data, "CORDIS" and "EDF"; fixtures in the integration tests |
| - | EDF extraction runs against a fixture PDF with a fake model | **Met** | `test_networks_edf.py` (a PDF written by `tests/pdfmaker.py`), and 284 real factsheets with the stand-in |
| - | Scratch cleaned | **Met** | "Scratch" at the end |

## Rows and bytes (scratch database, 17 October 2026, production `organisation` and `organisation_alias` copied in first)

| Table | Rows added | Bytes added (heap + indexes) | Per row |
|---|---|---|---|
| organisation (CORDIS) | 67,113 new, 5,404 matched to existing buyer rows | 29 MB | 432 B per new organisation |
| organisation_alias | about 72,500 | 21 MB | 290 B |
| project | 80,208 CORDIS + 284 EDF | 29 MB (heap 19 MB) | **362 B per project** (237 B heap) |
| participation | 382,155 CORDIS + 4,139 EDF | 63 MB (heap 34 MB) | **165 B per participation** (89 B heap) |
| consortium_snapshot | 77,109 (first snapshot) | 14 MB | 181 B |
| project_factsheet | 284 | 0.6 MB | 2.3 kB |
| resolution_review | 829 (EDF load; stage 3 run over 12,000 CORDIS organisations) | 0.4 MB | |
| raw store (gzip bundles) | 111 pages of CORDIS, 284 factsheets | 33 MB + 1.2 MB | |
| **Database** | | **314 MB -> 476 MB (+162 MB)** | |

Production estimate for the first load of everything: **+165 MB in the database, +35 MB in the raw store**, plus the
candidate pass (about 2,400 review rows, under 2 MB). The write-ahead log during the load was not measured. Free
disk on the host during this work: 2.5 to 3.8 GB.

## CORDIS

* Source of the data and why: `docs/sources/cordis.md` (read it first). `robots.txt` of cordis.europa.eu disallows
  `/data/`, where all bulk files live; `/datalab/sparql` is open. 80,208 projects, 72,534 organisations, 398,584
  participations, all EUR, no key, 10,000 rows an answer at most. Licence: Commission Decision 2011/833/EU
  (`COM_REUSE` on every distribution; cordis.europa.eu/about/legal).
* **First full load**: 35 minutes, status success, 551,237 rows read (72,534 + 80,208 + 398,495). 67,113 organisations
  created (66,857 by PIC, 258 by name because the service gives no PIC), 5,404 matched to organisations the
  buyer side already held (5,402 by alias, 2 by name; all with the same country), 4 ambiguous (queued), 13 skipped
  (no country). 80,208 projects, 382,155 participations (276 organisations met twice in a project were merged:
  coordinator wins, amounts added).
* **Not linked, counted, not hidden**: 16,064 of 398,495 participations (4.0 %) point at 1,021 organisation
  identifiers the service does not define at all (no triple), so there is no name, country or PIC to store. The
  role label carries a name only.
* Scope: all three frameworks. FP7 is 23,914 of 80,208 projects and about the same share of the bytes (about 42 MB
  of the 142); there is no reason to leave it out. `--programme` takes a subset.
* Framework of a project: from the topic prefix, else the call prefix, else grant number and start year.
  Loaded: **Horizon 2020 37,137, FP7 23,914, Horizon Europe 18,211 projects**; 946 have none of the signals (and no
  participant) and are stored without a programme.
* **Coverage limit**: the SPARQL copy lags the monthly package. Latest project start 2025-11-01; Horizon Europe
  holds 18,211 projects and some of 2023 (grant 101121253) are missing. Stated in `cordis.md`.
* Idempotency on the real data, same code twice back to back: see "Second runs" below.

### Hand check of rows (15 random participations, 17 October 2026)

Each row was read back from the live service with a differently shaped query (project record number and PIC,
role label, summed payment, country) and compared: **15 of 15 yes** (role, amount to the cent, country). Sample:
ALTFInator / UAB MEDIAPARK (LT) participant 127,937.50; NANOTRIOSTEO / CSIC (IT, PIC 999991722) coordinator
216,200.00; PERMAGOV / Finnish Environment Institute (alias match) participant 462,962.50; metaC-Hfunct / University
of Manchester (alias match) coordinator 183,454.80; Aqua Gratis / Cascade Water Products coordinator 50,000.00.
The 15 differ in framework (FP7, H2020, Horizon Europe) and in how the organisation was reached (13 by PIC, 2 by alias).

Matches to organisations the buyer side already held (5,324 organisations, counted by the PIC they now hold): 40 drawn at random and read by eye,
**40 of 40 the same body** (municipalities, universities, water boards, public agencies; the full list is not
reproduced). This is a reading by one person of name and country, not a registry check.

Observation worth a person's attention: CORDIS states the country of the **site** of a PIC, so the Spanish research
council CSIC (PIC 999991722) is a participant in Italy while the buyer side holds the Spanish body of the same name
(`ES`). The country veto keeps them apart. Gold kind `other_country` and `duplicate_pic` document the effect.

## EDF

* `docs/sources/edf_factsheets.md` has the URLs. **The plan's pattern holds for 2024 and 2025 only**: the five
  results pages are at four addresses, found from the site's sitemap. The file name convention holds for 2024 and
  2025 and has exceptions (a file with no grant number); 2023, 2022 and 2021 have their own. Not 57 projects but
  **60** factsheets for 2025 (two continuation grants of the 2024 RESILIENCE project and one CSA included; if those
  three are not "projects selected" the count is the appendix's 57, which is a guess, not a finding).
* Totals loaded (284 factsheets, 5 results pages, 2 duplicate uploads folded): **2021: 60, 2022: 41, 2023: 61, 2024: 62,
  2025: 60 projects; 2021-2024 together 224, which is the appendix's "224 projects selected across the four calls"**.
  EU contribution per call year: 1,162 M, 831 M, 1,008 M, 946 M, 1,037 M EUR. 4,139 participations; 2,021 distinct
  spellings of entities became 1,847 organisations (834 of them already in CORDIS with a PIC, 1,013 without).
  Appendix 2025 figures not reproduced: 634 entities (here 542 distinct spellings, 875 participations), DA/RA
  split 32/25 (here 27/32 by the file-name token, 691 and 343 M EUR against 675 and 332 M EUR).
* **The site rate-limits**: 125 of the first 284 downloads, made one a second, were answered HTTP 429 after about
  a hundred. `fetch_pdf` now waits out a 429 (the `Retry-After`, else 10 to 80 s), slows the whole run, and a site that
  keeps refusing ends the run as `partial` instead of failing files one by one. A file read in the last 25 days is not
  fetched again. The second pass, with the 125 left, took 31 minutes. A first live run will take about 40 minutes.
* Run status: a factsheet that cannot be read, one that gives no participants, the model budget reached, and a rate-limited
  site each make the run `partial`. On the real data one factsheet gave no participants (GEDIRIS, whose table header is
  split over two lines; a stand-in failure) and the run said so.
* **Quote check** on 284 real factsheets with the stand-in: 19 names not in the text dropped and counted. New in this
  work: the table of each factsheet is also read without a model (`table_rows`); a country the model pairs with a name
  differently from the name's own row is replaced by the printed one, and rows the model leaves out are counted
  (`missing_from_answer`).
* Estimated live cost: mean layout text 2,616 characters (max 14,422), about 1,300 input tokens and 700 output tokens
  a file at the configured prices: **about USD 0.42 for the 284 files**, once; a month later only new or changed files.
* Hand check: two factsheets read against the database in full (STRATUS: 13 of 13 entities, countries, amounts;
  EURODAMM: 12 of 12) and 15 random participations, each against its own factsheet read afresh: the entity's printed
  name and the country are in the file, **15 of 15 yes**. "Printed anywhere in the file" is weaker than "on the same row"; the
  row-level pairing is what `table_rows` now checks in the product.

## Resolution

* `dgate/resolution/`: `names.py` (Cyrillic transliteration of the Ukrainian national scheme, the legal forms of UA,
  RO, CZ and the Baltics, forms written without their dots, long forms spelled out, hyphens and ampersands as spacing),
  `trigram.py` (pg_trgm's arithmetic in Python; compared with the database in a test), `cascade.py`
  (`resolve(conn, name, country, identifiers, context) -> Resolution`), `evaluate.py`.
* Stages in the order they run: PIC; alias (country-bound, refused when the organisation holds another PIC);
  national number and VAT (only against a name that shares its words); exact normalised name in the country (one:
  that one, at 0.95; several: the better known, at 0.80, and the pair queued; a namesake with another PIC: a new
  organisation, the pair queued); trigram candidates at 0.85 in the country, same numbers in the name, queued and
  **never merged**. Stage 4 to 6 of the plan (embeddings, model adjudication, admin merge screens) are not built; the
  review queue is a table and the report.
* The old buyer-side key (`normalise_org_name`) is untouched: names stored with it are still found (both keys are
  tried), new rows get the new key. Changing the stored key would have orphaned every alias, as the code comment says.
* **Measured on the real load**: 829 rows in the review queue after the EDF load and a sample of 12,000 organisations
  of stage 3: `pic_conflict` 157 (the same name under two PICs), `exact_name_ambiguous` 7, `trigram` 665 (EDF
  spellings against CORDIS organisations, and the 12,000 sampled organisations). Stage 3 costs **38 ms an organisation** on the host (3,000 in 114 s,
  with the EDF load running at the same time), 46 minutes for all 72,500 CORDIS organisations; the estimate for the
  full queue is about 2,400 pairs. `--no-candidates` and `resolution-candidates` (resumable chunks) exist so the first
  load does not have to wait for it.
* **PIC is not the identity of an entity**: of 60 `pic_conflict` pairs read, nearly all were one body registered twice
  (Aalborg Universitet, Carl Zeiss SMT GmbH, Stanford, Paris Sciences et Lettres, ...) and a few were legal-form
  conversions (GmbH to AG). The cascade keeps them apart and queues them: a duplicate that waits for a person, not a
  merge that corrupts a history. This is the main thing the product owner should know about the graph.

## Gold set and evaluation

`backend/seeds/resolution_gold.json` (table `resolution_gold`, `dgate resolution-eval [--load]`): **172 pairs, 88
positive and 84 negative**, all taken from the real data of this work and labelled by one person (the implementer):

* 36 positives where a procurement notice and CORDIS state the same registry number under different names (identifier);
* 32 positives where an EDF factsheet spells a CORDIS organisation differently;
* 20 positives where one body is registered twice in CORDIS (two PICs; the cascade keeps these apart on purpose);
* 84 negatives: 29 parent and subsidiary or group mates (Thales, Safran, Siemens, Airbus, Kongsberg, Indra, Saab,
  BAE, Leonardo, ...); 20 numbered siblings (schools, depots, districts); 12 the same name in two countries;
  23 look-alikes of different institutions (7 universities, 9 pairs the stage-3 queue proposed, 5 pairs of
  companies (4 Polish) whose names differ by one word, 2 pairs where a notice states another body's registry number).

```
stage              said same  right  wrong  precision   recall
identifier                24     24      0      1.000    0.273
exact_name                14     14      0      1.000    0.159
candidate                 30     24      6      0.800    0.273
deciding_stages           38     38      0      1.000    0.432
positives no stage found: 26
```

* **Precision of the stages that decide alone: 1.000** (38 of 38). The command fails below 0.97 and a unit test runs it.
* **Recall of those stages: 0.43.** The gold is made of the cases that earlier stages left over (spelling variants of
  EDF against CORDIS, names with no word in common behind one registry number), so this is recall on hard cases, not
  on the whole flow; most easy pairs are already merged by stage 0 and 2 and are not in the set.
* Stage 3 proposes 30 pairs, 24 right: **precision 0.80, and it does not matter for safety**, because a proposal is
  only a row in `resolution_review`. The six wrong ones are real look-alikes (City University of London / University
  of London; Universidade Federal do Rio de Janeiro / Federal Rural; Kongsberg Maritime CM / Kongsberg Maritime;
  the two universities of Hong Kong; East China UST / USTC; Fundacao Universidade do Amazonas / Universidade do Estado).
* 26 positives are found by no stage: acronyms (`VRT`, `DZHW`), translations (`IBET`, `Jozef Stefan Institute`), script
  differences the scheme does not reach (`Obshtina Burgas` against `Община Бургас`), Greek, and the duplicate-PIC pairs.
  They stay duplicates until a person or stage 4/5 decides.
* **Caveat on independence**: the extra legal forms and the spacing rule of `names.py` were chosen after looking at
  the same EDF/CORDIS sample the gold positives come from, so the recall of `exact_name` is optimistic. The negatives
  were chosen independently of the rules (apart from the Polish long form, which turned 4 look-alike negatives into
  non-candidates). A second labeller has not seen the file.

## Snapshots and events

`networks.snapshot_consortia` (monthly job, day 7): one snapshot per project whose members or coordinator differ from
its last snapshot (or has none), one `consortium_change` row per project that had one before. On the real data: first
run **77,109 snapshots in 8.8 s**, second run 0 in 3.7 s; a participant marked inactive and snapshotted on a later day
gives exactly one change row (`removed [362103]`), the same day again none, the participant back one more.
Merged organisations are read through `merged_into` (test). A project that loses all its members gets no row. One
snapshot per project and day: a second change on the same day is recorded by the next run only.

## Report

`python -m dgate.ops.networks_report [--json] [--programme X] [--explain]`, on the full scratch data (read-only):

| Query | Execution (EXPLAIN ANALYZE) |
|---|---|
| projects and participations per programme and year | 2.0 s |
| 20 most frequent coordinators | 1.9 s |
| participants without PIC | 1.0 s |
| review queue | 1 ms |
| 20 organisations most often in an EDF project | 0.09 s |

Whole report 3.9 s from the command line (host idle; under load the same queries took 4.2, 4.1, 2.3 s). It is a command for the worker role, not an endpoint: against the API role's
5 s budget the first two queries would need the monthly numbers materialised (a table filled by the snapshot job); that
is for whoever builds the pages.

### EXPLAIN of the queries the resolver runs per organisation (scratch copy, 426,000 organisations, cold cache)

| Query | Plan | Execution |
|---|---|---|
| by PIC | `organisation_pic_uq` index scan | 4.9 ms |
| alias by normalised name | `organisation_alias_name_country_source_uq` index scan, then the organisation by key | 8.9 ms |
| exact name in a country | `organisation_country_name` index scan | 5.1 ms |
| registry or VAT number | bitmap-or of `organisation_reg_uq` and the new `organisation_vat` | 4.7 ms |
| trigram candidates (stage 3) | bitmap scan of `organisation_name_trgm` at 0.85 | 359 ms for one long name on a cold cache; 38 ms on average over 3,000 organisations |

No query of the first four scans a table; stage 3 is the one that costs, which is why it is optional in a bulk load.

## Second runs (idempotency on the real data)

Same code, back to back, on the scratch database that held a first load:

* **CORDIS, full pass (551,237 rows read, 12 minutes), twice**: 0 organisations created, 0 projects created or
  changed, 0 participations created, changed or deactivated. The row counts of organisation (425,953), alias
  (440,240), project (80,492), participation (386,302 then 386,341 after the EDF re-read below), raw_ingest (420) and
  resolution_review (829) are identical before and after each pass; only `ingest_run` grows. The raw pages are not
  landed again (same content hash).
* **EDF, 2022 (41 files fetched again with `--reread`)**: 0 model calls, 0 organisations, projects or participations
  created or changed, all six tables identical.
* An earlier pass of the same data with the code as it was 30 minutes before reported 131 changed, 8 new and 8
  deactivated participations. Two causes, both fixed: an organisation met twice in a project was written twice per run
  (now gathered and written once), and the spacing rule for hyphens had just changed the key of 39 EDF spellings, so
  they were re-resolved to the CORDIS organisations they belong to (their old rows were deactivated, not deleted). A
  change of key between releases does that once; a production first load uses the final code.

## Tests added

168 tests, none skipped, none weakened; the suite is 2,866 tests in all (ruff, unit and integration green on the branch).

| File | Tests | What it pins |
|---|---|---|
| `tests/unit/test_networks_names.py` | 33 | keys: Ukrainian example of plan M2-07, the legal forms of UA/RO/CZ/Baltics, dotless and long forms, spacing, the legacy key unchanged for Latin names, pg_trgm arithmetic, Thales SA against Thales Nederland, numbered siblings, the gold set (size, balance, kinds, precision >= 0.97, no parent or cross-country pair ever decided the same) |
| `tests/unit/test_cordis_source.py` | 22 | robots.txt first and refusal, keyset paging and its end, spacing of requests, retry, the key whitelist, framework from topic/call/dates, country codes, record readers, no abstract or keyword in any query |
| `tests/unit/test_edf_source.py` | 46 | 25 real file names of five call years, four result-page shapes in the sitemap, factsheet links (general sheets and other hosts excluded), description cut from a real PDF, quote check, wrapped names, table reader, country correction, 429 back-off, page cap, strict schema |
| `tests/integration/test_networks_cordis.py` | 15 | a full load against a stand-in service with 2-row pages, second run changes nothing, changed amount and vanished participant (marked, not deleted), an organisation twice in a project, PIC attached to a buyer organisation, namesake with another PIC queued, nothing merged, partial read refused, robots refusal, programme filter, rehearsal, no country, raw landed once, the real `/v1/health` |
| `tests/integration/test_networks_edf.py` | 17 | PDF to project and consortium, the description never reaches the model or the store, second run asks nothing, a changed file re-read and a leaver marked, organisation not duplicated, model down / budget / no participants / rate-limited = partial, duplicate upload, robots first, source switched on |
| `tests/integration/test_networks_resolution.py` | 26 | every stage and every refusal, Cyrillic and Latin one organisation, old keys still reached, VAT and registry numbers, candidates queued and never merged, review once, the resumable candidate pass, python and database similarity agree, gold loads once |
| `tests/integration/test_networks_snapshot.py` | 8 | two snapshots, one event; unchanged = nothing; leaver and coordinator; merged organisations; the report and EXPLAIN; API role reads and cannot write; worker role writes and cannot delete |
| `tests/unit/test_worker.py` | +1 and one expectation | the three monthly jobs in order and described; the job-list test names `cordis`, `edf`, `consortium-snapshot` (an expectation I extended on purpose) |

Existing tests whose expectation changed: only the worker job list. `test_the_worker_role_can_read_every_table_so_pg_dump_can`
stays green with the new tables.

## Hostile review of my own diff

I read every changed file again as a reviewer and ran the sample checks above against the real data. **18 issues
found, 18 fixed**, 16 of them pinned by a test that fails without the fix (13 and 18 concern the gold set,
which is itself the check):

1. The next-page key returned by the service went back into the next query as text, unchecked: now only identifier
   characters are accepted.
2. A failed CORDIS run recorded zero rows read (the counter was rebound only on success).
3. An alias without a country could carry a name across countries (`country_hint IS NULL`): the organisation must
   have the country asked for.
4. The EDF acronym check compared with tuple membership (equality), so the model's acronym was never used: found
   when the hand check of 15 rows failed on the first try. Substring now.
5. **`/v1/health` would have reported the service degraded from the day the migration is applied**: it lists every
   active source, calls a never-run one `unhealthy`, and calls a source with an entry in the weekday-floor table stale
   after 36 hours. The two sources start inactive (the first finished run switches them on), their floors are plain
   settings, their kind is `grant` (any other kind is listed as "tenders" on the public sources list). Tested through
   the real health endpoint, a run forty days old included.
6. A file uploaded twice (`X.pdf`, `X_0.pdf`) would have flipped the project between the two on every run: one file
   per project, the later upload.
7. The DEFIS site answers HTTP 429 after about a hundred downloads (125 of 284 refused): back-off, a slower pace for
   the rest of the run, `RateLimited` ends the run as partial, files read in the last 25 days are not fetched.
8. An organisation met twice in a project was written twice per run: every second run reported changes (131 on the
   real data). Gathered, merged, written once.
9. A link to another host, or a PDF of more than twelve pages, was accepted: host check, page cap.
10. A run where every file failed, or no file gave a participant, could end green: both end `partial`.
11. The VAT number was stored with the country prefix and could never meet the registry number of a notice: prefix
    stripped, both columns asked (the 36 identifier positives of the gold set).
12. Stage 3 inside the first load costs 38 ms an organisation (46 minutes): `--no-candidates` and a resumable
    `resolution-candidates`.
13. The evaluation ignored stage 3 for pairs with two PICs (the cascade queues those): precision of stage 3 went from a
    flattering 1.00 to the honest 0.80.
14. Cyrillic variants were stored under one key: both keys are stored, so old and new lookups find them.
15. The model could pair a printed name with a wrong printed country or leave a row out, and the quote check cannot see
    it: the table is read by rule and compared (`country_corrected`, `missing_from_answer`).
16. Long legal forms ("SPOLKA Z OGRANICZONA ODPOWIEDZIALNOSCIA") made every Polish limited company 0.85 alike: stripped.
17. The worker role had DELETE on the new tables through default privileges: revoked on all the entity, history and
    queue tables (tested).
18. The gold set first held only negatives that stage 3 could not meet (digits, countries); look-alike pairs from the
    queue were added so that the stage is actually exercised.

Left as they are, on purpose: the key of the buyer side (a change would orphan aliases); participations are not
re-pointed on a merge (see below); the first snapshot of a project has no event.

## What could not be checked, and what was not built

* **CSV packages** (the "package counts" of the brief): not fetchable under robots.txt. The loaded counts equal the
  service's own counts; whether the service equals the monthly packages is unknown.
* **A live model run**: none, by the rules. The 284 real factsheets went through the real crawler, PDF reader, quote
  check, resolver and loader with a stand-in model that reads the table by rule. The stand-in proves the pipeline; it
  does not measure the model. Plan M2-03 asks for a manual check of 10 factsheets after the first live run: read
  `project_factsheet.facts` and `.dropped` of ten rows beside their PDFs (`dropped` has `not_in_text`,
  `country_corrected`, `missing_from_answer`).
* **The quality of the labels**: one labeller, from knowledge of the entities; contested pairs were left out (for example
  Universitair Ziekenhuis Brussel against the Vrije Universiteit Brussel, which share a registry number in the notices).
* Not built, by the brief or by decision: embeddings and a model adjudication (stages 4 and 5), the admin screens and
  `organisation_merge_event`, NCAGE, SEDIA calls (M2-04), the API and pages for organisations and projects. Participation rows
  are not re-pointed when two organisations are merged (the existing merge code does not know them); whoever reads
  participations must follow `organisation.merged_into`, as the snapshot and the report already do.
* The CORDIS SPARQL copy ends in November 2025; EDF 2026 results do not exist yet.
* Memory: the roles of a CORDIS run (about 380,000 pairs) are held in memory before they are written (about 80 MB);
  not measured against the worker container's limit.

## Scratch

Created and deleted by me, at the end of the run: database `agent_h_scratch` (476 MB: a read-only COPY of production
`organisation` and `organisation_alias`, 357,874 and 354,922 rows, and the CORDIS and EDF loads), `/root/dev-h-scratch`
(about 40 MB: the raw store of those loads, five result pages, probe PDFs, the sitemap), the helper scripts in `/root/dev-h/`
(`*.sh`, `*.py`, `*.sql`) and `/root/dev-h-*.py`. Kept: `/root/dev-h/backend` (the test copy) and database `agent_h`
(created because it did not exist, empty after the tests); both are listed in `docs/DELETION_CANDIDATES.md`.
