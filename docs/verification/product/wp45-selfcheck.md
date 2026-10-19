# WP-45 self-check: page-level layout, part 1

Branch `wp-wp45` (from `integration` 2561de5, WP-44 foundation). Layout, structure, components and spacing only. No sentence of legal, positioning or regulatory text was edited or removed. Pages: /regulation, /requirements, /requirements/[code], /data/sovereignty, /privacy, /terms, /glossary, /methodology, /about, /data, /changes, /digest, /market, /calendar. Not touched: header-bar, footer, form.tsx, select.tsx, field.tsx.

## What was built

- `ContentPage`: every page frame (reading, `wide`, with or without a contents list) now spans the content box, exactly the header pill (the 988 px column is gone, per the owner). New `toc` prop: a sticky contents list from lg (220 px, 32 px links, generated from the `ContentSection` / `PageSection` / `Clause` children, or passed as items; placed after the content in the DOM so the text reads first; no list on a phone). `ContentSection split`. `.reading` split cards now use `220px | 1fr`.
- `/regulation`: each entry is a 2-column card. Left: tags (status, instrument, date), h2 with the permalink icon aligned to the right of the title, the summary, and a `Details` holding the status meaning, the verbatim quote, its source line and the line to cite (collapsed, all in the HTML, `#code` anchors kept). Right (460 px): facts grid: Status, Last checked, Who is affected, Source link, On this site links. Status chips (client, `EntryList`) hide entries with `hidden`, never remove them; a permalink clears the filter.
- `/requirements`: `PageSection` per group with `AutoGrid pairs` (a lone or odd last card takes the whole row), Cost and Time as `FactsGrid` cells, contents list of the 7 groups. `/requirements/[code]`: contents list, "At a glance" is a `FactsGrid`.
- Reading pages (privacy, terms, glossary, methodology, about, sovereignty): contents list; `ClauseGroup` = the 11 / 24 numbered clauses as one card with a hairline between (anchors `#cN` kept); glossary is one card with hairlines and a "Jump to a term" disclosure below lg; methodology steps as rows; sovereignty rows without the tinted boxes.
- `/data`: the three nested surfaces are gone (unboxed stat grid, source cards with plain fact rows, licence in sans), `AutoGrid` of source cards, contents list.
- `/changes`, `/digest`: entries in a 2-column `AutoGrid pairs` of `Card`s, the intro card is text left and the follow-links right, the repeated sentence "First collected by DefenceGate on this day." is now one legend per list (kept per entry for screen readers). `/market`: unboxed stats, `RankTable` and the chart table on `DataTable` (fits 375 px, bar column dropped below sm). `/calendar`: agenda day cards with the date in its own column, month-cell links 32 px, month text on the type scale.
- Owner additions: (1) frame = header on every page; (2) running paragraphs are justified with `hyphens: auto` from 768 px (`.justify-text`, `.justify-p` in globals.css; applied by `ContentPage`, `Prose`, the regulation summary), left on a phone; not headings, lists, cells, captions, `dl`, or the paragraphs of a card grid.
- Ad hoc `ch` caps: the 9 on /regulation and /requirements are gone (the 8 on the home page are WP-46). `lib/tokens.check.ts` now fails on any `max-w-[Nch]` outside breadcrumb, footer and home. The 2 arbitrary `text-[12px]` in the calendar moved to `text-label`.

## Route x width x result (script in the built-in browser, built `wp-wp45` served from the server, mock data, hidden same-origin iframe at each width, scrollbar 15 px)

Per cell: frame left/right == header pill left/right (+-1 px), no card narrower than 60 % of the frame unless a sibling shares its row, no horizontal overflow, longest visible paragraph <= 680 px. PASS(frame width, longest paragraph).

| route | 1280 | 1333 | 1440 | 1920 | 375 |
|---|---|---|---|---|---|
| /regulation | PASS(1201,680) | PASS(1254,680) | PASS(1296,680) | PASS(1296,680) | PASS(328,328) |
| /requirements | PASS(1201,680) | PASS(1254,680) | PASS(1296,680) | PASS(1296,680) | PASS(328,328) |
| /requirements/ncage | PASS | PASS | PASS | PASS | PASS |
| /data/sovereignty | PASS | PASS | PASS | PASS | PASS |
| /privacy | PASS | PASS | PASS | PASS | PASS |
| /terms | PASS | PASS | PASS | PASS | PASS |
| /glossary | PASS | PASS | PASS | PASS | PASS |
| /methodology | PASS | PASS | PASS | PASS | PASS |
| /about | PASS | PASS | PASS | PASS | PASS |
| /data | PASS | PASS | PASS | PASS | PASS |
| /changes | PASS | PASS | PASS | PASS | PASS |
| /digest (no issue in mock: empty state) | PASS | PASS | PASS | PASS | PASS |
| /digest-fixture (server-only page with a synthetic issue, not in the repo) | PASS | PASS | PASS | PASS | PASS |
| /market | PASS | PASS | PASS | PASS | PASS |
| /calendar | PASS | PASS | PASS | PASS | PASS |

(All PASS cells show frame 1201 / 1254 / 1296 / 1296 / 328 and longest paragraph 680, or 328 at 375.) Earlier runs of the same family of script also found: no heading glued to the block above, no card with a half-empty last row in `AutoGrid` groups, no target under 32 px in `main` on these pages at the 5 widths.

Playwright was not run (laptop and server rule). `e2e/wp45.spec.ts` encodes the same assertions plus the tracker, requirements, contents-list, justification and tap-target checks; CI runs it. Updated, not weakened: `wp36` (the last-checked day is now a fact: dt "Last checked" followed by a dd with the date), `ux.spec` U12 (the line to cite is hidden, opened by clicking the summary, then visible), `layout.spec` reading-page test (frame == header instead of a 988 px column).

## Justified text: rivers check (word-gap measurement on justified paragraphs, normal space about 4.5 px)

| page | width | justified paragraphs / lines | median mean gap | p95 | worst line |
|---|---|---|---|---|---|
| /methodology | 1280-1920 | 10 / 53 | 4.5 px | 7.1 px | 7.5 px |
| /privacy | 1280-1920 | 11 / 35 | 4.6 px | 10.6 px | 15.3 px (see note) |
| /terms | 1280-1920 | 32 / 94 | 4.7 px | 8.2 px | 9.4 px |
| /regulation | 1280-1920 | 18 / 92-94 | 4.6-5.2 px | 8.7-9.5 px | 12.0 px |
| /about | 1280-1920 | 3 / 7 | 4.5 px | 5.8 px | 5.8 px |

Text width is 680 px at every desktop width, so the numbers are the same at 1280, 1440 and 1920. Note: the one /privacy line over 12 px is a measuring artefact (an inline `font-mono` path such as `/tenders/[slug]` is not counted as a word, so the "gap" includes it); no real river. The pane is hidden (screenshots time out), so this is measurement, not eyes: the owner should still look.

## Before / after (same harness on the `integration` build with the same mock data; 1280 / 375 px page height, px)

| page | before | after | other |
|---|---|---|---|
| /regulation | 13,571 / 26,023 | 8,053 / 20,111 | entry median 693 (max 953) -> 367 (max 577); longest paragraph 680 |
| /requirements | 4,077 / 7,804 | 4,403 / 8,686 | 4 groups with a half-empty row (486 of 988) -> none; Time value 240 px wide -> 304-460 |
| /requirements/ncage | 10,811 / 19,239 | 10,561 / 19,164 | |
| /data/sovereignty | 3,141 / 6,638 | 3,109 / 6,309 | |
| /privacy | 5,533 / 12,147 | 5,642 / 11,728 | |
| /terms | 8,757 / 18,534 | 8,965 / 17,619 | |
| /glossary | 10,259 / 17,635 | 8,763 / 15,795 | 35 boxes -> 1 card |
| /methodology | 4,404 / 9,831 | 4,723 / 9,681 | |
| /about | 2,635 / 5,575 | 2,759 / 5,511 | |
| /data | 6,235 / 13,031 | 6,302 / 12,697 | nested rounded boxes removed |
| /changes | 3,497 / 6,342 | 2,750 / 5,988 | 20 paragraphs up to 1,159 px -> <= 680 |
| /market | 3,463 / 6,717 | 3,397 / 6,713 | tables fit 375 px without a 440 px scroll |
| /calendar | 6,162 / 9,615 | 5,490 / 9,683 | one 897 px paragraph -> 680 |
| /digest | not measurable with mock (no issue); live was 15,000 / 23,900 (ux3) | fixture 4,931 / 10,167 | cards 251-283 px, 2 per row |

Frame width: the reading pages were 988 px centred (139 px margins at 1280); now 1201 / 1254 / 1296 / 1296, equal to the header.

Server: `tsc --noEmit` clean, `npm run check` 21 files ok (incl. the new `ch`-cap rule), `next build` compiled and generated 42 static pages (`/root/dev-w45`, `node:22-alpine`, 1.5 GB; the build that served the table also held the server-only `digest-fixture` page). No ESLint config exists in the repo.

## Hostile review of my own work (found and fixed)

1. Moving titles back on top (contents-list pages) made privacy/terms/about/methodology 3-5 % longer than the WP-44 split cards; fixed in part with `ClauseGroup` (one card, 24 headers fewer) and a compact card header on contents pages.
2. `hidden` on a `display:grid` entry does not hide it (the utility wins): the chip filter adds the `hidden` class as well.
3. A contents list before the content broke `getByText(...).first()` in existing specs on a phone (first match hidden): it is after the content in the DOM and absent on a phone.
4. The first orphan detector counted the facts grid and the borders (0.67 px in the pane) as cards; the final script reads widths, not border strings.
5. 3 cards in a 2-column grid left a half-width last card: `AutoGrid pairs`.
6. Stale `.next/types` after deleting the temporary fixture page made `tsc` fail once; re-run clean.

## Not met / left

- /regulation with the live 19 entries will be about 8,700 px at 1280 (median entry 367 px, not 360): the asked-for facts stay visible. To go well under 8,000 the owner would have to accept "Who is affected" inside the fold or two entries per row. Left to the owner.
- Full-width frame means a text card is 1,036 px wide with a 680 px paragraph (about 300 px of empty card to the right of the text on contents-list pages). This is the price of keeping the measure and the frame; the alternative is unboxed sections. Owner to look.
- The duplicated intro sentence of /regulation (lead vs `feed.notice` vs "Newest event first") is textual, not a layout duplicate: kept, reported.
- "Eligibility rules: not read yet..." repeats on digest call cards, and "Last reviewed ..." on each requirement card: wording, kept (e2e checks the latter).
- No contents list on a phone (headings are the structure; the glossary has a "Jump to a term" disclosure).
- New UI strings (labels only): "On this page", "Contents", "Jump to a term", "Quote, source, status and how to cite", fact labels "Status" / "Source", "Show entries by status", "All", "Showing N of M entries.", legend tags "New" / "New call" (the legend sentence is the existing one), aria names "Follow this list" / "Follow the digest". The status meaning now reads "Adopted. The institutions have adopted ..." inside the fold.
- The digest, the live calendar data and real titles were not available: mock data only (digest through a synthetic server-only page). Card heights on real titles add 0-28 px.
- Playwright not run; no mobile (375 px) eye check of the new pages beyond the script.
- Header/footer targets (24-28 px) untouched by rule.

## Server scratch

Created and removed: `/root/dev-w45`, `/root/dev-w45b` (hardlinked `node_modules` of w46 only), containers `dev-w45-web`, `dev-w45b-web`, `dev-w45-build`, `dev-w45b-build`, tunnels on ports 3045 and 3055. Production not accessed.
