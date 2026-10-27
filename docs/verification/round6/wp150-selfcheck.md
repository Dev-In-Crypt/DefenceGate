# WP-150 self-check: design pass, phase 2 (site-wide, bolder)

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP150.md` (owner-approved 27 Oct 2026). Branch `wp-wp150` on `integration` 0fa7e45.
Nothing is merged or deployed: phases 1 and 2 go out together after the owner approves the screenshots in `D:\DEFENCEGATE TESTS\wp150\shots\`
(`<page>-before-*` from 0fa7e45, `<page>-after-*` from this branch; 1440x900 and 375x812 dark, `-1440-light` one light shot per page,
`-320-full` and `-1440-full` whole pages).

Rules kept from WP-149: the first screen holds the title, one line and the service; a reassurance, scope or method note is a `NoteLine`
(icon, one small sentence, the rest behind a disclosure), a framed `Callout` only for what changes what the visitor must do; the card hover
rule; both themes; no sideways scroll at 320 px; legally required text stays on the page (behind a link at most).

## A. Home, bolder

Each tile is now: the question (the heading), one short line, the big number(s) and one action. The numbers are 40/48 mono (32/40 in the
two-action tile, where two stand one above the other). The headline is unchanged; the lead is the owner's text word for word.

What was dropped from the tiles, and where it is said instead:

| Tile | Dropped sentence | Where the reader finds it |
|---|---|---|
| What is open? | "Defence and dual-use tenders from TED and national portals, and EU and national funding calls, with their deadlines." | The /tenders lead and the /funding lead (both say what the list is, each linked to its source); deadlines are on every card. |
| Who is already in? | "Companies and research bodies in EU-funded defence projects, those with the most defence projects first, each with its projects and partners." | The tile's figure ("N organisations in EU-funded defence projects"); /organisations: its tab line, its sort "Most defence projects first", each organisation's page. |
| Can I take part? | "One question first, then the check that fits. For EU funding, five steps of 24 to 35 questions: the answer says what the EDF, EDIP and SAFE rules mean for your company, with the rule text it rests on. To supply defence buyers, one page of 17 to 53 questions." | The tile's figure ("5 steps, 24 to 35 questions, no account"); /check (the page the tile opens): "Answer one question first, then the check that fits", "Five steps of 24 to 35 questions ... rule by rule", "one page of 17 to 53 questions". |

The lead named EDF, EDIP and SAFE (with their glossary expansions); the owner's shorter lead names none, so the home page has no
abbreviation left to expand (`/glossary` keeps the three entries).

## B. The phase 2 table, row by row

| Pages | Done |
|---|---|
| /funding and its list views (`CallListTemplate`; `/funding?status=closing-soon` is the same page) | Lead to one line; search hint one line ("Matches whole words.") with the rest behind "What is searched"; the phone result tools are the compact row of links (as tenders and buyers since WP-149). |
| Every form (`Field`, `Fieldset`) | Label gap 4 -> 8 px (`Field`: the label has 4 px of its own under it, the hint stays 4 px under the field; `Fieldset`: legend 8 px). Hand-written labels on /suppliers and in the readiness wizard (load answers) moved to 8 px too. **Funding form budget:** the folded funding filter form measures **1,696 px at 1280 and 1,558 px at 375 (filters opened)** against wp47's 1,700 px (`D:\DEFENCEGATE TESTS\wp150\shots-after.log`; about 1,688 before: the hint went from three lines to one, the "What is searched" line and the 4 px label gap were added). It fits, with 4 px to spare; the budget is unchanged and `wp47.spec.ts:116` passes. The next addition to that form needs room made first. |
| /readiness/supplier, /readiness/spain-automotive, results, roadmap | The privacy Callouts of the supplier page and the Spain page are `NoteLine`s with their full text unchanged behind "What is kept and what is sent" (as /readiness). On the supplier page "Who this is for and what you get" and the privacy line form one block; the form starts at y = 432 at 1440x900. Kept as Callouts, by the policy: the Spain page's "Indicative, sources linked, not legal advice" (a legal caveat on how to use the results), the results page's "N of your answers are not used" (a warning) and the roadmap's "Read the ranges with care" (it says which totals are incomplete). |
| /check | Lead already one line; no change. Its card texts carry the counted question ranges that WP-121/WP-131 pin, and now carry what the home tile dropped. |
| /organisations, /suppliers (Companies) | The tab line is one line each. The programme scope of /organisations is a `NoteLine` (same words, `role="status"` kept) instead of a tinted box. |
| /buyers | Lead to one line. |
| /calendar | Lead to one line. The two count lines above the list stay: they are short and exact (wp87 pins them). |
| /search | The large page search fills the column (no `max-w-2xl`), as on home. |
| Tender page | A row of head facts under the title: value (the same label as Key facts: Estimated value, Awarded value, ...), deadline (from lg; on a phone the deadline box above says it) and buyer(s), replacing the "Buyer: ..." line. Then the source's own words and the method lines (original title, subject, "Why this is here", "Listed by our automatic rules"). Title, status, deadline, value and buyer are on the first screen at 1440x900 and 375x812. |
| Call page | The same row: deadline (with the countdown), budget and funder, replacing the funder line. Title, status, deadline, budget and funder on the first screen at both sizes (the deadline was at y = 640 at 1440 and below the first screen at 375). |
| Buyer page, organisation page | Already met the rule (title, a row of facts, then the method lines); no change, except that the buyer page's row of four facts is now two by two on a 375 px phone, as its CSS comment meant (`facts-grid--4` minimum 160 -> 152 px; at 160 px two columns needed 344 px and a phone has 343). The same row is used by the new tender and call head facts. |

## C. Account-area defects (cause fixed)

1. **React #418 on /app.** Reproduced against the local signed-in setup (cabinet-shots chain, copied to `D:\DEFENCEGATE TESTS\wp150\`):
   12 loads per configuration, production build: 375 touch 1/12, 1280 2/12, 375 no-touch 3/12, 1280 touch 1/12 in one run, similar in two
   others. It is not tied to 375 px; it is timing. The server HTML of a failing and a passing load is byte-identical. A probe in React's
   `throwOnHydrationMismatch` (test copy only, reverted) showed the failing fiber: `<main>` of `app/(app)/app/layout.tsx`, with React's
   hydration cursor already on main's first child. The server payload (RSC) arrives in pieces at the end of the document, and large
   parts of it are separate rows referred to from their parent (`$L24`: `<main>`; the page under `<main>`). When hydration started before
   such a row had arrived, React paused while reading the children of the host element around it and, on resuming, tried to claim that
   element again from inside it. **Fix:** a keyed `Fragment` between those host elements and their children (`<Fragment key="shell">`
   inside the layout's grid `div`, `<Fragment key="page">` around the page in `<main>`): React resumes the Fragment, which claims nothing.
   A `<Suspense>` around the page fixed the error too but broke the server-action redirects of the account pages (/app/settings stayed
   without its `?n=` notice; `wp79.spec.ts` "settings" failed), so it was not kept. Evidence, production build, four configurations (375
   and 1280 px, touch and not): before, 7, 12 and 8 of 48 fresh loads failed in three runs; with the Fragment around the page alone one
   failure was left in 288 warm loads, at the grid `div` (the same pattern one level up), hence the second Fragment. With both: 0 of 140
   fresh loads and 0 of 140 warm-cache loads on the two local signed-in setups, and 0 in 288 loads of the e2e loop (`wp150.spec.ts` C1
   repeated 12 times in both projects). Ruled out on the
   way: the theme script's inserted `theme-color` meta (removing it changed nothing).
2. **Underlined title in "Changes on what you follow".** Cause: `globals.css` underlines every `li > a` at rest (links in running text);
   that block put its title link straight into the `li`, the others inside a `div`/`span`. **Fix:** one `ItemTitle` (components/account/ui.tsx)
   used by the item rows, the changes and the follows: the title link is always inside its own span, so it underlines only on its own hover.

## Every text change (before -> after)

| Where | Before | After |
|---|---|---|
| Home lead | Defence and dual-use tenders and EU funding calls, the companies already in EU-funded projects, and a step-by-step check against EDF, EDIP and SAFE rules. Free to browse, every fact linked to its source. | Defence tenders, EU funding calls, partners and an eligibility check. Free, every fact linked to its source. (the owner's words) |
| Home tile "What is open?" | (description, see A) | removed |
| Home tile "Who is already in?" | (description, see A) | removed |
| Home tile "Can I take part?" | (description, see A) | removed |
| /funding lead | EU and national funding calls for defence and dual-use projects: filter by programme, country or deadline, and open a call for its rules and source. | EU and national funding calls for defence and dual-use projects, each linked to its source. |
| /funding search hint | Titles, IDs and the source’s topic keywords, whole words; drone also finds unmanned. | Hint: "Matches whole words." Disclosure "What is searched": "Titles, call IDs and the source’s topic keywords, as whole words; drone also finds unmanned." |
| /funding phone result tools | The CSV sentence shown under the button | The same sentence behind "What the file holds" (as tenders and buyers, WP-149) |
| /buyers lead | The bodies that publish defence and dual-use tenders. Open a buyer to see its notices in our archive, open ones first. | The bodies that publish defence and dual-use tenders. |
| Companies, tab "Won contracts" | Companies named as winners of defence contracts in public award notices of the last three years. | Winners of defence contracts in public award notices of the last three years. |
| Companies, tab "In EU-funded projects" | Companies and research bodies that took part in EU-funded defence and research projects: the European Defence Fund, Horizon Europe, Horizon 2020 and FP7. | Companies and research bodies in EU-funded defence and research projects. (the programmes are named by the scope line right under it and the Programme filter) |
| /calendar lead | The deadlines of open defence tenders and funding calls, soonest first, each linked to its record and source; times in UTC, or the date alone where only a date is given. | The deadlines of open defence tenders and funding calls, soonest first; times in UTC. |
| /readiness/supplier privacy | Box heading "Your answers are not stored on our server" with the disclosure "What is kept and what is sent" | Line "Your answers are not stored on our server." with the same disclosure; its two paragraphs word for word unchanged |
| /readiness/spain-automotive privacy | Box heading "Your answers are not stored on our server" with its paragraph open | Line "Your answers are not stored on our server." with the paragraph, word for word unchanged, behind "What is kept and what is sent" (new summary text, the same as on /readiness) |
| Tender page | "Buyer: <name>" / "Buyers: <names> (joint procurement)" | Head facts: "<value label>" <value>, "Deadline" (from lg) <date, countdown>, "Buyer" or "Buyers" <names> (joint procurement kept) |
| Call page | "<funder> · <programme>" line under the title | Head facts: "Deadline" <date, countdown>, "Budget" <budget or its short note>, "Funder" <funder> · <programme> (same words) |
| /organisations scope | (tinted box) | the same words as a line with a filter icon |
| /search, /check, buyer and organisation pages, account dashboard | none | none |

## Component and token changes

| File | Change |
|---|---|
| `web/app/(public)/page.tsx` | Tiles: `TileHead` (question + one line), `Figure` big (40/48, 32/40 in the split tile); no body; owner's lead; `Abbr` and the unused imports removed. |
| `web/components/dg/field.tsx`, `form.tsx` | Label 8 px above its control; `Fieldset` legend 8 px. |
| `web/app/globals.css` | `facts-grid--4` minimum 152 px (two by two on a 375 px phone). |
| `web/components/funding/filter-bar.tsx` | One-line hint plus "What is searched" (`AboutData`). |
| `web/components/funding/call-list-template.tsx` | Phone `ResultTools` `compact`. |
| `web/components/networks/parts.tsx` | `ProgrammeScope` is a `NoteLine` (also on any page that uses it). |
| `web/components/dg/companies-tabs.tsx` | One-line tab descriptions. |
| `web/app/(public)/tenders/[slug]/page.tsx`, `funding/[slug]/page.tsx` | Head facts row (`FactsGrid facts-grid--4`, `data-head-facts`). |
| `web/app/(public)/readiness/supplier/page.tsx`, `spain-automotive/page.tsx` | Privacy `NoteLine`. |
| `web/app/(public)/buyers/(list)/page.tsx`, `calendar/page.tsx`, `search/page.tsx`, `suppliers/page.tsx`, `components/readiness/wizard.tsx` | Leads, search width, label gaps. |
| `web/app/(app)/app/layout.tsx` | Two keyed Fragments (C1). |
| `web/components/account/ui.tsx`, `web/app/(app)/app/page.tsx` | `ItemTitle` (C2). |
| `web/e2e/support/fake-accounts.mjs` | Answers `/v1/account/dashboard` (one entry per titled block) for the gated account test. |

Files outside the brief's pages, by a shared component: `ProgrammeScope` (also /networks pages if used there), `Field` (every form),
`facts-grid--4` (buyer and organisation heads). Two hand-written labels on /networks/ukraine-partners and /networks/consortium-gaps still
have 4 px: not in this pass's page list (backlog).

## Tests

- New `web/e2e/wp150.spec.ts` (desktop and mobile-375): home tiles (one short line, no description, numbers at least 32 px, the three tiles
  on the first screen at 1440), the owner's lead; the 8 px label gap (funding search, a readiness select); /funding one-line lead, hint and
  "What is searched", compact phone tools; tender and call pages with title, status, deadline, value or budget and buyer or funder on the
  first screen at 1440x900 and 375x812; /search full width; readiness privacy lines (no aside, closed disclosure holding `data-what-is-sent`);
  /organisations scope line; no sideways scroll at 320 px on the fourteen pages of the pass. Gated by `E2E_FAKE_ACCOUNTS` (as wp79): C1 /app
  twelve loads with no console or page error, C2 no dashboard title underlined at rest and the changes title underlining on its own hover.
- Assertions changed on purpose (each pinned text or layout this pass changed; none loosened):
  - `wp117.spec.ts:12` the lead constant -> the owner's new lead; `wp117.spec.ts:63` "five steps of 24 to 35 questions" in the tile -> the
    tile figure's exact label "steps, 24 to 35 questions, no account".
  - `wp121.spec.ts` test 3: the tile's two description sentences -> the tile figure; the supplier range now checked on /check (the page the
    tile opens). Test 7: the abbreviations in the lead -> the hero and the tiles name no programme bare; the /glossary part unchanged.
  - `wp125.spec.ts:117,131` and `wp131.spec.ts:124`: the tile's description -> the figure, and /check for the supplier range (wp131 still
    compares the counted min and max with /check and /readiness).
  - `wp86.spec.ts:111` the lead regex -> the new lead.
  - `wp95.spec.ts:19` "Buyers:" -> the "Buyers" label of the head facts. `wp58.spec.ts:191` the buyer link is found in the head facts (still a
    32 px target).
  - `layout.spec.ts:146` reads the Key facts card's grid (the first `dl.facts-grid` of a call page is now the head row of four).
- Results (test copy `D:\DEFENCEGATE TESTS\wp150\`, final.log): tsc 0; lib checks 0; `next build` 0; the whole e2e suite (92 spec files,
  desktop, mobile-375 and both fake-api projects) **1163 passed, 103 skipped, 0 failed**; against the fake account API
  (`E2E_FAKE_ACCOUNTS=1`, fake-accounts.mjs behind https-proxy.mjs; `acc-run.ps1`) wp150 C1/C2 and all of wp79's account flows **20 passed**,
  and C1 repeated 12 times per project 24 passed.
- Harness note: a screenshot server and the e2e fake-api server share one `.next` folder; a home page revalidated by the fake-api server
  is then served by the other with the fake numbers (1,522 open tenders). The after-shots were therefore taken right after a fresh build.
