# WP-128 self-check: the fake-API spec nobody ran, the calendar page budget, the change feed's 304

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP128.md`, plus the orchestrator's item of 25 October (changes.atom 200
instead of 304). Branch `wp-wp128` from `integration`. Web only. No migration, no ops module, no production access. Test copy
`D:\DEFENCEGATE TESTS\wp128\` (`measure.ps1`, `measure-old.ps1`, `web-run.ps1`; pages in `pages\` and `pages-old\`).

## 1. T9: the November calendar page, 323,802 bytes against 300,000

- Before: `next start` of the integration build against `e2e/support/fake-api.mjs`: `/calendar` 241,238 B,
  `/calendar?view=month&month=2026-11` 323,802 B, December 320,785 B. The WP-63 commit (`2cb0c83`) built the same way, same
  fake: 194,143 / 276,562 / 273,479 B (WP-63's own numbers, so the measurement is the same).
- What grew (November, WP-63 to now, +47,240 B; HTML markup +19,712, inline page data +27,528, the same things a second time):
  - every agenda row +146 B of classes: WP-118's `ROW_HOVER` (`hover:bg-surface-inset hover:shadow-[...] has-[:focus-visible]:...`),
    50 rows: +7,300 B markup and as much again in the page data;
  - the filter column +11,416 B markup: WP-106 lists every buyer country (31 checkboxes) instead of the three in the data. That is
    information (a filter could not be widened), so it stays;
  - header +1,078 B, footer -467 B. The month grid is unchanged (31,865 B).
  The budget is right: the page data duplicates the markup, and the limit is WP-63's remedy for the React #418 race; it is not raised.
- Change: the classes repeated on every row are named once in `web/app/globals.css` (`@layer components`): `.row-hover`
  (`ROW_HOVER` in `components/dg/card.tsx` is now that name, so the funding calendar, search and CPV rows shrink too) and
  `.tag` / `.tag-programme` / `.tag-neutral` (`components/dg/tag.tsx`, 100 tags on a calendar page). Same rules (`@apply` of the
  same utilities); `bg-primary text-on-primary` stay on the programme tag because the print rule `.bg-primary.text-on-primary`
  needs both classes on the element (a first version applied them too and lost the printed border: found in the built CSS).
- Test: T9 itself; new `e2e/wp128.spec.ts` (a real calendar tag: padding, size, pill, weight, the mono face and the primary colours
  on screen; dark text and a border in print); `e2e/wp118.spec.ts` (the row tint) green; `e2e/wp54.spec.ts`, `wp106.spec.ts` green.
- After: `/calendar` 207,330 B, November 289,834 B, December 286,748 B (agenda rows 37,450 B against 47,050 at WP-63). No entry,
  link, label or filter removed.

## 2. T10: the feed and the digest week (moved to the current contract)

| | old assertion | new assertion |
|---|---|---|
| feed | `/changes.atom` has 2,311 `<entry>`; no "This feed holds the newest"; 2,312 unique ids | read through `rel="next"`: 6 pages, each at most 400 entries, 2,311 entry ids, all unique; page 1 has 400 and says "This feed holds the newest 400 of the 2,311 changes; the page lists them all. The older ones are on the next pages of this feed (400 a page)."; page 6 says "Page 6 of 6 of this feed: changes 2,001 to 2,311 of 2,311, newest first." and has no next link; `?page=7` is 404 |
| Poland | 2,400 entries, "This feed holds the newest 2,400 of the 3,100 changes; the page lists them all." | 8 pages, 3,100 unique entry ids (the whole window, no cap cuts it now), page 1 "This feed holds the newest 400 of the 3,100 changes; the page lists them all." |
| week/kind | `?week=2026-W42&kind=new` body equals the feed | unchanged (equals page 1) |
| digest week | `getByText(/Week 42: 12 to 18 October 2026/).first()` visible | the Period combobox has value `2026-W42` and holds the option named "Week 42: 12 to 18 October 2026"; `h2#window` reads "This week so far: 12 to 12 October 2026" (the pinned clock, 12 October, is inside week 42, WP-90) |

Why the old ones failed: the feed is paged at `FEED_MAX = 400` since WP-100; since WP-106 the week label's first text match is the
Period `<option>`, never visible. Nothing is looser: the whole window is still checked entry by entry.

## 3. The gated specs now run in every local run

- Why nobody ran them: `wp52b-api.spec.ts`, `wp127-api.spec.ts` and the fake-API part of `wp63.spec.ts` skipped unless
  `E2E_FAKE_API=1` with a site started by hand on `DG_API_URL`; `playwright.config.ts` started only the demo site, CI
  (`.github/workflows/web.yml`) and the orchestrator (`wp106\web-run.ps1`) run plain `npx playwright test`, and nothing set it.
- Change: the tests are tagged `@fake-api` (the env skips removed); `playwright.config.ts` adds the projects `fake-api-desktop` and
  `fake-api-mobile-375` (`grep: /@fake-api/`, those three files) and two more web servers: the fake on `E2E_PORT + 1010` and a
  second `next start` of the same build with `DG_API_URL` at it on `E2E_PORT + 100` (4010 / 3100 by default, as the fake's
  header said). `desktop` and `mobile-375` leave the tag out. Against `E2E_BASE_URL` there are no fake projects; there the tests
  run only with `E2E_FAKE_API=1`, as before. Time: the 20 fake tests run in about 36 s in parallel with the rest (T16 waits for
  `/data` to refresh); the four touched specs 55 s in all.
- CI and the orchestrator need no change: both run `npx playwright test`. The orchestrator's `web-run.ps1` sets `E2E_PORT=3106`, so
  it also needs ports 3206 and 4116 free; nothing else. Docs: `web/README.md`, the fake's header, a comment in `web.yml`.
- Other specs behind a variable that no run sets (not wired here, open items):
  - `wp79.spec.ts` "against the fake account API": `E2E_FAKE_ACCOUNTS=1`, `e2e/support/fake-accounts.mjs` and
    `e2e/support/https-proxy.mjs` with a throwaway certificate made by `openssl` (the `__Host-` cookies need https);
  - `wp123.spec.ts` second part: `E2E_REAL_ACCOUNTS=1` and `E2E_MAIL_DIR`, the backend stack of `backend/tests/e2e_api.py`;
  - `wp122.spec.ts` "billing open" branch: a build with `NEXT_PUBLIC_BILLING_OPEN=1` (a second build).
  The `WPnn_SHOTS` variables only choose where screenshots go; they gate nothing.

## 4. `/changes.atom` answered 200 instead of 304 (e2e/changes.spec.ts)

- Before: `getChangesForFeed` serves a kept page while it builds a fresh one (WP-98c); the kept copy comes from memory or from
  disk (`lib/last-good.ts`, `recall('feed:#1')`). The disk file was keyed by the request alone, in the shared temp folder: a
  copy written by another build (an older deploy, another builder's build on this machine) or another data service (the
  fake-API site, which now runs beside the demo site in every e2e run) was served as this server's first answer, and the
  second request got the rebuilt page with another ETag: 200, not 304.
- Change (`web/lib/last-good.ts`, the one store every kept answer goes through): the file name hashes the build
  (`.next/BUILD_ID`, also in the standalone image) and the data service (`DG_API_URL`, or the demo data) with the key. A copy of
  the same build and service is still served on a restart, so the speed of WP-98c stays; it is the same page when the data has
  not changed, so the next conditional request is a 304.
- Other feeds: `calendar.ics`, `funding.atom` (WP-120 `withCachedEtag`), `digest.atom`, `regulation.atom` keep built answers in
  process memory only, per address, for their max-age, and never serve one copy while building another; the disk store reaches
  them only as the fallback of a failed API read, which is now of the same build and service too. No other change needed.
- Test: new `web/lib/wp128.check.ts`: a copy written under another service is not offered; after a restart with another
  service's copy of feed page 1 on disk, two consecutive requests give the same body (the ETag of the route's body), and with
  the server's own copy too. Red on the old store key (`the first request is not served the other copy`), green now.
  `e2e/changes.spec.ts` unchanged and green.

## Test runs (batched scope, lock held for build and browser)

- `tsc --noEmit` 0; `run-checks` 0 (every check, `wp128` ok); `next build` 0.
- Playwright (`--workers=4`, all four projects): `wp128`, `wp54`, `wp106`, `wp52b-api`, `wp127-api`, `wp63`, `wp118`, `changes`,
  `wp52b`: 88 passed, 18 skipped (their own single-viewport skips), then `wp128` again after its fix: 2 passed. The first run of
  `wp128.spec.ts` failed on `display` (a flex item reads `flex`, as before the change); the assertion was corrected, not removed.

## Open items

- `wp79`, `wp123`, `wp122` branches above still need a run that sets their variables (fake accounts with an https proxy, the
  backend stack, a billing-open build).
- Old files in the shared temp folder `dg-last-good` are now never read; they age out of use (6 h) and can be deleted by hand.
