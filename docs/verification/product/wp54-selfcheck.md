# WP-54 self-check: rendering stability and no-JS

Branch `wp-wp54` (from `integration` 4fbdc87, then `integration` b015eee merged in), 19 October 2026. Web only; no backend, no wording, no readiness component touched.
Work on the server in `/root/dev-w54` (Playwright 1.51.1 in `node:22-bookworm-slim`, CI env `DG_USE_MOCK=1`, `NEXT_PUBLIC_DG_NOW=2026-10-12T08:00:00Z`, one worker). Measurements with a clean headless Edge on the laptop against the local build through an SSH tunnel and, read-only, against the live site (public GETs, 1 request a second, `DefenceGate-e2e` agent where a script identified itself). Scripts: scratchpad `w54/` (`hydr.js`, `measure.js`, `slowproxy.js`, `labproxy.js`), derived from the system audit's `run.js`.

## R1 React error #418 and the lost theme

**Reproduced on the live site, not on a mock build.** Clean Edge, no injected script, dark theme stored through `storageState`, fresh browser context per load:

| page | loads | #418 | theme lost |
|---|---|---|---|
| live `/tenders` | 100 | 1 | 1 |
| live `/tenders` (second run) | 22 | 4 | 4 |
| live `/calendar` | 100 | 11 | 11 |
| live `/calendar` (second run) | 100 | 6 | 6 |
| mock build (`next start`), `/tenders`, `/calendar`, a call page, a tender page, `/buyers` | 100 each | 0 | 0 |
| mock build, `/tenders`, `/calendar` with CPU 6x and 150 ms network | 60 | 0 | 0 |

So the system audit's suspicion of its own instrumentation was wrong for the part that matters: with nothing injected, 1 to 11 loads in 100 fail, and every failure also lost `data-theme`.

**What the failures have in common.** On each hit the error fires at the moment the HTML document ends: `responseEnd` 2.1 to 5.2 s, `main-app` JS finished at 1.8 to 3.3 s, error time within 20 ms of `responseEnd`, `readyState` already `complete` when the handler runs. The server's HTML and the DOM after React's recovery have the same elements (1071 against 1072, the extra one is `next-route-announcer`), so nothing in the markup differs; it is the hydration attempt that fails. A dynamic page here is 300 to 360 KB, of which about 200 KB is the inline RSC data (`self.__next_f.push`) that arrives after the visible shell; the server is slow to produce it (load 6 to 13 on the host).

**Lab proof.** The saved production HTML of a page replayed through a local proxy, with the scripts and styles taken from the live site (so the same chunks), delivered in two ways:

| delivery of the same document | page | loads | #418 |
|---|---|---|---|
| all at once | `/calendar` | 20 | 0 |
| shell and the first rows at once, rest in one chunk 3 s later | `/about` | 30 | 0 |
| shell at once, rest in 20 slices over 3 s | `/calendar`, `/about`, `/changes` | 15 each | 4, 4, 4 |
| same | `/funding`, `/requirements`, `/readiness` | 15 each | 2, 1, 1 |
| same | `/market`, `/buyers` | 15 each | 0, 0 |
| shell at once, rest in 100 slices | `/about` (a static page of 78 KB) | 30 | 7 |
| same, no stored theme / dark theme | `/about` | 40 / 40 | 8 / 10 |
| production image (`dgate-web:local`) with the real API, same slicing | `/about`, `/calendar` | 30 each | 3, 4 |
| production image with demo data, same slicing | `/about`, `/calendar` | 30 each | 0, 0 |
| this branch's build with the real API, same slicing | `/calendar`, `/tenders` | 30 | 3, 2 (baseline) |

Controls: removing the JSON-LD scripts from the saved HTML (a real mismatch) fails 24 of 24, so the lab does detect a mismatch; the theme script is not the cause (same rate without a stored theme); moving the metadata row of the flight data to the front changed nothing (6/40 against 6/40); replacing every `next/link` by a plain `<a>` changed nothing (7/40 on `/calendar`); making the footer a synchronous component with props changed nothing (9/40). A dev build (React's readable message) reproduced it once in 90 loads and named the footer subtree (`<Footer>`: the client expected the card `div` where the DOM had its child); I could not turn that into a cause.

**Conclusion, stated honestly.** The failure needs the document to arrive in many pieces while the browser has already started to hydrate; it is a hydration race of Next 15.5.27 with React 19.3 on a page whose RSC data trickles in, and it shows on the live site because the dynamic pages are large and the host is loaded. I did **not** find a line of our code that causes it, so there is no code fix for the race itself, and the warning is not suppressed. What is done and what is not:

- Done: **the saved theme can no longer be lost** (below). That was the damage a visitor saw.
- Done (R2, below): the Suspense streaming of `/tenders` and `/buyers` is gone, which removes the hidden `S:` blocks; it does not by itself remove the race (the live `/calendar` has no streamed block and still fails 6 to 11 %).
- Not done, needs the owner: deliver the HTML whole. Burst and single-chunk delivery gave 0 failures in the lab. The place for it is the edge: in `infra/Caddyfile`, `reverse_proxy web:3000 { response_buffers 4MiB }` (the directive validates on the deployed Caddy 2.11.4; I did not run it against a trickling backend, and it delays the first byte until the page is complete, so it is the owner's call). Smaller pages (fewer cards per page) shorten the window and are the other lever.

**Theme fix.** `components/dg/theme-sync.tsx` (client, rendered first in `<body>` of the root layout) re-applies `data-theme="dark"` from `localStorage` after every mount of the tree, so the client re-render that follows a failed hydration puts it back. Proof of the mechanism: on the old build a deliberate text mismatch injected into `/about` (route interception) gave `#418` and `html[data-theme]` gone; `e2e/wp54.spec.ts` "a page that fails to hydrate keeps the saved dark theme" does the same and asserts the theme survives. It passed on this build; it was not run against the old build in Playwright (the same experiment was run by hand, above).

## R2 No-JS: `/tenders` and `/buyers`

Cause as for `/funding` in WP-43: `loading.tsx` wraps the page in a Suspense boundary, so the server sends the skeleton and puts the list in a hidden `S:` block that only a script swaps in. Removed `tenders/(list)/loading.tsx` and `buyers/(list)/loading.tsx` (comments in both layouts say why). The filters and the WP-49 pending states do not depend on them (`LiveListScope`, `LinkBusy`).

| JavaScript off | before (live site) | after (build) |
|---|---|---|
| `/tenders` | 0 cards, `Loading tenders` status, 900 characters | 10 cards, 21 links, "Showing 1", no status |
| `/buyers` | 0 cards, `Loading buyers` status | 5 cards (demo data), no status |

Tests: `e2e/wp54.spec.ts` ("the first page is in the HTML the server sends, before any hidden block" and "with scripts off the list, its sort and its pager are there as links", for both pages, both projects). Not done: the no-JS readiness wizard ("Loading your saved answers") lives in `components/readiness/wizard.tsx`, which this package may not touch (WP-53); a `<noscript>` line there is a two-line change for whoever owns it.

## R3 Sideways scroll

Measured with `measure.js overflow` (document wider than the window) on the demo build over 17 pages (`/tenders`, `/buyers`, `/calendar`, `/changes`, `/market`, `/`, `/funding`, 10 tender pages) at 1024, 768, 640, 375, 320:

| | before | after |
|---|---|---|
| 640 px | `/changes` (718 px), `/market` (653 px): 2 | 0 |
| 320 px | all 10 tender pages (348 px): 10 | 0 |
| 1024, 768, 375 | 0 | 0 |

Causes and fixes: the Source and attribution list (`SourceBadge` full) had `grid-cols-[auto_minmax(0,1fr)]` and values without `min-w-0`, so the label column took what it wanted and left the value 14 px (320 px) or let a long word run on (375 px, the German source name): now one column below `sm` (label above value), two from `sm`, and values `min-w-0 [overflow-wrap:anywhere]`. The confidence tooltip was `invisible absolute w-72` (still counts as scrollable overflow at 768 px) and is now `hidden` until hover or focus. The `/changes` and `/market` filter forms are `sm:flex-row` with two selects of 224 and 288 px minimum plus buttons: now `sm:flex-wrap`. Calendar entries (`Agenda` rows) used `break-words`, which does not break a run of no-break spaces in a flex or table context: now `[overflow-wrap:anywhere]`.

Not reproduced here, only fixed from the cause: `/tenders` at 1024 px (2 pages), tender pages at 768 and 375 px with the real German source names and a tooltip near the edge, calendar call 153 (live `/calendar?month=2027-01`, `?page=2`, `?page=3` at 375 and 320: 0 overflow today, so the case is gone from the live data or fixed by the data). The demo data has none of those strings. `e2e/wp54.spec.ts` therefore **injects** a 70-character German word as the source name and a run of U+202F as a calendar title and asserts no sideways scroll at 768, 375, 320.

## R4 Clipped card titles

`CARD_TITLE` was `line-clamp-3 md:line-clamp-2` (the window's width). Now `line-clamp-4 cq:line-clamp-3` (the card is a size container; `cq` is its 664 px step) and the link carries the whole title in `title` (tender, call, buyer and organisation cards; the link text is unchanged and complete). Measured on the live pages with the new rule injected as CSS (page 1 of each list; clipped titles / titles):

| | before | after |
|---|---|---|
| `/tenders` 1440 / 768 / 375 | 7/10, 9/10, 7/10 | 5/10, 7/10, 7/10 |
| `/funding` 1440 / 768 / 375 | 1/10, 5/10, 2/10 | 0/10, 2/10, 1/10 |
| `/buyers` 1440 / 768 / 375 | 0/20, 5/20, 0/20 | 0/20, 0/20, 0/20 |
| `/tenders` median card height 1440 / 768 / 375 | 319, 441, 693 px | 339, 469, 721 px |

Tender titles on the live site are long procurement descriptions, so many stay cut at three or four lines; they are readable in the tooltip. A five-line variant was measured (7→2 at 1440 for tenders) and rejected for height (+50 px per card). A `title` is a mouse and keyboard-focus aid only; touch users read the whole title on the notice page. The demo titles are short, so the demo build clips nothing (`measure.js clamp`: 0 of 10 at every width) and the e2e test asserts the rule (clamp value follows the card width; title attribute equals the link text), not the live counts.

## R5 Print

The urgent deadline box is `bg-urgent` with `text-on-urgent` (white); with backgrounds off it printed white on white. `globals.css`, inside the existing `@media print`: `.text-on-urgent, .text-on-primary` take `--ink`, and `.bg-urgent, .bg-primary.text-on-primary` lose the background and get a 1.5 px ink border. That also covers the programme tags, the Amended pill and the current page in a pager, which had the same fault (live `/funding/173`: the "National" tag is `rgb(255,255,255)` on a dark fill with `print-color-adjust: economy`). After: no light text on a fill on the demo pages in print emulation (`measure.js print`: none; before on the live page: 1 tag). Test: `wp54.spec.ts` adds an urgent box and a tag and checks colour, inner colour and border in print media.

## Checks run

- `tsc --noEmit`: ok. `npm run check`: exit 0, all `lib/*.check.ts` ok. `next build` (merged tree): compiled, all routes listed.
- Playwright (`--workers=1`, CI env, desktop and 375 px): `wp54`, `layout`, `routes`, `funding`, `wp47`, `wp49`, `changes`: **134 passed, 9 skipped, 1 failed**. The failure, `wp49` "a run of ticks is one request…" at 375 px, timed out waiting for a debounced address under host load (load 7 to 9); alone, 3 repeats on each project: 6 of 6 passed. The skips are the viewport skips the tests declare, plus two of this package's: the confidence-badge tooltip test (the demo data holds no badge on `/tenders`) and the hydration/theme test on the phone project (not width-dependent).
- The full Playwright suite was **not** run (shared server, load 7 to 13, free memory 170 MB to 1.7 GB).

## Not done or not checked

- The cause of the hydration race (see R1); the Caddy buffering remedy is untested end to end.
- Safari, Firefox, a real phone, a real printer (print emulation in Edge only).
- The no-JS wizard.
- The tooltip test and the live-title clamp counts are not covered by the demo data (the clamp numbers come from the live site with injected CSS).

## Scratch removed

`/root/dev-w54` (with hard-linked `node_modules`), `/root/pw-cache`, `/tmp/w54c`, containers `w54-*`, SSH tunnels and local proxies. Nothing was written to production; the live site received read-only GETs (the three hydration runs, 3 layout probes, the print and no-JS probes).
