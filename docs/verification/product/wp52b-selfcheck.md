# WP-52b self-check: the web side of the tender data fixes (UX audit of 19 October 2026: T2, T3, T8-T11, T13, T14, T16-T18)

Branch `wp-wp52b` (from `integration` 891d85b). Web only (`web/`); no backend, no wording changes beyond the labels the new API fields need.
The API fields are the ones of `docs/verification/product/wp52-selfcheck.md` and "Changes of 19 October 2026" in `docs/design/API_CONTRACT.md`.
Nothing of the new API is deployed yet, so everything below ran against the demo data (`lib/mock`, updated to the new shapes) and against a
**fake API** (`web/e2e/support/fake-api.mjs`) that answers the new endpoints with the audit's numbers. No production request was made.

## What ran, and where

On the server in `/root/dev-w52b` (a copy of `web/`; `node_modules` hard-linked from another builder's tree, nothing installed), `node:22-alpine`
and `node:22-bookworm-slim` containers, CI environment (`DG_USE_MOCK=1`, `NEXT_PUBLIC_DG_NOW=2026-10-12T08:00:00Z`), one Playwright worker, a run only
started when the load was under 8 and more than 1,000 MB available (the load stayed between 7 and 19 because of the other builders and my own run).

| Step | Result |
|---|---|
| `tsc --noEmit` | clean |
| `npm run check` (every `lib/*.check.ts`, 25 files) | all ok, among them the new `lib/wp52b.check.ts` (123 assertions) |
| `next build` | ok |
| Playwright, demo build: `wp52b`, `routes`, `layout`, `changes`, `digest`, `wp54`, `ux`, `funding`, desktop and 375 px | **171 passed, 9 skipped (the specs' own viewport skips), 0 failed** (5.7 min) |
| Playwright, fake API: `wp52b-api` (6 tests x 2 projects) | **12 passed** (1.2 min) |

The final run is of commit b233155 plus this file. Earlier runs of the same code found the two test mistakes listed under "Hostile review" (151 of 153, then 10 of 12); both were in the specs, not in the pages.

Not run: the whole Playwright suite (only the specs above: those I touch plus routes, layout, tenders-related, changes, digest), `next lint` (no ESLint config in the repo),
anything against the real API or production, a screen reader, the printed page. Two e2e failures on the way were mine and are fixed (below).

## What changed, task by task

**T9, `/calendar` reads `/v1/tenders/calendar`.** Before: `loadTenders` read five pages of 100 of `/v1/tenders?status=open&sort=deadline-asc`, the 500 earliest of 1,529;
November had none of its 593; the month view put up to 300 cards in one page. After: one request (`getTenderCalendar`, `lib/api.ts`), every open notice with a deadline
(1,449 in the fake, like production), converted by `lib/calendar-tenders.ts` (the status, the three-year rule and the date-only rule are the notice page's own). Both views list
their entries 100 to a page (a month of 593 is six pages; a page past the last is redirected to the last, the month view too), and a month cell's "+N more" leads to the page that holds the day
(`pageOfDay`; the anchors of a paged agenda would otherwise point at cards that are not on the page). Fake API, measured: "593 deadlines in November 2026", `Showing 1-100 ... 501-593 of 593 deadlines in this month`,
HTML sizes of the production build against the fake (server render with a loaded machine, load 7 to 9): `/calendar` 297 kB in 1.4 s, a month of 593 380 kB in 0.9 s, its last page 365 kB; the spec's budget is 600 kB.
That is mostly the 100 cards of a page and the page's data for the browser; a month used to put up to 300 cards in one page. No horizontal scroll at 1280 and 375 px. Mock: `queryCalendar`, and the demo notices keep the same shape.

**T10, Atom feed and digest.** Feed: `getChangesForFeed` reads the window page by page (200 an entry page, at most 12 pages = 2,400 entries; the API's largest page, five tokens a request),
keeps the assembled window five minutes in the process (a feed is up to 12 requests), de-duplicates by entry id, and fails the feed (502) rather than serving one cut short by a failed page.
Before: 100 of 2,311. Fake API (the fake's entries are short: 870 kB for 2,311, so expect more with real titles; 0.2 s from the process cache; a cold build is 12 requests to the real API, not measured here): 2,311 entries with no cap note; for Poland (3,100) 2,400 entries and the subtitle says "This feed holds the newest 2,400 of the 3,100 changes; the page lists them all."
(the subtitle says it only when the cap cuts). A `week` or `kind` in the feed address is dropped. Digest: a row with `repeats` shows "x13" (visible "×13", "13 identical notices" for a screen reader),
the "Showing the first N of M" counts notices, not rows (30 rows = 49 of 873), and "the list has the rest" is now "the list of changes of this week", which leads to `/changes?week=2026-W42&kind=new`
(plus the digest's country when it is a buyer country). `/changes` reads `week` and `kind` (validated, sent to `/v1/changes`), says which week it shows ("Week 42: 12 to 18 October 2026", with the last day, not the
exclusive end), links back to the digest and to the last 14 days, keeps both in its form, is noindex, and a week outside the archive or not ended is a 404 page. Fake API: 873 new and 79 amended, `Showing 1-25 of 873 changes`.

**T2 / T3, the bounded list.** `totalCapped`: the heading reads "of at least 10,000 tenders" (and the CSV note "at least"); `maxOffset`: the pager is built on `min(total, maxOffset)` (`lib/list-count.ts`), so the last page is page 1,000
(9,991-10,000) and no link goes past it; the redirect of a page past the end (layout and page) uses the same number; a sentence above the pager says "The list shows the first 10,000 tenders of this search. Narrow it with the filters
(country, CPV code, deadline dates, status) to reach the others." The counts in headings now have thousands separators on every list that uses `ListPage`. Fake API (503 beyond offset 10,000, as the real one would at a deeper page):
`status=closed&page=1000` and `page=5000` answer 200, never the error page; `q=Bundeswehr&status=closed` is "at least 10,000".

**T13.** The list says "Counts as of HH:MM UTC" (its `asOf`) in the line under the title; the scope group says "Counts as of 07:55 UTC, for the other filters as they are now." and, when `overlap` is above 0,
"Core and supplies add up to 46 more than the first count: 46 supply notices are the national copy of a core notice, which the first count shows once." (1,522 = 294 + 1,274 - 46); a count that is `capped` reads "(at least N)". The home
page's three counters carry the same two sentences.

**T8.** `status=planned` is a choice of the status filter ("Open, Planned, Closed, All"), parsed, sent and sorted like the API (newest deadline first, as Closed); the account's saved-search words know it. Demo data: a planned notice
(neither open nor closed; Closed and Open do not list it, All does). A buyer page shows its planned notices in a "Planned tenders" section (they were in "Earlier tenders" while they counted as closed).

**T11.** `tenderChangedLabel(source)`: "Last change seen at the source" only when `lastChangeKind` is `amendment`; otherwise (`first_seen`, null, or an API that does not send it) "First seen by us". On the card, the notice page and the evidence page.

**T16 / T18.** `/data` and its summary use `updateFreq`, `stale` and `statusReason`: a monthly source is not "Stale" after three days (it says "Collected monthly, last ran N days ago"), the rule is printed from the API's own numbers
("a run is late for a daily source after 3 days, a monthly source after 40 days"), the tiles read "OK (run on time)" and "Stale (run late)", and a partial or failed run says why in the API's fixed sentence ("Why the last run is partial: ..."), also when
"Met expected minimum" is Yes. An API that sends none of it keeps the old three-day rule.

**T17, the CPV label.** The lookup is not wrong for any code (a code never gets another division's title); the defect is that `cpvLabel` returns the title of the code's group or division when the code is not one of the 366 of
`lib/data/cpv.json` and the card printed it as the name of the code: 39225500 (a grenade tender, TED's "Pyrotechnics") read "Furniture, furnishings, domestic appliances and cleaning products", the title of division 39. The card
now prints `cpvOwnName`: the code's own title or nothing (the code chip stays); the notice page keeps "Within: <division>", which says what it is. `wp52b.check.ts`: all 366 codes of the selection are named by their own title; 56 codes (50 random with a fixed
seed, the audit's 39225500 and four fixed ones) never receive another division's (or, in 35, another group's) title, and a non-exact name is never printed beside the code; the demo card for CPV 39150000 shows no "Furniture".

**T14.** The buyer page lists open and earlier tenders with `scope=core`, the scope "Open now" and "Tenders in archive" count (they used the site's default, `relevant`, so a buyer could list more open tenders than it said). Demo buyer 4 has two open core notices and
one open supply notice: "Open now" 2, two cards (the old code listed three). Open + planned + earlier = Tenders in archive on a one-page buyer (test).

## Tests added

- `web/lib/wp52b.check.ts` (123 assertions): bounded counts and the pager, scope notes, planned, the calendar (593 in November, six pages, `pageOfDay`, long-running and closed entries), digest helpers, week/kind parsing and the mock week, feed subtitle, labels, source rhythm and reasons, 366 + 56 CPV codes.
- `web/e2e/wp52b.spec.ts` (8 tests, both projects): planned status, scope-count stamp, card CPV name, source stamp labels, calendar month, `/changes` week and kind (and the 404s), `/data` rhythm and reason, buyer counts against its lists.
- `web/e2e/wp52b-api.spec.ts` (6 tests, both projects; skipped without `E2E_FAKE_API=1`) with `web/e2e/support/fake-api.mjs`: the numbers of the audit (593 in November, 287,634 closed notices stopping at 10,000, "at least", overlap 46, a feed of 2,311 and 3,100 changes, a digest week with x13) end to end.
- Demo data (`lib/mock`): `lastChangeKind`, a planned notice, `asOf`/`totalCapped`, `queryCalendar`, `week`/`kind` of the change list, rhythm and reason on three sources, and the supply notice "Laboratory consumables" moved from buyer 2 to buyer 4 (so a buyer has an open supply notice).
No existing test was changed, weakened, skipped or deleted.

## Hostile review of my own diff

I read the whole diff again after the first green run and found 10 problems; all 10 fixed:
1. The lead of `/changes` lost the space before "No account is needed" when I made it conditional (JSX drops the line break next to an expression): `{' '}`.
2. The pager and the redirect past the end used `total`, so with a total of 287,634 the pager offered page 28,764 and the redirect went there: both use `reachable` now.
3. A month cell's "+N more" pointed to an anchor that is not on the page once the agenda is paged: it links to the page that holds the day.
4. The month view had a 300-card cap and no way to the rest; it is paged like the list, and a page past the last redirects (it only did in the list).
5. Pages of the feed read some seconds apart can overlap when the window moves between them: a duplicate `<id>` makes the feed invalid; entries are de-duplicated.
6. A failed later page of the feed would have given a feed silently cut short: it fails the request (502) instead.
7. "This result has 10,000 rows" for a count that stopped: "at least" (`ResultTools`).
8. The accounts service accepts open, closed and all for a saved tender search (`accounts.py`), so "Save search" on Planned would be refused: the control is left off that view (a backend follow-up, below).
9. A buyer page on an API that does not know `status=planned` would have thrown: that read falls back to nothing.
10. My own e2e: the T11 test asserted the other label absent from a page that lists related notices as cards (it now looks at the source panel); the fake digest rows stood for 51 notices, not 49; and the site's persisted fetch cache served the previous run's digest to the first request (README says to delete `.next/cache/fetch-cache`).

## Left, and notes for the orchestrator

- **Deploy order:** the API with `/v1/tenders/calendar` first (or together). On an older API `/calendar` says "Tenders could not be loaded just now" (404), and the planned read of a buyer page and `status=planned` answer 422.
- Saved searches for status Planned need `("tender", "status")` in `dgate/accounts.py` to accept `planned`; until then the site hides the control on that view.
- The feed is up to 12 API requests (5 tokens each) per distinct query every five minutes per web process; `FEED_MAX_ENTRIES` (2,400, about 1.5 MB of XML for 2,311 entries) is the knob. A filtered feed is charged to the reader's address, an unfiltered one to the site's bucket.
- `/changes` still lists identical notices as separate entries (the API merges only in the digest); only the digest shows `repeats`.
- The glossary line "Partial means the run fetched less than we expected" (content, not touched) is not true for a partial run that met its minimum; the data page now says why next to it.
- Left alone on purpose: tailwind tokens, `globals.css`, call pages, `/requirements`, `/regulation`; the buyer cards' unformatted counts ("5366"); the first page of Closed still starting with the awarded and the cancelled notice that state a deadline ahead (API).
- Scratch on the server for the orchestrator to delete when no longer needed: `/root/dev-w52b` (a copy of `web/` and its scripts; `node_modules` there is hard links to `/root/dev-w53-web`, so it takes no disk, and deleting the folder does not touch the original). The build, logs, screenshots and containers are already removed; the shared `/root/dev-w53-pw` (browsers) was only read.
