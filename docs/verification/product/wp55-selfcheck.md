# WP-55 self-check: design-system fixes that need no brand-book decision (key `wp55`)

Branch `wp-wp55`, from `integration` 891d85b. Web only; no wording changed; the type scale (h1/h2/h3 sizes), card paddings and radii and token renames are untouched (owner decision D1 pending). Nothing deployed, no model call, no secret, production not touched.

## How it was measured

A local production build of the site (mock data, `DG_USE_MOCK=1`, the same build the CI uses) served on the server (`/root/dev-w55`), then the audit's checks re-implemented in one in-page script (`measure.js`, same formulas as `inpage.js` of the system audit: alpha-blended contrast, `getComputedStyle`, bounding boxes) on **30 URLs x 3 widths (1440, 768, 375) x 2 themes** with headless Chromium. "Before" is the unchanged `integration` build, "after" is this branch. Counts are element counts summed over the 30 pages at that width; the mock has 22 calls, 11 tenders, 4 organisations, so the production figures of the audit (510 links, 692 mono bold, ...) are larger but the same rules hit them.

| # | Item (audit id) | Measure | Before 1440 / 768 / 375 | After 1440 / 768 / 375 |
|---|---|---|---|---|
| 1 | Field borders (M4, D3) | fields with border under 3:1 | 40 of 40 / 30 of 30 / 30 of 30 | **0** / 0 / 0 |
| 1 | | lowest border ratio, light / dark | 1.34 / 1.63 | **3.40 / 3.22** |
| 1 | Placeholder (M3) | placeholders under 4.5:1 (light) | 12 of 12 / 4 of 4 / 4 of 4 (2.54:1, #9CA3AF) | **0** (lowest 6.53:1, `--ink-muted`) |
| 2 | Links in text (M2) | plain (no underline) links in running text | 62 / 52 / 52, all under 3:1 from the text | **1** / 1 / 1 (see "Left") |
| 3 | Logo (m1, D2) | dark theme: disc on header; "Gate" colour | 1.02:1; #E07A3A (4.46:1) | **11.83:1; #F09A62 (6.04:1)** |
| 4 | DM Mono 600/700 (m2) | mono elements with weight >= 600 | 42 / 42 / 42 | **0** |
| 4 | Faux italic (m3) | elements with `font-style` other than normal | 5 / 5 / 5 | **0** |
| 4 | Off-token line height (m4) | size/line-height pairs not in the type table | 201 / 184 / 202 | **0** / 0 / 18 (one WP-56 page, see "Left") |
| 5 | Tap targets (M5, D4) | interactive, not in a sentence, under 32 px | 46 / 48 / 30 | **2** / 2 / 2 |
| 5 | | under 24 px (WCAG 2.5.8) | 25 / 26 / 22 | **2** / 2 / 2 |
| 5 | | under 44 px (all, informational) | 1639 / 1484 / 1241 | 1638 / 1484 / 1240 (secondary controls are held at 32 by design) |
| 6 | Squeezed icons (m9) | icons in a flex row that may shrink (`flex-shrink` not 0) | 286 of 336 / 232 of 246 / 232 of 246 (24 are external-link icons) | **0** |
| 6 | FactsGrid hairline (F-11) | in-card grids: first-row cells that still show a top rule | 3 / 8 / 0 | **0** / 0 / 0; cells of the first row start at one height |
| 6 | Mono prose (m11) | mono elements with more than 8 words | 30 / 30 / 30 (footer status line) | **0** |
| 6 | Scheme (A2) | first visit, system dark, nothing saved | `light`, body `rgb(244,241,234)` | **`dark`**, body `rgb(15,29,23)` |
| 6 | | saved "light" under a dark system | light | light (the choice is kept) |
| 6 | | `theme-color` metas for a dark choice | `#F4F1EA` / `#0F1D17` by system scheme only | **all `#0F1D17`** (and all `#F4F1EA` for light) |

Squeezed external-link icons: the mock's link labels are short, so the production case (128 icons under 15 px at 375) did not occur and cannot be counted here. The cause is closed instead (every `Icon` is `shrink-0`; the one raw Lucide icon found, in the readiness wizard, got the class) and measured as "may shrink" above. Horizontal overflow stayed 0 pages at all three widths.

## What changed (all shared, no page edited except four one-class input fixes)

1. **Inputs** (`app/globals.css`, `tailwind.config.ts`, `components/dg/field.tsx`): new token `--input-edge` (light #7A857D, dark #719080), 3.8:1 / 3.4:1 against surface / page / inset in light, 3.6 / 4.7 / 3.2 in dark; `--input` (shadcn alias) points at it; the shared field box uses `border-input-edge`. Four hand-written inputs (suppliers filter, the two networks filters, the readiness paste box) use the same class. Placeholder: `input::placeholder, textarea::placeholder` set to `--ink-muted` (preflight's `input::placeholder` had the same specificity as the old rule).
2. **Links in text**: base rule underlines `p/dd/q/blockquote/figcaption/li > a` unless the link is a flex/block/grid box or says `no-underline` (cards, buttons, nav, pagination keep their look).
3. **Logo** (`components/dg/logo.tsx`, `--logo-*` tokens): default, small and favicon marks read the tokens; light values are the old ones, dark values are the brand book's ("bone disc, pine posts", chevron #C4581F as in `mark-reversed.svg`, "Gate" #F09A62; verified in the zip: `pages/00-shared.md` line 85, `code/public/brand/mark-reversed.svg`). The print block keeps the light logo. `reversed` stays fixed.
4. **Fonts**: DM Mono exists only in 400/500 (the typeface has no 600/700, the book loads 400/500), so heavier requests are mapped to 500 in one stylesheet rule (bold class on a mono element or inside a mono box, and a mono span inside a heading, `th`, `strong`, bold class). No font loaded, no family added. Faux italic: `italic` removed from the three shared components; `.italic { font-style: normal }` keeps the two `q.italic` left in the call page (WP-56's file) upright. Line heights: `body` is 16px / 1.625 (= the body token's 26 px; preflight gave 16/24 on every unclassed element), source badge 13/18 and 12/18 -> 13/20 (`text-mono` size in the body font), count chip 12px -> `text-label`.
5. **Tap targets**: padding on the inline box (no change to line height, so no change to table or card density; it enlarges the clickable area and the reported box) for links that stand alone: `th`, `dt`, `h2-h4` children, and `p/dd/span > a:only-child`, `li/dd > a:first-child`. Table links 19 px and label links 17 px become about 35 and 33 px (the measure shows none of them under 32 any more), card-title links 27 px about 43. Buttons, inputs, pagination were already 44 (`min-h-11`).
6. **Other**: `Icon` gets `shrink-0`; `FactsGrid` in a card (`border-b-0`) clips the top pixel of the grid and keeps the first cell's border so its content no longer sits 1 px higher than its neighbour; `PageHeader` meta line and the footer status line (two lines) are `font-sans text-small`, the Source card sets source name, licence and attribution in the body font and only dates and the version in mono; `lib/theme.ts` has `pickTheme` and the pre-paint script (saved choice first, else `prefers-color-scheme`), `ThemeSync` restores it after a failed hydration, the toggle and the script set every `theme-color` meta to the chosen theme.

Files: `web/app/globals.css`, `tailwind.config.ts`, `app/layout.tsx`, `lib/theme.ts`, `components/dg/{field,form,icon,logo,facts-grid,footer,page-header,source-badge,theme-sync,theme-toggle}.tsx`, `components/funding/{call-readiness,eligibility-check}.tsx` (the `italic` class), `components/readiness/wizard.tsx`, `app/(public)/{suppliers/page,networks/consortium-gaps/page,networks/ukraine-partners/page}.tsx` (the input border class), `web/README.md`; new `lib/wp55.check.ts`, `e2e/wp55.spec.ts`. `footer.tsx` was edited (one class) although the round-A brief reserved it for navigation wiring: the change is one line and merges clean.

## Tests

- `lib/wp55.check.ts` (in `npm run check`): contrast of `--input-edge` against surface, inset and page in both themes (>= 3:1), placeholder >= 4.5:1, dark logo colours, `input::placeholder` present, and the inline theme script run against `pickTheme` for 4 saved values x 2 system schemes (theme and both metas), including a storage that throws.
- `e2e/wp55.spec.ts`, 7 tests x desktop and 375 px: first visit follows the system and a saved choice wins; toggle moves the metas and the choice survives a reload; field border and placeholder ratios in the browser; no plain link in running text; dark logo >= 3:1 and #F09A62; no mono element above weight 500, no italic, licence line not mono; in-card grid clipped, first-row cells aligned, label link >= 32 px. The spec was not run against the old build; the "before" column is the evidence that each rule was broken.
- Server run (container `node:22-alpine`, own dir `/root/dev-w55`, memory and load checked before each step): `tsc --noEmit` exit 0; `npm run check` 25 of 25 ok; `next build` compiled; Playwright `--workers=1` on `wp55, wp47, wp49, layout, routes, ux, wp45, wp46, wp48, wp54`: **220 passed, 18 skipped** (the skips are the specs' own viewport conditions), 0 failed. The first run (before the last fix) had 3 failures, below.

## Hostile review of my own diff: 3 issues found, 3 fixed

1. Source line 13/18 -> 14/20 made the line wrap into three lines and the tender card 261 px (wp47 limit: median 245): moved to 13/20 in the body font; card median is back under the limit.
2. The wizard's "Clear my answers" button had a raw Lucide icon outside `Icon` that could shrink: `shrink-0` added.
3. My first "after" run measured `/` unstyled (cold first request of a fresh container); added a warm-up and re-ran, so the 1440 numbers above are all from styled pages.
Also seen: two wp49 tests failed once under load (radio apply, tick debounce; the server was at load 10-15 from other builders) and passed on re-run; not changed.
A hazard avoided on purpose: making table/heading links `inline-block` would have broken `line-clamp` on card titles, so the area is padding on the inline box.

## Left (not met or not in scope), with reasons

- Plain links in text: 1 (`/digest`, the empty-state paragraph sits in a `div`, not a `p`); 2 more are under 32 px (the buyer link in a tender page's sentence, 22 px; sibling text under the 8-character rule). Both are WP-52b/WP-56 pages.
- Off-token line height: `/regulation` uses `max-sm:leading-6` (WP-56 page, 17 elements at 375); the home hero h1 is 36/40 (page file, type scale = D1). Deadline badge 20/26 and 24/30 are not off-token in the table the audit used and were not changed.
- Primary controls under 44 px, unchanged: the desktop nav chevron buttons (32 x 44, in `header-bar.tsx`, not touched), the inner `input`/`select` of a 44 px field box (42 px: the 1.5 px border, a measurement artefact; the box is 44), and the calendar view toggle (36 px, WP-52b page).
- DM Mono weights are mapped to 500, not loaded (the typeface has no 600/700). A future design with a real bold mono needs another face.
- `italic` is still written in `app/(public)/funding/[slug]/page.tsx` (2 places, WP-56's file); the stylesheet neutralises it, WP-56 may delete the class.
- No-JS visitors with a dark system still get the light theme on first visit (the scheme is applied by the inline script; a duplicate of the whole dark token block in a media query was not worth it).
- `body` line-height 26 px applies to unclassed 16 px text only; unclassed text of other sizes keeps a proportional 1.625 line (not a token, as before with 1.5).

## Could not run

Not the 192-URL x 7-width crawl against production (production is read-only and this build has mock data); not Edge or DPR 2; not the specs `funding, networks, readiness, suppliers, changes, digest, fit, wp36, wp53, wp57` (they test pages these changes touch only through shared classes; `layout`, `routes`, `ux` cover the shared components; worth one full CI run); not the signed-in `/app` pages; the production external-link squeeze (see above).

## Scratch

Server: `/root/dev-w55` (4 MB of scripts, results and the source copy; `.next` and screenshots deleted; the container `w55-site` is stopped). Local scratch: `scratchpad/w55` (measure script, before/after JSON, screenshots). Nothing else touched.
