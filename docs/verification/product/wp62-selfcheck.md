# WP-62 self-check: the site brought to the brand book, with a reading measure

Branch `wp-wp62` from `integration` at `edffcde`. Owner decisions of 21 Oct 2026: "pull the site to the brand book" and "set the
reading measure / justification if needed". Brand book: `Next.js funding hub implementation.zip` (`design_handoff_defencegate/pages/00-shared.md`,
`01`-`04`, `code/app/globals.css`, `code/tailwind.config.ts`, `code/components/dg/cards.tsx`) and `docs/design/pages/05-07` of the main
checkout. Gap evidence: `ux-audit-brand-data.md` Part 1 (B-01..B-23), `reaudit-content-brand.md`, `ux-audit-system.md` /
`reaudit-system-a11y.md`.

Not touched (other owners): `header-bar.tsx`, `footer.tsx` (orchestrator), Caddyfile, list-page status codes, page titles and the copy
of `/pricing`, `/pack`, `/alerts` (WP-63). No production access, no model calls, no push, no deploy.

## 1. Tokens changed (old -> new, book reference)

Book reference for every colour: `00-shared.md`, "Design tokens", and `code/app/globals.css` of the handoff.

| Token | Theme | Old | New | Book |
|---|---|---|---|---|
| `--line` | light | `#D8D2C4` | `#DDD8CC` | `--line #DDD8CC` |
| `--surface` | dark | `#1D3428` | `#17291F` | `--surface #17291F` |
| `--surface-inset` | dark | `#254034` | `#1F3328` | `--surface-inset #1F3328` |
| `--line` | dark | `#44604F` | `#2C4237` | `--line #2C4237` |
| `--open-bg` | dark | `#25503F` | `#1F3A2C` | `--open-bg #1F3A2C` |
| `--open-fg` | dark | `#B6E0C8` | `#A8D5BB` | `--open-fg #A8D5BB` |
| `--soon-bg` | dark | `#4A2C1B` | `#3D2416` | `--soon-bg #3D2416` |
| `--closed-bg` | dark | `#2F4238` | `#26332C` | `--closed-bg #26332C` |
| `--edge` | both | `#D0CABB` / `#3F5A4B` (outline of every card) | `var(--line)`, only the hairline of a floating layer (header sub-menu, mobile menu, tooltip) | the book has no `--edge`; cards have no border |
| `--shadow-menu` | both | `0 8px 24px ...` | removed; the select list has a 1.5px `--input-edge` border instead | "No shadows" (README, global rules) |
| `--space-1..10` | | not defined | `4 8 12 16 20 28 48 64` px | "Spacing" line of 00-shared |
| `--content-max` | | 1296 px | 1200 px | "Content width: 1200px max" |
| `--gutter` | | 16 / 24 (640) / 32 (1024) | 16 / 28 (768) | "page gutter 16px (mobile) / 28px (md+)" |
| `--measure` | | `100%` | `62ch` | owner decision; 62ch is the book's cap of the funding intro (03-funding-hub, "max 62ch") |
| body line height | | 1.625 (16/26) | 1.5 (16/24) | `body 16/24` |
| Tailwind default transition | | 150 ms `cubic-bezier(0.4,0,0.2,1)` | 120 ms `ease` (the token) | "Motion: --transition 120ms ease" (B-10) |

Type scale (`tailwind.config.ts`, book table of 00-shared):

| Step | Old | New | Book |
|---|---|---|---|
| `display` | 56/60 800 -2 | same | 56/60 800 -2 |
| `display-sm` (hero below md) | 44/48 800 -1.5 (used at md+) | 40/44 800 -1.5 (phone only; 56/60 from md) | landing: "56/60 on desktop, 40/44 on mobile" |
| `h1` | 36/44 700 -0.5 | 40/48 800 -1.5 | 40/48 800 -1.5 |
| `h1-sm` | 32/40 700 -0.5 | 32/40 800 -1 | "On mobile, h1 drops to 32/40" (weight and tracking not stated: kept 800, -1) |
| `h2` | 24/32 700 -0.3 | 28/36 700 -0.5 | 28/36 700 -0.5 |
| `h2-sm` (new) | | 22/30 700 -0.5 | CallCard title "22/30 on mobile" |
| `h3` | 20/28 700 | 20/28 600 | 20/28 600 |
| `h4` | 18/26 600 | 18/24 600 | not in the book (kept, see 4) |
| `lead` | 18/28 | same | not in the book (kept, see 4) |
| `body` | 16/26 | 16/24 | 16/24 |
| `small`, `label`, `mono`, `mono-strong`, `figure` | as book | unchanged | as book |

Components:

| Part | Old | New | Book |
|---|---|---|---|
| Card surface (`CARD_SURFACE`, 58 inline copies) | 1px `--edge` outline | 1px transparent border (no outline; forced-colours mode still draws it) | "CallCard: surface ... no shadow"; book code `border-transparent` |
| Card padding (`CARD_PADDING`, 26 inline copies, titled-card head, reading-card grid) | 20 / 24 (sm) | 20 / 28 (sm) | "padding 28 (20 on mobile)" |
| List card (`cards.tsx`, `networks/parts.tsx`) | 1px edge, padding 20, gap 8, hover border | 1.5px transparent border, hover `--ink-muted`, padding 20 / 28, gap 20 | "gap 20 ... Hover: 1.5px --ink-muted border and underlined title" |
| List card title | 20/28 700 | 28/36 700; 22/30 in a card under 664 px (container query) | "the title (h2; 22/30 on mobile)" |
| List card facts | a 340 px side column of hairline rows (xl), 13/20 mono | `repeat(auto-fit,minmax(160px,1fr))`, gap 12, inset cells padded 16, mono-strong 15/22, soon tone tinted | "fact grid (repeat(auto-fit,minmax(160px,1fr)), gap 12)", FactCell "inset cell" |
| Table rows | no hover | `--surface-inset` on hover | B-11 "table row hover --surface-inset" |
| DeadlineBadge lg countdown | 36/44 | 40/48 800 -1.5 (follows `h1`) | "countdown in h1 size" (B-13) |
| Home hero h1 | 36/40 phone, 44/48 md+ | 40/44 phone, 56/60 md+, `text-wrap: balance`; figures column 22rem -> 20rem and counter gap 12 so the headline takes two lines at 1280 | landing hero (B-23) |
| Evidence page h1 | 28/36 800 below md | `page-title` sizes (32/40, 40/48) | m5 |
| Chart swatches and bars, calendar entry | radius 2 px | pill / 14 px | radii md, lg, pill only (n4) |
| `/cpv` group heading, calendar feed heading | 16/24 bold | `h4` 18/24, `h3` 20/28 | m5 (heading scale per page type) |
| `/styleguide` type table and spacing specimen | documented the old scale | documents the new one | 01-styleguide |

Contrast: no book value fails. Every text pair is computed by `lib/tokens.check.ts` (both themes) and by the crawl (below). The book's
darker dark surfaces raise text contrast: on `#17291F` ink 13.4, muted 6.89, link 7.73, accent-text 6.92, alert 6.34; on the inset
`#1F3328` muted 6.06, alert 5.57; pills open 7.59, soon 8.06, closed 7.23. So no "nearest passing value" was needed. The one colour kept off
the book is `--input-edge` (field borders, WCAG 1.4.11): 3.84:1 on the dark inset, 4.97:1 on the dark page; the book's `--line` would be
1.42:1 on white.

## 2. Reading measure and justification

- `--measure: 62ch` caps running paragraphs (`max-w-prose`, already on 98 elements, plus the evidence panels, list cards, the regulation
  entries and two text lists); frames keep the header width (`--reading-max: 100%`, cards and the page column unchanged). `ch` follows the
  font size, so 14 px notes and the 18 px lead get the same characters per line as the body. 72ch was tried first and measured 95-110
  characters a line in Manrope, so it was narrowed to 62ch.
- Justified text only where it reads well: a paragraph in a column of at least 560 px (container query: `.justify-text`, `.card-body` and
  `.justify-col` are inline-size containers), hyphenated; left-aligned on phones, in narrow columns (the 386 px regulation text column at
  1024 px that made the 9.1x rivers) and for 14 px notes.
- `text-wrap: pretty` on `p, li, dd, blockquote` (headings had it) removes one-word last lines (m8).
- e2e helpers: `paragraphsOutsideFrame` keeps the frame rule (doc updated); new `paragraphsOverMeasure` counts the characters of each
  rendered line (a wrapped word is shared between its lines by width) and fails a paragraph over 95 characters. Used in `layout.spec`,
  `wp45.spec`, `wp47.spec`. The justification test in `wp45.spec` now asserts: no justified paragraph under 500 px wide, none at 14 px,
  every justified one hyphenated, none on a phone, some in the wide columns.

## 3. Measurements

Audit crawl `run.js` + `inpage.js` (copied to `D:\DEFENCEGATE TESTS\wp62\crawl`, base URL and widths changed, card detection extended to
borderless cards), 30 URLs x 3 widths (1440, 1024, 375) x 2 themes (layout read in light, colour in light and dark), against the local mock
build (CI env of `web.yml`, `TZ=UTC`). Before = `edffcde` (port 3101), after = this branch (port 3102). 90 snapshots each, 0 page errors,
0 bad responses. Summaries: `crawl/before.txt`, `crawl/final.txt` (`summ.py`); raw data `raw-before/`, `raw-final/`.

| Measure | Before | After |
|---|---|---|
| 1440: lines of 90+ characters (non-last lines) | 513 of 840 (61.1 %) | 64 of 1,327 (4.8 %) |
| 1440: lines of 110+ | 430 | 58, all in the footer disclaimer (`footer.tsx`, not mine) |
| 1440: longest line | 211 (`/regulation`) | 115 (footer); under 110 outside it (6 lines of 90-109) |
| 1440: lines of 60-90 characters | 83 (9.9 %) | 934 (70.4 %) |
| 1024: lines of 90+ / longest | 213 (15.3 %) / 156 | 7 (0.5 %) / 95 |
| 375: longest | 59 | 59 |
| Justified lines with rivers (mean gap > 2.2 spaces or one > 4), 1440 | 17 of 253 (6.7 %), worst 4.1x | 65 of 409 (15.9 %), worst 4.5x |
| same, 1024 | 95 of 455 (20.9 %), worst 9.1x | 39 of 306 (12.7 %), worst 3.8x |
| One-word last lines 1440 / 1024 / 375 | 110 / 183 / 260 | 18 / 25 / 126 |
| Text elements whose size/line is not in the book scale (1440) | 1,547 | 155: wordmark 21/21 x120, lead 18/28 x22, h4 18/24 x13 |
| h1 / h2 / list-card title / h3 weight / body | 36/44 700 / 24/32 / 20/28 / 700 / 16/26 | 40/48 800 / 28/36 / 28/36 (22/30 narrow) / 600 / 16/24 |
| 20 px-radius boxes with a visible outline (1440) | all (1px `--edge`) | none (transparent) |
| Card padding at 1440 / 375 | 24 / 20 | 28 / 20 |
| Text pairs failing AA, light / dark | 0 of 16,163 / 0 of 16,163 | 0 of 16,163 / 0 of 16,163 |
| Off-token colours | 95 (`--input-edge`, unknown to the harness) | 95 (same) |
| Shadows (1440 / 375) | 0 / 8 (ScrollBox cue) | 0 / 8 (same) |

Card heights (`crawl/cards.js`, 1280 px): call cards 215 -> 331-371 px, tender cards about 260 -> 388-429 px; at 375 call 591-645,
tender 588-735. Home at 1280x800: hero 497 -> 500 px, the "Three questions" list starts at 788 px (759 before; test limit 800).

Checks run in `D:\DEFENCEGATE TESTS\wp62\web` (CI env, `TZ=UTC`): `npx tsc --noEmit` clean; `npm run check` all ok (`tokens.check.ts`
rewritten to the book, see 5); `npx next build` ok (two "Failed to copy traced files ... dg-last-good" warnings of the Windows standalone
trace, an absolute temp path, not from this change); full Playwright `--workers=4`, both projects, on the committed code:
**448 passed, 40 skipped, 0 failed** (`e2e-final2.log`). One earlier run (`e2e-final.log`) had one failure, `digest.spec.ts:67`
(`/digest.atom` answered 200 instead of 304 to its own ETag under 4 workers); that spec passed 5 of 5 on `--repeat-each=5` and in every
other run; the feed is not touched by this change (a flake to watch, not fixed here).

## 4. What stays different from the book, and why

- `--input-edge` (`#7A857D` / `#719080`): field borders need 3:1 (WCAG 1.4.11); the book's `--line` is 1.42:1.
- `--edge` kept as an alias of `--line`: `header-bar.tsx` (orchestrator's file) uses `border-edge` for the sub-menus and the mobile menu.
- Shadows: `shadow-lg` on the three header sub-menus (`header-bar.tsx:94`, not mine) and the ScrollBox scroll cue (a functional hint that a
  table scrolls; it comes with a text line). The select list lost its shadow.
- Footer: its disclaimer is the only text over the measure (115 characters a line) and it pads 20/24; `footer.tsx` is not mine.
- Spacing: Tailwind's scale is not redefined. The book's code makes `p-6` 28 and `gap-8` 48 for every utility; tried here, it widened the
  header pill (`pl-6`) by 4 px and the page scrolled sideways at 320 px. The book's steps are all on Tailwind's scale, so cards use `p-7`
  (28) and `--space-*` holds the values. Section gaps stay 48 px from md and 32 px on a phone (the book gives one value, 48).
- Extra type steps: `lead` 18/28 (opening paragraph), `h4` 18/24 (heading inside a card), `h1-sm` weight/tracking (the book states only
  32/40), the 21 px wordmark (`logo.tsx` lockup, unchanged).
- Results count headings (`Showing 1-10 of 19 calls`) stay 16/24 600: that is the book's own code (`text-body font-semibold`).
- Detail-page facts keep the hairline FactsGrid (EU F&T layout) rather than the book's inset FactCells; only list cards were moved
  (B-05). The 44 px hit-target rule, native checkboxes (B-09), the header bar items (B-12), the extra status pills (B-14), the logo size
  (B-15), `/styleguide` in production (B-16), loading states (B-20) and the page contents of B-17..B-19, B-21 are unchanged.
- Cards are taller (above). The earlier compact card was a WP-47 audit fix; the book anatomy wins by the owner's decision.
- Justified rivers at 1440 rose from 6.7 % to 15.9 % of justified lines (shorter lines spread the same gaps over fewer spaces; median
  flagged gap 2.9 spaces, worst 4.5x, on `/regulation` entries); at 1024 they fell. If the owner prefers left-aligned text everywhere,
  that is one CSS rule (`globals.css`, the `@container` block).
- Dark card on dark page is 1.14:1, light 1.13:1 (book values; cards carry no outline). Cards are not controls; the hover edge is 5.79:1 /
  7.83:1.

## 5. Tests changed (to the new rule, not weakened)

- `lib/tokens.check.ts`: every one of the 22 colours in both themes must equal the book; `--edge` is `var(--line)`; no `--shadow-menu`;
  card surface without outline and padding `p-5 sm:p-7`, and no inline card keeps `p-5 sm:p-6`; measure 62ch, content 1200, gutters 16/28;
  `--space-*` values; no spacing override; the book's type steps exact; body 1.5; default transition `ease`. Field border 3:1 on surface,
  page and inset in both themes (new). AA text pairs unchanged.
- `e2e/layout.spec.ts`: gutters 16/28; page title 40/48 (32/40); card test rewritten (no outline in both themes, the book's dark surface
  and page, 1.5px `--ink-muted` edge on hover); list card heights bounded at the measured book anatomy (call 380 / tender 460 at 1280,
  700 / 780 at 375) with the title 28/36 (22/30).
- `e2e/wp47.spec.ts`: tender card median 420 / 680, max 460 / 780 (was 245 / 560 and 300 / 600).
- `e2e/wp48.spec.ts`: the tinted deadline is its own fact cell, exactly 12 px from the next (was: 16 px to a hairline row).
- `e2e/wp45.spec.ts`, `wp47.spec.ts`, `layout.spec.ts`: frame rule plus the measure rule; justification rule as in 2.

Hostile review of the diff: 4 issues found and fixed (the Tailwind spacing override that broke 320 px; uncapped paragraphs in the evidence
panels, list-card meta lines and regulation details; a measure helper that counted a wrapped URL on one line; a hover test that read the dark
card while the pointer was still on it).

## 6. Follow-up: compact list cards (owner, 21 Oct 2026)

The owner judged the book-anatomy list cards too tall and asked for compact cards in the book's look. Changed (`components/dg/cards.tsx`,
`data-display.tsx`, `networks/parts.tsx`, `tailwind.config.ts`):

- Card: padding 20 at every width (was 20 / 28), 12 px between the parts (was 20); surface, no outline and the 1.5px `--ink-muted` hover edge kept.
- Title: the card-title step 20/28 bold (was 28/36, 22/30 narrow), clamped to 2 lines in a wide card and 3 in a narrow one (was 3 / 4).
- Facts: compact inset cells (padding 4 / 12, 4 px apart), label at the left and the 13/20 mono value at the right; the labels share one
  column as wide as the longest (subgrid), so a date stays on one line in a 343 px card. From a 664 px card the facts are a 22rem column
  at the right of the text; the provenance runs under both on one line. Every fact stays visible; the soon tone keeps its tint.
- Organisation cards: the wide layout threshold `cqw` 884 -> 820 px, because a list card in the 1200 px page is 845 px inside.
- Contrast unchanged (same tokens); no new interactive element, the 32 px link targets are untouched.

Heights (`crawl/cards.js`, demo data, every card on the first page):

| Cards | Before WP-62 | WP-62 book anatomy | Now |
|---|---|---|---|
| Calls, 1440 | 193-230 | 331-371 | 205-225 |
| Calls, 1280 | 193-233 | 331-371 | 205-225 |
| Tenders, 1440 | 229-270 | 388-429 | 220-289 |
| Tenders, 1280 | 229-298 | 388-429 | 220-289 |
| Buyers, 1440 / 1280 | 166 | 253-281 | 135-163 |
| Organisations, 1440 / 1280 | 193 / 378 | 313 | 193 / 193 |
| Calls, 375 | 437-519 | 591-645 | 419-465 |
| Tenders, 375 | 457-593 | 588-735 | 438-553 |
| Buyers, 375 | 300 | 431 | 267 |
| Organisations, 375 | 482 | 492 | 482 |

Tests moved to the new numbers: `layout.spec.ts` (call at most 260 / 520 px, tender 300 / 600 px, title 20/28), `wp47.spec.ts` (tender
median 260 / 540, max 300 / 600), `wp48.spec.ts` (the tinted deadline cell 4 px from the next), `wp54.spec.ts` (title clamp 2 wide / 3 narrow).
tsc, `npm run check`, `next build` ok; full Playwright `--workers=4`: 448 passed, 40 skipped, 0 failed (`e2e-compact2.log`).
What this leaves different from the book: the list card padding (20, the book's mobile value, at every width), the 20/28 title, the fact
cells' 4 / 12 padding and 13 px values (book FactCell 16 padding, 15 px), and the facts beside the text instead of under it.
