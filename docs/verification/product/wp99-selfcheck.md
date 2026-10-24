# WP-99 self-check: funding and eligibility (persona round of 23 October 2026, D)

Branch `wp-wp99` from `integration` (58d6bd9). Input: `D:\DEFENCEGATE TESTS\ux-oct23\SUMMARY.md` section D and the evidence of
p05-fr-cyber, p08-ua-drones, p09-be-consultant (problems.csv, dumps, screenshots). No deploy, no push, no production write, no
procurement portal called. Production was **read** (read-only transactions in `dgate-api-1`, scripts in the scratchpad) to find why
the NCC and Cross-Border Cyber Hub topics were not read and to count what the Horizon change does; nothing was written. Owner priority:
correctness ("the product must not lie about where a company can apply"), completeness, usability. The 60-pair regression set
(`web/lib/data/wp93-pairs.json`) stays 60/60.

## 1. "Fits my profile" and "Your topics" over the whole list

- Switched on, the filter opens the same search with every call on one page (`/funding?...&fit=1`, at most the API's 500), so the
  hiding and the topic order (CSS `order`) see every call, not the 10 of a page. No pagination there; the count line says
  "Of the N calls of this search: ..." instead of "On this page". Switched off, back to the paged list. The profile still never leaves
  the browser (only call ids go out, as before). `fit=1` pages are `noindex` and never redirected as a page past the end.
- `components/funding/fit-badge.tsx` (`WholeList`), `call-list-template.tsx`, `app/(public)/funding/(list)/page.tsx` and `layout.tsx`.
- Not done: a filter changed on the `fit=1` page leaves it (the form does not carry `fit`); switching it on again is one click.

## 2. Designated bodies: the NCC network and the Cross-Border Cyber Hubs

- Cause, from the production texts (`call_document_text` of documents 8e1d6074 = CYBER-11, a435bd6f = CYBER-12, d3dec6b2 = CYBER-10):
  their topic headings separate the code from the title with an en dash or an em dash (`...-11-NCC – Enhancing the NCC Network`,
  `...-12- CBCH — Cross-Border Cyber Hubs`, `...-09-UPTAKE– Uptake`), and `rule_readings._HEADING` accepted only `-` or `--`. No topic
  section was found in any ECCC document; NATCH and NCH were read only because their "For the topic ..." paragraph of the eligibility
  section names them again. Fixed: the heading takes `-`, `--`, `–` or `—`, stays on one line (a code split over two lines is a budget
  table row), and a table-of-contents line whose dot leaders wrap to the next line is not a heading.
- The strongest phrase now wins wherever it is ("only entities designated ... are allowed to apply" in the eligibility section before
  "targeted stakeholders are public bodies acting as ..." in the topic section), and a page footer before "Targeted stakeholders" is not
  part of the quote.
- Production, read only with the new code (report of 24 October): CYBER-11-NCC `National Coordination Centres` with the consortium
  route (others take part only as partners), CYBER-12-CBCH and CYBER-10-CBCH `Public bodies acting as National Cyber Hubs`,
  CYBER-12-NATCH `National Cyber Hubs` (the eligibility sentence), CYBER-10-NCH `National SOCs` (that 2026 document's own words in its
  eligibility section). No open topic of the documents reads anything (AI4SME, COORDPREP, CYBERAI, DUALUSE, EULEG, REGCABH, ...).
- Words: "Only National Coordination Centres may apply; anybody else can take part only as a partner in a consortium with one." (a
  check); "Only National Cyber Hubs may apply. You are not eligible unless your organisation is one." (a no for a company).
- Badge: a call whose `designated_applicants` has no consortium route is "Designated bodies only" (`who_apply.py`, value
  `designated`, migration `0111_wp99_who_may_apply_designated.sql` widens the check constraint); /funding/191 said "Companies can take
  part" from its entity list. The filter `who` keeps its two values (a designated call is in neither).
- **Orchestrator, on the server after the deploy:** `python -m dgate.ops.rule_readings` (report: expect the NCC and both CBCH rows
  and changed quotes of NATCH/NCH), then `--yes`; then `python -m dgate.ops.cascade_flags` / `--yes` (cascade and who may apply:
  expect `designated` for CYBER-12-NATCH, CYBER-10-NCH and both CBCH calls) and `python -m dgate.ops.ukraine_flags` / `--yes` (expect
  about 38 Horizon calls `horizon_associated`). The nightly `cascade_flags` job of the worker runs the last two by itself.

## 3. Horizon "Open to Ukraine" from the verdict's association list

- `ukraine.decide`: a Horizon Europe call (the EIC included) whose own list of eligible countries (call, topic or the EIC work
  programme, not the general annexes) is open to the countries associated to Horizon Europe, read by `verdict.country_status` with
  `ASSOCIATED` (the list the verdict reads: Ukraine is associated), is open to Ukraine, reason `horizon_associated`, with the list's
  sentence and the annexes' sentence as evidence. The badge, the filter and the verdict now agree.
- Production, read only: 38 more Horizon calls open (24 EIC Accelerator, 25 STEP, 128-130 Pathfinder, the CL3 BM/DRS/FCT/INFRA/SSRI
  topics, 33, 142, 152), 8 were already; the ones whose only list is the general annexes' stay unmarked (the verdict says "check" for
  them too), the Bridging topic 151 (a closed list without associated countries) stays unmarked.
- Glossary "Open to Ukraine" says so, and that the non-government controlled areas are not checked for Horizon. The call page's basis
  line names the new reason.

## 4. Ukraine and the EEA EFTA states apart; the partner; the EIC STEP investor

- Wizard and supplier page: the control question offers "Yes, but only by Ukraine (for example Ukrainian owners)" and "Yes, but only
  by an EEA EFTA state" (kept as `control: 'ua_eea_only'` with `controlCountry`, the API's fields unchanged); a company established
  outside the EU gets a hint (for Ukraine: choose "Yes, but only by Ukraine"). The component question is two: Ukraine, and an EEA EFTA
  state. Profile version 5 (`lib/profile.ts`): a version 1 to 4 "only by Ukraine or an EEA EFTA state" without its country is
  unanswered again; a joint "no" or "not sure" about components answers both, a joint "yes" neither.
- Engine: `control_country` is read by the rules (asked only after the control answer that leads to it, `asked_after`), and
  `components_from_ua` / `components_from_eea_efta` are fields; the joint answer of an older client still works (`Profile.fields`).
  USI-CONTROL is met for control from Ukraine; USI-ORIGIN-35 counts only EEA EFTA components against the 35 %, EDIP-ORIGIN-35 still
  both. A Ukrainian-controlled Ukrainian company with Ukrainian components (20 % from outside) is **Eligible** under the USI
  (`tests/unit/test_wp99.py`).
- No Ukrainian partner: the USI rule stays a condition (the verifiers read these calls as "can only with a Ukrainian partner": pairs
  1, 8, 16, 32, 47), but the badge and the verdict say "Not without a Ukrainian partner (you said none takes part)", never "Nothing
  known blocks you"; the rule's text starts "Not without a Ukrainian partner." Unanswered, it stays an open question.
- EIC STEP: investor answer "no" on a call with the pre-commitment fact is a "no" (already so since WP-93; the persona's run was before
  the readings were applied); a test holds it.

## 5. Non-government controlled areas

- No primary source in the repository states the territorial clause of Ukraine's association to Horizon Europe, so the Horizon (and
  EIC) verdict of a company in such an area has a line "Non-government controlled areas: ... not checked here: no text we hold says so.
  Ask the National Contact Point or the call's helpdesk" (a check), instead of silence. TS and Python, the same words.
- The blocked USI text is the fact: "Blocked: Your company is established in a non-government controlled area of Ukraine" (badge),
  and the rule's not-met text starts with the same sentence (`fit.ts`/`verdict.py` `BLOCKED_AS`).

## 6. Readiness results cover Digital Europe, the EIC and national calls

- A section "Digital Europe, the EIC and national calls" with three cards (what each is judged on, honestly: no programme rules
  encoded, each call's own rules) and links with the profile filter on; a "See matching calls" button to `/funding?fit=1#results`.
  National links to the company's own country when it has one.

## 7. Partners

- ECCC/Digital Europe cyber calls (`DIGITAL-...-ECCC-...` or a `CYBER` token): partners from CORDIS projects of the Horizon Europe
  cybersecurity calls (`HORIZON-CL3-<year>-CS`, 43 projects in production) and the Horizon 2020 digital security calls (`H2020-SU-DS`,
  `SU-ICT`, 52), then the EDF category CYBER (6); said as our grouping by subject. Other Digital Europe calls still have none, and say so.
- Organisations: the name box is labelled "Name of the organisation"; a name search lists "These are the organisations whose name has
  “cyber”" with a link to the same search by project topic (the topic box, WP-91, already searched project titles: Thales, CNRS, INRIA,
  Airbus DS for FR "cyber" in production).
- "Put organisations from <country> first" is hidden when that country has 0 organisations in the area; a sentence says none took part.
- Ukraine partners: a column "Projects are" (Defence / Dual-use / Civil, from the API's counts), a keyword (`q`, the funding search's
  words and synonyms, applied by the API to the project acronyms and titles), pages of 25.

## 8. ASAP

- No primary source in the repository states that ASAP ended or what succeeds it, so no note: only the synonym (ASAP also finds the EDIP
  calls), in `textsearch.SYNONYMS` and its mirror `lib/text-search.ts`.

## 9. Funding subscription and calendar

- "Subscribe to this search" on /funding (webcal of `/funding.ics` and the Atom feed `/funding.atom`, both with q, programme, status,
  country and the other filters of the list); the feed lists the calls of the search, the newest first, up to 100.
- "Deadline calendar of this search" opens the list's own calendar view with the search (it opened `/calendar?kind=funding`).
- `/funding.ics` of a search says how many of its calls state no deadline (or no date to come) and are not in it.
- The .ics no longer says "17:00 Brussels time" for an EU portal call: it says what the page says (the source gives a day and no time;
  the call document may set an hour).

## Tests (local, `D:\DEFENCEGATE TESTS\wp99`, own Postgres 17 container on 55499, E2E_PORT 3099)

- ruff: clean. Unit: 3578 passed. Integration: 1291 passed (full suite, 13 min 50 s).
- tsc: clean. Lib checks: all pass, `wp93.check.ts` "60 pairs correct, 240 call x profile verdicts equal to the API's"; new
  `wp99.check.ts`. `next build`: ok. Playwright, full: 728 passed, 56 skipped, 0 failed (desktop and mobile-375).
- New: `backend/tests/unit/test_wp99.py` (production heading shapes, designated badge, Horizon association, territory line,
  "Not without a Ukrainian partner", blocked fact, Ukrainian company eligible under the USI, follow-up question, joint answer of an older
  client, EIC STEP investor), `backend/tests/integration/test_wp99.py` (Ukraine partners keyword, cyber partners, designated served),
  `web/lib/wp99.check.ts`, `web/e2e/wp99.spec.ts`; `fit.spec` covers the whole-list filter.
- Regenerated from the code: `web/lib/mock/requirements.json` and the e2e request/assess fixtures (`python -m dgate.readiness.export`),
  `web/lib/data/wp93-pairs.json` (`WP93_WRITE=1` then `python -m tests.wp93_golden readings derive`; the golden rules now carry each
  rule's outcome).
- Changed expectations (by the requirement, not to make a run green): profile version 5 in the checks and specs; the joint component
  "yes" of an older client is now an open question under the USI (it does not say whether the parts are Ukrainian); topics 33 and 152
  are open to Ukraine like their verdict; the .ics no longer names 17:00 Brussels.

## Open decisions for the owner

- Control from an EEA EFTA state under the EDF is control by an associated country (Regulation 2021/697, Article 5); the EDF rule still
  calls it a condition. Not changed here (out of the asked scope).
- Horizon calls whose only list of countries is the general annexes' stay unmarked for Ukraine, as their verdict stays "check".
- The 2026 NCH document calls the designated bodies "National SOCs" in its eligibility section; we quote it as written.
