# WP-88 self-check: jargon and walls of text (UX audit of 22 October 2026, section 3)

Branch `wp-wp88` from `wp-wp86` (b213e9e). Owner, 22 October 2026: fix everything that can be fixed; usability, completeness,
correctness; no Spanish translation now. Copy and structure only: no product fact or number changed, no data logic, no migration,
no deploy, no push, no production read or write, no secret, no model call. Not touched (parallel builder WP-87): tender list and
tender pages, buyer pages, calendar, changes and digest feeds, list default scopes and scope labels, /data; /privacy and /terms text.

## 1. The rule and how it is built

Every changed page opens with at most one short sentence ("what this is and what to do") before its first useful element (list,
form, table, result). What explains coverage, method, caveats, licences or confidence moved, unchanged in substance, into a
collapsed block:

- `web/components/dg/about-data.tsx` (new): `AboutData`, a native `<details>` ("About this data", "How we count", or a named
  summary) marked `data-about`, keyboard operable without script; `InfoLink`, a 24 px (i) link to a glossary entry, named for a
  screen reader ("What “PIC” means").
- Prints open: `PrintOpenDetails` moved from the funding call page to the public layout, so every collapsed block opens for
  printing on every public page (and closes after); the print CSS already opens `details` where `::details-content` is supported.
- A wide table reads as cards below 640 px: `.stack-sm` in `globals.css` (one row a block, the header row for screen readers only,
  each cell under its column name from `data-label`). It stays a `<table>` with its name.

## 2. What changed, page by page

| Page | Change |
|---|---|
| /suppliers | Coverage card, counts, natural-person note, credits and the aggregate note → "How we count" (collapsed, under the tab sentence). The three help paragraphs of the search (product words, supplier vs buyer country, order) → "How the search works". The list comes first, the aggregate tables ("By product group and country") after it. Empty state: "Spain’s national procurement portal" instead of PLACSP. |
| /suppliers/[slug] | The ~110-word coverage paragraph → one line ("Contracts this company won in published award notices of the last three years; it may have won more that are not published here.") + About this data. Notice source label "Spanish portal" instead of PLACSP (`sourceLabel`). |
| /organisations | Footnote (EDIDP/PADR, counting rule, removal route) → "How we count", the programmes named in full there. Scope line: "the European Defence Fund and its two predecessor programmes". Country rule (CountryNote) inside the sources block. |
| /organisations/[slug] | Programme tags by name (European Defence Fund, Horizon 2020, Horizon Europe; EDIDP and PADR in full). "EU contribution (CORDIS)" → "EU contribution". "How we recognised this organisation": one plain line with an (i) to the PIC entry; the per-method note, PIC, variants and merges → "How each project was matched". Sources, licences, amounts, the country rule and the removal route (≈180 words) → one line + About this data. Names tab: "Confidence" column → "How sure (1 is certain)". |
| All organisation-layer pages (`DataSources`) | "Where this comes from": one line ("The European Commission’s public records of EU-funded projects, organisation-level facts only.") + About this data with every source, licence, read date, amount note and method link. |
| Backend `resolution_note` (`network_api.py`) | "alias", "exact normalised name", "Lowest confidence 0.95", "No PIC is held" → "matched to a spelling of its name that was linked to it before", "matched by the same name (ignoring accents, capitals and the legal form) in the same country", "How sure the least certain match is: 0.95 on a scale to 1 (1 is certain)", "The sources give it no PIC, so it was recognised by its name"; ambiguous pairs "queued for a person to check". |
| /networks/consortium-gaps | Lead one sentence. Definition, the category-code note and Limits → "How we count"; the result line and the category links stay. Table cards on phone (`.stack-sm`). Backend definition: no backticks (`topic` → "the topic you give"), "Category: the country of establishment" → "Country: where a participant is established (its country of establishment)"; limit "`projects`" → "the project total". Programme select: EDIDP and PADR named in full. |
| /networks/ukraine-partners | Lead one sentence. Definition, totals and Limits → "How we count". Scope line names the defence default in words. Table cards on phone. |
| /funding | Lead one sentence; "Deadlines in UTC" moved to the meta line. Filter legends "Regime" → "Defence or dual-use", "Financial support to third parties" → "Cascade funding" (explanations and glossary links unchanged). Call cards: the label says whose budget it is ("Call budget, all topics") instead of a second caveat line. |
| /funding/[slug] | Panel "Financial support to third parties" → "Cascade funding". Partner suggestions: intro without source codes; the caveat, sources, model note and licence → one line + About this data. |
| /readiness | Lead one sentence. Callout heading "Your answers stay in this browser" → **"Your answers are not stored on our server"**; its two paragraphs (accurate and unchanged: saved in the browser, the verdict request sent once, not stored or logged; plus the lead's former second and third sentences on what the check returns) → "What is kept and what is sent". EDF/EDIP/SAFE line in words. |
| /readiness/supplier | Lead one sentence. "Who this is for" (4 paragraphs) → "Who this is for and what you get" (collapsed). Same callout change. |
| /readiness/spain-automotive | Lead one sentence; PLACSP in words; callout heading as above. Typo "companieswould" fixed (JSX line break). |
| Results / report / winners (`approach.tsx`, `demand.tsx`, `report.tsx`, `winners.tsx`) | Who-to-approach explainer: one sentence + "Why this list comes first". Method and coverage lines → "How we count"; demand sources → "Sources and what the counts mean"; the PDF instructions → "How to keep a PDF"; winners' source line → "Where the winners come from". |
| Backend `demand.py` | Mojibake "e-ZamГіwienia" → "e-Zamówienia" (coverage text on results, report and Spain automotive). |
| Questionnaire (`engine.py`, `lib/profile.ts`) | "NATO international competitive bidding (NSIP) tender" → "... tender (NATO Security Investment Programme)". Generated web files re-exported (`python -m dgate.readiness.export`). |
| /requirements | Lead one sentence (issuer/source/review date sentence moved to "About the costs"). (i) links by HSEM, HSES and PIC to new glossary entries. |
| /regulation | Feed notice → About this data under "Newest event first; last checked …". Seed text "(topic codes EDF-EDIP-P-...-FNLC-CPA-...)" → "(the calls whose topic code contains CPA)" (`seeds/regulation_tracker.json`, applied on worker start; mock too). |
| /market | Lead one sentence. Each chart's basis lines → "How we count"; "Reading these figures" → collapsed; the amendment caveat moved from the fact cell into it. |
| /glossary | Lead one sentence. New entries: PIC, How sure a match is, EDIDP, PADR, CORDIS, PLACSP, HSEM, HSES (each ≤ 3 sentences, facts only from our own copy and seeds). |
| Funding call readiness block | "Your answers stay in this browser." → "Your answers are not stored on our server." |

Not changed (the page is reading matter, or the rule already held): /methodology, /about (prose pages; leads ≤ 27 words),
/check, readiness results' and roadmap's leads.

## 3. Words before the first useful element

`docs/verification/product/wp88/words.cjs` (Playwright, desktop 1280): visible words in `<main>` in document order before the
first visible form, table, dl, article, list item or `[data-useful]` (the Spain automotive start button), not counting breadcrumbs,
nav, the h1, text inside a closed `details` (its summary counts) or visually hidden text. "Prose" = visible words of all paragraphs
on the page outside closed details, lists, tables and forms (the walls of text anywhere). "Terms" = listed internal terms visible in
`main`. Before: b213e9e (dev build, mock data); after: this branch (production build, mock data). Raw: `wp88/before-words.json`,
`wp88/after-words.json`.

| Page | Words before, before | after | Prose, before | after | Terms visible, before | after |
|---|---|---|---|---|---|---|
| /suppliers | 247 | 26 | 409 | 21 | none | none |
| /organisations | 28 | 28 | 311 | 63 | CORDIS, EDIDP, PADR | none |
| /suppliers/1-demo-airframes-gmbh | 0 | 0 | 138 | 51 | none | none |
| /organisations/101-alpha-systems-gmbh | 3 | 7 | 276 | 36 | normalised name, CORDIS | none |
| /funding | 30 | 31 | 73 | 74 | Regime, Financial support to third parties | none |
| /funding/1-edf-2026-… (call page) | 10 | 10 | 201 | 196 | CORDIS | none |
| /readiness | 138 | 41 | 215 | 111 | none | none |
| /readiness/supplier | 372 | 50 | 368 | 35 | none | none |
| /readiness/spain-automotive | 156 | 32 | 431 | 424 | PLACSP | none |
| /readiness/supplier/report (with a profile) | 219 | 103 | 1,272 | 804 | PLACSP, HSEM, NSIP | HSEM |
| /readiness/supplier/winners (with a profile) | 45 | 45 | 74 | 45 | PLACSP | none |
| /readiness/roadmap (with a profile) | 42 | 42 | 194 | 194 | none | none |
| /requirements | 48 | 30 | 105 | 107 | HSEM | HSEM (with (i) to the glossary) |
| /regulation | 100 | 39 | 85 | 21 | FNLC | none |
| /networks/consortium-gaps | 36 | 32 | 176 | 72 | CORDIS, EDIDP, PADR, backticks | none |
| /networks/ukraine-partners | 32 | 21 | 288 | 77 | CORDIS, EDIDP, PADR, "country of establishment" | none |
| /market | 25 | 18 | 178 | 18 | none | none |
| /glossary | 29 | 21 | 29 | 21 | (the entries) | (the entries) |

The count before the first element includes the h1-adjacent tab sentence, the meta line and summary labels ("How we count", 3
words), so 20-50 means one sentence plus labels. /readiness/supplier (50) is the lead (26), two summaries and the callout heading.
The results page with a profile has 70 words before its first list after the change (lead, buttons, the one explainer sentence; the
base dev server did not render the profile in time, so there is no before figure). HSEM remains in the report's quoted regional grant
texts and in requirement names, explained by an (i) link; the Spain automotive landing keeps its "What you get" sections after the
start button (prose 424): that page is the explanation.

Phone 375 px, `wide.cjs` on the production build: /suppliers, /market, /networks/consortium-gaps?topic=CYBER&lacking=UA and
/networks/ukraine-partners: scroll width 375 = viewport, no element of `main` outside the viewport. On production data /suppliers
and /market were slightly wider (audit); the mock data could not reproduce it, the e2e check guards it from now on.

## 4. Tests

Rewritten (asserted moved or renamed visible text; none deleted or skipped; owner-approved copy change): `networks.spec.ts`
(definition/limits read after `openAbout`; organisation factsheet, defence-projects and PIC lines), `suppliers.spec.ts`,
`wp85.spec.ts`, `ux.spec.ts` (U9, U10 programme wording, U10 phone table now cards with no scroll hint, U11), `wp46.spec.ts`,
`wp67.spec.ts` ("Who this is for" is a summary), `wp68.spec.ts` and `wp80.spec.ts` (Spain automotive lead), `readiness.spec.ts` and
`wp46.spec.ts` (callout heading), `digest.spec.ts` (call panel "Cascade funding"), `fit.spec.ts` (two "not a recommendation"
matches: `.first()`), `lib/wp61.check.ts` (`sourceLabel`), backend `tests/unit/test_network_api.py` and
`tests/integration/test_network_api.py` (the resolution note's new words). New helper `openAbout(page)` in `e2e/helpers.ts`.

New `e2e/wp88.spec.ts` (desktop + 375 px): on 11 main pages no listed internal term is visible outside a closed block (regex list
of the audit), and (10 of them) an About this data is present, closed by default and opens with Enter on its summary; the block
opens on `beforeprint` and closes on `afterprint`, and the moved coverage text is still on the page; /readiness heading; organisation
recognition in plain words with the PIC (i) link; every new glossary id exists; 375 px: no horizontal scroll on Consortium gaps,
Suppliers, Market; Consortium gaps rows are blocks and the table is no wider than its box.

Local, `D:\DEFENCEGATE TESTS\wp88` (own venv, Python 3.11; Postgres 17 container `dgate-wp88` on 55488; TZ=UTC; web mock env of
`web.yml`; E2E_PORT 3088; Playwright 4 workers), final code:

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit (`pytest`) | **3272 passed**, 1218 deselected |
| integration (`pytest -m integration`) | **1218 passed**, 0 failed (10 min 46 s) |
| `tsc --noEmit` | exit 0 |
| `npm run check` (`scripts/run-checks.mjs`) | all ok |
| `next build` (mock) | exit 0 (the usual Windows "failed to copy traced files" ENOENT warning of the standalone output) |
| Playwright, desktop + 375 px | **576 passed, 56 skipped** (the fake-API group as before, plus the width-specific tests of wp86/wp88), 0 failed |

Screenshots (first screen, desktop 1280 and phone 375), `docs/verification/product/wp88/`: `before-*` (b213e9e) and `after-*`
for /suppliers, a supplier, an organisation, /readiness, /readiness/supplier, Consortium gaps, Ukraine partners, /market,
/requirements, /regulation, /funding. `shots.cjs` makes them.

## 5. Open points and decisions for the owner

- **Pages not touched because WP-87 owns them**: the internal terms on tender pages ("Defence-relevant (core + supplies to defence
  buyers)", "Core: the notice itself is defence", "Why this is here - Defence body - Medium confidence", "Classified automatically
  (the confidence is a sample estimate)", LCSP, SDA), the scope filter under "More filters" with plain names, /data's ~190 words
  (SEDIA appears there), /changes' ~180 words. Same AboutData component is ready for them.
- The requirement names "HSEM facility security clearance (Spain)" / "HSES ..." come from `seeds/requirements.json`; explained in
  place with (i) links rather than renamed (a rename changes the catalogue and the generated fixtures). Rename if wanted.
- The supplier report keeps its detailed text (it is the printable document); the repeated methodology paragraph (section 4 of the
  audit) is the next package.
- Organisation-layer pages lost the visible licence lines (now in About this data, printed open). If a licence requires attribution
  visible on screen rather than one click away, say so and the one-line summary will carry it.
- Times stay in UTC (audit: low priority).
