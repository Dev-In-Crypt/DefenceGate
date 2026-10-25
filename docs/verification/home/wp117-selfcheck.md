# WP-117 self-check: simpler homepage (owner's option A, 25 Oct 2026)

Branch `wp-wp117` from `integration`. Web only; no backend, no migration, no ops module.

## What changed

| Item | Change |
|---|---|
| Hero | h1 and lead are the owner's text, exactly. One search (SiteSearchForm). Removed: the three task buttons, "Free to browse" line, the five-figure statistics column, the "Open now, for example" links, the CPV finder link. |
| Three tiles | One link each (`aria-labelledby` question + title, the body and figures as its description), keyboard focus uses the site's `:focus-visible` outline. What is open? -> /tenders with the live open tenders (the /tenders default list total) and open funding calls (`getSiteStats().openCalls`, the /funding default list). Who is already in? -> /companies with the supplier map's count (`getSupplierSummary().suppliers`, already cached for an hour; no number when it is null). Can I take part? -> /check, "5 steps": the readiness wizard has five steps (`components/readiness/wizard.tsx`, "Step n of 5"); /check says "five short sets of questions", so the tile says that. Under them: "Make parts or provide services? See who buys what you make" -> /readiness/supplier (the supplier route /check leads to). |
| Closing soon | "Tenders closing soon" and "Funding closing soon" side by side from md, stacked below; 3 rows each: title (display name as the lists show it, two lines at most), country or programme, value or budget if stated (a call budget shared by topics is stated once, as on the cards), days left + date. No licence, confidence, original title, "why this is here", notice ID. Links "All N open tenders" -> /tenders, "All N open calls" -> /funding. |
| Trust line | Number of sources, last update (`lastDataUpdate`), Methodology, Source status. |
| Digest | Same block shape, no e-mail field and no form: "Read the latest digest" -> /digest, "Atom feed" -> /digest.atom. |
| Questions | Four of the existing answers, unchanged words (Is it free? Where does the data come from? How current is it? How do you decide what counts as defence or dual-use?), then "More questions" -> /about. FAQ JSON-LD on home: those four only. |
| /about | Gets "Why DefenceGate", "How it works", the "Please note" callout and the full FAQ (11), same components and texts (moved to `web/lib/site-copy.ts`, read by both pages). JSON-LD FAQ on /about: the seven questions home does not show. `revalidate` 3600 -> 60 because the moved texts follow the sources list and whether sign-in is open, as they did on home. |
| Removed from home | "Three questions, three parts" (the tiles replace it), "What changed in the last N days" (in What's new), "Why DefenceGate" and "How it works" (moved), "Save searches" teaser (only shown when sign-in is open; sign-in itself is in the header then), the long FAQ (moved), "Please note" (no test or legal text needs it on home; the footer carries the same disclaimer; moved to /about). |
| Menu | `web/lib/nav.ts`: Tenders & funding (Tenders, Funding, Buyers, Market overview), Partners (Companies, Ukraine partners, Consortium gaps), Check my company (Check my company, Requirements, Regulatory tracker), What's new (What changed, Weekly digest, Deadline calendar). "Tenders & funding", "Partners", "What's new" are no page's h1, so they are buttons that open their small menu; "Check my company" is the h1 of /check, so it stays a link with a button. Footer reads the same groups; its "Directory" group became "Tenders & funding" with the same four links; every link kept. No header component change was needed. |

Copy made true (product copy may change only to make it true):
- Tile 2 body: the brief's "took part in EU-funded defence projects" would be untrue for the CORDIS Horizon/FP7 participants; it reads "Companies that won defence contracts or took part in EU-funded projects, and partners in Ukraine."
- Digest button: "Read the latest digest", not "this week's": /digest shows the latest complete week.
- Tile 3: "Five short sets of questions" and "5 steps", not "five questions" (the lead keeps the owner's approved wording) and no "~3 min" (not measured).

## Interactive elements in the homepage main (demo build, DG_USE_MOCK=1, 1280 and 375 px, same numbers)

| | links | buttons | inputs | total (links+buttons+inputs) | FAQ summaries |
|---|---|---|---|---|---|
| Before (integration c19a1eb) | 31 | 1 | 1 | **33** | 11 |
| After | 17 | 1 | 1 | **19** | 4 |

With the summaries: 44 -> 23. Header: 6 items -> 4.

## Tests

New: `web/e2e/wp117.spec.ts` (h1 and lead text; exactly three tiles, hrefs, counts equal to the /tenders and /funding list totals and the supplier map's own count, nothing clickable inside a tile, focus outline by keyboard; no statistics row and no Why DefenceGate on `/`; both lists at most 3 rows with no licence/confidence/original-title/why text and a link with the count; trust line; digest links and no e-mail input; 4 FAQ items equal to the JSON-LD and a link to /about; /about has Why DefenceGate, How it works, 11 questions, Please note, and JSON-LD for the 7 others; header four items; 375 px no horizontal scroll and stacked; dark theme). `web/lib/wp86.check.ts` extended (below).

Changed (no assertion deleted or loosened; each checks the new homepage contract or the moved block where it now is):

| File / test | Old assertion | New assertion | Why |
|---|---|---|---|
| all home visits (fit, layout, routes x4, ux x3, wp46 x2, wp48, wp68, wp86 x3) | h1 contains "Defence and dual-use tenders and funding" | h1 contains "Win, partner, qualify." | owner's new headline |
| lib/wp86.check.ts | labels = Tenders, Funding, Buyers, Companies, Check my company, What's new; Market under Tenders | labels = Tenders & funding, Partners, Check my company, What's new; exact children of Tenders & funding and Partners; the three groups without a page have no href; Check my company href /check | owner's menu |
| wp86 "header has the six items" | 5 top links visible + What's new button; What's new opens 3 pages; footer groups Companies, Check my company, What's new, Directory, About the data | exactly 4 items in the bar; Check my company link; 3 buttons; every button opens its exact pages; footer groups Tenders & funding, Partners, Check my company, What's new, About the data | owner's menu (stricter: item count and every group's pages) |
| wp86 "home: one sentence for whom, three tasks…" | "Start here" nav: Find a tender /tenders, Find funding /funding, supplier button /readiness/supplier; lead "For suppliers…"; search on first screen; task targets >= 44 px | owner's lead; three tiles /tenders, /companies, /check; supplier link /readiness/supplier (WP-97 kept); search on first screen; tiles start on first screen; tile targets >= 44 px | buttons replaced by tiles |
| routes "home: the tasks, the site search…" | text "Find a tender", "Find funding" | text of the three tile titles; rest unchanged (search, no "Get alerts", a "What changed" link visible: now the footer's) | tiles |
| routes "home: Find a tender lands on /tenders" | click "Find a tender" in Start here | click the "Find tenders and funding" tile | tiles |
| routes "header has Market overview under Tenders" | hover link Tenders | hover button Tenders & funding | menu |
| routes "never prints a dash for a counter" | dl Live data: no counter "–", >= 4 unique labels | tile figures: every number matches /^\d[\d,]*$/ (an unavailable figure is left out), >= 4 unique labels | statistics row removed, figures in tiles |
| ux U15 "names the three parts in the first screen" | list "The three parts of DefenceGate" with 1./2./3. texts, Check my company -> /check, after "Funding calls closing soon", before "Why DefenceGate" | list "What do you want to know?" with the three question headings, tile -> /check, "Three questions, three parts" absent, top in the first screen, before "Tenders closing soon", "Why DefenceGate" absent | tiles replace the block; Why DefenceGate moved |
| ux U16, wp58 Escape test | button "Companies: more pages", #sub-companies | button "Partners", #sub-partners | menu |
| wp58 route-change focus test | click top link Tenders | open Tenders & funding, click Tenders in #sub-open | menu |
| fit "the home page names the three parts" | heading "Three questions, three parts" + 1./2./3. headings, Check my company link in it | region "Three questions" + the three question headings, its tile -> /check | tiles |
| layout "text-h4 is defined" | heading /What is open to me?/ is 18 px, >= 600 | heading "What is open?" is 18 px, >= 600 | tile question is the text-h4 heading |
| wp46 "figures at the top of the hero…" | figures right of the headline, at the hero's top; search left of figures; hero <= 760 px | no dl or figure in the hero; search under the h1, in its column, on the first screen; hero <= 760 px | statistics row removed |
| wp46 "three parts named once…" | heading "1. What is open to me?" once; "Open funding calls" once | heading "What is open?" once; "open funding calls" once | tiles |
| wp48 "links under the lead, two columns as tall" | Find a tender under the lead, left of the figures; note in left column; columns +-40 px | search under the lead; three tiles under the search, one row, heights +-1 px | two-column hero removed |
| networks "partners section ranks partners" | visit text /^Partners$/ page-wide | same text, inside #main | the header now has a "Partners" item: page-wide it hit the hidden header button on a phone (and passed trivially on desktop) |

wp56 C5 (footer groups = header groups) passes unchanged; its 'Tenders' -> 'Directory' mapping no longer applies.

## Runs (test copy D:\DEFENCEGATE TESTS\wp117, demo build, lock held)

- `npx tsc --noEmit`: 0. `node scripts/run-checks.mjs`: 0 (65 checks). `next build`: 0.
- Playwright: the filter arguments matched every spec (the copy's path contains "wp117"), so the whole suite ran once: 895 passed, 1 failed (networks, fixed above), 66 skipped. Re-run of networks.spec + wp117.spec after the fix: 48 passed. After the last change (row titles two lines instead of one, they were cut to two words on a phone): tsc 0, build 0, and the specs covering home, menu, footer and /about (wp117, wp86, routes, ux, fit, layout, wp46, wp48, wp55, wp56, wp58, wp59, wp68, wp87, networks): 302 passed, 18 skipped (width-specific), 0 failed.

## Not in this package

- Remembering the visitor's country/CPV in the browser (needs privacy-notice wording: owner).
- Digest e-mail subscription (needs an e-mail provider: owner).
- Click analytics: later, from the server's access logs; no code, no tracker.
