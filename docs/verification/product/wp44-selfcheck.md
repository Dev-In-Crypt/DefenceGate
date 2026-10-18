# WP-44 self-check: the layout foundation

Branch `wp-wp44` (from `integration` 8cb677d). Layout, spacing, typography, components and tokens only: no wording, legal text or claim was changed. Pages WP-45..47 build on this.

## What was built

### Tokens (`web/app/globals.css`, `web/tailwind.config.ts`)

| Token | Value | Notes |
|---|---|---|
| Spacing scale | Tailwind's own: 4=16, 6=24, 8=32, 12=48, 16=64, 24=96 | The override (`6`=28, `8`=48, `10`=64) is gone. The 30 usages of the old `8`/`10` (48/64 px) were rewritten to `12`/`16` so those boxes did not move; `p-6`/`gap-6` are now 24 (was 28) on purpose. `lib/tokens.check.ts` fails if a `spacing:` override comes back. Write `gap-12` for 48 px. |
| `--content-max` | 1296 px (content box); container = content + gutters = 1360 px | Centred. At 1280 px content is 1216-15, at the owner's 1333 px it is 1254 (was 1144). |
| `--gutter` | 16 / 24 (sm) / 32 (lg) | `.page` uses `padding-inline: var(--gutter)`. |
| `--measure` | 680 px; `max-w-prose` | The one reading measure. 70 ad hoc `62/70/75/80/90ch`, `860px`, `560px` caps in 33 files were replaced (`max-w-prose`, forms `max-w-form`). 17 remain in home (8), regulation (5) and requirements (4), which belong to WP-45/46, plus the breadcrumb (40ch) and footer (36/34ch), which are not prose. |
| `--reading-max` | 988 px = 220 + 40 + 680 + 48; `max-w-reading` | Width of a reading page. |
| Type | h1 36/44 (32/40 below md, class `.page-title`) wt 700; h2 24/32; **h3 20/28 wt 700 (card title)**; **h4 18/26 wt 600 (new: it was undefined, seven headings on five routes rendered as plain text)**; lead 18/28 ink (`.lead`, `text-lead`); body 16/26 | List card titles were 28/36, change entries 20 px hand-written: all are `text-h3` now. The 17 hand-written h1 strings are `page-title`. |
| `--edge` | light `#D0CABB`, dark `#3F5A4B`, print `#BDB8AC`; `border-edge` | 1px outline of a card. |
| Dark surfaces | surface `#1D3428` (was `#17291F`), inset `#254034`, line `#44604F`, open/soon/closed pills lifted | Card vs page 1.14:1 -> 1.30:1; edge vs page 2.3:1, edge vs surface 1.76:1. Text on surface: ink 11.7, muted 6.0, link 6.7, accent-text 6.0, alert 5.5; on inset muted 5.1, alert 4.7 (all >= 4.5). |
| Light | line `#D8D2C4`; every card has the edge | Edge vs page 1.45:1, vs surface 1.63:1 (surface vs page is still 1.13:1 by design, the edge does the separating). |

`web/lib/tokens.check.ts` (runs in `npm run check`) asserts: AA for text on surface and inset in both themes, the pill pairs, edge contrast, dark surface lift, measure/content/gutter tokens, no spacing override, every `text-h*`/`text-lead` class used in the app is defined.

### Components (`web/components/dg`) - API, kept stable

- `PageHeader({ crumbs?, title, sub?, lead?, meta?, actions?, children?, titleProps? })` (`page-header.tsx`). Breadcrumbs + h1 + lead (18/28, `max-w-prose`) + mono meta line + actions as one unit with 12 px between parts. Used by `ContentPage`, `ListPage`, `CallListTemplate`, `AppHeader`, `DigestView`, calendar, changes, suppliers, digest error state (9 of the 17 copies; the rest are bespoke detail heads, see "left").
- `Card({ title?, id?, anchor?, headingLevel?, action?, as?, className, bodyClassName })`, `TextCard({ aside, ...CardProps })`, `CARD_SURFACE`, `CARD_PADDING`, `slugId` (`card.tsx`). Plain: `rounded-lg border border-edge bg-surface p-5 sm:p-6`, children 16 px apart, paragraphs capped at the measure. Titled: 56 px header row (h2, optional `action` right) + hairline + body; it is a `section` labelled by its heading (`id` or slug of the title). `anchor` = id of the card element. `TextCard` / any titled card in a reading page: from lg the title (sticky) is a 220 px column and the text sits beside it.
- `FactsGrid({ items?: {label, value, mono?, wide?}[], children })`, `Fact({ label, mono?, wide? })` (`facts-grid.tsx`) and the CSS class `facts-grid` (`<dl className="facts-grid m-0 border-b border-line">` for `FactCell` children): label above value, hairline above every row, at most 3 columns, 1 on a phone, no tinted boxes. `FactCell` was rewritten to the same look; the 12 `dl grid-cols-[repeat(auto-fit,minmax(Npx,1fr))] gap-3` blocks use `facts-grid`.
- `AutoGrid({ as?: 'div'|'ul'|'ol', min = 320, className })` (`auto-grid.tsx`): `repeat(auto-fit, minmax(min(100%, min), 1fr))`, gap 16 (24 from lg). A lone card takes the row. At 1296 px the default gives 3 columns at most. `BenefitGrid`, `Steps`, `AudienceGrid` and the 404 link grid use it.
- `Prose({ as?, muted? })` (`prose.tsx`): measure, 16/26, 16 px between blocks, list markers.
- `Details({ summary, defaultOpen? })` (`details.tsx`): native disclosure, 44 px summary, breaks long strings, panel at most one measure.
- `DataTable({ label, minWidth = 480 })` (`data-table.tsx`): table inside `ScrollBox`, keeps its width at 375 px, 14 px text, 10 px row padding, tinted header.
- `ContentPage({ crumbs, title, lead, draft?, wide? })`, `ContentSection({ title, aside? })`, `PageSection({ title, id?, intro? })` (`content-page.tsx`). The measure cap (`p`, `blockquote`, `dd`, bulleted/numbered lists) applies **whatever `wide` is** (the old `wide` removed it: up to 184 characters per line). Two kinds: reading (default) = one centred 988 px column in which every titled card has the title in its own column from lg; `wide` = the data page, full content box. Sections are 32 px apart (`gap-8`); `PageSection` = h2 (24/32) + 16 px + content, so a heading is 2x closer to its content than to the section above. `main` gap is 32 px (48 from md), page padding 32/48.
- Shared components migrated: `Callout`, `BenefitGrid`, `Steps`, `AudienceGrid`, `Faq`, `Clause` (numbered anchor kept), `StateShell`/`LockedFeature`/skeleton, account `Block`/`AppHeader`, the two detail `Panel` copies (funding, tender; heading ids unchanged), all 46 files with `rounded-lg bg-surface` now carry the edge and the one padding (`p-5 sm:p-6`), chips and segmented control of the funding list.
- List cards (`cards.tsx`): `CallCard`, `TenderCard`, `BuyerCard`, `OrgCard` share one shell. From xl: text at the left, facts as hairline rows at the right (340 px); below xl facts are 3 columns, on a phone label-left/value-right rows. Title 20/28, two lines (three on a phone), the full title stays in the link. Only a closing-soon deadline is tinted. Provenance (`SourceBadge inline`) is one hairline row in 13/18 sans, not a monospace sentence; the information is the same. "Why this is here", the confidence badge and the automatic-classification line are all still on the card.

### Tests

- `web/lib/tokens.check.ts` (new, in `npm run check`).
- `web/e2e/layout.spec.ts` (new, 10 tests, desktop and 375 px): container centred with gutters 16/32 and <= 1360; h1 36/44 or 32/40, lead 18 px in ink; `text-h4` heading 18 px/600 on home; no paragraph on four reading pages wider than 680 px and the column centred <= 990; sections >= 32 px apart and the heading closer to its content; about grid has no card alone on a row; 1px card edge in both themes and dark card >= 1.25:1 against the page; call card <= 300 px, tender card <= 340 px (650 at 375), title 20/28; call-page facts grid <= 3 columns (1 at 375); no target under 32 px in `main` of `/funding`, `/calendar`, `/market`. **Not run** (CI runs Playwright; not run on the laptop or the server by the rule). The numbers it asserts were checked by hand in the built-in browser against a build (below).
- No existing spec or lib check was changed or weakened. Existing e2e locators (roles, ids, `section[aria-labelledby="results-heading"] > ul > li`, "Why this is here", panel ids) were read against the new markup and still match.

Server run (`/root/dev-w44`, `node:22-alpine`, `--memory 1500m`): `tsc --noEmit` clean, `npm run check` 21 files ok (incl. `tokens.check.ts`), `next build` compiled, 42 static pages. There is no ESLint config in the repo (`next lint` asks to create one), so no lint result.

## Before / after

"Before" = the live site as measured in `ux3-live.md` / `ux3-benchmark.md` (18 Oct). I did not rebuild the baseline. "After" = the built `wp-wp44` served from the server (mock data, `DG_USE_MOCK=1`), measured in the built-in browser by `getBoundingClientRect`/computed style, 1280/1333/375 px. Mock tenders have short titles; real titles can wrap to the 2-line clamp (add about 28 px).

| Measure | Before | After |
|---|---|---|
| Content box at 1440 / 1920 | 1144 px (margins 148 / 388) | 1296 px (margins 72 / 312) |
| Content box at 1333 (owner) | 1144, 85 % of the width | 1254 (gutter 32) |
| Longest paragraph, reading pages (/privacy /terms /methodology /about) | 878 px (~105 characters) | 680 px (measured 680 on /about, /privacy, /methodology, /requirements) |
| Longest paragraph, `wide` pages (/market /data) | 1060-1144 px (130-160 characters) | 680 px (measured 680 on /data and /market) |
| Reading page layout | 1144 card, text in the left 78 %, right 22 % empty | 988 px centred column (139 px each side at 1280), title column 220 + text 680 |
| h1 / lead | 40/48 wt 800 / 16/24 muted | 36/44 wt 700 (32/40 on a phone) / 18/28 ink |
| `text-h4` headings (home, call readiness, eligibility, roadmap) | undefined, plain 16 px text | 18/26 wt 600 (measured on home: 18px/600) |
| Space between sections in a ContentPage | 16 px (h2 20 px above its own card, 34 px under the previous) | 32 px between sections, 16 px under the h2 (measured 32.0 / 16.0 on /about) |
| Card padding | 20/28 (`p-5 sm:p-6` with 28), 28, 48, 64 in places | 20 / 24 everywhere |
| Dark card vs page | 1.14:1, no edge | 1.30:1 plus 1px edge at 2.3:1 |
| Funding call card at 1280 px | 455 px (836 wide at 1920) | 219-223 px; 255 for a closing-soon call (the tinted deadline cell wraps) |
| Tender card at 1280 px | 554 px | 242-311 px, typical 254 (basis chips + the automatic-classification line are 46 px of it) |
| Tender card at 375 px | 952 px | 485-605 px (call card 439-515) |
| Card title | 28/36 (list), 20/600 (content) | 20/28 wt 700 everywhere |
| Horizontal scroll at 375 px | none | none (checked /funding, /tenders, /about, /privacy, /regulation, /market, /data, /, consortium gaps, a call page) |
| Targets under 32 px in `main` | /calendar 27 title links 26 px, /market summary 20 px, supplier and market tables 60 px cells | 0 on /funding, /tenders, /buyers, /changes, /readiness, /data at 1333 and /funding, /market (after the summary fix), consortium gaps at 375. The calendar link fix (`py-1`) and the table `min-w` were applied after the last scan and were not re-measured. |
| Reading page heights at 375 (mock data) | n/a | /about 5527, /privacy 11635, /market 6571 (a real-data comparison needs the live data) |

## Hostile review of my own diff (issues found and fixed)

1. A generic `li` cap in `ContentPage` would have capped a lone full-width card at 680 px and left-aligned it (the complaint itself): the cap is on `p`, `dd`, `blockquote` and bulleted lists only.
2. First version of the reading cards still left the card 1296 px wide with 680 px of text (about 25 % empty): reading pages are now a 988 px centred column with the title in its own column.
3. Dark `--surface-inset` lifted for card separation dropped `--alert` text on it to 4.36:1 (below AA, "Failed" run pill): inset tuned to `#254034` (4.7:1), and `tokens.check.ts` now fails on that.
4. The styleguide drew the spacing scale from the `--space-*` variables I removed, and listed the old type scale: rewritten, and a "Layout components" section now shows every new component (so each one is compiled and rendered).
5. 404 link grid left an orphan row (3 + 2): `AutoGrid`.
6. Tap targets: calendar title links 26 px, market "Figures as a table" summary 20 px, breadcrumb/buyer links 24 px -> 32+ px.
7. Dev-mode preview was OOM-killed twice at 1.3 GB (my container only); I measured on the production build instead and removed `/root/dev-w44`, the container and the tunnel when done.

## Not met / left for later

- Not done by rule: `header-bar.tsx` and `footer.tsx`. They got only mechanical edits (the spacing migration, the edge on the dropdown/mobile panel and the footer card, the footer legal line on the measure). Their targets are still 24-28 px (logo, footer links, mega-menu links at 1024); the orchestrator should fix them when it wires the navigation.
- Page-level work left to WP-45/46/47: `/regulation` entry card (still one long stacked card, 25 297 px tall at 375), `/requirements` (`md:grid-cols-2` per category and inline Cost/Time `dl`: use `AutoGrid` + `FactsGrid`; its page is now a centred 988 column), home hero and duplicated blocks, placeholder pages, 17 `max-w-[52|62|70|80|90ch]` caps left in home, regulation and requirements (replace with `max-w-prose`; the `ContentPage` rule already caps them on the content pages), `max-w-[860px]` on `/alerts`, the readiness wizard form width (`max-w-form`).
- Detail pages (`funding/[slug]`, `tenders/[slug]`, organisations, suppliers, buyers, projects) keep their own head; use `PageHeader` with `titleProps` and `children` there. Their fact blocks are `facts-grid` already; the `ROW` constants (`[200px_minmax(0,1fr)]` rows) could become `Fact`s.
- Directory cards (buyers, organisations, suppliers) are still one per row; `AutoGrid min={280}` would give 3 per row. Tables on suppliers/networks/organisation pages should move to `DataTable` (min width added on suppliers and market only).
- Calendar month view: day-cell links are 12 px text (16 px high).
- The Playwright spec was not run; real API data was not used (mock data), so card heights on real titles are +0 to +28 px.
- The tender card is 254 px typical, above the 200-240 target (call card is inside it): the "Why this is here" chips and the classification line stay visible, as the information was not to be removed.

## Server scratch

Created and removed: `/root/dev-w44` (283 MB), container `dev-w44-web`. Nothing else touched; production was not accessed.
