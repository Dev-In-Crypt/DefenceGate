# WP-38 self-check: UX fixes from the persona walkthroughs

Branch `wp-wp38` (from `integration` at `70fa80e`), 18 October 2026. Test database letter `s` (`agent_s`), no migration (0082 and 0083 unused).
Source: `docs/verification/product/verify2-ux.md`, defects U1 to U16 except U2 and U3 (the rules content and the EDF association status,
handled by another package; `eligibility-check.ts` verdict logic and the readiness seed are untouched beyond what U4 and U5 need).
No language model was called. Production was only read: a read-only query on the partner tables through the API container's own
read-only role (code run in memory, nothing copied into the container), one `psql` read-only session for the programme and organisation
facts, and one public GET of `/api/fit/facts` on the site.

## What was built, per defect

| Defect | Cause found, and what changed |
|---|---|
| U1 partners: "your country comes first" was false | **Cause**: the browser re-sorted the 20 rows the API returned, which are the 20 largest organisations of the whole area, and a Polish organisation ranks below the top 20 (call 113: 73 Polish organisations in the area, 0 in the first 20). **Fix**: `GET /v1/funding/{slug}/partners?prefer=XX` orders that country first on the server (`dgate/partners.py`), the proxy passes it, the page no longer sorts. The country goes out **only when the visitor presses "Put organisations from Poland first"** (the readiness page promises the profile does not leave the browser except for the verdict; see "Decisions"). A second button gives the largest organisations of all countries back. |
| U4 badge never decides; form re-asks four answers | The three-state logic is **unchanged** (`fit`). New display layer in `lib/fit.ts`: `shownFit` (a "yes" that carries a condition is shown as a condition, never "eligible"), `fitLabel` ("Nothing known blocks you, N conditions to check" / "Blocked by: the rule" / "Eligible" only without a condition / "Rules not read"), `linesSummary` ("2 of 4 lines need your check; none is a no"). The list counts say the same words. The in-page form "Check your company" is filled from the saved profile (country, size, control); the partner question, which the profile never asks, stays the visitor's to answer; once an answer is changed the profile no longer overwrites it. |
| U5 "Consortium required: No" beside 4 countries | `consortiumUnclear` (minimum entities or countries above 1 next to "no consortium"): the fact row reads "The document is unclear, read it: it says no consortium is required and also asks for at least 4 countries."; the line is a "check" with the note carried; the badge gets it as a condition. |
| U6 partner area "all 283 projects" | The category or topic is used wherever the code names one (it already was: `areas_of`); where it does not (every EDIP call: the codes `FNLC-CPA-AMDS` etc. match no project topic, checked on production), the page says "names no capability category, so this list is compared with the whole programme ... Choose a country first", and the country choice comes **before** the list. |
| U7 wizard | Export: "Download my answers" (file `defencegate-answers-<name>.json`) and "Copy my answers"; import from a file or a pasted block, checked field by field (`importProfile`: version, size limit 20,000, every field through `parseProfile`). Clear asks first (`alertdialog`, focus on "Keep my answers"). A finished profile opens at the first step with an unanswered question (`unanswered`, `firstStepToAnswer`), else step 1; the unanswered questions are named (list on the wizard, and on the results: each missing answer is a link `/readiness?step=N`). The stepper is clickable (buttons, 44 px). |
| U8 roadmap | `daysRange(0, 0)` reads "no time needed"; the API sentence "up to 0 days" reads "need no time" (`roadmap.py`); the converted EUR figure (`cost.alt`) is not shown and the callout says money is shown in the source's currency and never converted; an optional (contract) step no longer says "Asked by: EDF; ..." but "Named by contracts under ...; not a condition for applying to a programme"; programme keys are names; "UA" and the issuer's name are separated by a space; the four "What is this?" links carry the step's name. |
| U9 suppliers | Product search (`?product=ammunition`): the word is matched to the **titles of the codes in the CPV finder** (`cpvForWords`, headwords first so "ammunition" is 3533 and not the whole weapons group 353) and the prefixes go to the existing `cpv` filter; the page says which codes matched and that a product replaces the CPV box; no match gives an empty list, never the unfiltered one. `/cpv` is linked. The order "Most wins first" is explained as a count, not a ranking. Country names for every ISO code (`Intl.DisplayNames`, fallback to the code), the names of CPV divisions 37 and 92 (verbatim from the vocabulary). |
| U10 directory and Ukraine partners | A programme filter that defaults to the defence-relevant programmes (`EDF`, `EDIDP`, `PADR`; only the EDF holds organisations today: 1,744) with a visible line and link "Show all programmes" (`programme=all`) and back; `GET /v1/analytics/ukraine-partners?programme=` plus `byProgramme` so the page says what the wider choice adds. **Multi-site country (CSIC under Italy) is not solved**, see "Not met". |
| U11 consortium gaps | Selects for programme and country; the capability codes listed with our plain reading of the abbreviation (`DS` has none: we do not read it with confidence), said to be ours. |
| U12 tracker and digest | A permalink icon (`#code`) and a "Cite this entry" line (title, status, event date, day checked, address, primary source) per entry; newest event first (page and Atom feed). Digest: "What 'new' means here" (from the backend's own definition), the statement when a week has no new, opened or moved funding call, and that the page shows the last complete week. |
| U13 artefacts | Footnote digits glued to a word in a quoted sentence are dropped at display (`cleanQuote`, a documented heuristic: two or three digits after a lowercase letter at the end of a word); the stored quote is untouched. Programme keys (`GENERAL`, `NATO-SUPPLY`, `EDIP-USI`) are shown as names. Rules that do not apply to the company (the Spanish clearance for a Polish one) are kept in a separate closed block "N rules that do not apply to you". "Open the legal text" under "Legal basis: none stated" now says "Open the page of the source". |
| U14 long pages | An index "On this page" (parts present only) at the top of every call page with five parts or more; a sideways-scroll cue for every wide table (`ScrollBox`: a line above the table and an edge shadow, only while there is more to scroll). |
| U15 home | The three layers are the first thing under the hero lead, above the tender form. |
| U16 focus, targets, menu | After Next or Back the focus is on the heading of the step; a refused Next puts it on the field to fix; the desktop menus open from a button with `aria-expanded` (one tab stop instead of four, closes with Escape and when focus leaves), hover still works; the mobile menu opens with focus on its first link and Escape returns it to the button; stand-alone links under 24 px (logo, breadcrumbs, card links, footer) are at least 24 px. |

## Acceptance evidence

**Tests added.** Backend: `test_prefer_lists_that_countrys_organisations_first_and_keeps_the_others` (U1), `test_ukraine_partners_can_be_narrowed_to_programmes_and_says_what_the_others_hold` (U10), an assertion in `test_call_timing_yes_when_the_slowest_path_fits` (U8). Web self-checks: `fit.check` (U4, U5), `eligibility-check.check` (U5), `profile.check` (U7), `readiness.check` (U8, U13), `networks.check` (U10, U11), `regulation.check` (U12), new `quote.check` (U13), new `cpv.check` (U9). Playwright: new `e2e/ux.spec.ts` (22 specs, each at desktop and 375 px; the API routes the pages call are mocked), and the existing `fit`, `readiness`, `networks` specs updated to the new words and flows.

| Run | Result |
|---|---|
| `ruff check .` (server) | clean |
| backend unit suite (server) | all pass |
| backend integration: `test_wp32`, `test_network_api`, `test_readiness_api`, `test_wp31`, `test_funding_api`, `test_networks_snapshot` (server, `agent_s`) | all pass |
| `tsc --noEmit` and `node scripts/run-checks.mjs` in `node:22-alpine` on the server | clean; 19 self-check files pass |
| `next build` with the demo data, then the whole Playwright suite (desktop and 375 px) on the laptop | see the last section for the final numbers |

**Real data (read-only, 18 October 2026).**

*U1.* The new `partners_of` run against production (call topics, limit 20):

| Call topic | Area | Polish organisations in the area | in the first 20 before | in the first 20 with `prefer=PL` |
|---|---|---|---|---|
| `EDF-EDIP-USI-2027-LS-IRA-CUXS` (call 113) | all EDF: 283 projects, 1,744 organisations | 73 | **0** | **20** (Wojskowa Akademia Techniczna 12 projects, ITTI 8, Siec Badawcza Lukasiewicz, Politechnika Warszawska, XYSENSING: the names the verifier found by hand) |
| `EDF-2026-DA-SPACE-PRS-STEP` | EDF category SPACE: 9 projects, 154 organisations | 5 | 0 | 5, then the largest |
| `HORIZON-CL3-2026-01-BM-01` | CL3 destination BM: 21 projects, 194 organisations | 0 | 0 | 0 (nothing to put first; the list is unchanged) |

`prefer=ES` on call 113: 20 of 162 Spanish organisations first. Timings: 1.4 s for the first (cold) call of the widest area, 0.15 s and 0.3 s after; the rest 0.02 to 0.2 s; the sort adds nothing (same queries, the key of one `sorted`).

*U4.* The facts of the nine open EDF and EDIP calls (public `/api/fit/facts`) run through the new `fit.ts` with a small Polish company (programme verdict from the repository's ES fixture, which has the same rules for a Member State):

| | Before ("Check"/"Unknown") | After |
|---|---|---|
| Poland, 9 calls | 0 eligible, 8 Check, 1 Unknown | 0 eligible, **8 "Nothing known blocks you, 3 conditions to check"** (calls 110: who may apply, ownership control, a consortium of 3 entities from 3 countries; 113: who may apply, country, ownership control; 193: country, ownership control, a consortium of 4 countries), 1 "Rules not read" (call 114) |
| Ukraine, 9 calls | 7 Not eligible, 2 Check | 7 "Blocked by: Established in the Union or an associated country and 1 more" (the EDIP Programme), 2 "Nothing known blocks you, 3 conditions to check" (the USI calls 113 and 118) |

The badge is therefore not "more decisive" than the data allows: for a Polish company the honest answer on these calls is that three things need checking, and now the page says which kind and how many, with the list in the tooltip and on the call page.

*U10.* Directory by programme (production `organisation_network`): H2020 40,809, FP7 30,239, HORIZON 26,141, EDF 1,744; no EDIDP or PADR rows. CSIC: organisation 418756, country IT, 2,054 projects; rows 32392, 418946 and 420446 are Spanish (5, 1 and 1 projects).

**Layout at 375 px (the built demo pages, read from the DOM with Playwright at 375 x 812).** No page scrolls sideways (`scrollWidth` 375) on `/`, a call page, `/readiness`, `/organisations`, `/networks/ukraine-partners`, `/networks/consortium-gaps`, `/suppliers`, `/regulation`, `/requirements`. The Ukraine table is 720 px in a 303 px frame and the consortium table 640 px in 303 px: both show "More columns to the right: scroll sideways." and the edge shadow; a screenshot was read. The "On this page" index of a call page, first built below the facts at 1,448 px, was moved to just under the deadline badge (now at 644 px, 236 px high, on the demo call page). The wizard's stepper buttons and the new buttons are 44 px (`min-h-11`) or 32 px (text buttons in a list). The scan in `ux.spec.ts` ("no button or stand-alone link is smaller than 24 px") covers `/`, a call page, `/readiness`, `/readiness/results`, `/regulation`, `/networks/consortium-gaps` at both widths; before the fixes it found 20 px links (logo, breadcrumbs, card buyer and "View original" links, the footer's "Source status").

## Hostile review of my own diff: issues found and fixed (15)

1. The first version sent the profile's country to the server on page load (`prefer`), against the stated contract ("the profile is never part of a request except the one that computes a verdict", `docs/DATA_PROTECTION.md`, the readiness page): now only on the visitor's button; `DATA_PROTECTION.md` updated.
2. The index anchors replaced the headings' ids that existing tests (`wp36.spec`) and `aria-labelledby` use: found by the full Playwright run; restored.
3. Two anchors (`terms`, `scope`) would have duplicated a heading id: the index uses the heading ids.
4. The "questions without an answer" list showed on the first pass through the wizard (noise): only for a finished profile.
5. "Ammunition" matched the group "Weapons, ammunition and associated parts" and filtered all weapons: headwords first.
6. A product word together with typed CPV codes would have been an OR of two lists: the product replaces them, and the page says so.
7. `Intl.DisplayNames` returns "Unknown Region" for `ZZ`: filtered to the code.
8. "1 of 3 lines need your check": grammar by the number that counts.
9. The roadmap line "Not an eligibility condition of NATO and NSPA supply" was not what the seed says for NATO (a contract that names AQAP requires it): a wording that is true of all five programmes.
10. `Change my answers` for a finished profile with nothing missing opens step 1 (the old tests expected step 5): tests changed and the stepper added so any step is one click.
11. The call-readiness heading "Rules not read" was wrong where rules were read but none concerns the profile: separate words.
12. A badge that said "Blocked by: European Defence Industry Programme (EDIP): the Programme: Established in the Union ..." was too long for a card: the rule only, the tooltip keeps both.
13. Stand-alone links under 24 px (logo, breadcrumbs, card links, the footer's "Source status"; above).
14. The tracker test counted nested lists (`ol > li`): scoped to the entries.
15. The partner-mock array carried a property that Playwright's `toEqual` serialises: compared as a plain array.

## Decisions for the orchestrator

- **`prefer` is opt-in.** One constant-free line (`mine` state in `partner-suggestions.tsx`) turns it on at load; that changes the privacy statement in `DATA_PROTECTION.md` and on `/readiness`, which is the owner's call.
- I touched `header-bar.tsx` (desktop menus, mobile menu focus) and one class on `footer.tsx` (the "Source status" link), which the common brief reserves; the brief for this package asks for the menu and the targets. No navigation entry was added or renamed.
- The demo data of the site (`web/lib/mock/calls.ts`) gained rules read for the first demo EDF call, so that the form and the contradiction can be tested without an API.

## Data fixes that belong elsewhere (not done here)

- **Footnote digits in quotes**: the stored quotes carry them because the quote check compares with the PDF text. A real fix keeps the footnote positions at extraction (`dgate/eligibility.py`); the display heuristic cannot drop a footnote number set apart by spaces ("small mid-caps 196 established") or a one-digit one.
- **Multi-site organisations (CSIC under Italy)**: `participation` holds no country per site and the CORDIS import keeps one country per PIC (`MIN(?cc)` in `dgate/sources/cordis.py`), so neither "several countries" nor the legal seat can be shown. The pages now say the country is the one recorded for the registration, that a multi-site body is recorded under one of them, and name CSIC as the example. A fix needs the importer to keep the set of countries per PIC (a column or table) and a re-import: production commands for the orchestrator, none run here.
- **Seed**: the Spanish clearance rule (`G-HSEM`) carries Spanish passages for every company; it is now shown apart for a company it does not apply to. The seed text is unchanged (not mine).
- `DS` (an EDF category code) has no plain reading in the repository; it shows as the code.

## Not met, not checked

- **U9**: each supplier row still shows its CPV divisions, not the codes that matched; that needs a field in `GET /v1/suppliers`.
- **U10**: the multi-site country (above).
- **U11**: the default "with no participant from" stays Ukraine, not the saved profile's country (the page is a server page; the select makes it visible, the hint says "Ukraine unless you choose another country").
- **U14**: the page length of a production call page (19,581 px at 375 px in the walk-through) was not re-measured; the demo call page is 10,003 px at 375 px and the index is now the first block under the deadline.
- **U16**: the 24 px scan covers six pages, not every page; no screen reader (NVDA, VoiceOver), no 200 % zoom, no dark theme, only Chromium (Playwright) was used.
- U7: results pages still have no print or copy of the verdict (not in the brief).
- Not run: `docker compose`, anything on production, the full backend integration suite (see the last section).

## Commands for production

None: no migration, no data change, no new job. The API change is additive (`prefer`, `programme`, `byProgramme`); the web needs the usual image rebuild.

## Final numbers

- Playwright, the whole suite on the final build (`next build` with the demo data, `next start`, desktop 1280 and 375 px): **201 passed, 7 skipped, 0 failed** (208 tests; the 7 skips are specs that say one width is enough, or that need data the demo build lacks: 2 in `ux.spec.ts`, 5 in the existing `changes`, `digest` and `funding` specs, unchanged). `ux.spec.ts`: 44 runs, 42 passed, 2 skipped by design (the desktop menu spec at 375 px, the mobile menu spec at desktop).
- `tsc --noEmit` and the 19 self-check files in `node:22-alpine` on the server: pass.
- Backend: `ruff` clean, unit suite passes, the six integration modules above pass. **The full integration suite was not run**: on the shared server (3.8 GB, other runs in parallel) it advanced 7 % in 15 minutes and was stopped; the modules this branch touches are covered by the targeted run, as in the WP-29, WP-31 and WP-32 self-checks.
- Scratch on the server: `/root/dev-s` (16 MB, the backend copy and outputs) and the test database `agent_s` (small); the `node:22-alpine` image was already used by other runs. Nothing on production was written.
