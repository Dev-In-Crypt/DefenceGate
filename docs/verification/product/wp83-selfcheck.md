# WP-83 self-check: running text takes the full width of its block (22 October 2026)

Branch `wp-wp83` from `integration` (a49580d). Owner decision of 22 Oct 2026, chosen from the options: "Текст на всю ширину блока".
It replaces the 62ch reading measure of 21 Oct (WP-62). No deploy, no push, no backend change. Supplier and readiness components (WP-81)
were not edited: they use `max-w-prose`, which now resolves to 100 %.

## 1. What changed

| Change | File |
|---|---|
| `--measure: 62ch` -> `--measure: 100%`, comment states the 22 Oct decision replaces the 21 Oct rule | `web/app/globals.css` |
| Justify comment updated; the rule itself unchanged (justify + hyphens only in a container of 560 px or more) | `web/app/globals.css` |
| `maxWidth.prose` comment | `web/tailwind.config.ts` |
| Token check asserts `--measure: 100%`; `ALLOWED_CH` drops the home page (it has no `max-w-[..ch]` left) | `web/lib/tokens.check.ts` |
| Footer disclaimer: `max-w-3xl` removed, it fills its grid column | `web/components/dg/footer.tsx` |
| Comments only (no "62ch" / "one reading measure" left) | `components/dg/prose.tsx`, `components/dg/card.tsx`, `app/(public)/styleguide/page.tsx` (specimen label) |

Other caps looked at: every `max-w-prose` (content-page.tsx, blocks.tsx, card.tsx, page-header.tsx, prose.tsx, the readiness, network,
digest and market components) now resolves to 100 %, so no edit was needed there. `max-w-[..ch]` left in `ALLOWED_CH`: the breadcrumb's
last crumb (40ch, truncated, `feedback.tsx`) and the footer tagline (30ch, `footer.tsx`), neither is running text. No grid was changed:
frames and columns keep their widths (e.g. the two-column cards, the 220 px title column of a TextCard, the 280 px filter column).

## 2. Tests (owner-approved rule change)

`e2e/helpers.ts`: `paragraphsOverMeasure` (at most 95 characters a line) is replaced by `paragraphsNarrowerThanBlock`: a visible running
paragraph of `main` with more than 200 characters is at least 90 % as wide as the content box of its block. The block is the nearest card
body, padded box, grid or flex-row column, or `main`; a wrapper with its own max-width (anything but none / 100 %) is never the block, so a
cap on a wrapper is caught too. `BLOCK_WIDTHS = [1440, 1024]`.

Rewritten uses (not deleted or skipped): `layout.spec.ts` (reading pages), `wp45.spec.ts` (13 pages), `wp47.spec.ts` (list and record
pages, plus `/suppliers`, `/suppliers/1-demo-airframes-gmbh`, `/readiness/spain-automotive` from the owner's screenshots). On the desktop
project each page is measured at 1440 and 1024 px; on the 375 px project `visit` checks there is no horizontal scroll. The frame rule
(`paragraphsOutsideFrame`) stays. WP-62 comments updated.

The new rule fails on the old build (run against the `a49580d` build before the CSS change): `/about` at 1440 px (paragraph 605 px in an
882 px block), `/regulation`, `/funding`, 3 failed. One adjustment during the run: a paragraph in a padded box inside the 280 px filter
column (`/calendar` feed, `/funding` Ukraine note: 238 px in a 240 px box) was compared to the column, not the box; padded boxes now count
as the block. That is the correct reading of "nearest card body", not a loosening.

## 3. Runs

Local, `D:\DEFENCEGATE TESTS\wp83` (own copy of `web/` and `backend/` sources, node_modules copied from wp80, same lock file), TZ=UTC,
mock env of `web.yml`, Playwright 4 workers on its own port (`E2E_PORT=3183`; a first run on port 3000 reused another builder's server and
was discarded).

| Check | Result |
|---|---|
| `tsc --noEmit` | exit 0 |
| `npm run check` (lib/*.check.ts) | exit 0, all ok incl. `tokens` |
| `next build` (mock) | exit 0 |
| Playwright, full, desktop 1280 (+1440/1024 inside the rule tests) and 375 px | **519 passed, 47 skipped (the fake-API group, as before), 0 failed** |

No page-height budget or layout test needed changing: pages only got shorter.

## 4. Screenshots at 1440 px (`docs/verification/product/wp83/`, `<page>-before.png` / `<page>-after.png`)

| Page | Full-page height before -> after |
|---|---|
| `/tenders` | 3580 -> 3532 px |
| `/suppliers` ("What this map covers") | 2537 -> 2257 px |
| `/suppliers/1-demo-airframes-gmbh` (intro text) | 2198 -> 2138 px |
| `/funding` | 3316 -> 3288 px |
| `/readiness/spain-automotive` | 2917 -> 2381 px |
| `/privacy` | 5959 -> 4807 px |

Before: page leads and card text stop at about 620 px, the right half of wide cards empty. After: they run to the card's or column's
right edge; grids and frames unchanged. The owner's "What is in here" section is on the home page (`/`), covered by the same token.
