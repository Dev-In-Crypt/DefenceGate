# WP-162 self-check: the "Who to sell to" supplier report, automated (owner, 31 Oct 2026)

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP162.md`. Branch `wp-wp162` on `integration` (85541ff). Nothing merged, pushed or
deployed. Test copy `D:\DEFENCEGATE TESTS\wp162\` (Postgres `dgate-wp162` on 56162, deleted at the end). No price in any file.
Samples: `D:\DEFENCEGATE TESTS\wp162\samples\`; screenshots `D:\DEFENCEGATE TESTS\wp162\shots\`.

## 1. Plan (written before the build)

### Reuse list (read first; nothing below is rebuilt)

| Section | Reused module / function | What it gives |
|---|---|---|
| 1 Profile (mode A) | `network_api.live_organisation` / `org_ref` (404/410 as the pages), `award_set` (`FROM`, `scope`, `OF_ORGS`, `KEY_HASH`), participation/programme as `organisation_funding` reads them | name, country, the CPV classes of what it won, EU projects by programme |
| 1 Profile (mode B) | `components/readiness/supplier.tsx` `CpvPicker` (CPV dictionary `lib/cpv.ts` `cpvSearch`, WP-57 product words `cpvForWords`/`productNote`, `CODE_SETS`), `lib/profile.ts` `CERTIFICATES`/`REGISTRATIONS`/`holds`, `use-readiness.useProfile` (prefill from the browser's supplier profile), `wizard.tsx` `Radios`/`COUNTRY_OPTIONS`/`EXPORT_OPTIONS` | the form, CPV suggestion without any model |
| 2 Who buys | `demand.demand` (WP-66/80/97: buyer families per country, procurements, awarded contract values per currency, the award set's 3-year window), `demand.MATCH`, `demand._notices` | rows by country with count and value; each row's newest notice |
| 3 Who wins | `demand.demand` `approach` (award set, legal entities only, natural persons never counted or named, `PRIMES`/`prime_of`, `suppliers.value_totals`) | winners, contracts, countries, value |
| 3 Mosaic | the first-N / sign-in pattern of `competition`/`signals` (WP-155); size rule on `demand.PRIMES` (SIPRI source) | named only when large or the cell has >= 5 companies |
| 4 Open tenders | `tenders.list_tenders` called as a plain function (as `accounts.run_search`) | up to 5 open notices under the codes, `securityClearance` |
| 4 Open calls | `funding.list_funding` (as `exports.open_calls`), product words of `search_terms.groups()` (WP-98 map: CPV -> words) | up to 5 open calls, `whoMayApply`/`smeOnly` as the flag |
| 5 Ending soon | seam `sell_report.ending_soon` (None until WP-160 is wired) | section skipped when absent |
| 6 Qualify | `readiness.api.content` (requirements, rules, primary passages of `seeds/requirements.json`), `readiness.api.ProfileIn`/`assess_payload` (the readiness rules' verdicts) | requirement, applies-to, cost/time only from a verified source, status, quote + link |
| 7 Next steps | fixed templates (`sell_report.STEPS`) | no model text |
| 8 Sources | `demand.COVERAGE` (the "about a tenth" line), `TED_NOTE`, `placsp_note`, `tenders.cpv_titles` | coverage, attribution, disclaimer |
| Access | `billing.may/require/report_limit/plans_on_sale` (switch `DGATE_COMPANY_REPORT_OPEN`, WP-124 rule), `competition.open_report` quota pattern (advisory lock, 402 `report_quota`), `app_user.report_name` (Consultant), `associations` | gates and quotas |
| Output | `components/readiness/report.tsx` print pattern (`PRINT_CSS`, `window.print()`), `components/dg/*` (Waypoint tokens, Manrope, DM Mono), `PrintButton`, `Logo`, `safeHttpUrl`, `cleanQuote` | print-ready HTML and PDF |

### What was added (only what was missing)

- `backend/dgate/sell_report.py`: the builder (one function per section), routes, mosaic rule, requirement rules v1, 90-day
  templates, quota/pool, consented profile, Consultant logo, the section-5 seam.
- `backend/dgate/ops/sell_report.py`: the admin's one-off report (read-only session, JSON out, never counted).
- `backend/migrations/0154_wp162_sell_report.sql`: `sell_report_use` (count, no form data), `sell_profile` (consent only),
  `report_logo`, `association.sell_reports_per_year`.
- Web: `lib/sell-report.ts` (types and every label, `L`), `lib/sell-report-api.ts`, `components/sell-report/report.tsx` (the
  page, print CSS), `components/sell-report/form.tsx` (mode B), pages `/reports/who-to-sell-to` (form), `/sample` (public),
  `/company/[slug]` (mode A), settings logo upload (`app/(app)/app/settings/logo-actions.ts`), `scripts/sell-report-pdf.mjs`
  (the same page to PDF, local), fake-API routes and fixtures, `e2e/wp162-api.spec.ts`, `lib/wp162.check.ts`.
- `docs/legal/drafts/data-protection-sell-report-draft.md` (DRAFT, not published).

## 2. Gates and how each is enforced (file:function)

| Rule | Enforced in |
|---|---|
| Dark until the owner opens it | `sell_report._require_open` (404 `not_open` without `DGATE_COMPANY_REPORT_OPEN=1`), `get_sample`/`get_named_sample` (404); `billing.may` treats `sell_report` like `company_report` (nobody's while the switch is off); web pages 404 when the sample is not served |
| Free: one fixed public sample, no generation | `sell_report.get_sample` (`GET /v1/sell-report/sample`, fictitious `DEMO` company, cached 1 h, names=False); page `/reports/who-to-sell-to/sample`; never counted (test) |
| Pro 3 / Team 15 / Consultant unlimited a month | `sell_report.quota` with `billing.report_limit` (`REPORTS_PER_MONTH`, as the company report); mode A one company once a month (unique index), mode B every generation; refused before the work (`count=False` first) |
| Cluster licence pool per year | `sell_report.quota`: a member of a licensed association with `sell_reports_per_year` draws on the pool (calendar year, all members); set by `python -m dgate.ops.association --association NAME --reports N [--yes]` |
| WP-124 rule | `quota`: while `plans_on_sale()` is false the limit is None (rows still written); `billing.may` true for everyone then |
| Admin: any report, not counted | `python -m dgate.ops.sell_report` (READ ONLY session, statement timeout 30 s, writes no row); no admin web route (SECURITY_REQUIREMENTS D1: no admin session class exists) |
| Names in sections 2/3 only for signed-in users | `market(names=...)`: the public sample builds with names=False (section 3 rows empty, counts by country); section 2 names contracting authorities/entities (public bodies that publish the notices) for everyone |
| Mosaic rule (constraint 2) | `sell_report.mosaic` + `CELLS` query: cell = country of registration x CPV prefix of the report; named if `is_large` or every cell >= `MOSAIC_MIN` (5); otherwise counted in `notNamed`, no link |
| Size rule | `sell_report.is_large`: on `demand.PRIMES` under the SIPRI Top 100 2024 source (each far above the EU medium-enterprise ceiling, Commission Recommendation 2003/361/EC: < 250 staff, turnover <= EUR 50 m). Everything else may be an SME |
| Privacy (constraint 1) | `generate`: the form is used in memory; `sell_profile` written only with `consent`; audit line carries `mode` only; `ReportIn` `extra="forbid"`; the 422 handler does not echo; the web action passes the body to the API and keeps nothing; CPV suggestion in the browser from the dictionary and the product-word map |
| Honest wording (constraint 3) | section title `L.s3` "Who wins these contracts"; `wp162.check.ts` and the spec assert no "needs sub-suppliers" anywhere |
| Every row links to its source; missing shown as missing (constraint 4) | buyer and winner rows: page link + newest source notice (`_newest_buyer_notices`, `_newest_award_notices`, `demand._notices`); "No contract value stated", "Not stated", "No primary source states them"; no estimate anywhere |
| Natural persons excluded (constraint 5) | award set `WINNERS` condition via `demand.demand` and `CELLS` (`award_set.scope`) |
| Consultant white-label | `sell_report.brand_of` (`branded_reports`: name from `app_user.report_name`, logo from `report_logo`); cover shows them instead of our logo; `put_logo` (PNG/JPEG by magic bytes, <= 10 KB, no SVG) |
| Account data | export (`accounts.export`: `supplierReports`, `supplierProfile`, `reportLogo`), retention (`accounts._prune`: counts older than the previous calendar year), cascade on account delete |

## 3. Requirement rules v1 (section 6)

Sourced (primary text, rule status V, origin primary; quote and link printed on each item):

| Item | Quoted rule(s) | Applies to (as the quote says) | Status rule | Cost / time |
|---|---|---|---|---|
| RID (ES) | ES-RID, MoD e-office SIA 993054 | prime (MoD catalogue of suppliers) | have/missing | none stated |
| PECAL (ES) | ES-PECAL-CONTRACT, MoD Aseguramiento de la calidad | prime (suppliers in contracts that include it) | have/missing | none stated |
| HSES (ES) | ES-HSES (SEGINFOEMP) + ES-HSEM (Ley 24/2011 art. 21.2) | prime and every subcontractor with access | always "needs a consultant" | none stated |
| HSEM (ES) | ES-HSEM (Ley 24/2011 art. 21.2, BOE) | prime and every subcontractor with access | always "needs a consultant" | none stated |
| AQAP 2110, AQAP 2310 | NATO-AQAP-ED (MoD: AQAP/PECAL 2000 contractual requirements) | whoever the contract names | have/missing | none (the vendor range is not a verified source) |
| NCAGE | ES-NCAGE (MoD Catalogación) | not stated | have/missing | free; up to 14 working days (REQ-NCAGE, verified NSPA source) |
| ISO 9001 | ES-PECAL-ISO (DGAM PA 4302) | not stated | have/missing | none stated |
| EN 9100 | Q-EN9100-FILTER (DGAM PA 4302) | not stated | have/missing | none stated |
| Export classification | EU-DUALUSE-EXPERT (Reg. 2021/821 art. 3(1)) + G-EXPORT-MIL (Directive 2009/43/EC art. 4(1); CP 2008/944/CFSP art. 1(2)) | whoever exports | always "needs a consultant" | none |
| ITAR / EAR | new: 15 CFR 734.3(a)(2)-(3) and 22 CFR 123.9(a), official annual CFR edition on govinfo.gov (GPO), read 31 Oct 2026 | whoever holds US-origin items | always "needs a consultant" | none |

Plus the readiness rules' verdicts (ES-MOD, NATO-SUPPLY, EDF, EDIP) on the form's answers, from `assess_payload`.

**Not sourced (listed in the report under "Not covered", never assessed):**
- NSPA Source File: www.nspa.nato.int answered 403 to an automated read (a bot check, not bypassed); the ePortal registration page
  redirects to a sign-in. No primary text quoted.
- ISO/IEC 27001: no primary text we hold makes it a condition of defence supply; iso.org refused an automated read.
- Security clearances outside Spain (Germany and others are later, per the owner).
- eCFR (ecfr.gov) refused an automated read too; the govinfo annual edition (same text, official) was used instead.

## 4. Samples (production data, read-only, 31 Oct 2026 11:32-11:55 UTC, four runs; the last one is in the PDFs)

Run as the brief says: branch `backend/dgate` copied to `/root/wp162-dgate/` (removed at the end), `docker compose run --rm -T
--no-deps -v ...:/app/dgate:ro worker python -` with a read-only session, JSON exported, rendered locally by
`web/scripts/sell-report-pdf.mjs` through the site's own sample page (fake API serving the JSON).

| Case | Company | Time on production | PDF |
|---|---|---|---|
| 1 Spanish company with TED defence awards | Suyfa Defence, S.L. (427910): 312 contracts in the award set, its six main CPV classes; itself left out of "who wins" (137 of these contracts are its own) | 5.6 s | `samples\wp162-case1-spanish-company-ted-awards.pdf` |
| 2 EDF projects, no awards | Embention Sistemas Inteligentes (412678), 3 EDF + 1 H2020 projects, codes from the product word "drone" (35613000, 34711200) | 1.2 s | `samples\wp162-case2-edf-projects-no-awards.pdf` |
| 3 Civilian automotive supplier, form | "Example wiring-harness maker (fictitious, Navarra)": 31611000, 31612000, 34330000, 35422000; ISO 9001, IATF 16949 | 1.3 s | `samples\wp162-case3-automotive-supplier-form.pdf` |
| Public sample | the fictitious demo company (automotive set), anonymous view | 6.9 s (cached 1 h) | `shots\public-sample.pdf` |

The server copy `/root/wp162-dgate/` was removed after the last run (checked: nothing named wp162 left in /root).

Compared with the hand-made study (`sales\sernauto-sample\study.pdf`): the same demand numbers' source (`demand.demand`), the same
buyer families and prime marks; the automated report is per company (3-5 pages), without the study's trend table and
value-by-main-code split (not asked here).

## 5. Tests

- Backend unit `tests/unit/test_wp162_sell_report.py`: mosaic rule and size rule, form validation, requirement items (primary
  quotes only, consultant items, cost/time only when verified, Spain vs elsewhere), 90-day templates, empty market, the seam.
- Backend integration `tests/integration/test_wp162_sell_report.py`: **privacy** (no form field in any log line or any table
  without consent; with consent only `sell_profile`, exported and deleted), **mosaic rule** (six in ES named, one in PT counted,
  BAE always named, anonymous sample names nobody), **quotas per tariff** (WP-124 none counted; Free 402; Pro 3 then 402; Team
  15; Consultant unlimited; mode A once a month; switch off 404), **cluster pool**, **empty report**, **white-label** (Team 402,
  SVG refused, Consultant name and logo on the cover).
- Web: `lib/wp162.check.ts`; `e2e/wp162-api.spec.ts` (fake API, 1440 and 375): sample has the sections and no names, sign-in and
  plan gates, form -> report, empty report renders cleanly, Consultant name on the cover, quota message.
- Pins changed on purpose (the new feature row only): `tests/unit/test_wp155.py` TABLE, `tests/unit/test_wp124.py` feature set,
  `tests/unit/test_associations.py` (the switch-gated features list), `web/lib/wp155.check.ts` PAID_FEATURES.

Results in the test copy: ruff clean; backend unit 4187 passed; full integration 1645 passed (17 min, one run on the branch
before the last two small edits; `test_wp162_sell_report.py` and `test_wp155.py` re-run after them: 15 passed); tsc clean; lib
checks all ok (with the CI environment of `web-run.ps1`); Playwright `wp162-api`, `wp152-api`, `wp155-api` on the fake-API
projects at 1440 and 375 px: 26 passed. Every PDF is 5 A4 pages. Screenshots light and dark at 1440 and 375 in `shots\`.

## 6. What is missing for Spanish and German

- Spanish: every label is in `web/lib/sell-report.ts` `L` (one object); a Spanish object of the same keys and a locale switch are
  needed. The 90-day templates (`sell_report.STEPS`) and the requirement names come from the backend in English: they need a
  Spanish copy each (the quotes are already Spanish for the Spanish rules).
- German: no German requirement rule in v1 (the seed has DE-GHB-*, DE-VSNFD, DE-SIBE, DE-EXPORT-BAFA, which v1 does not show);
  security clearances outside Spain are listed as not covered; German labels as for Spanish.

## 7. Open items

- Section 5 waits for WP-160: wire its end-date function into `sell_report.ending_soon` at merge.
- The quota is separate from the company report's (both 3/15/unlimited): owner to confirm whether they share one count.
- The public sample takes about 7 s to compute on production (cached for an hour after); a generated report 1-6 s, above the API's usual 5 s aim for the larger ones (each statement is short; the web waits up to 30 s).
- NSPA Source File and ISO 27001 need a primary text the owner can provide (no automated read possible).
- Entry links from the supplier and organisation pages to `/reports/who-to-sell-to/company/{slug}` are not added (shared pages);
  the orchestrator may add them when the report opens.
- Privacy notice and DATA_PROTECTION texts: DRAFT only (`docs/legal/drafts/data-protection-sell-report-draft.md`).
