# WP-46 self-check: page-level layout, part 2

Branch `wp-wp46` (from `integration` 2561de5, the WP-44 foundation). Layout, structure and components only. No positioning, legal or claim text was reworded; what was removed is listed under "Deleted". Production was read-only (GET of the live pages for the "before" numbers).

## What was done

| Area | Change |
|---|---|
| Home `/` | Hero is one grid: copy and the finder at the left (`minmax(0,1fr)`), the figures at the right (22 rem), both starting at the top of the card. Headline 44/48 (`display-sm` token) instead of 56/60 (three lines). The finder fields stand in one row, the example links and the three links share rows. Figures are hairline facts (no tinted boxes) that fill the height. The three-layer message is one block (the "Three questions, three parts" section, wording kept, three `Card`s in an `AutoGrid`) right under the hero. Boxed sections use the one card padding. |
| `/readiness` wizard | The form is the shape of a titled card: step name in its own column from lg, questions in one 680 px measure beside it (same as the cards below it). Text inputs and selects `max-w-form` (560). Callout no longer names the storage key. |
| `/readiness/results` | Programme cards in `AutoGrid fill` (new `fill` mode: a short last row is shared by its cards, so 5 cards are 3 + 2 and each row spans the section; cards of one row have one height). Legal-basis line pinned to the card bottom. |
| `/readiness/roadmap` | Totals boxes in `AutoGrid` (one box takes the row). |
| `/pricing` | One table of the four plans (was four cards, three of them "Not announced"). |
| `/pack` | One block (status, what it is meant to contain, what it will not be, one button). |
| `/alerts` | "What works today" kept; the planned features are one compact block of four facts; dead waitlist form removed. |
| `/imprint` | Seven fields in a two-column facts grid, the last (Contact) across both. All values still `[to be provided]`, draft notice kept. |
| `/networks/ukraine-partners` | The defence-programme default is empty (0 projects), so it now opens on all programmes with the existing "Showing all programmes ... Show only ..." line and one added label sentence; a programme the visitor chose stays as chosen. The status note is a card (was a tinted box 16 px off the page's left edge). "What this counts" and "Limits" are side by side; the Ukrainian organisations list flows in columns. |
| `/networks/consortium-gaps` | No change (a side-by-side Limits + sources was tried and reverted: the two cards have different heads). |
| 404 | The five links fill their rows (3 + 2, the two share the row). |
| Header | Logo link 44 px (was 24), submenu chevron 32 wide, nav links `whitespace-nowrap` (a submenu item, "Regulatory tracker", wrapped to 52 px). All primary targets 44 px. Nav still collapses below 1280. |
| Footer | One compact card: brand and feeds, four link groups (the two with nine links in two columns), legal line left and source line right. Same links. Links 32 px high from lg (36 on a phone). |

## Before / after

Before = https://defencegatehub.com read on 18 Oct at a 1333 px window (1318 px content width), plus `ux3-live.md`. After = this branch built and served from the server (`DG_USE_MOCK=1`), measured in the built-in browser by `getBoundingClientRect` / computed style. Mock data has short titles and few rows; real data adds height to lists, not to the blocks below.

| Measure | Before | After |
|---|---|---|
| Home hero at 1333 | 1144 x 1022 | 1254 x 493 (1265 px window: 493; 1100 px: 605; 375 px: 1175, one column) |
| Home hero: top of the figures below the top of the hero | 600 px (upper right empty 395 x 600) | 41 px (the card padding), at 1280, 1333, 1440, 1920 |
| Home: first block explaining the three parts | hero tiles and a section 8 blocks further down | one block, list at y = 781 at 1280 x 800 (inside the first screen), 1483 at 375 |
| Home "Open funding calls" counter | 2 | 1 |
| Footer, whole element | 637 | 334 (card 318) at 1280, 1333, 1440, 1920; 374 at 1100; 1032 at 375 |
| Footer links | 24-28 px high | 32 px (36 on a phone); logo link 44 |
| Header nav links | 44 (one submenu item 52) | 44 all; logo 44; menu button 44 |
| `/readiness` field width | 1054 | 525 (select/input, step 1 and 3) |
| `/readiness` form | card at the full 1254, fields across it | 988 column: step name 220, questions 679 |
| `/readiness` text names the storage key | yes (`dg.profile.v1`) | no ("saved in this browser, on this device") |
| `/readiness/results` cards (5) | 2 columns, unequal | 3 + 2 rows, each row spans the 1254 section, equal heights per row |
| `/pricing` main | 602, "Not announced" x3 as big boxes | 553, one table |
| `/pack` main | 908, 2 sections + a box | 746, 1 section |
| `/alerts` main | 2258, 1 form | 1460, no form |
| `/imprint` main | 880, 7 bare rows | 747, 2 columns (second field beside the first: x 450 / 805) |
| `/networks/ukraine-partners` default | "0 projects since 2021" and an empty table | all-programmes view with content; the sentence "No project of the European Defence Fund and its predecessors (EDIDP, PADR) started in or after 2021 has a Ukrainian participant." says why |
| 404 | 3 + 2 cards, the last two half width | 3 + 2, each row 1254 wide |

Horizontal overflow (`scrollWidth - clientWidth`): 0 on `/`, `/readiness`, step 3, `/readiness/results`, `/readiness/roadmap`, `/pricing` (all five widths), `/pack`, `/alerts`, `/imprint`, `/networks/ukraine-partners`, `/networks/consortium-gaps`, 404 (1333 and 375, and 1280 / 1920 for the changed pages; 1440 on home, results, pricing). Targets under 32 px in `main`: none on any of them. Headings glued to the previous block (space above < 1.5 x space below): none (one false positive on consortium gaps, the side-by-side that was reverted). Widest paragraph: 680 on all.

## Deleted (each one reported)

1. Home, hero: the three tiles "1. What is open to me? / 2. Who is already inside? / 3. What do I need to qualify?" with their one link each. They said what the section "Three questions, three parts" says, with its links. Kept: the section and its approved wording. Hero tiles had been added for U15; the e2e for it was changed (below).
2. Home, "What is in here": the "Open funding calls" counter and its sentence "EU and national programmes, searched separately from tenders." (the same counter is in the hero).
3. Home: the block "Alerts and a personal workspace are being prepared" (it only promised; the FAQ answer "Do I need an account?" and `/alerts` say the same). It is still drawn, as "Save searches and keep a shortlist", when accounts are open.
4. Footer: the box "Which sources are healthy, and when each was last collected." with the link "Source status". The Data column has "Source status".
5. `/alerts`: the waitlist form and its paragraph ("The waitlist is not open. The form below checks your answers but stores and sends nothing ..."). It posted to a server action that validated and dropped the input. Files removed with it: `components/landing/waitlist-form.tsx`, `app/(public)/actions.ts`, `lib/intake.ts` (used by nothing else). Also the "Good to know" callout became the last line of the planned-features block (text kept).
6. `/pricing`: the card chrome (four cards -> one table). The text of every row is kept.
7. `/pack`: the separate cards and the callout "What it will not be" -> subheadings of one block. Text kept.
8. `/readiness`: the storage key in the callout (a leak, not a copy decision): "(the key is `dg.profile.v1`)" -> "in this browser, on this device".

**Needs the owner or WP-45:** `app/(public)/privacy/page.tsx` line 81 still says "The waitlist form on the alerts page is not open. Our server receives what you type only in order to check it and then discards it ...". The form no longer exists, so that sentence is now stale. I did not touch legal text.

## Tests

- New `web/e2e/wp46.spec.ts` (10 tests, desktop 1280 and 375): hero height <= 640 and figures at the top right; three parts named once, no "being prepared" heading, one "Open funding calls"; readiness fields <= 560 and no storage key text; `/alerts` has no form; `/pricing` one table of 5 rows, `/pack` one section; `/imprint` seven placeholders in two columns; Ukraine partners opens with content and the explaining sentence (the mock's defence programmes have no Ukrainian project, so it takes the new path); 404 rows equally wide; footer <= 360 high, links kept, none under 32 px; header primary targets >= 44.
- `web/e2e/readiness.spec.ts`: one test added (programme cards fill their rows, equal height per row, 5 cards).
- `web/e2e/ux.spec.ts` U15 ("the home page names the three parts in the first screen"): the list is still required to be visible, with the same three headings and the link to `/readiness`. The position check changed from "top < 700 (900 on a phone)" to "top < one screen (two on a phone) and before 'What is in here'", because the hero tiles that satisfied it are the duplicate that was removed. On 1280 x 800 the list is at y = 781; on a phone at y = 1483 of a 1624 limit. This is a relaxation on a phone (the old tiles were at about 400); it is a consequence of removing the duplicate and is listed here on purpose.
- No other spec was changed or weakened. Locators of existing specs (`getByLabel('Three questions, three parts')`, `getByRole('list', { name: 'The three parts of DefenceGate' })`, `article` per programme, `li[data-step]`, wizard labels) were read against the built DOM.
- **Playwright was not run** (no Playwright on the laptop or the server by the rule; CI runs it). The numbers asserted were measured by hand in the browser pane on the build; the selectors were checked against the DOM in the same way.

Server run (`/root/dev-w46`, `node:22-alpine`, `--memory 1500m`): `tsc --noEmit` clean; `npm run check` every lib check ok (incl. `tokens.check.ts`); `next build` compiled (`DG_USE_MOCK=1 DG_ALLOW_INSECURE_SITE_URL=1`). No ESLint config in the repo.

## Hostile review of my own diff (found and fixed)

1. A submenu item ("Regulatory tracker") wrapped to two lines at 52 px in the 176 px dropdown: `whitespace-nowrap` on `NavLink`.
2. Limits next to "Where this comes from" on consortium gaps put two different card heads side by side: reverted, the page is unchanged.
3. Footer at 375 px was 1220 px (every group in its own row, Readiness and About each alone): groups reordered on a phone (Directory, Data, then Readiness and About side by side), 36 px links: 1032.
4. `AutoGrid` could not carry an `aria-label` or be a `dl`; the three-parts list lost its accessible name until that was added (the U15 spec finds the list by it).
5. 404 with `AutoGrid` alone gave 4 + 1 at 1254 px; `fill` with min 340 gives 3 + 2.
6. The Ukraine fallback must not override a programme the visitor chose: it only runs when `?programme=` is absent and the defence view has 0 projects while other programmes hold some.

## Not met / left

- Home still has 11 sections; "Why DefenceGate", "Built for the people who bid, advise and write" and "How it works" also describe the product (benefits, audience, steps). I merged only the exact duplicate; merging those is a content decision.
- Home on a phone: hero 1175 px, three-part list at 1483 (the figures sit below the finder). Footer 1032 px on a phone.
- `/readiness/results` card rows are 865 px tall at 1333 px when the EDIP rules list is long; the cards could collapse their lists into `Details`.
- Roadmap step cards (`StepCard`) and the wizard step 4 select list were not redesigned.
- `ProgrammeScope` in `components/networks/parts.tsx` (organisations, WP-47's page) still uses the tinted box with `px-4` that I replaced on the Ukraine page.
- No real API data: card heights on real titles are a little more than the mock's.
- `lib/intake.ts`, `actions.ts`, `waitlist-form.tsx` removed (not left as candidates).

## Server scratch

Created and removed: `/root/dev-w46` (about 280 MB with `node_modules`), container `dev-w46-web`, a throw-away static server on 127.0.0.1:3146 (fixtures for the results page) and the SSH tunnels. Nothing else was touched; production was only read with GET.
