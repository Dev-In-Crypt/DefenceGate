# WP-67 self-check: supplier roadmap, printable report, entry copy (21 October 2026)

Branch `wp-wp67` from `integration` (135bbb0). Plan row: WP-67 (and the entry-copy part of WP-68) of
`docs/plans/MVP_SPAIN_AUTOMOTIVE_2026-10-21.md`. No model call, no spending, no external request, no production access, no migration.
Not touched: `backend/dgate/sources`, `backend/dgate/ops` (WP-70), header and footer.

## 1. What was built

- **Supplier roadmap** (`web/lib/supplier-roadmap.ts`, pure): one line per requirement, red / amber / green, from the engine's answer and
  the stored profile only. Colour rules, in order:
  1. green: the profile holds it, or every rule that names it is met;
  2. amber "A condition comes first": a rule naming it is `conditional` (Spain's NCAGE without a justified need; PECAL without prior
     contract experience);
  3. amber "Only when a contract names it": an optional roadmap step (AQAP 2110, PECAL);
  4. red "Missing, and needed for what you said you do": a rule is `not_met`, or a supply route (kind `route`/`general`) says `to_obtain`
     for a mandatory rule;
  5. amber "Only if you apply for EU funding (...)": a `to_obtain` that only funding programmes ask (the PIC);
  6. amber "Needs an answer" / "Depends on the contract" otherwise.
  Also listed: certificates no rule reads (IATF 16949: green, "no rule of this check reads it"), a supply-route rule that is not met and
  names no requirement (e.g. a foreign investor without the Council of Ministers authorisation: red), and every "consultant needed" flag of
  the answer that no line carries (US components / ITAR).
  **Order**: green, red, amber; within each the engine's roadmap order (its prerequisite graph); then a prerequisite is always moved before
  what needs it (ISO 9001 and the RID before PECAL; ISO 9001 before AQAP 2110), whatever its colour.
  **Cost and time**: printed only when the requirement's source is primary. New field `RoadmapStep.origin` (`backend/dgate/readiness/roadmap.py`,
  one line, the seed's `text_origin`; documented in `docs/design/API_CONTRACT.md`). Primary but silent prints "Not stated in the sources";
  non-primary prints "Not stated in a primary source". Today no primary requirement states a figure, so **no figure is printed**: the
  NCAGE "free of charge" and the PIC "free, immediate" are research-notes origin, AQAP 2110 is a vendor range. The report says the
  roadmap page still shows those, labelled.
  **PECAL**: never red (an optional step), carries the engine's chicken-and-egg note ("not a block before a first contract") and the prime
  qualification flag. **Consultant flags**: export classification (EU-DUALUSE-EXPERT), ITAR (US-COMPONENTS), HSES path (ES-HSES), prime
  qualification (ES-PECAL-CONTRACT), foreign-capital authorisation (ES-FOREIGN-CAPITAL): each shown on the line of its rule, or as its own line.
  **Summary line**, e.g. civil: "2 items are in place, 1 is needed now on your answers, and 5 depend on a contract, a condition or an answer.
  2 items need a specialist. Meeting these requirements does not win a contract: each buyer sets its own conditions in the tender documents."
- **Report** `/readiness/supplier/report` (`app/(public)/readiness/supplier/report/page.tsx`, `components/readiness/report.tsx`): built in the
  browser from `dg.profile.v1` and the same stateless assess call as the results page (the e2e proves exactly one POST, equal to the
  generated request fixture, and no other non-GET request). The server part only reads the public requirement catalogue for names (no
  visitor data; falls back to the stored labels if it fails). Sections: company profile as entered (country, region, size, NACE, investor,
  CPV codes with titles, processes, certificates with expiry, US components, classified access, answered Spanish questions); readiness
  results (verdict per programme/route, what is not met / to obtain / conditional, missing answers); supplier roadmap; "Who buys what you
  make" (prop `demand`, rendered only when given: hidden now, for WP-66); "About this report" (disclaimer, rules reviewed date, generated
  stamp, what left the browser). Disclaimer "Indicative, sources linked, not legal advice." under the title and in the last section.
  Print CSS (scoped to the page): A4, 16/14 mm margins, a page break before every section after the first, items not split, outside links
  followed by their URL, buttons and breadcrumbs hidden (header and footer were already `print:hidden`). "Print or save as PDF" button with
  the hint to choose "Save as PDF" and to turn off the browser's headers and footers. No server-side PDF.
  Entry: "My supplier report" button on `/readiness/results` when the supplier page was used.
- **Entry copy** on `/readiness/supplier`: section "Who this is for" (civilian manufacturers in Spain moving into defence supply chains;
  what the check reads; that it does not find contracts or say you will win one; where a specialist is needed; usable elsewhere without the
  Spanish rules). Every claim maps to a rule or behaviour of the check; "usually comes with a first contract" for PECAL is the research's
  wording (ES-PECAL-CERT outcome mapping).

## 2. The three sample companies (WP-65 fixtures; stored profiles `web/e2e/fixtures/profile-es-sup-*.json`)

| Profile | List (in order) |
|---|---|
| civil (castings, ISO 9001 + IATF) | green ISO 9001, green IATF 16949, **red RID**, amber PIC (EU funding only), amber NCAGE (no justified need), amber AQAP 2110 (contract), amber PECAL (contract, after ISO 9001 and RID), amber export classification |
| defence (RID, NCAGE, AQAP 2110, classified access) | green NCAGE, ISO 9001, AQAP 2110, RID; **red HSEM (REQ-FSC-ES)**; amber PIC, PECAL (condition: prior contract), export classification, US components (ITAR) |
| partial (profile fields only) | green ISO 9001; **red NCAGE, red RID**; amber PIC, AQAP 2110, PECAL, EN 9100, HSEM/NSFCC (answers), export classification, US components |

Printed report (Chromium print emulation, full page) and PDF (Chromium `page.pdf`, A4, 9 pages each):
- `D:\DEFENCEGATE TESTS\wp67\screens\es-sup-civil-desktop-print.png`, `...\es-sup-civil-mobile-375-print.png`, `...\es-sup-civil.pdf`
- `D:\DEFENCEGATE TESTS\wp67\screens\es-sup-defence-desktop-print.png`, `...\es-sup-defence-mobile-375-print.png`, `...\es-sup-defence.pdf`
- `D:\DEFENCEGATE TESTS\wp67\screens\es-sup-partial-desktop-print.png`, `...\es-sup-partial-mobile-375-print.png`, `...\es-sup-partial.pdf`

I looked at the civil desktop print picture: no site chrome, no buttons, sections in order, every non-green line with its source line, URL and
first verbatim passage.

## 3. Not met / limits (honest list)

- **RID before NCAGE**: the research file does not state that the RID is a prerequisite of an NCAGE code (it says the RID is needed to be in
  the MoD supplier catalogue, and that a Spanish NCAGE request needs a justified need). I did not invent the dependency. For the civil
  company the RID comes first anyway (NCAGE is amber: no justified need); for the partial company, which did not answer the NCAGE-need
  question, the engine's order puts NCAGE before RID (both red). If the owner wants RID first, it needs a source and a seed prerequisite.
- For the partial company NATO supply's "to obtain" makes NCAGE red while the Spanish question is unanswered; the line shows that question.
- A requirement marked "in progress" is shown red (needed now), without "in progress" on the line.
- No cost or time is printed at all today, because no primary source in the seed states one (correct by the rule, but the report is thin
  there). The PDF is the browser's; page breaks are set by CSS and were checked in the computed style, the PDF pages counted, not each page read.
- The browser's own print header/footer can only be turned off by the visitor (the hint says so).
- 47 Playwright tests skipped in the full run (not examined; WP-65 had 40 skipped before WP-62's additions).
- Navigation: new route `/readiness/supplier/report` (noindex; linked from the results page). Not added to header, footer or sitemap
  (private page). Deletion candidates: none.

## 4. Tests

New: `web/lib/wp67.check.ts` (the three lists in order, prerequisites first, PECAL amber with note, no figure without a primary source,
every consultant flag on the list, summary; synthetic cases: PECAL not met stays amber, foreign-capital red line with its specialist, a
primary figure prints, catalogue names win); `web/e2e/wp67.spec.ts` (3 reports + no profile + entry copy and results link, desktop and
375 px = 10 tests); backend `test_a_roadmap_step_says_where_its_text_and_figures_come_from`. Regenerated fixtures `assess-*.json` (only the
new `origin` field). Changed: `components/readiness/results.tsx` (report button), `supplier.tsx` (`ES_REGIONS` exported). No test loosened.

## 5. Results (local, `D:\DEFENCEGATE TESTS\wp67`, own venv, Postgres 17 container `dgate-wp67` on 55467, TZ=UTC, web mock env of `web.yml`)

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit (`pytest`) | 2967 passed, 1145 deselected (WP-65: 2966; +1) |
| integration (`pytest -m integration`) | INTEGRATION_RESULT |
| `dgate.readiness.export --check` (in the unit run) | up to date |
| `tsc --noEmit` | exit 0 |
| `npm run check` | all ok, incl. `wp67.check.ts` |
| `next build` (mock) | exit 0; `/readiness/supplier/report` static, 7.41 kB (the known Windows-only standalone trace warning, as in WP-65) |
| Playwright, 4 workers, desktop + 375 px | **477 passed, 47 skipped, 0 failed** |

## 6. Hostile review

Found and fixed 3 before the final runs: the report had no h1 when no profile was stored (the title is now always rendered); a held RID
showed two different names on one report (step name vs. stored label: the prerequisite names are now used); the entry copy said PECAL
"comes only with a contract" (the research says a newcomer usually meets it inside a first contract: reworded).
