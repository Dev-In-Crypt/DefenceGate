# WP-29 self-check: readiness (layer 3)

Author: implementer wp29, 17 October 2026, branch `wp-wp29` (from `integration` at 012fb61). Written by the
author of the change: an independent verifier is to check it again. A criterion that was not met is listed as
not met.

## What was built

- Content: `backend/seeds/requirements.json` (12 requirements, 23 issuer rows for 12 countries, 3 prerequisite
  links, 6 programmes and routes, 30 rules), migrations 0063 to 0065, the loader `dgate.readiness.seed`
  (validates, then writes; a row the seed stops listing is switched off, never deleted).
- Engine `dgate/readiness/engine.py` (`assess(profile, statuses, programme)`, a pure function, no model),
  roadmap `dgate/readiness/roadmap.py` (steps, tracks, totals, the ISO 9001 branch, `call_timing`).
- API `dgate/readiness/api.py`: `GET /v1/requirements`, `/{code}`, `/{code}/issuers?country=`,
  `GET /v1/readiness/programmes`, `POST /v1/readiness/assess`. Documented in `docs/design/API_CONTRACT.md`.
- Web: `/readiness` (wizard in 5 steps), `/readiness/results` (dashboard), `/readiness/roadmap`,
  `/requirements`, `/requirements/[code]`, the proxy route `/api/readiness/assess`, `lib/profile.ts`.
- Tests: 122 unit tests and 49 integration tests (backend), two web self-checks, Playwright specs.

## Test results (on the server, test database `agent_i`)

- `ruff check .`: clean.
- Unit suite: **2083 passed** (122 of them are new: engine 57, seed 24, roadmap and scenarios 38, generated files 3).
- Integration suite: **785 passed, 1 failed**. The failure is `test_security_hardening.py::test_the_rate_limit_answers_429_with_a_wait_and_leaves_the_probe_alone`.
  It sends 135 requests and expects the bucket (120 tokens, 2 refilled a second) to run dry, so it fails when a request takes more than about 50 ms; the
  server was loaded by other implementers' runs (load average 6 to 12; one `/v1/health` call took 54 ms). It passed in an earlier full run of this
  branch on a quieter server, and **it fails the same way on the unmodified `integration` code** (run twice on the archive of that branch against the
  same database). It is not caused by this branch; it will pass on a quiet machine such as CI. 49 of the integration tests are new
  (`tests/integration/test_readiness_api.py`).
- Branch coverage of `dgate/readiness/engine.py` (the evaluator and the assessment): **100 %** (102 branches), measured with `coverage run --branch`
  over the unit tests (`coverage` was installed in a scratch folder for the measurement only; it is not a dependency).
- Web: `tsc --noEmit` clean, `npm run check` ok (11 self-checks, 2 new), `next build` succeeds on the demo data.
- Quotes: `python tests/verify_quotes.py` against the Official Journal texts and the appendix: 53 passages, 0 not found.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| A UA and an ES test profile receive correct, explainable assessments for EDF, EDIP and SAFE | Met | `tests/unit/test_readiness_roadmap.py` states the verdicts rule by rule; `tests/integration/test_readiness_api.py` repeats them through the API. UA with nothing: EDF blocked by the PIC only, EDIP (the Programme) blocked (Ukraine is not an associated country there: Regulation (EU) 2025/2643 Article 2 and 9(1)), EDIP Ukraine Support Instrument blocked by the PIC only, SAFE eligible, NATO supply blocked by the NCAGE. ES with ISO 9001: EDF, EDIP and the Ukraine Support Instrument blocked by the PIC only, SAFE eligible. Each line carries its reason, the verbatim source and a link |
| Roadmap totals sit within the appendix's stated ranges | Met | table below; asserted in `test_ua_roadmap_total_with_aqap_equals_the_appendix_full_cycle_range` and `test_es_manufacturer_with_iso_9001_roadmap` |
| Every rule has a source | Met | `test_every_rule_has_a_source_url_a_reference_a_verbatim_text_and_a_status` (30 rules); the loader refuses a rule without a passage; `test_every_line_of_an_assessment_has_its_source_and_a_date` through the API |
| The catalogue has no requirement without `source_url` | Met | `source_url TEXT NOT NULL` (0063); `test_the_catalogue_has_no_requirement_without_a_source_url_or_a_review_date`; `test_no_requirement_and_no_rule_is_stored_without_a_source_url` (also an INSERT without it is refused) |
| Nothing is persisted server-side | Met | `test_an_assessment_runs_with_nothing_but_the_read_only_api_role_and_writes_no_row` (the call succeeds under the `dgate_api` role, which cannot write), `test_nothing_of_the_body_is_logged` (DEBUG log of a request holds none of its values), `test_a_refused_body_is_not_echoed_back...`; the site's route passes the body on without reading or logging it; `docs/DATA_PROTECTION.md` has a section |
| e2e and unit tests written | Partly | written: `web/e2e/readiness.spec.ts` (13 tests, desktop and 375 px), `lib/profile.check.ts`, `lib/readiness.check.ts`. **The Playwright specs were not run** (see "Could not check") |
| Self-check lists every rule with its source line number in the appendix | Met | the last section |
| SAFE Article 16(10) is two rules | Met | `SAFE-ORIGIN-35` (threshold, field `non_eu_component_cost_pct`, denominator "the estimated cost of the components of the end product") and `SAFE-NO-RESTRICTED` (categorical); `test_the_35_percent_is_measured_on_component_cost_not_on_contract_value` |
| AQAP is never an eligibility condition of EDF, EDIP, SAFE | Met | five rules (`EDF-AQAP`, `EDIP-AQAP`, `USI-AQAP`, `SAFE-AQAP`, `NATO-AQAP`), obligation `conditional`, no condition; `test_aqap_is_never_an_eligibility_condition_of_edf_edip_or_safe` (a company with no AQAP is still eligible) |
| Do not invent a rule, a number or a body | Met, with the limits below | every passage is verbatim (53 checked by `tests/verify_quotes.py`: 0 not found); where the appendix is silent the field is empty |

### Roadmap totals against the appendix

| Scenario | Roadmap says | Appendix says | Result |
|---|---|---|---|
| Ukrainian manufacturer, nothing held, AQAP 2110 included | USD 17,000 to 48,000; 90 to 240 days (EUR 15,700 to 44,200 shown beside it, as the appendix converts) | Full cycle, 30-80 employees: USD 17,000-48,000 (about EUR 15,700-44,200), 3-8 months | equal |
| Spanish manufacturer, ISO 9001 held | USD 17,000 to 25,000; 90 to 120 days | Small firm with existing ISO 9001: USD 17,000-25,000, 3-4 months | equal, and inside the full-cycle range |
| NCAGE | free; 5 to 20 calendar days | up to 14 working days on average; routine 10 calendar days; emergency 3 working days | 3 working days = 5 calendar days (7/5, rounded up), 14 working days = 20 |
| PIC | free; immediate | free, immediate | equal |
| Starting from zero without ISO 9001 | the full-cycle range plus the source's sentence ("adds roughly 30-40 % to the budget and 1-2 months") | same | not computed into a new figure: the sources do not say what the 30-40 % is a share of, so no number was derived |

## Hostile review of my own diff

I read every changed file again as a reviewer. 14 issues found and fixed:

1. Seed: NCAGE minimum 4 days while the note said 5 (3 working days at 7/5 rounded up): corrected to 5, tests and fixtures regenerated.
2. Seed: the Ukraine Support Instrument control rule passed control by an EEA EFTA state. The regulation counts an EEA EFTA state as associated only if it applies the Regulation, and the answer cannot tell Ukraine from an EEA state, so it is now a condition to check (as under EDIP).
3. Public pages showed our own crawler remarks ("the site answers 403 to automated clients") as source references: moved to `docs/sources/requirements.md`.
4. The eligibility-rule requirement pages (EDF, EDIP, SAFE) listed no rule: they now list the programme rules they stand for.
5. An unloaded rule set answered `eligible` against zero rules: it is now a 503 with `Retry-After` (test).
6. A call whose deadline had passed read "closes in -17 days": a `closed` result of its own.
7. Cost sentence "(vendor quote) (vendor range, not a benchmark)" doubled the brackets; the unknown-country issuer note named a code ("in UA") instead of "your country".
8. The roadmap listed an optional AQAP step before required steps of the same level: required first, then optional.
9. `REOCE` was listed as a prerequisite of the licence for non-Spanish exporters: a "before or together with" link only orders steps that are there anyway.
10. A validation error of the assessment echoed the offending input (the framework default): replaced for `/v1/readiness` (test).
11. The wizard used a native `required` on the country, which would have hidden our own message: removed, the message is ours.
12. The proxy route had no body limit of its own: 4 KiB, as Caddy's.
13. Blockquotes of source text could overflow at 375 px: `break-words`.
14. I added a worker job to `JOBS` and the existing test that pins the set of jobs failed: removed the entry (the worker applies the seed on start; `python -m dgate.readiness.seed` applies it by hand) so that the pinned set is not touched.

Not fixed, by decision: the 35 % rule is about one end product but a profile has one answer, so a company with several products answers for the main one (the page says so).

## Verification against real data (read-only)

Production has 40 EDF calls (9 with a deadline ahead), no EDIP call and 67 Horizon calls (17 October 2026).
The cross-layer question was run on 15 real calls with `scratch/verify_prod.py` (SELECT only, 30 s statement
timeout; the whole evaluation took 3.8 ms). Hand check of each row:

| Call id | Programme | Deadline | Profile | Result | Hand check |
|---|---|---|---|---|---|
| 118 | EDF | 2026-11-10 | UA, nothing held | blocked (PIC only), realistic yes, 24 days left | yes: the PIC is immediate |
| 114 | EDF | 2026-11-12 | UA, nothing held | blocked (PIC only), yes, 26 days | yes |
| 193 | EDF | 2026-12-15 | UA, nothing held | blocked (PIC only), yes, 59 days | yes |
| 112 | EDF | 2027-02-16 | UA, nothing held | blocked (PIC only), yes, 122 days | yes |
| 117 | EDF | 2027-02-16 | UA, nothing held | blocked (PIC only), yes, 122 days | yes |
| 110 | EDF | 2027-02-16 | ES, nothing held | blocked (PIC only), yes | yes |
| 111 | EDF | 2027-02-16 | ES, nothing held | blocked (PIC only), yes | yes |
| 113 | EDF | 2027-02-16 | ES, nothing held | blocked (PIC only), yes | yes |
| 116 | EDF | 2027-02-16 | ES, nothing held | blocked (PIC only), yes | yes |
| 83 | EDF | 2026-04-28 | UA, PIC held | eligible, closed | yes: deadline long past |
| 115 | EDF | 2026-06-16 | UA, PIC held | eligible, closed | yes |
| 86 | EDF | 2026-09-29 | UA, PIC held | eligible, closed | yes: 17.8 days ago |
| 1 | Horizon | 2026-01-20 | ES, PIC held | no rules encoded, `covered: false` | yes: no Horizon rules are built |
| 3 | Horizon | 2026-01-20 | ES, PIC held | `covered: false` | yes |
| 2 | Horizon | 2026-01-20 | ES, PIC held | `covered: false` | yes |

15 of 15 agree with the hand reading. What this does not show: no EDIP call exists on production yet, so the
EDIP timing is tested only on a fixture call; and an "everything fits" result for the PIC is not a test of the
"maybe" and "no" branches, which the unit tests cover with the NCAGE (5 to 20 days).

### Timings and plans

On the test database `agent_i` holding the seed (200 requests each through the framework's test client, so the
figures include its own overhead and one database connection per request):

| Endpoint | Size | Median | p95 |
|---|---|---|---|
| `GET /v1/requirements` | 7 KB | 28 ms | 38 ms |
| `GET /v1/requirements/REQ-AQAP2110` | 8.5 KB | 29 ms | 42 ms |
| `GET /v1/requirements/REQ-NCAGE/issuers?country=ES` | 0.6 KB | 28 ms | 50 ms |
| `GET /v1/readiness/programmes` | 45 KB | 36 ms | 61 ms |
| `POST /v1/readiness/assess` | 39 KB | 37 ms | 63 ms |

First request after the rules cache is empty (60 s): 31 to 151 ms. The API role's budget is 5 s.
`EXPLAIN (ANALYZE)` of the four content queries: a sequential scan and a sort of 6 to 30 rows, 0.04 to 0.47 ms.
The call lookup of `assess` (`funding.SELECT ... WHERE c.id = 118`), on production: index scans on `call_pkey` and
`programme_pkey`, execution 0.33 ms. Rows and bytes of the new tables: 12 requirements (98 KB with indexes),
23 issuers (66 KB), 3 prerequisites (33 KB), 6 programmes (33 KB), 30 rules (123 KB): 352 KB in all.

## Could not check, and not met

- **The Playwright specs were not run.** A browser needs about 1 GB on the server, which has 2.5 GB free, and the
  disk guard (`/root/disk_guard.sh`) stops the running history load below 2 GB. I did not take that risk. In place of a run:
  `tsc --noEmit` is clean, `npm run check` passes (including the two new self-checks), `next build` succeeds on the
  demo data, and `next start` served `/requirements`, `/requirements/aqap2110` (HTML read), `/requirements/req-ncage`
  (308), an unknown code (404), `/readiness` and `/readiness/results` (200). The wizard is client-rendered, so its
  locators were checked against the markup by reading it, not by running it. Expect the CI run to find at least a
  locator to adjust.
- The text of rules quoted from the technical appendix (NCAGE, PIC, ISO/EN, AQAP, Spanish export control, REOCE,
  HSEM) was **not** compared with the primary pages, only with the appendix; the pages say so (`text_origin = notes`).
  The addresses `iso.org`, `nso.nato.int`, `iaqg.org` answered 403 to a program and `comercio.gob.es` could not be
  reached from the server; they are used as the appendix and the standards give them.
- Only the texts as published in the Official Journal were read, not the consolidated versions. Article 9 of
  Regulation (EU) 2021/697 is not among the articles Regulation (EU) 2025/2653 amends (its Article 3 was read).
- Not encoded because no rule was read for it, and listed on the page as not done: the EDF consortium composition, the location of
  infrastructure (a note on each rule says the service does not ask), Article 17 agreements of SAFE, the conditions
  each call sets, environmental, social and governance requirements (the appendix says none was confirmed).
- Cross-layer question 1 (tenders I am eligible for) and the matching view (M3-14, M3-19), re-scoring and
  notifications (M3-07), regulation monitoring (M3-08), the extraction assistant (M3-09) and the admin editor are
  not part of this package or need accounts.
- The ten NATO countries other than Spain and Ukraine have an NCAGE row that says the national codification
  bureau was not collected (status U). Only Spain's National Security Authority is known.
- Production counts after the deploy are listed in the report; the tables do not exist on production yet.

## Every requirement and rule with its source and the line in the appendix

"Appendix lines" are line numbers of `docs/spec/eu-defence-portal-technical-appendix.md`; "table" is the
row of the consolidated requirements table. A rule marked "added from the regulation text" has no line in the
appendix: it comes from the Official Journal text (`USI-TERRITORY`).

| Code | Where it applies | Obligation or kind | Source (reference) | Appendix lines | Text checked against | Status |
|---|---|---|---|---|---|---|
| REQ-NCAGE | requirement | document | NSPA NCAGE Code Request Tool | 568-608; table 740 | appendix (quoted) | V |
| REQ-PIC | requirement | document | EU Funding and Tenders Portal, Participant Register | 672-680; table 741 | appendix (quoted) | V |
| REQ-EDF-ELIG | requirement | rule | Regulation (EU) 2021/697, Article 9 | table 742 | Official Journal | V |
| REQ-EDIP-ELIG | requirement | rule | Regulation (EU) 2025/2643, Articles 9 and 26 | table 744 | Official Journal | V |
| REQ-SAFE-35 | requirement | rule | Council Regulation (EU) 2025/1106, Article 16(10) | 544-562; table 743 | Official Journal | V |
| REQ-ISO9001 | requirement | document | ISO 9001:2015, ISO catalogue | 624-626 | appendix (quoted) | S |
| REQ-EN9100 | requirement | document | ASD-STAN, the European standardisation body of the aerospace and defence industry | 625-626 | appendix (quoted) | S |
| REQ-AQAP2110 | requirement | document | NATO Standardization Office. The prices are vendor quotes: no neutral body publishes them | 610-650; table 745 | appendix (quoted) | S |
| REQ-AQAP2310 | requirement | document | NATO Standardization Office | 617; table 746 | appendix (quoted) | S |
| REQ-EXPORT | requirement | document | Regulation (EU) 2021/821, Article 3(1) | 652-670; table 747 | Official Journal | V |
| REQ-REOCE | requirement | document | Secretaría de Estado de Comercio | 657-660; table 748 | appendix (quoted) | V |
| REQ-FSC-ES | requirement | document | Centro Nacional de Inteligencia, Oficina Nacional de Seguridad | 682-691; table 749 | appendix (quoted) | V |
| EDF-ESTABLISH | EDF | mandatory | Regulation (EU) 2021/697, Article 9(1) and Article 5 (as replaced by Regulation (EU) 2025/2653) | table 742; 712 | Official Journal | V |
| EDF-EXEC-MGMT | EDF | mandatory | Regulation (EU) 2021/697, Article 9(2) | table 742; 560 | Official Journal | V |
| EDF-CONTROL | EDF | mandatory | Regulation (EU) 2021/697, Article 9(3) and (4) | table 742; 712 | Official Journal | V |
| EDF-PIC | EDF | mandatory | EU Funding and Tenders Portal, Participant Register | 680; table 741 | appendix (quoted) | V |
| EDF-AQAP | EDF | conditional | No AQAP requirement appears in Regulation (EU) 2021/697 or in Regulation (EU) 2025/2653 (text checked on 17 October 2026) | 646-648 | appendix (quoted) | V |
| EDIP-ESTABLISH | EDIP | mandatory | Regulation (EU) 2025/2643, Article 9(1), Article 8 and the definition of 'associated countries' in Article 2 | table 744; 529 | Official Journal | V |
| EDIP-EXEC-MGMT | EDIP | mandatory | Regulation (EU) 2025/2643, Article 9(1) | table 744 | Official Journal | V |
| EDIP-CONTROL | EDIP | mandatory | Regulation (EU) 2025/2643, Article 9(5) and (6) | table 744 | Official Journal | V |
| EDIP-PIC | EDIP | mandatory | EU Funding and Tenders Portal, Participant Register | 680; table 741 | appendix (quoted) | V |
| EDIP-AQAP | EDIP | conditional | No AQAP requirement appears in Regulation (EU) 2025/2643 (text checked on 17 October 2026) | 646-648 | appendix (quoted) | V |
| USI-ESTABLISH | EDIP-USI | mandatory | Regulation (EU) 2025/2643, Article 26(1) | table 744; 535-538 | Official Journal | V |
| USI-EXEC-MGMT | EDIP-USI | mandatory | Regulation (EU) 2025/2643, Article 26(1) | table 744 | Official Journal | V |
| USI-TERRITORY | EDIP-USI | mandatory | Regulation (EU) 2025/2643, Article 26(1), second subparagraph | no appendix line; added from the regulation text | Official Journal | V |
| USI-CONTROL | EDIP-USI | mandatory | Regulation (EU) 2025/2643, Article 26(5) and (6) | table 744 | Official Journal | V |
| USI-PIC | EDIP-USI | mandatory | EU Funding and Tenders Portal, Participant Register | 680; table 741 | appendix (quoted) | V |
| USI-AQAP | EDIP-USI | conditional | No AQAP requirement appears in Regulation (EU) 2025/2643 (text checked on 17 October 2026) | 646-648 | appendix (quoted) | V |
| SAFE-ESTABLISH | SAFE | mandatory | Council Regulation (EU) 2025/1106, Article 16(3) | 560 | Official Journal | V |
| SAFE-EXEC-MGMT | SAFE | mandatory | Council Regulation (EU) 2025/1106, Article 16(3) | 560 | Official Journal | V |
| SAFE-CONTROL | SAFE | mandatory | Council Regulation (EU) 2025/1106, Article 16(3) and (5) | 560 | Official Journal | V |
| SAFE-ORIGIN-35 | SAFE | mandatory | Council Regulation (EU) 2025/1106, Article 16(10), first sentence | 550-556; table 743 | Official Journal | V |
| SAFE-NO-RESTRICTED | SAFE | mandatory | Council Regulation (EU) 2025/1106, Article 16(10), second sentence | 550-556 | Official Journal | V |
| SAFE-SUBCONTRACT-RELIEF | SAFE | conditional | Council Regulation (EU) 2025/1106, Article 16(4) | 558 | Official Journal | V |
| SAFE-AQAP | SAFE | conditional | No AQAP requirement appears in Council Regulation (EU) 2025/1106 (text checked on 17 October 2026) | 646-648 | appendix (quoted) | V |
| NATO-NCAGE | NATO-SUPPLY | mandatory | NSPA NCAGE Code Request Tool | 604; table 740 | appendix (quoted) | V |
| NATO-AQAP | NATO-SUPPLY | conditional | NATO Standardization Office | 646 | appendix (quoted) | S |
| G-REGIME | GENERAL | conditional | DefenceGate technical appendix, Export control | 668 | appendix (quoted) | S |
| G-EXPORT | GENERAL | conditional | Regulation (EU) 2021/821, Article 3(1) | 654-670; table 747 | Official Journal | V |
| G-REOCE | GENERAL | conditional | DefenceGate technical appendix, Spain export control | 660; table 748 | appendix (quoted) | V |
| G-HSEM | GENERAL | conditional | DefenceGate technical appendix, Facility and personnel security clearance | 685-689; table 749 | appendix (quoted) | V |
| G-CLASSIFIED-OTHER | GENERAL | conditional | DefenceGate technical appendix, Facility and personnel security clearance; Ukraine requirements path | 691; 709 | appendix (quoted) | U |
