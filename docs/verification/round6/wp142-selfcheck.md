# WP-142 self-check: two recurring e2e flakes, stale figures, frequent-word search

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP142.md`. Branch `wp-wp142` from `integration` (f2b783d). Test copy
`D:\DEFENCEGATE TESTS\wp142\` (own venv, Postgres `dgate-wp142` on 55542, removed at the end). Production was only read:
SELECT/EXPLAIN through psql in the postgres container (30 s statement timeout, read-only transactions) and curl from the laptop,
at least 3 s apart (scripts and outputs in `D:\DEFENCEGATE TESTS\wp142\prod\`). Lab scripts and outputs:
`D:\DEFENCEGATE TESTS\wp142\lab\`. Migration `0142_wp142_search_match_sets.sql`; no ops module (the worker's warm_lists job
computes the new sets).

## 1. Flake: /digest.atom answered 200 to its own ETag (e2e/digest.spec.ts:67)

**Before.** 26 Oct full run (wp106 copy, 4 workers): `Expected: 304, Received: 200` at digest.spec.ts:87; passed on repeat.

**Cause.** The e2e `desktop` project reads the demo data, which has no digest: the feed has no issue, and
`buildDigestAtom` dates an empty feed by `generatedAt`, which the route passed as `new Date().toISOString()`. So `<updated>`
was the second of the request, and the ETag (a hash of the body) changed every second: two requests that straddled a second
(4 workers, a loaded machine) had two ETags. Not a refresh or a second worker's copy: the body itself had the clock in it.
`/regulation.atom` had the same fallback (an empty tracker).

**Change.** `app/(public)/digest.atom/route.ts` and `app/(public)/regulation.atom/route.ts`: an empty feed is dated like its
own Last-Modified (the newest issue's week end / the tracker's last check, 1970-01-01 when none), never by the clock. The
assertion is unchanged.

**Test.** `e2e/wp142.spec.ts`: for both feeds, a request, 1.1 s pause, the same request with If-None-Match must be 304 and the
ETag the same (the flake's race made certain). Before the change (baseline build): **20 of 20 failed** for /digest.atom
(`e2e-baseline.log`). After: wp142.spec.ts 40/40 and digest.spec.ts:67 **20/20** with `--repeat-each=20 --workers=4`
(`e2e-repeat.log`).

## 2. Flake: React error #418 on /tenders?q=fastcounts (e2e/wp127-api.spec.ts:10, fake-api-mobile-375)

**Before.** 26 Oct full run: `Minified React error #418; ...args[]=HTML&args[]=` on the fastcounts visit, once; passed on
repeat. `args[]=HTML` is an element mismatch, not text.

**Looking for differing text.** None found. The page's text is the same in every render: the counts are awaited on the server
(`within`, then rendered or left out), the stamps are the data's times (`asOf`), the site clock is pinned
(`NEXT_PUBLIC_DG_NOW`), and no client component on the page reads the window, a time or storage during render.

**Reproduction** (`lab/hydr.js`, fresh context per load at the e2e's 375 px Pixel 5, the baseline build with the fake API):

| delivery of the same page | loads | #418 |
|---|---|---|
| whole (next start directly) | 60 | 0 |
| shell at once, the rest (the inline RSC data, 170 of 282 KB) in 100 slices over 3 s (`lab/slicer.js`, WP-63's) | 60 | **28** |
| `--repeat-each=20` of the spec in the e2e (4 workers), baseline | 40 | 0 |

So it is the WP-54 / WP-63 race: the browser begins to hydrate while the document is still arriving, which a loaded e2e
machine produces (the e2e sites have no edge; production's Caddy sends a page whole, `response_buffers 1MiB`, WP-63).

**Cause in our code.** With React's development build (`next dev` through the same slicer, `lab/dev-a.txt`), the failing load
reports the tree out of step at a component inside the list (a `useId` of the sort select differs), and WP-54's dev
reproduction named the footer. `components/dg/footer.tsx` was the one async server component of the page's tree
(`export async function Footer() { const health = await getHealth(); ...}`): an async component is a part of the page that
the RSC stream delivers on its own, after the list, so a hydration that starts early suspends there, in the middle of the
document, and resumes out of step. Lab experiment (`lab/exp-footer.py`, the same page with the footer synchronous and its data
read by the layout): **1 of 60** sliced loads (`lab/labdev-footer.txt`), against 28 of 60.

**Change.**
- `components/dg/footer.tsx`: synchronous, `health` as a prop; `app/(public)/layout.tsx` and `app/not-found.tsx` read it beside
  the account status they already await (`Promise.all`; the same cached call the footer made).
- `components/dg/alerts-line.tsx` (the other async component, on the tender and call pages): a client component that reads the
  accounts status the public layout already provides (`useAccountsOpen`), so the same rule holds there. Same output.

**Test.** `lib/wp142.check.ts`: no component under `components/` is async, and both layouts hand the footer its data. After:
the sliced lab on this branch's build: **1 of 120** sliced loads, 0 of 120 whole (`lab/lab-after.txt`; before: 28 of 60); wp127-api.spec.ts **40/40** with `--repeat-each=20 --workers=4` (both fake-API
projects, `e2e-repeat.log`); the touched specs below.

**Not done.** The remaining sliced failure (1 of 120) is the race itself, in Next 15.5 / React 19 (WP-54);
production does not see it while Caddy buffers the page.

## 3. Stale figures on /methodology and /about

**Before.** /methodology: "about 100 TED notices of mid-September 2026", "221 [versions with e-mail addresses] on
21 October 2026", "about 1,000 buyer names". /about: "earlier versions in our private archive still hold some", "about 1,000
buyer names".

**Facts** (privacy 1.7, published 26 Oct; docs/DATA_PROTECTION.md, WP-140 re-count of 25 Oct): the raw store holds up to about
12,600 TED records landed until 21 Oct with contact fields (and PLACSP before 12 Oct, not counted); 0 archive versions hold an
e-mail address; 961 organisation names / 1,133 alias spellings carry a contact block ("about 960 ... about 1,130" in
privacy 1.7).

**Change.** /methodology (Collect): "up to about 12,600 TED records landed until 21 October 2026 (counted on 22 October 2026),
and Spanish payloads (PLACSP) landed before 12 October 2026, which were not counted. The earlier versions of notices in the
archive hold no e-mail address (re-counted on 25 October 2026). About 960 buyer names (with about 1,130 spellings) hold a
telephone, fax or e-mail block as the source wrote it." /about: "Older payloads in our private archive still hold some, and
about 960 buyer names (with about 1,130 spellings) hold a telephone, fax or e-mail block". Privacy and terms not touched.

**Test.** `lib/wp142.check.ts`: the privacy notice holds the reference figures, and /methodology and /about give the same ones
and none of the stale ones (221, "about 1,000 buyer names", "earlier versions ... hold e-mail/some").

## 4. Word search for frequent words

**Before** (production, 26 Oct, `prod/probe-before1.tsv`, `probe-before2.tsv`; a page size the site never asks makes the list
cold): `/v1/tenders?q=ammunition&status=all` **3.31 s / 3.47 s** (warm 0.31 s); `q=fuel&status=closed&page=2` **3.53 s /
4.30 s**; `q=fuel&status=open` 1.99 s / 3.05 s; scope counts `q=ammunition&status=all` **503** after 1.59 s, `q=fuel` 3.42 s.
Matches (`prod/q-sizes.out`): ammunition 8,851 search rows (8,850 defence), fuel 7,024; reading the match set costs 2.68 s and
0.25 s. EXPLAIN ANALYZE of the request's statements as the API writes them (`prod/before-*.sql`, captured from the API's own
`list_tenders`, no time box): ammunition all 0.68 + 3.78 + 6.88 s (the API cuts its counts at 2 s and says "at least"); fuel
closed page 2 1.22 + 0.63 s; fuel open 0.38 + 0.26 s.

**Change** (the smallest that holds, exact and list/count-consistent):
- `tenders.search_match(q)`: the search condition, moved out of `_tender_filters` unchanged (one place for the list, the
  counts, the export and the stored sets).
- Migration 0142: `search_match_set` (key = sha256 of the condition and its parameters, the search as typed, the ids of every
  search row that passes it, the xmin of the snapshot they were read in); `opportunity_search.changed_xid`, the transaction that
  last wrote the row (set by the search-row trigger; index).
- `tenders.refresh_search_sets` (the worker, at the end of `ops/warm_lists`, every 4 hours): one INSERT ... SELECT per search,
  ids and `pg_snapshot_xmin(pg_current_snapshot())` in one statement. Searches: the first term of each of the 13 product groups
  (uniform, spare parts, machined parts, drone, fuel, logistics, ammunition, night vision, body armour, wiring harness, stamping,
  casting, cyber) and `DGATE_SEARCH_SET_WORDS` (default `boots`, the home page's link): 14 sets. A set of a search no longer
  listed is deleted.
- `tenders.stored_matches`, read first by `search_ids` (once per request, the memo of WP-120): the stored ids, with the search
  rows written at or past the set's xmin re-tested against the live condition (at most `SEARCH_SET_RETEST_MAX` = 2,000 rows;
  more, or a set older than 24 h, or any error: None, and the live query runs as before). The ids are therefore those of the
  live condition now, and every statement of the request (the rows, the counts, both parts of `all`) reads the same ids:
  list and count agree by construction. Case: a set is keyed by the search as typed; "Ammunition" runs live.

**After** (EXPLAIN ANALYZE on production of the same statements with production's own match ids, `prod/after-*.sql`; the
re-test of rows written since the set measured over the 176 notices first seen in the last 24 hours, `prod/q-churn.out`: a
normal day rewrites about 200 search rows, the set is renewed every 4 hours):

| request | before (statements) | after (statements) |
|---|---|---|
| q=ammunition, status=all | 0.68 + 3.78 + 6.88 s (API: 3.3-3.5 s, counts cut at 2 s) | 0.11 + 0.04 + 0.32 + 0.24 s = **0.71 s**, counts exact |
| q=fuel, status=closed, page 2 | 1.22 + 0.63 s (API: 3.5-4.3 s) | 0.03 + 0.32 + 0.27 s = **0.62 s** |
| q=fuel, status=open | 0.38 + 0.26 s (API: 2.0-3.1 s) | 0.05 + 0.10 + 0.10 s = **0.25 s** |

The re-test is the bounded part: over 18,000 rows (the day of 25 Oct's bulk re-check, all versions) it took 4.7 s, which is why
it stops at 2,000 rows (about 0.5 s) and falls back to the live query.

**Tests.** `tests/integration/test_wp142.py`: (1) the worker's set lists what the live search lists, with a notice written
after the set and one whose title stopped matching; list total = rows, scope count the same; (2) an old set is not used, a set
no longer listed is deleted, report mode writes nothing; (3) the trigger stamps a row only when a searched column changes;
(4) past the re-test limit the set is not used. `tests/conftest.py`: the new table is emptied between tests (as
`list_snapshot`).

## Runs (test copy, batched)

- ruff: clean. Unit: 4,075 passed. Integration: 1,560 passed (15 min).
- tsc: clean. Lib checks: all passed (`wp142.check.ts` among them). Build: ok.
- Playwright (4 workers): `--repeat-each=20` of wp142.spec.ts, digest.spec.ts:67, wp127-api.spec.ts: 100 passed, 60 skipped
  (the other viewport), 0 failed.
- Touched specs (wp142, digest, layout, routes, wp117, wp118, wp121, wp130, wp131, wp45, wp46, wp54, wp55, wp56, wp67, wp86,
  wp87, and the fake-API specs wp127-api, wp52b-api, wp63, wp132-api), one run after the repeats: 344 passed, 5 failed, all five
  home-page tests of the desktop project (routes:171, wp117:41, wp121:18, wp121:113, wp131:44) that read the fake API's figures
  ("3 tender and 2 funding sources") on the demo site. Cause, not this package: both `next start` servers of the e2e run use one
  build, and Next's route cache on disk (`.next/server/route-cache/APP_PAGE/.../index.html`) is shared; a page of the fake-API
  site that regenerates "/" (revalidate 60 s, e.g. a prefetch of the logo link) writes the fake figures where the demo site
  reads them (the file held "3 tender and 2 funding sources" after the run). It shows only when the desktop home tests run more
  than a minute after the build and after the fake-API projects, as in this second run. The same specs on a fresh build, the
  demo projects alone: **312 passed, 0 failed** (`e2e-specs-demo.log`); the fake-API specs passed in the batch run. Open item.

## Ops after deploy

1. Migration 0142 runs with the deploy (`migrate` service): a column (catalogue only), the trigger function, one index over
   394,000 rows (seconds), one table.
2. `docker compose ... run --rm worker python -m dgate.ops.warm_lists` (report): expect `search_sets: 14`, `search_sets_written: 0`.
3. Either wait for the worker's next warm_lists round (every 4 hours) or `... python -m dgate.ops.warm_lists --yes`: expect
   `failed: 0`, `search_sets_written: 14`, `search_sets_removed: 0`; the views as before (about 10 minutes), the sets about
   20 s more (ammunition 2.7 s, fuel 0.3 s each).
4. Check (read-only): `SELECT q, cardinality(ids), computed_at FROM search_match_set ORDER BY q;` 14 rows, ammunition about
   8,850, fuel about 7,000; then the probe (`prod/probe.sh after 19`): q=ammunition&status=all and q=fuel page 2 under 1.5 s cold.

## Files

Web: `app/(public)/digest.atom/route.ts`, `app/(public)/regulation.atom/route.ts`, `app/(public)/layout.tsx`, `app/not-found.tsx`,
`components/dg/footer.tsx`, `components/dg/alerts-line.tsx`, `app/(public)/methodology/page.tsx`, `app/(public)/about/page.tsx`,
`e2e/wp142.spec.ts`, `lib/wp142.check.ts`. Backend: `dgate/tenders.py`, `dgate/config.py`, `dgate/ops/warm_lists.py`,
`dgate/worker.py` (docstring), `migrations/0142_wp142_search_match_sets.sql`, `tests/integration/test_wp142.py`,
`tests/conftest.py`.

## Open items

- e2e: the demo site and the fake-API site share one build's route cache on disk, so a regenerated page of one can be served by
  the other (5 home-page failures in the batch run, above). A fix is a build directory of its own for the fake-API site, or
  no disk cache for the e2e servers; it is a test-harness change outside this package.
- The trickle race itself (1 of 120 sliced loads after the change) is in Next 15.5 / React 19; production avoids it at the edge.
- A stored set is keyed by the search as typed: another spelling of a listed word runs live (as before).
- Production: deploy, then the ops steps above; re-probe `q=ammunition&status=all` and `q=fuel` page 2.
