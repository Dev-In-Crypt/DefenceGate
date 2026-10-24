# WP-114 self-check: speed, scheduled jobs and health (coverage audit of 24 October 2026)

Branch `wp-wp114` from `integration` (ea00dca). Migrations `0126` (apply) and `0128` (HELD BACK, owner decision).
Evidence: `D:\DEFENCEGATE TESTS\coverage-oct24\api\` and `db\` (problems.csv, pg_stat_top.txt, explain-1.txt,
accesslog-agg.txt) and `site\problems.csv`. Production was read only: short SELECT / EXPLAIN ANALYZE through the postgres
container (each < 6 s, evening of 24 Oct), `curl` from the host, the postgres log. Two read-only timing scripts ran in
the worker container early on (before the rule against tools in production containers reached me); nothing since, and
their two files in the container's /tmp go with the next redeploy (the container user may not delete them).

Production runs `main` e0d73b7 (round 4 and WP-110 not deployed), so "after" figures are the new statements timed on
production data with psql, and the code is proven by the tests.

## 1. /changes.atom and /v1/changes

- Before: amendment candidate scan 655 calls, mean 2.2 s, max 4.9 s, 61 cut by the 5 s timeout in 48 h (postgres log);
  timed now on production: **5.34-5.67 s** for the 14-day scan (313,572 of 423,847 window versions touch a listed field,
  396,751 `remapped` notes to hash), 348 candidates. `build_events` cold 5.3 s / warm 1.6 s.
- Change: `changes.amended_candidates` is the scan; the worker stores its result for the last 15 days in `list_snapshot`
  (`changes-candidates`, first view of `ops/warm_lists`, also in `run_first` at the worker's start). `/changes` reads the
  snapshot and scans only what was observed after it (minus a 1 h overlap for batches still committing). Candidates are a
  pre-filter: `_amendments` re-reads each timeline with its notes, so the answer is the live one. No snapshot, an old one
  (> 8 h) or one that does not reach the window's start: the live scan, as before. The 14-day window and the archive
  weeks (`bounded`, digest) are unchanged (the digest still scans its own week).
- After (production data, psql): scan after the snapshot **1-10 ms** (5 h of versions), new-notice query 0.12-0.18 s,
  collapse of the window 0.11-0.15 s, timelines of 400 notices 0.02-0.16 s: **~0.3-0.5 s of SQL for a cold window**
  (target < 2.5 s cold, < 1 s warm; warm is the 5-minute in-process cache, 25-90 ms).
- `/changes.atom?page=999`: 404 "at most N pages" (was 502); an API 422 is a 422, not a 502.
- Tests: `test_wp114.py::test_the_change_window_reads_the_snapshot_and_what_came_after_it`,
  `::test_the_worker_writes_the_candidates_first`; e2e `wp114.spec.ts` (page 999). `test_wp98c.py` first-views count 7 -> 8.

## 2. /v1/tenders/calendar

- Before: 503 cold with defaults (5.4 s under load), wide range always 503. Production now: SQL of the calendar is fast
  (count 26 ms, rows 57 ms, wide range 69 ms: EXPLAIN ANALYZE); the cost was `_buyer_names` for every buyer of the open
  set: **0.76-0.85 s** of the 1.2-1.4 s quiet-time total (459 buyers, all their notices counted).
- Change: only buyers whose notice states no usable name of its own are looked up (the name is read only then).
- After: the calendar's SQL is the two queries above plus twin extras; expected ~0.2-0.4 s cold. The 3,000-item bound
  stays (`maxItems`). Not precomputed: at this cost a snapshot (8 h behind the deadlines) is not needed.
- Test: covered by the existing calendar suite (names unchanged; `test_wp52`, `test_wp96` calendar tests green).

## 3. Tender page winners query

- Before: 7,346 calls x 335 ms; plan = Seq Scan on award (explain-1.txt). Production EXPLAIN ANALYZE now, three largest
  suppliers: **121-220 ms**, Seq Scan on award (47,460 rows).
- Change: `award_set.OF_ORGS`: the award rows of the ids and of rows merged into them first (`award_organisation`,
  `organisation_merged_into`), then the set's conditions; used at both call sites (tender page, award summaries).
- After: **20.6-23.4 ms**, no Seq Scan on award. Test: `test_wp114.py::test_the_winners_query_starts_from_the_organisations...`
  (same answer as the old form, merged rows included).

## 4. Statements cut at 5 s

- Finding: of 401 cancellations in the log (48 h), 224 + 24 + 10 are the tender list's **time-boxed counts**
  (`_count_up_to`, 1.2 s budget by design, 0.6 s for `_few`), not the 5 s role timeout: the default Open list count
  (170 of them: open, relevant scope, no filter) takes **0.06-0.10 s** quiet (timed now) and is cut only at the load
  peaks (11 UTC 135, 16-17 UTC 158 on 24 Oct), when the list says "at least" honestly. 61 were the change scan (item 1),
  19 the buyer/supplier `WITH base` aggregate, 13 `_buyer_names` (item 2).
- Change: none to the counts (already bounded and honest); the load behind the peaks is items 1, 3 and 9.
- Open: `_buyer_names` (29,984 calls, mean 42 ms, max 4.8 s) is shared by every list; a covering partial index on
  `opportunity (buyer_org_id, buyer_name_raw) WHERE is_defence AND NOT suppressed AND NOT buyer_withheld` would make it
  index-only; not added (no measurement possible without building it on production).

## 5. Worker: catch-up and job history

- Before: catch-up covered ingest jobs and backups only; ted_awards, digest, warm_lists ... skipped after a restart; job
  history only in the container log.
- Change: migration 0126 `job_run`; `worker.run_job` (and `job_controls`) record start and end; a starting worker closes
  its own running rows as `interrupted`; `worker.catch_up_jobs` runs every other scheduled job whose last slot passed
  since it last started, oldest slot first (twins, families, digest keep their order), from the scheduler's own
  triggers. A job with no record yet runs if it is daily or more often; a weekly/monthly one waits for its slot (a
  restart must not start a CORDIS or EDF crawl). `/v1/health` `jobs`: last start, end and status per job (no detail).
- Tests: `test_wp114.py::test_a_job_run_is_recorded...`, `::test_the_catch_up_runs_every_job_whose_slot_passed...`
  (24 Oct 15:53 restart: link_twins and ted_awards run, digest not, cordis not, ted_daily left to the ingest catch-up);
  unit `test_wp114.py::test_the_last_slot_of_a_daily_four_hourly_and_monthly_trigger`.
- `DGATE_JOB_RUNS=0` in `tests/conftest.py` (unit tests have no database), like the other test defaults there.

## 6. Health and /data

- pl_ezam 403: the re-read loop now notes `source refused access (HTTP 403)` when its failures in a row are 401/403/451
  (`pipeline.run_ezamowienia`); `funding.run_reason` kind `refused` (before "below minimum"), sentence with "Refused since
  <first run of the row>"; `/v1/sources` `statusReasonSince`; `/v1/health` marks the source unhealthy (`refused_since`).
  The day searches (`sources/ezamowienia.fetch_window`) swallow their errors into the unread days and were not touched
  (source module).
- Stale earlier than 72 h: a daily source whose every run of the last 24 h fetched nothing (with a minimum) is `stale`
  at once; two such runs in a row make it unhealthy on `/v1/health`.
- Checks in alert: `control_check.alert_since` (0126; kept by `ops/controls._save`); `/v1/sources` `alerts` (fixed
  sentences), `/v1/health` `alerting_controls` and status `degraded`; `/data` shows "Data checks in alert" with since when.
- Interrupted runs: `run_reason` kind `interrupted` ("cut off by a restart ... run again when the service starts"); the
  ingest catch-up already re-runs them (last success older than the slot), and the job catch-up now does so for the rest.
- edf_factsheets partial since 17 Oct: run 333 "1 factsheets could not be read" (283 of 284 read, detail
  files_failed 1). Which file and why is lost: it was only in the container log, which the 24 Oct recreation erased.
  Now the run keeps `failed_files` (name, error type, message) in `ingest_run.detail`. The file is retried by the next
  monthly run (6 Nov, it is not in the known hashes) or by `python -m dgate.worker --once edf` (an external crawl: the
  orchestrator's call).
- Tests: `test_wp114.py::test_a_source_that_refuses_access...`, `::test_a_check_in_alert...`,
  `::test_a_run_cut_off_by_a_restart_is_interrupted`; unit `::test_a_refused_source_and_an_interrupted_run...`;
  e2e `wp114.spec.ts` (/data alert).

## 7. ETag / 304, sitemap

- JSON API: `hardening.ETag` (pure ASGI, inside SecurityHeaders): every 200 GET under /v1 (not /v1/account,
  /v1/internal) gets a body-hash ETag; a matching If-None-Match is a 304 with no body. Unit test
  `test_the_json_api_answers_a_conditional_request_with_304`.
- Web: `lib/etag.ts withEtag` on calendar.ics, funding.ics, the four CSVs, the sitemap index and files (lib check
  `wp114.check.ts`, e2e).
- Sitemap: `/sitemap.xml` is an index of `/sitemaps/pages.xml` (the old content without tenders), `/sitemaps/suppliers.xml`
  (`GET /v1/suppliers/slugs`: 8,308 suppliers, the slug their page answers under, 0.34-0.40 s) and
  `/sitemaps/tenders-<n>.xml` (`GET /v1/tenders/sitemap?page=n`: the core notices, every status, of id range
  [n*50,000, (n+1)*50,000): <= 50,000 URLs a file, a primary-key range, 1-83 ms per page on production; 8 pages for
  max id 397,653). Only core tenders: a supply notice's page is `noindex`. `app/sitemap.ts` removed; three e2e specs that
  read `/sitemap.xml` for page URLs now read `/sitemaps/pages.xml`.

## 8. Small

- `/v1/tenders`, `/scope-counts`, `/export`: unknown parameter 422 (`known_params`), country must be two letters, `cpv`
  digits (`cpv_prefixes`, as `notCpv`): `test_the_tender_list_refuses_what_it_cannot_read`. The site sends only known keys.
- CSV exports refuse an unknown parameter with 422, as the Atom feeds (one behaviour): e2e.
- versionCount vs /versions: new `correctionCount`; versionCount + correctionCount = entries of /versions (test).
- "at least 11,560" for scope=all: warm_lists now also stores the first page of status closed/all with scope `all`, so the
  exact total is repeated on every page of it (`_snapshot_total`).
- raw_ingest (source_id, native_id): index `raw_source_native` in 0126 (orchestrator: CONCURRENTLY first, statement in
  the file) and `ANALYZE raw_ingest`. Before: 9.5-13.3 s a lookup (pg_stat). After: an index lookup (not measurable before
  the index exists).
- Unused indexes (pg_stat_user_indexes, idx_scan 0, > 5 MB): raw_plain_key 451 MB is **used** by `ops/compact_raw.py`
  (kept, documented); alias_norm_trgm 56 MB, opp_search 38 MB, opp_core_published 5.9 MB have no reader: dropped by the
  HELD-BACK `0128_wp114_drop_unread_indexes.sql` (evidence in the file; listed in docs/DELETION_CANDIDATES.md).

## 9. Memory (compose, no host change)

`infra/docker-compose.yml`: postgres `max_parallel_workers_per_gather=1`, `max_parallel_workers=2`, `jit=off`
(reasoning in the file: 2 cores, 256 MB shm, 11 DSM errors and 340 aborted workers; JIT compiled 22 functions per call of
0.1-2 s queries); work_mem stays 16 MB (reasoned). Web: `mem_limit 768m` and `NODE_OPTIONS=--max-old-space-size=448`
(the 17:54 OOM kill; host budget in the file). Applying needs `docker compose up -d postgres web` (a Postgres restart:
seconds of downtime, the orchestrator's call).

## Site items (coordinator, 24 Oct)

- 429 to the site's own renders: the API already charges a forwarded visitor (x-dg-client-ip from a private peer, with
  the shared secret) to the visitor; such a visitor now has buckets 4x a direct client's (`FORWARDED_FACTOR`): an office
  behind one address browsing filtered company lists (7-9 tokens a view) is not refused. Unit tests (both buckets);
  `test_hardening.py` passes its small buckets for both kinds.
- Web memory: item 9. Feed 502s: item 1. Supplier pages in the sitemap and one parameter rule: items 7 and 8.

## Files outside the package's list

`dgate/award_set.py` (OF_ORGS), `dgate/suppliers.py` (slugs endpoint, import), `dgate/funding.py` (run reasons, alerts),
`dgate/db.py` (refused/interrupted texts), `dgate/pipeline.py` (403 note in the pl_ezam re-read), `dgate/networks.py`
(failed EDF files kept), `dgate/ops/controls.py` (alert_since), `dgate/hardening.py` (ETag, forwarded budget),
`dgate/config.py` (job_runs), `tests/conftest.py`, `tests/unit/test_hardening.py`, `tests/integration/test_wp98c.py`,
web: `lib/api.ts`, `lib/types.ts`, `lib/export.ts`, `lib/filters.ts`, `lib/mock/sources.ts`, `app/(public)/data/page.tsx`,
the feed/CSV/ics routes, `e2e/networks|wp68|wp86.spec.ts` (sitemap file), `docs/DELETION_CANDIDATES.md`.

## Runs

Backend (local copy, Postgres 17 on 55514): ruff clean, unit 3834 passed, integration 1395 passed (16 min).
Web: tsc clean, 63 lib checks ok (wp114 included), next build ok, Playwright 845 passed / 65 skipped (first run; final
run below).

## Ops for the orchestrator (production)

1. Before deploying 0126: `CREATE INDEX CONCURRENTLY IF NOT EXISTS raw_source_native ON raw_ingest (source_id, native_id);`
   (minutes, no write lock). Do NOT deploy `0128` until the owner approves it.
2. After the deploy the worker's start writes `changes-candidates` (run_first) and the job catch-up runs the daily jobs
   skipped since their last slot (no record yet: all daily ones run once, in slot order: expect warm_lists, twins,
   families, digest, ted_awards, cascade flags, controls, health report, eu_topics at that start).
3. `docker compose up -d postgres web` for the new settings (item 9) at a quiet hour.
4. Optional: `python -m dgate.worker --once edf` to retry the unread factsheet now rather than on 6 Nov.
