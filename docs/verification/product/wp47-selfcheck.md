# WP-47 self-check: page-level layout, part 3 (record pages, lists, directories, profiles)

Branch `wp-wp47` (from `integration` 2561de5, the WP-44 foundation). Layout, structure and components only. The words that were on the pages are still there; the few places where a word was added, moved or dropped are listed under "Text" below.

## What was built

### New components and rules (`web/components/dg`, `web/app/globals.css`)

| Piece | What it does |
|---|---|
| `DetailLayout`, `SectionNav` (`detail-layout.tsx`, `.detail` in globals.css) | A record page: text in one column, **key facts and deadline in a side column** (CORDIS style), **"On this page" as a sticky list** (EU Funding & Tenders style). Slots `top / nav / facts / main / side`; the DOM order is the phone order (deadline, index, facts, panels, actions). From lg: main 1fr + side 320 px, the index sits under the facts in the side column and sticks; from xl with an index: 200 px index column at the left, main, 320 px side (at 1280: 200 / 632 / 320, at 1333: 200 / 685 / 320, at 1440 and 1920: 200 / 712 / 320). |
| `FoldGroup` (`form.tsx`) | A filter group that folds: native `<details>`, the summary is the legend and shows how many options are chosen, the options stay in the form (a closed group is still submitted), a group with a chosen option opens by itself, `scroll` keeps a 31-country list in a 256 px box. Options are 36 px apart (the label is the target). |
| Filter column (`FILTER_COLUMN` in `list-page.tsx`, used by `ListPage` and `CallListTemplate`) | Sticky from lg (`top-4`, `max-height` of the window, scrolls inside itself, thin scrollbar); the Apply/Clear bar is sticky at the foot of the form. On a phone the toggle reads "Show filters" / "Hide filters" (plus "· N active"). |
| `PageHeader` `eyebrow` | The row of tags above the title (programme, status) is part of the header unit. |
| `Fact` / `FactItem` label is a node (a glossary link can be the label); `.facts-grid--4` (up to four columns, 160 px minimum) | For four short facts in a row (a profile head) and the three-column facts block of an organisation card. |
| `ClassifiedNote`, `BasisChips note`, `TenderCard classifiedNote` | The "Classified automatically ... see how" line is said **once above a list** and not on every card. |
| Card shell (`cards.tsx`: `CARD_BODY`, `CARD_TEXT`) | Call and tender cards: from xl the provenance row sits **under the text in the left column**, the facts column (the tallest part) sets the height. `BuyerCard` and `OrgCard` use the same split (text left, facts right). |
| `lib/mock/suppliers.ts` | Five invented suppliers for the demo build, so the supplier pages have something to lay out in CI and here (before, `/suppliers` was empty in the demo). `getSuppliers`, `getSupplierSummary`, `getSupplier` use it only when `DG_API_URL` is unset. |

### Pages

- `/funding/[slug]` (call): `PageHeader` with tags as eyebrow; `DetailLayout` with the sticky index, a **Key facts** card (the 10 facts and the glossary line) and the deadline/actions card in the side column; Scope, Who can apply and Terms are `FactsGrid` (label above value, a long value takes the row); Rules that apply: one hairline per rule instead of an inset box in a card, the sentence of the regulation in `Details`; the eligibility lines stack label over value (the 256 px label column left 330 px for the text in a 617 px column); Source panel is no longer a box in a box; related calls are a list of full-width cards (three 400 px columns squeezed the xl card into 411-477 px).
- `/tenders/[slug]`: same layout without an index (four parts); related notices as a list.
- `/tenders`, `/funding`, `/buyers`, `/organisations` lists: folded, sticky filter column; call/tender/buyer/organisation cards as above; the list footnote is on the measure.
- `/buyers/[slug]`: `PageHeader`, four facts in one row, the classification line once.
- `/organisations/[slug]`, `/projects/[slug]`: `PageHeader`, `Card` for every section, all tables are `DataTable` (min width 560-720 px, scroll box, nowrap on short columns); "By programme" with one or two programmes is a facts list, not a one-row table; "How we recognised this organisation" is `FactsGrid`.
- `/suppliers`, `/suppliers/[slug]`: cards with titles, summary tables in an `AutoGrid` of two, **buyers as a `DataTable`**, notices table at 760 px.
- `/cpv`: sections are titled cards, the codes run in two columns from lg.

## Before / after (computed in the built-in browser by `getBoundingClientRect` / computed style, mock data, 1280 / 1333 / 1440 / 1920 / 375 px)

"Before" is `integration` 2561de5 built and served from the server (`/root/dev-w47`, `DG_USE_MOCK=1`, `NEXT_PUBLIC_DG_NOW` pinned). "After" is `wp-wp47` the same way. The pages were rendered in a hidden same-origin iframe at each width and measured with the same script (heights of `article` cards, widest paragraph, targets under 32 px, cells with wrapped text under 100 px, headings with less space above than below, cards alone on a row). Card heights are min / median / max of the page.

### List cards (desktop figures are the same at 1280 to 1920, because the content box is capped at 1296 px)

| | Before | After |
|---|---|---|
| Tender card, desktop | 242 / 254 / 311 | **222 / 234 / 263-291** (median under 240; the tall ones carry an original-title line or a tinted closing-soon deadline) |
| Tender card, 375 px | 471 / 529 / 591 | 447 / 505 / 567-590 (limit 600) |
| Funding call card, desktop | 217 / 221 / 261 | **187 / 187 / 223-227** |
| Funding call card, 375 px | 425 / 459 / 493 | 429 / 463-483 / 497-525 (the provenance row now sits last, as before; no limit was asked) |
| Buyer card, desktop / 375 | 209 / 209 / 237; 370 | **164**; 296 |
| Organisation card, desktop / 375 | 279; 479 | **191**; 479 |
| Classification line | on every card (9 on a buyer page, 10 on the tender list) | once per list |
| Filter column height: `/funding` | 2100 | 1594 (country, deadline, budget folded; sticky, scrolls inside) |
| `/tenders` | 2800 | **1130** |
| `/buyers` | 1692 | **348** |
| `/organisations` | 744 | 710 |

### Record pages (page height in px; widths 1280 / 1333 / 1440 / 1920, then 375)

| Page | Before | After |
|---|---|---|
| Call `1-edf-...additive-manufacturing` (rules, readiness, partners) | 5035 / 5003 / 4955 / 4955; 9487 | 4877 / 4865 / 4819 / 4819; 9609 |
| Call `14-pl-...vouchers` (plain) | 3161 / 3129 / 3109 / 3109; 6299 | **2793** x4; 6429 |
| Tender `1-framework-agreement-...` | 3297 / 3265 / 3265 / 3265; 5746 | **2542 / 2538 / 2538 / 2538**; 5877 |
| Related cards on those pages | 411-545 px each, three columns | 183-234 px, one column |
| Buyer `1-demo-armaments-agency` | 3282; 6381 | 3135 / 3123; 6391 |
| Organisation `101-alpha` | 2429; 4722 | 2523; 4831 (+ the 56 px title rows of its cards; it has three programmes, so the table stays) |
| Organisation `101-alpha?tab=partners` | 2389; 4855 | 2413; 4933 |
| Project `201-alpha` | 2290; 4343 | 2337; 4462 |
| `/cpv` | 18731 / 18707; 29999 | **10987 / 10857 / 10831**; 28825-30303 (font loading moves a text-heavy page by about 5 % between runs; no real change on a phone, 366 rows) |
| Not measurable before (no suppliers in the demo) | | `/suppliers` 2617; 5365. `/suppliers/1-demo-airframes-gmbh` 2367; 4549. Organisation with one programme `104-echo` 2405; 4951 |

The call and tender pages are shorter because the facts moved from three rows of a 3-column grid above the text into the side column, and the cards of related items no longer stack three at 400 px. On a phone the order is the same as before (the facts are one column there), so the page is as long.

Call page geometry (measured boxes, left + width): 1280: index 32+200, main 264+632, side 928+320; 1333: main 264+685; 1440: index 72+200, main 304+712, side 1048+320; 1920: index 312+200, main 544+712, side 1288+320 (equal margins). Key facts card 749-791 px tall in the side column. At 375: one column, every part 343 px wide: deadline (card), index, facts, panels, actions.

### Required checks (all five widths, every page above)

| Check | Result |
|---|---|
| Longest paragraph outside a card is at most 680 px | **680** on every list and profile (it was 889-984 on `/funding`, `/tenders` and 1167-1247 on `/organisations*`, `/projects`, `/cpv`: the source notes). Inside the call page's text column it is 567-663 (the column is 632-712 minus the card padding). |
| Horizontal scroll of the page | none, any page, any width |
| Targets under 32 px high in `main` (links, buttons, summaries, selects, checkbox labels) | **0** on all pages, 5 widths (before: 1 on `/projects`, the CORDIS link at 20 px; the first run after the demo suppliers were added found 5 supplier names at 28 px, fixed to 32) |
| Table cells with wrapped text narrower than 100 px at 375 | **0** (before, by the width-only metric of the first run: 5 cells on the organisation partners table at 92 and 99 px, 4 on the project consortium at 98 px, 4 on the buyer page at 69-100 px; the line-counting metric used after is stricter about what is squeezed and gave 0) |
| Heading with less space above than below, or under 16 px above | **0** |
| A card alone on a row of a multi-column grid | **0** (the only grids: related items are one column, summary cards are an `AutoGrid`) |
| Every table keeps its width at 375 | `DataTable` min width 240-760 px, scroll box with the "more to the right" line |

## Text (the exceptions to "no wording change")

1. The mobile filter toggle reads "Show filters" / "Hide filters" (was "Filters"); the four e2e `openFilters` helpers were updated to match.
2. Two new headings: **"Key facts"** on the call and tender pages (the facts are a titled card now).
3. The "What do these terms mean? In the glossary: ..." line of a call is in the Key facts card (same words).
4. Supplier profile, Buyers: the rows "Name (CC), N notices" are a table with the column headings "Buyer", "Country", "Notices" and the numbers as cells (the singular "notice" is gone).
5. "By programme" with one or two programmes is a facts list with the labels Programme / Projects / EU contribution / Years (the table's own column headings).
6. The "Classified automatically ... see how" line: once above the tender list, once on a buyer page, once under "More from this buyer"; the cards of those lists do not repeat it. The home page cards are unchanged (WP-46).
7. `DataTable` writes its label as the screen-reader caption, so the caption of a few tables changed in wording for screen readers only (for example "Members of the consortium, coordinator first" is now "Members of the consortium").
8. Nothing else was deleted. `conditionsText` of a call and the source paragraphs are capped at the measure (width only).

## Tests

- `web/e2e/wp47.spec.ts` (new, 13 tests, desktop and 375): side column and sticky index geometry; phone order; tender page side column and related list; tender card heights (median <= 245, max <= 300 / 560 and 600 at 375) and the classification line once; buyer page once; filter groups (>= 4, the country group closed but all >= 20 countries in the form, option rows >= 32 px, the column sticky, the "Show filters" toggle); funding filters (cascade and Ukraine reachable, form <= 1700 px); no paragraph over 680 px on six pages; organisation with one programme (facts) and with three (table); tables keep width and have no squeezed cell on four pages; supplier list target and profile tables; `/cpv` two columns. **Not run** (CI runs Playwright; not run on the laptop or the server by the rule). The numbers it asserts are the ones measured above.
- Existing specs: only the `openFilters` regexes (4 files) and one comment (`suppliers.spec.ts`) changed. Their locators were read against the new markup: `section[aria-labelledby="results-heading"] > ul > li` (still the results list), `#results-heading`, `getByRole('navigation', { name: 'On this page' })` (still there, visible from 1280 at the left and on a phone at the top), `Only calls with cascade funding` and `Only calls open to Ukraine` (their groups are open by default), `Defence goods only` and the scope radios (open), `dl.facts-grid` first (the Key facts card, one column), the supplier spec (the demo now has suppliers; the test already handled both).
- Server run (`/root/dev-w47`, `node:22-alpine`, `--memory 1500m`): `tsc --noEmit` clean, `npm run check` 21 files ok, `next build` compiled (42 static pages), final build after the last change below.

## Hostile review of my own diff (11 issues found and fixed)

1. A sticky filter column inside a grid cell with `items-start` does nothing (the cell is as tall as its content): the stickiness is on the column element itself.
2. The sticky index in the side column had a grid area of one row (no room to stick): it spans the remaining rows.
3. My first group component was called `FilterGroup`, which is already a type in `filter-bar.tsx`: renamed `FoldGroup`.
4. The shared Apply-bar class lives in a server module (a constant imported from a `'use client'` file arrives as a client reference).
5. The first e2e selector for related cards (`#related ~ ul`) matched nothing (the h2 is inside a div), so the loop was vacuous: now `section[aria-labelledby=related] ul > li > article`, and the test asserts there is at least one.
6. My first narrow-cell metric used the cell's height, which is the row's: a 91 px date cell in a three-line row was flagged. It now counts the lines of the cell's own text. Both numbers are given above.
7. The buyer page would have said "Classified automatically" with no tender under it: guarded.
8. The related cards on a call page were in `lg:grid-cols-3`: at 400 px the xl split card was 411-477 px tall, taller than the list cards; now a list.
9. Two-column supplier tables had a 320 px minimum, so "Notices" scrolled out of a 303 px card at 375: 240 / 280 px.
10. CPV rows had a 64 px indent at the fourth level: 160 px left for the title at 375; indents are 12-32 px below sm.
11. `DataSources` list items were 1247 px wide (their text was not capped): `max-w-prose`.

## Not met / left

- **Tender card <= 240 px**: the median is 234; cards with an original-title line (263) or a tinted closing-soon deadline with three lines in the facts column (up to 291) are above it, and real titles that need the second line add 28 px. The "why listed" chips are on one line already; the facts column is now the tallest part (192 px), not the text.
- `/cpv` at 375 px is still about 29,000 px (366 codes, each on 2-3 lines): not changed in substance. At desktop it fell from 18,700 to 10,900.
- The funding filter column is 1594 px high even folded (two groups carry the long explanatory paragraphs the e2e tests need open); it scrolls inside its sticky column.
- No scroll-spy (the index does not mark the part being read).
- The supplier list stays a one-column list of cards (a table would break `suppliers.spec`'s locator for the first link).
- The Playwright suite was not run; the layout was not looked at on real API data (mock titles are short; real ones add 0-28 px per card). Screenshots were looked at for the call page (375, 1440), the tender list (1440), the supplier profile (375) and the funding list at 375; the other pages were judged by the numbers above.
- Merge risk: `components/networks/parts.tsx` (tables, `DataSources`, `OrgCard`, `OrgFilterBar`) is also used by the networks pages of WP-46; `list-page.tsx`, `page-header.tsx` and `facts-grid.tsx` got small additive changes; the four `openFilters` helpers changed in the e2e specs.

## Server scratch

Created and removed at the end: `/root/dev-w47` (node_modules and builds, about 700 MB), container `dev47-web`, an SSH tunnel on 127.0.0.1:3047. Nothing else was touched; production was not accessed.
