# WP-127 self-check: slow search page, 502s during deploys

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP127.md`; evidence `D:\DEFENCEGATE TESTS\verify-oct25\ops-r8\`.
Branch `wp-wp127` from `integration`. No migration, no ops module, no production access (the "before" numbers are the ops
runner's curls of 25 October 2026; the "after" numbers are local, nothing is deployed).

## 1. `/tenders?q=ammunition` 1.7-2.0 s warm

- Before (`05-search-probe.tsv`, warm, from the laptop): page 1.67-1.71 s TTFB / 1.91-1.96 s total; list API 0.32-0.34 s;
  `/v1/sources` 0.34 s; `/v1/tenders/scope-counts?q=ammunition` **503 after 1.52-1.55 s on every request**.
  `05-timings.tsv`: `/tenders?q=ammunition` cold 2.51 / 2.76 s, warm 1.76 / 2.01 s.
- Cause: (a) `tender_scope_counts` raises 503 when the `relevant` count finds nothing within `COUNT_BUDGET_MS` (1.2 s);
  `cache_list` never keeps a failure (`stats.cached`), so every request spent the time box again. (b) The page awaited
  list, sources and counts together (`Promise.all`), so the slowest, the failing count, set the page time.
- Change, API (`backend/dgate/tenders.py`): a "took too long" is kept `UNAVAILABLE_SECONDS` (5 min) per query in the list
  store (`stats._list_cache`, bounded by `LIST_CACHED`); within that time the endpoint answers the same 503 at once, without
  a count. Not with the cache off (`DGATE_LIST_CACHE_SECONDS=0`, the test suite) and not in the worker's exact snapshots.
  The 503 contract stays (the site already shows the scope labels without numbers on it; `test_wp52` asserts it).
- Change, site (`web/app/(public)/tenders/(list)/page.tsx`, `web/lib/list-count.ts`): the counts are started with the list
  but awaited only `SCOPE_COUNTS_GRACE_MS` (250 ms) past it (`within`); later or failed counts are left out (labels without
  numbers) and the API keeps the answer when it comes, so the next view has them. Suspense streaming was not used: Caddy
  buffers each page whole (`response_buffers 1MiB`, WP-63, hydration errors), so a streamed boundary would not move the
  first byte.
- Other list pages: funding (`getCalls` + `getHealth`, the latter a shared cached call), buyers (one call), suppliers
  (`getSuppliers` + cached `getSupplierSummary`), search (one call): no slow secondary call in the critical path; unchanged.
- Tests: `tests/integration/test_wp127.py` (a timed-out count is not run again for the same query, another query is, an
  expired mark is counted again; with the cache off nothing is kept); `web/lib/wp127.check.ts` (`within`: in-time value
  kept, a 3 s answer cut at the bound, a failure is null); `web/e2e/wp127-api.spec.ts` with the fake API answering the
  scope counts of `q=slowcounts` after 5 s.
- After (local, `next start` of the build against `e2e/support/fake-api.mjs`): `/tenders?q=fastcounts` 425 ms with numbers;
  `/tenders?q=slowcounts` 666 / 663 ms (counts take 5 s) without numbers; the spec asserts < 3 s and passes on both
  projects. Expected on production: the warm page at about the list call (0.3 s) plus render (0.25-0.3 s, as `/tenders`
  0.55 s warm), i.e. under 1 s; cold bounded by the list (2.1 s cold in `05-timings.tsv`), under 3 s.

## 2. 502 x39 and 503 x2 during the 25 Oct 13:24 deploy

- Before: one container per service; while one is replaced its name does not resolve / its port refuses, and Caddy answered
  502 at once. Local reproduction (`D:\DEFENCEGATE TESTS\wp127\restart-test.sh before`: caddy:2 in front of a stand-in
  upstream removed for 6 s, a request every 0.1 s): 82 x 200, **3 x 502**.
- Change, `infra/Caddyfile`: both `reverse_proxy` blocks (`api-edge:8000`, `web:3000`) get `lb_try_duration 30s` and
  `lb_try_interval 250ms`: a failed dial is tried again for up to 30 s (any method; a request that reached the upstream is
  only retried per Caddy's default, GET). Passive/active health checks were not added: with one upstream they only add a
  window in which a healthy container is still treated as down; the dial retry covers the gap.
- Change, `infra/docker-compose.yml`: api and web healthchecks get `start_period: 60s`, `start_interval: 2s`, so
  `up --wait` returns within seconds of the container being ready; the deploy order (build first, `up --no-build --wait api
  worker`, then `--profile web up --no-build --no-deps --wait web`, `caddy reload` for a changed Caddyfile) is written at
  the top of the compose file.
- Change, `web/lib/api.ts` `http()`: a request whose connection never opens (undici `TypeError: fetch failed`, the API
  container being replaced) is tried again every 500 ms for up to 15 s instead of failing the render (a 500, which Caddy
  turns into 503: the likely source of the 2 x 503). A timeout or any answer is not retried.
- Tests: `tests/unit/test_wp127.py` (both upstreams carry the hold; api/web healthchecks probe while starting; the deploy
  order is in the file). `caddy validate` of `infra/Caddyfile` (caddy:2, local): Valid configuration. `docker compose config`
  with the example env: valid, `start_interval: 2s` kept.
- After: `restart-test.sh after`: 79 x 200, **0 x 502**, the slowest request 9.8 s (held through the 6 s gap). Fake API
  stopped for 3 s while `/tenders?q=deploygap` was requested: 200 after 3.98 s with the list shown (before: the page fails).

## Test runs (batched scope)

- ruff: clean. Unit: full suite green. Integration (Postgres 17, port 55527, container removed): `test_wp127`, `test_wp52`,
  `test_warm_lists`, `test_tenders_api`, `test_list_cache_and_scope`, `test_wp34`, `test_wp49`, `test_wp90`, `test_wp98`,
  `test_wp114`, `test_wp120`: 151 passed.
- Web: `tsc --noEmit` 0; `run-checks` 0 (wp127 ok); `next build` 0; Playwright (lock held) `e2e/wp52b.spec.ts` (mock) green;
  with the fake API `e2e/wp127-api.spec.ts` green on desktop and mobile-375.
- `e2e/wp52b-api.spec.ts` (fake API; its fake gained the delayed route): T3, T13, T16-T18 pass; T9 (calendar month 323,802 B
  against < 300,000), T10 feed (400 entries: the feed is paged at `FEED_MAX = 400` since WP-100) and T10 digest (the week is
  now an `<option>`, not visible text) fail. These read pages WP-127 does not touch and assert behaviour changed by earlier
  packages; the spec is skipped in normal runs (needs `E2E_FAKE_API`). Not changed here; listed as an open item.

## Open items

- Deploy needs a Caddy reload (`docker exec dgate-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile`)
  for the hold to take effect; then measure the next deploy with the ops runner's curl loop.
- The worker does not warm open-list scope counts for frequent words (WP-52: the open view is read live so that counts and
  list are of one moment); the 5-minute "unavailable" mark and the page bound make that unnecessary for speed. The counts of
  `q=ammunition` on the open list stay unavailable (no numbers beside the scope choices) until the count itself is faster.
- `e2e/wp52b-api.spec.ts` T9/T10 are out of date with WP-100 and later (see above).
