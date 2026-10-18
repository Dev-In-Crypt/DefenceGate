# WP-32 self-check: "does this call fit me" and partner suggestions

Branch `wp-wp32` (from `integration`), 17 and 18 October 2026, migration 0070 (0071 not used), test database `agent_l`
(and `agent_l2`). Written by the implementer for the verifier. Everything ran on the server; production was only read
(SELECT, read-only transaction, `statement_timeout` 30 s, through `psql` in the postgres container, `pg_dump` and
`COPY` of nothing). No language model was called.

## What was built

- **Call page** (`/funding/{slug}`): "Your readiness for this call" (`CallReadiness`). Without a saved profile it is a
  path to the five-step check and does nothing else (no request). With one it shows (a) the call document's rules against
  the profile (`web/lib/fit.ts`, the same facts and conservative rules as the older four-question form, which is kept), and
  (b) the programme's rules and the time left, from `POST /v1/readiness/assess` with the call id (verdict, blocking rules,
  the steps with vendor ranges, `realistic`), and one sentence that puts the two together and never says more than the
  weaker (`web/lib/call-readiness.ts`).
- **Lists** (`/funding`, `/changes`, the digest): a badge per call (Eligible / Check / Not eligible / Unknown) and the switch
  "Fits my profile", client-side only (`web/lib/fit-store.ts`, `components/funding/fit-badge.tsx`). The server renders and
  caches the same page for everybody; the browser asks `GET /api/fit/facts?ids=` (public ids only, never the profile)
  and, for EDF and EDIP calls, the programme verdict once per profile.
- **Partner suggestions** (`GET /v1/funding/{slug}/partners`, `dgate/partners.py`, panel "Partners from earlier projects"):
  organisations of earlier projects of the call's area, ranked, with at most three projects as evidence, country filter,
  profile's country first. Loaded when the visitor asks (or has a profile).
- **Fix found on the way**: the portal files the EDIP calls under the EDF; `POST /v1/readiness/assess` with `call` judged
  them by the EDF rules. `programmes_of_call` now routes `EDF-EDIP-P-...` to EDIP, `EDF-EDIP-USI-...` to the Ukraine Support
  Instrument. For a Ukrainian company the answer changes from "blocked by the PIC only, realistic yes" to "not possible"
  on the EDIP Programme calls (110, 112, 114, 116, 117, 193), see the table below. WP-29's hand check of calls 112, 114, 117
  and 193 was therefore of the wrong programme.
- **Verifier's extra scope** (docs/verification/product/verify-eligibility-radar.md): E1, E2, F6, F7, below.
- `docs/design/CROSS_LAYER.md` (the four questions of the concept), `docs/design/API_CONTRACT.md`, `docs/DATA_PROTECTION.md`,
  the home page ("Three questions, three parts"), `docs/DELETION_CANDIDATES.md`.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| A UA and an ES profile see different, correct verdicts on 10 real calls | **Met, at line level and at programme level; at badge level only where the document's facts carry no notes** | table "10 real calls" |
| Partner suggestions hand-checked on 15 calls with yes/no per call | **Met (16 calls), with two "no" for usefulness** | table "Partner suggestions" |
| No extra server work for a visitor without a profile | **Met** | `fit-store.check.ts` ("no request without a profile"), `e2e/fit.spec.ts` (no `/api/fit/facts` and no `/api/readiness/assess`), the call-page block does nothing without a profile; the partner list is fetched on request |
| Page weight does not grow for visitors without a profile | **Met for the HTML and the data; the JavaScript grows** | the server payload of a list page gains only `<li>` wrappers and an empty client component per card; the call page gains the static text of the two panels (a few hundred characters; not measured). Client chunks added: `fit-store`, `fit`, `call-readiness`, `partner-suggestions` (not measured with `next build`: see "Not checked") |
| Cross-layer questions documented, built where the data allows | **Met** | `docs/design/CROSS_LAYER.md`: question 3 built; 2 and 4 are WP-28's, linked; 1 cannot be answered (no certification requirements are extracted from tenders) |
| Tests with fixtures for each that is built | **Met** | below |

## 10 real calls: ES and UA profiles (production data of 18 October 2026, read-only)

Facts: `GET /v1/fit/facts` logic run on production (`verify_wp32.py facts`); verdicts: `web/lib/fit.ts` unchanged, compiled
and run on those facts. Programme level: `roadmap.call_timing` with `programmes_of_call`. ES = a Spanish small company,
nothing held; UA = a Ukrainian small company, nothing held. "doc" = the call document's rules.

| Call | Facts it rests on (abridged) | ES small | UA small | Correct? |
|---|---|---|---|---|
| 110 EDF-EDIP-P-2027-FNLC-CPA-AMDS (open) | entity types: contracting authorities, international organisations, SEAPs, EDA; countries: Member States and EDIP associated countries | doc: check (entity, control); EDIP: blocked by the PIC only, realistic yes (122 days) | doc: check (entity, country); **EDIP: not possible** (establishment and management rules) | yes: a company is not one of the named kinds (E1); Ukraine is not an EDIP associated country (Regulation (EU) 2025/2643 Art. 9, as encoded in WP-29) |
| 117 EDF-EDIP-P-2027-LS-IRA-PE (open) | legal entities (public or private bodies); countries: Member States, EEA, EDIP associated | doc: check; EDIP: PIC only | doc: check; **EDIP: not possible** | yes |
| 118 EDF-EDIP-USI-2026-LS-IRA-MAB (open) | Public and private bodies; countries: Member States and Ukraine (not the non-government-controlled areas) | doc: check; Ukraine Support Instrument: PIC only | doc: check; Ukraine Support Instrument: PIC only, realistic yes (24 days) | yes: the instrument is open to a Ukrainian company |
| 114 EDF-EDIP-P-2026-2027-FNLC-SA-SEAP (open, 26 days) | as 110 | PIC only, realistic yes | **not possible** | yes |
| 12 DIGITAL-2026-SKILLS-09-LEAGUE-OF-ACADEMIES (closed) | public bodies, private bodies; Member States, EEA, Digital Europe associated; no ownership restriction | **Eligible** | Check (country) | yes (closed: no badge, no verdict on the page, F7) |
| 122 DIGITAL-2026-BESTUSE-MCP-10-HUB (closed) | legal entities, EDICs, ERICs; countries as above | Check (entity named) | Check (country) | yes |
| 39 HORIZON-CL3-2026-01-BM-01 (open) | entity types: Border or Coast Guard Authorities; consortium required (2 from 2) | Check | Check | yes: both told to check who may apply; no programme rules for Horizon |
| 131 HORIZON-EIC-2026-DEFENCE-01 (open) | SME or small mid-cap; countries "Union, Ukraine, or an EEA member"; guarantees for controlled applicants | Check | Check | yes (E2: a controlled company would get "check", not "no") |
| 96 EDF-2026-DA-ENERENV-AWC-STEP (closed) | legal entities, sole traders by exception; ownership restriction with approved guarantees | Check | Check | yes |
| 149 DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC (open) | countries: Member States and EEA; no consortium; ownership restriction | Check (note on countries) | Check (country not listed) | yes |

Over all 193 calls on 18 October: 149 have facts. Badge from the document alone, ES small: 5 eligible, 144 check, 0 not
eligible, 44 unknown (no facts read or no source); UA small: 0 eligible, 149 check. With the programme's rules, the six
EDIP Programme calls are "Not eligible" for the UA profile and "Check" for the ES one. **The honest reading**: the
document-level badge says "check" on 144 of 149 calls for a Spanish company because nearly every extracted fact carries a
note ("A condition applies"); that is the existing conservative rule of the form, kept. It is informative as a filter
(unknown and not eligible are removed) more than as a ranking. A better split would need the extractor to separate condition
notes from context notes (out of this package).

## Partner suggestions: 16 real calls, hand check

How: `partners_of` run on production through `verify_wp32.py run` (the module's SQL, unchanged); for the first three
organisations of each call an independent count (organisation and its merged rows, active participations, projects chosen by
a case-insensitive regular expression on the call code or the category, no helper of ours) was compared with the count served:
**48 of 48 equal**. Then I read the names against what the call is about. "yes": the list is what a reader would expect.

| Call | Area used (projects, organisations) | First names | Right? |
|---|---|---|---|
| 39 CL3 BM-01 | CL3 destination BM (21, 194) | Home Office; Romanian and Bulgarian border police; Cross-Border Research Association | yes |
| 40 CL3 DRS-04 | destination DRS (28, 311) | UPC Barcelona; Johanniter; IIASA; Dutch fire-brigade body; Romanian interior ministry | yes |
| 42 CL3 FCT-02 | destination FCT (30, 284) | Moldovan/Romanian police inspectorate (16); KEMEA; Spanish interior ministry; Hellenic Police | yes (see the note on country below) |
| 54 CL3 INFRA-01 | destination INFRA (7, 133) | Netcompany; Friuli-Venezia Giulia; Spanish interior ministry; Telekom Slovenije | yes |
| 48 CL3 SSRI-01 | destination SSRI (15, 120) | French and Spanish interior ministries; Fraunhofer; Civipol | yes |
| 30 CL3 CS-ECCC-01 | destination CS (43, 276) | AEGIS IT Research; Telefonica; Security Labs; Cyberalytics | yes |
| 33 CL4 DIGITAL-EMERGING | CL4 destination DIGITAL (213, 1176) | Fraunhofer; CNRS; imec; VTT; Chalmers | yes |
| 138 EuroHPC SPT-10 | no destination data: cluster JU-EUROHPC, wider (5, 32), says so | Luxembourg bodies, 2025 only | yes (thin) |
| 24 EIC Accelerator | destination ACCELERATOR (423, 451) | 423 single-company grants, one project each | **no**: correct by the rule, useless: a call for one company has no partners |
| 131 EIC Defence | destination DEFENCE has no project yet; the EIC as a whole (1,137 projects) is over the 600-project limit and is not ranked | empty, with the note "the nearest comparable area is too broad" | yes (honest empty; the first version listed CNRS, CSIC and TU Delft from all of EIC, which is not a useful list and cost 4 s under load: that is why the limit exists) |
| 77 RAISE | none | empty, with the note | yes (honest empty) |
| 95 EDF SPACE | EDF category SPACE (9, 154) | Leonardo; Airbus D&S (FR, DE, ES); GMV; Thales Alenia Space Italia; AIT | yes |
| 88 EDF CYBER | category CYBER (6, 87) | Indra; Romanian MoD; Leonardo; AIT; Airbus Cybersecurity; CY4GATE | yes |
| 89 EDF AIR | category AIR (7, 106) | Indra; Leonardo; Thales AVS; Elettronica; Dassault Aviation | yes |
| 98 EDF GROUND | category GROUND (15, 220) | Escribano; Safran E&D; Elettronica; John Cockerill Defense; Saab; Rheinmetall Electronics | yes |
| 102 EDF NAVAL | category NAVAL (3, 36) | Navantia; Naval Group; Fincantieri; Saab Kockums; Thales Nederland; MBDA France | yes |
| 84 EDF MCBRN | category MCBRN (7, 99) | AIT; CEA; Fraunhofer; CNRS; Zatloukal Innovations | yes |
| 110 EDIP-P (no category in its code) | all EDF projects (283, 1744), says so | Leonardo (74); Indra (64); Fraunhofer; AIT; TNO; Thales | yes (broad, labelled) |

One "no" of 18 lines (the rows above are 18 calls; the first sample had 16): EIC Accelerator. Findings from the reading:

- **CORDIS gives the country of the site of a PIC**, so the Spanish research council CSIC appears under Italy (already noted by
  WP-26). The country filter follows that data.
- 16 projects for one "Inspectoratul General al Politiei" under Moldova in FCT: the name is the Romanian police's; the organisation
  record and its country come from CORDIS/WP-26 resolution and were not changed here.
- The EDF 2021 and 2022 factsheets name no category, so EDF category lists rest on 2023 to 2025 (3 to 15 projects per
  category). That is stated by the `rule` sentence of the response ("2023 onward" is visible in `area.firstYear`).
- The real CORDIS topic code of a Horizon Europe project is `HORIZON_HORIZON-CL3-2023-BM-01-02` (a prefix); the **call code**
  (`HORIZON-CL3-2023-BM-01`) is clean. The first version matched the topic code and found nothing on production; the
  production check caught it, the area is now matched on the call code, and the fixtures were changed to look like the real data.

### Timings (EXPLAIN ANALYZE of the module's queries on production)

The server was heavily loaded the whole time by other work (load average 9 to 114, 3.8 GB of memory shared by about 17 test runs),
so absolute figures are pessimistic. Per call: one light query on `project`, one aggregate over the area's participations,
one evidence query by organisation, and a `source` lookup. Execution time of the statements, **without** the migration's index
(not applied on production yet), at load 14: call 95 SPACE 38 ms, 110 (all EDF: 283 projects, 1,744 organisations) 384 ms,
42 FCT 834 ms, 24 EIC Accelerator (423 projects) 1.4 s, 40 DRS 1.7 s; in quieter moments 42 FCT 121 ms, 33 CL4 379 ms,
24 EIC Accelerator 772 ms, 102 NAVAL 8 ms. The filter of `project` is a sequential scan of 80,208 rows (295 ms); on a copy of the
`project` table the index `project_call_upper` of migration 0070 makes it 15 ms (408 kB). The first version, which also fell back
to the EIC as a whole (1,137 projects), took 5.8 s under load: areas over 600 projects are now not ranked (a test fixes the
limit). The response is cached ten minutes in memory (`cache_list`). **The brief's 1.5 s cold budget is met in the quiet
measurements and probably after the index; it is not demonstrated for the wide areas (EIC Accelerator, all EDF) on a quiet
server with the index, because the index is not on production.** The orchestrator should run `EXPLAIN ANALYZE` of call 24
and 40 after the migration.

## Verifier's extra scope (E1, E2, F6, F7), each with a test that failed before

All in `web/lib/eligibility-check.ts` and the call page; tests in `web/lib/eligibility-check.check.ts` (calls named in comments).

| Id | Change | Test |
|---|---|---|
| E1 (call 78, 16, 14) | `entity_types` is read: a call that names who may apply is a "yes" only when the list plainly covers the profile's kind (generic "legal entities", "private bodies", "SMEs"...); otherwise, or when the profile gives no kind, "check" with the list shown. Never "no" (a list may be partial). `entity_types` is now among the facts of `/v1/fit/facts`. Not fixed here: call 78 has no `entity_types` fact at all (extraction, `eligibility.py`, other package) | "authorities only: not a yes for a company", unknown kind, generic list still yes |
| E2 (calls 96, 131, 60, 109) | "controlled from abroad = yes" is "no" only when neither note nor quote names a way round (guarantee, screening, exemption, "unless", approved by, China, high-risk, limited to); otherwise "check" with the note shown | guarantee wording, China-only (call 60), strict wording still "no" (call 144), note that names the route (131) |
| F6 (calls 17, 131, 118, 144) | an EU applicant is never told "Your country is not an EU Member State": the text now matches `member states / Union / EU`, and an EU country not covered gets "the document lists the countries in its own words, check that yours is among them"; "No consortium is required" next to `min_entities` of 2 or more becomes "check" with the contradiction stated, and a note is carried (`A condition applies: ...`) | call 17 for a German applicant, call 131 for a German applicant (yes), contradiction, noted consortium |
| F7 (call 78) | on a closed call the "Can you apply?" panel lists the rules read and says "This call is closed, so there is no verdict"; no form, no verdict, no readiness block; no badge on a closed call card; the EDF-only readiness panel is not shown | page logic (`closed` prop); covered by `e2e/fit.spec.ts` only indirectly (specs not run), see "Not checked" |

The hotfix of the three headline strings on `integration` ("Nothing in the document excludes you so far", "The document appears
to exclude you: read the quoted sentence") is adopted in this branch so that the merge does not conflict.

## Tests added

Backend (server, `agent_l`/`agent_l2`): `tests/unit/test_wp32_areas.py` (areas of a call, real topic codes, regular
expressions, injection characters, programme routing), `tests/integration/test_wp32.py` (21: ranking by projects then recency,
evidence and its dedupe, merged organisation counted once, organisation removed on request, inactive participation, country
filter and counts, limit bounds, fallback to the wider area, EDIP compared with all EDF, Horizon destination vs other
destinations and clusters, wrong source, no-data answers, 404/410, slug by leading id, `partnerArea`, fit facts: only the read
facts and no quote, not read / no source / removed, licence row, id validation, EDIP calls judged by the EDIP rules, both reads under
the read-only `dgate_api` role). Web: `lib/fit.check.ts`, `lib/fit-store.check.ts` (store behaviour with a fake browser),
`lib/call-readiness.check.ts`, extended `lib/eligibility-check.check.ts`, `e2e/fit.spec.ts` (written, see below).

## Hostile review of my own diff: issues found and fixed

1. A test of mine left `source.commercial_ok` NULL for every later test (reference data is not truncated): restored in `finally`.
2. The real CORDIS topic code has a `HORIZON_` prefix: partner suggestions found nothing on production; matched on the call code.
3. The first query plan scanned the area three times and was slow for the widest areas: one aggregate query plus an evidence query by organisation.
4. After a profile change the store did not ask for the programme verdict again (found writing its check).
5. A consortium requirement turned every call into "check" for everybody: it is now a condition shown beside the verdict.
6. A verdict of "yes" from a general-annex fact: now "check" (the brief: never a yes without conditions where the data is general).
7. The badge changed from "check" to "not eligible" when the programme verdict arrived: shown only when both are in.
8. Calls of the EDIP were judged by the EDF rules (see above).
9. The badge on a closed call (F7), and a nudge on every list for visitors without a profile that costs nothing.
10. Facts of the badge did not include `entity_types` (E1).

## Not checked, not met

- **The Playwright specs (`e2e/fit.spec.ts`) were not run** (no browser on the server); written against the markup by role and label.
- `next build` and the page weight in kB were not measured. `tsc --noEmit` is clean and the checks `fit`, `fit-store`, `eligibility-check` and `call-readiness` pass on the final code; the other `npm run check` files passed on the previous build of the branch (they do not import anything changed since).
- The widest partner areas against the 1.5 s budget on a quiet server (above).
- "Eligible with one step" (plan M3-19's second filter) is not built: the badge is the four-way verdict the brief asks for.
- The Digest items carry no programme: their badge comes from the facts endpoint, which names programme and topic, so it matches the list.
- Navigation: none new from this package. The home page links `/organisations` (WP-28).

## Test results (server)

- `ruff check .`: clean.
- Targeted run on the final code (`test_wp32`, `test_wp31`, `test_readiness_api`, `test_funding_api`, `test_calls_api`,
  `test_networks_snapshot`, `test_eligibility`): 142 integration tests passed, 58 unit tests (`test_wp32_areas`, `test_worker`,
  `test_eligibility`, `test_funding_terms`) passed; `test_wp32` alone, 21 tests, passed again after the last change.
- Full suite: unit passed on the code of 17 October; the full integration run of that code had one failure,
  `test_security_hardening.py::test_the_rate_limit_answers_429_with_a_wait_and_leaves_the_probe_alone`, the load-sensitive test that
  fails the same way on unmodified `integration` (see the WP-29 and WP-31 self-checks). **The full suite was not run on the very last
  commit**: the shared server (3.8 GB, 17 parallel test runs) killed the run by memory; the targeted run above covers the
  modules this branch changes.
- Web: `tsc --noEmit` clean; checks above pass.
