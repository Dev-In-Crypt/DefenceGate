# WP-28 self-check: networks API and pages (layer 2 for the user)

Implementer wp28, 17 to 18 October 2026, branch `wp-wp28` (from `integration` at `fa24892`). Test database letter `k`,
migrations 0068 and 0069. No language model was called. Production was only read (counts above, and a `pg_dump` of the
CORDIS and EDF tables into a scratch database; nothing written to production).

## What was built

* `backend/dgate/network_api.py` (new router, included in `api.py`): `GET /v1/organisations`, `/slugs`, `/{slug}`,
  `/{slug}/funding`, `/{slug}/partners`, `/{slug}/projects`; `GET /v1/projects/{slug}`, `/{slug}/history`, `/slugs`;
  `GET /v1/analytics/ukraine-partners`, `/v1/analytics/consortium-gaps`. Contract: `docs/design/API_CONTRACT.md`
  (section "Networks", WP-28). `/v1/buyers/{slug}` gained `organisationSlug`.
* Migration 0068: `dgate_live_org()`, `dgate_merged_in()`, view `organisation_merged_live`, derived table
  `organisation_network` (the directory; rebuilt by `networks.refresh_organisation_network()` at the end of
  `dgate pipeline cordis`, `edf` and `consortium-snapshot`). Migration 0069: index `organisation_alias(organisation_id)`.
* Web: `/organisations` (filters, search, sort, pagination), `/organisations/[slug]` (Overview, Funding, Partners, Projects,
  Names as sections reachable by link), `/projects/[slug]`, `/networks/ukraine-partners`, `/networks/consortium-gaps`;
  the buyer page links to the profile; sitemap entries; demo data `lib/mock/networks.ts` for the CI build.
* Tests: 37 integration (`tests/integration/test_network_api.py`), 9 unit (`tests/unit/test_network_api.py`), the web
  self-check `lib/networks.check.ts`, 13 Playwright specs (`web/e2e/networks.spec.ts`, run at desktop and 375 px by CI).
  `backend/tests/wp28_verify.py` is the by-hand verification script used below.

## Acceptance criteria

| Criterion | Evidence | Met |
|---|---|---|
| Counts on the pages equal the SQL counts for 15 organisations checked by hand | `wp28_verify.py orgs` on a copy of production (386,193 participations, 425,314 organisations): profile = SQL written independently (raw participations of the organisation and everything merged into it) = directory row, for 15 of 15: the three biggest (CNRS 4,336 projects / 1,928 as coordinator / EUR 2,597,363,164.50; Fraunhofer 2,727; CSIC 2,054), mid-size and one-project organisations in PL/FR/ES/GR/BG, two Ukrainian universities, a defence engineering firm (ISDEFE) and the Polish Military University of Technology. Projects, participations, coordinated, EU sum, first and last year all equal | yes |
| Partners tab of the 10 most frequent EDF organisations looks right to a reader | Listed below (live API on the copy, `programme=EDF`). Leonardo 74 EDF projects / 781 partners in 27 countries, Indra 64, Fraunhofer 47, AIT 39, TNO 38, Thales SIX GTS 33, Safran Electronics & Defense 32, Saab 31, Airbus Defence and Space GmbH 31, Elettronica 31. Top partners are the other primes (Leonardo-Indra 56 shared, Leonardo-Saab 27, Leonardo-Elettronica 27); Airbus DS GmbH / SA / SAS and Thales SIX / Thales stay separate rows (subsidiaries are not merged). Judgement of a reader: plausible. Two blemishes in the underlying resolution, see "Found in the data" | yes, with the blemishes |
| Merged organisations resolve to their live row | Fixtures: the slug of a merged-away row answers with the live organisation (`slug` canonical, the page redirects 308), its participations are counted in the profile, the directory, the partners and the project page; a duplicate row removed on request does not resurface through the row it was merged into (tests). **Not checkable on production data**: none of the 505 merged-away organisations holds a participation today | fixtures only |
| Every endpoint under 1.5 s cold on production data | Measured on the copy, see "Timings". CPU used per request is below 0.45 s for everything except the partners tab of the biggest organisations (CNRS: 1.25 s CPU; 2.7 to 6.4 s wall on a host at load 16 to 38) | **not shown for the 5 biggest organisations' partners tab**; everything else yes |
| Ukraine-partners returns a hand-checked answer | `since=2021`: 239 projects, 152 coordinators, 223 Ukrainian organisations, 12 projects led from Ukraine. Independent SQL (distinct projects started since 2021 with an active participant established in UA): 239, equal to the API total (on the first, smaller copy 238 = 238). First coordinator COFAC (PT): 5 projects since 2021, SQL lists the same 5 (INNMEDSCAN, DETMED, EWALD, CATCHER, PhytoAPP) each with its Ukrainian participant | yes |
| Consortium-gaps returns a hand-checked answer | `programme=EDF&topic=CYBER&lacking=UA`: 6 projects in the area, 22 organisations with 2 or more of them, none with a Ukrainian participant. Independent SQL: 6 projects, 22 organisations, 0 Ukrainian participants. **Limit found**: no EDF participant is established in Ukraine at all (0 in the whole programme), so for UA the list is every repeat participant, not a gap. The response now says so (`limits`), and the page shows it. Fixtures check a real filter (a CYBER area where one country is present) | yes, with the limit stated |
| Each page says where the data comes from, its licence and the day it was read | `DataSources` block on every page (CORDIS / EDF factsheets, licence Commission Decision 2011/833/EU, last finished run date); EDF pages say participants were read by a model and show what the quote check removed (`project_factsheet.dropped`); e2e specs assert these texts | yes (e2e not run here) |
| Public pages carry no personal data | Organisation-level fields only; e-mail addresses in a name are redacted, an alias that looks like it carries a telephone number is not listed; every e2e `visit` also checks the page for an e-mail address | yes |

## "Capability area" and "category" (consortium-gaps)

Capability area = the projects of the programme narrowed by `topic`: the EDF capability category held in `project.category`
(from the factsheet file name: CYBER, GROUND, SMERO, DIS, SME, DIGIT, SENS ...) or the start of a topic code. CORDIS carries
topic codes but no capability taxonomy, so for Horizon a topic prefix is required (a whole programme is refused). Category
= the country of establishment of a participant. The data holds no SME flag, no organisation type and no consortium
identity, so "consortia" are not listed and "category" cannot be "SME" or "university". Documented in the contract and on the page.

## Timings

Production was shared with other implementers' test runs (load average 16 to 114 on 2 cores while measuring), so wall times
are inflated by up to 8 times. Each request is measured three times; the table gives the wall time of the first call, the
best wall time, and the CPU used (database container cgroup counter plus application process time, the smallest of three
runs): what an idle host would need. Database role `dgate_api` (5 s `statement_timeout`), scratch copy of production
(`agent_k_real`), directory table built.

| Request | wall first | wall best | CPU |
|---|---|---|---|
| `/v1/organisations` (default) | 1,268 | 229 | 105 ms |
| `?country=DE&programme=FP7&role=coordinator` | 2,137 | 320 | 132 |
| `?programme=EDF` | 802 | 588 | 214 |
| `?q=universit` (broad word, capped count) | 1,029 | 926 | 392 |
| `?q=thales` | 393 | 360 | 134 |
| `/v1/organisations/{CNRS}` (4,336 projects) | 4,976 | 2,018 | 790 |
| `/{CNRS}/funding` | 1,387 | 705 | 381 |
| `/{CNRS}/partners` (9,663 partners) | 6,430 | 2,733 | 1,250 |
| `/{CNRS}/partners?country=DE&programme=H2020` | 2,681 | 2,148 | 1,425 |
| `/{CNRS}/projects` | 616 | 272 | 215 |
| profile of a 215-project organisation / of a one-project one | 445 / 304 | 199 / 215 | 189 / 147 |
| `/v1/projects/{largest}` (49 KiB, 200+ members) | 269 | 269 | 156 |
| `/v1/projects/{id}/history` | 299 | 85 | 65 |
| `/v1/analytics/ukraine-partners` (since 2021 / 2014) | 1,255 / 1,018 | 651 / 1,018 | 449 / 675 |
| `/v1/analytics/consortium-gaps` (EDF all / CYBER / Horizon CL4) | 1,297 / 320 / 571 | 761 / 320 / 413 | 370 / 166 / 195 |

Earlier runs of the same script, on a quieter moment, gave 58 to 120 ms CPU for the directory and 71 to 87 ms for a mid-size
profile. The CNRS-class partners tab (organisations with more than 2,000 projects: three today) is the one request that
is not demonstrably under 1.5 s cold: its response is cached 5 minutes in the API and an hour by the site, but the first
request after expiry costs about 1.3 s of CPU. Not fixed because the remedy (a pair table of 2 to 30 million rows) is
too big for the disk.

What the measurements changed (each found by EXPLAIN on production-sized data): the directory aggregate over
`participation` took 2.2 s, hence the derived table; the profile read 432,000 `organisation_alias` rows per request (no
index; 26 s with the family computed per row), hence 0069; the planner joined all 380,000 participations to their projects
before filtering to the Ukrainian ones (4.7 s), and hashed all 450,000 organisations to join 10,000 partners (2.5 s); a
recursive function called per merged row cost 0.25 s in every query (now a set-based view). A broad search word took
1.5 s to count, hence the 10,000 cap on the directory total (`totalExact: false`).

Refresh of `organisation_network`: 73,347 rows, 62 MB with its four indexes; 33 s on a quiet host, 117 s at load 16.

## Hostile review of my own diff: 16 issues found and fixed

Planner and cost (6): per-row recursive function in the merged view; full scan of `organisation_alias`; partner query hashing
every organisation; Ukrainian query joining the whole `participation`; profile counting partners live for the biggest
organisations (the count moved to the partners tab); `ANY` over the project ids to steer the partner query to the index.
Correctness and privacy (8): a duplicate row removed on request surfaced through the row it was merged into (directory,
partners, project page, Ukraine analysis, gaps); the country of a removed organisation entered `countryCount`; an alias
with a telephone number was listed; the alias total counted names the list hides; the CORDIS link built from an unquoted
grant number; `topic` accepted `%` and `_` as LIKE wildcards; results deeper than 10,000 were served; a "gap" list for a
country that is absent everywhere looked like an answer (now says so). Web (2): `tokens()` removed repeats before folding
case (`DE,de` gave two codes; caught by `networks.check.ts`); `Record` typing of the demo data (caught by `tsc`).
A tooling accident, for the record: the shared scratch directory held another implementer's `sync.sh`, which replaced mine, so
two of my early server runs tested older code; every result in this file was produced after I moved my script out of it
and re-ran the suites.

## Found in the data (not mine to fix, for the orchestrator)

* **CSIC is an Italian organisation in the data**: organisation 418756, PIC 999991722, country `IT`, 2,054 projects. The CORDIS
  source gives several sites per legal entity and WP-26 took one. It shows under Italy in the directory and counts as an
  Italian participant (and would hide a Spanish one in the gaps analysis). Same risk for any multi-site entity.
* EDF names resolved by exact normalised name sometimes leave case/hyphen twins: `fraunhofer-gesellschaft zur forderung ...`
  (lower case, no PIC) next to the Fraunhofer row with a PIC; `ministere des armees` and `technische universitat munchen`
  in lower case. They are separate profiles. The review queue (`resolution_review`) is the place; the stage-2 key does not
  fold hyphens the way CORDIS legal names are spelled.
* No EDF participant is Ukrainian; 223 Ukrainian organisations are in Horizon 2020 / Horizon Europe / FP7.

## What I could not check

* **Playwright e2e** did not run: no browser image on the server and the host was saturated. The specs were checked
  line by line against the demo data (counts, captions, table names). CI runs them.
* **`next build`**: compiled successfully (4.3 min) but the type/lint step was killed (SIGKILL, memory) on the shared host;
  `tsc --noEmit` and `npm run check` (all `lib/*.check.ts` including mine) passed separately.
* Merged-away organisations with participations: none in production, tested on fixtures only.
* The buyer link both ways: fixtures only (the copy has no `opportunity` table). On the copy, defence bodies do have profiles
  (Ministero della Difesa IT, 26 projects; ISDEFE, 54), so the link is exercised on real organisations once the buyer side is deployed.
* Timings at an idle host: not obtained, CPU time given instead.
* The full suite on the final code: ruff clean; unit all pass; integration all pass **except one that also fails on the
  untouched `integration` copy** (`test_security_hardening.py::test_the_rate_limit_answers_429_with_a_wait_and_leaves_the_probe_alone`:
  135 requests to `/v1/health` never reach a 429 on this host; it fails identically in `/root/dev-int`, so it is not caused by
  this work). Not diagnosed further.

## Production commands (for the orchestrator)

1. Deploy the branch; migrations 0068 and 0069 apply at start (0069 builds an index on 432,000 alias rows: about a second;
   it may be created `CONCURRENTLY` beforehand with `CREATE INDEX CONCURRENTLY IF NOT EXISTS organisation_alias_org ON
   organisation_alias (organisation_id)`).
2. Fill the directory once (the loads already ran, so no hook has fired): `python -m dgate.pipeline consortium-snapshot`
   (also writes the first project snapshots). Expect 73,347 organisations, +62 MB, 30 to 120 s. After that every
   `cordis`, `edf` and `consortium-snapshot` run rebuilds it.
3. Check: `GET /v1/organisations?pageSize=1` has `total` about 73,347; `/v1/organisations/220347-x` is CNRS with 4,336 projects.

Navigation entries needed (header/footer not edited): "Organisations" `/organisations`; analyses `/networks/ukraine-partners`
and `/networks/consortium-gaps` (a sub-menu or the footer). Routes added: `/organisations`, `/organisations/[slug]`,
`/projects/[slug]`, `/networks/ukraine-partners`, `/networks/consortium-gaps`. The visit counter (`lib/hits.ts` `routeKey`) files
them under `/other` until its allow-list (web and API) learns the new prefixes.

Scratch: `agent_k_big` and `agent_k_real` (about 700 MB together) and the web copy with `node_modules` were deleted at the end; what is left (`agent_k`, `/root/dev-k/backend`) is in `docs/DELETION_CANDIDATES.md`.
