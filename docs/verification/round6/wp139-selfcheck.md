# WP-139 self-check: site and system findings of verification round 8

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP139.md`; evidence `D:\DEFENCEGATE TESTS\verify-oct25\r8-site\` and
`r8-system\`. Branch `wp-wp139` from `integration` (6395099). No migration, no ops module. Production was only read: SELECTs
through psql in the postgres container (30 s statement timeout) and curl from the laptop, at least 3 s apart (probe scripts
and outputs in `D:\DEFENCEGATE TESTS\wp139\prod\`).

## Site

1. **Tab titles cut on a word that leads into the next** ("Suministro de repuestos consumibles para…", "Commissariat a L
   Energie Atomique et Aux…", r8-site meta.txt). Change: `trimAtWord` (lib/seo-trim.ts, the one cut every title and
   description goes through) drops trailing articles, prepositions, conjunctions and lone letters of the notices' languages
   before the ellipsis. After: "Suministro de repuestos consumibles…", "Commissariat a L Energie Atomique…". Test:
   lib/wp139.check.ts (section 1); wp56, wp59, wp130 checks unchanged and green. Not changed: the 46-character limit
   (60 with " · DefenceGate", WP-56). The auditor's "up to 60 characters before the site name" would keep "related to
   aircraft" in the Bulgarian title; it is a change of the title rule of WP-56/WP-130 and is left for a decision.
2. **"1 defence-relevant contracts"** (supplier description). Change: `plural()` and `formatNumber()` in
   app/(public)/suppliers/[slug]/page.tsx. Test: wp139.check.ts (section 2).
3. **Funding call 114: "Who may apply: Check" over a blocking line "Not allowed. an established SEAP."** Not changed: it is
   the funding eligibility verdict (web/lib/fit.ts `callFit` / `applicantFit` / `verdictLines`), WP-137's area. Reported to
   WP-137 by message. Cause: with a saved profile, `applicantFit`'s blocker goes into `blockedBy` while the document's
   `entity` line stays (the no-profile path `answersFit` replaces it since WP-121); `verdictLines` writes the blocker as
   `${rule(b)}.`, hence the lower-case fragment. Wanted: one line, "Who may apply: No. Only an established SEAP may apply."
4. **Tenders list header "Latest run of its sources: 17:39 (e-Zamówienia)"** while the home page said 06:57. Cause: the API's
   `stats.last_run` took the newest success/partial run, a refused source's run of 0 records included. Change: it takes the
   newest run that brought data (`records_fetched > 0`), the home page's and the footer's rule (WP-131 `lastDataUpdate`). The
   funding list reads the same function. Test: tests/integration/test_wp139.py::test_a_run_that_read_nothing_is_not_the_lists_latest_run;
   the WP-87 test in test_tenders_read_side.py unchanged and green.
5. **Phone menu: "Check my company" a dark link among grey group headings.** Change (components/dg/header-bar.tsx): every
   group of the phone menu is a heading of one kind, its pages links under it, the group's own page among them. Test:
   e2e/wp139.spec.ts (headings of one colour and weight, the /check link under its heading, hover and focus of its links);
   wp117, wp86, wp58, wp121, ux specs green.
6. **/regulation description 55 characters** (the trim kept the part before the bracket). Change: a description of 158
   characters that names SAFE, EDIP, the Ukraine Support Instrument, the EDF and directive 2009/81. Test: wp139.check.ts
   (section 4), e2e/wp139.spec.ts.

## System

1. **robots.txt.** Before: no rule for filtered lists; 99 of 111 fast 503s of 25 Oct were ClaudeBot on `/suppliers?...`.
   Change (app/robots.ts): `Disallow: /*?` (every address with a query string: each such view is noindex, canonicalises to its
   plain page, and the sitemap lists none), `Allow: /` and `Allow: /_next/` (the scripts and images a rendering crawler needs;
   the longer rule wins). Plain list pages and detail pages stay open. Test: e2e/wp139.spec.ts, wp139.check.ts (section 3).
2. **Sitemap parts over 2 MB.** Before: tenders-1/-2 were 3.0 and 3.1 MB of JSON (23,000 and 20,500 notices in 50,000 ids), not
   kept by the site's fetch cache, rebuilt on every request (1.80 and 1.88 s). Change: `SITEMAP_ID_SPAN` 50,000 -> 12,500
   (backend/dgate/tenders.py). Worst case, every id of a range a core notice with a 9-digit id and the longest slug: 1.5 MB,
   under the 2 MB limit; 50,000 URLs a file and 50,000 files an index stay far off (about 32 files now). Test:
   tests/unit/test_wp139.py::test_a_full_sitemap_page_fits_the_sites_fetch_cache; test_wp114 sitemap test green. After: each
   part is kept an hour; expected under 0.5 s cold, cached afterwards (not measurable before a deploy).
3. **Ingest floors.** Measured on production (read-only):
   - `ted_awards`: runs 348, 349, 447, 484, 488; 488 (25 Oct 14:10) fetched 0 with expected_min 0, "success". Core result
     notices per TED publication day 7 Sep - 23 Oct: 5 to 27, Monday to Friday. Floor (config `_TED_AWARDS_FLOORS`, env
     `DGATE_FLOOR_TED_AWARDS`): 0 on Sunday and Monday, 2 Tuesday to Saturday, for the whole UTC day: `run_awards` sets
     `expected_min = max(notices asked, day floor - what the day's earlier runs read, 0)`, so the second run after a
     catch-up is not short.
   - `eu_portal` second daily run (`run_topic_details`, runs 409, 428, 449, 485 and 14 earlier): expected_min was NULL;
     1 to 150 pages a run, every page asked was read. Floor: half the pages asked, at least one (`eu_topics_floor_share`).
   Tests: tests/unit/test_wp139.py (the table, the env override), tests/integration/test_wp139.py (a day with nothing read is
   `partial`, its second run is not; the topic run records its floor and is `partial` when 3 of 4 pages fail).
   Note: `ted_awards` is now in the weekday-floor table, so `/v1/health` and the daily health report read it as a daily
   source (it runs daily at 14:10).
4. **A deploy killed the weekly re-check.** Before: job_run 28 `requalify_weekly` started Sun 12:00, `interrupted` at 13:24
   (1 h 24 min) by the deploy; the catch-up counted its 12:00 start as the slot's run, so the next was 1 Nov. Done before the
   cut (backfill_day markers of fingerprint f705fe2225): fr_boamp, nl_tenderned, de_bkms, pl_ezam, es_placsp (29 days each,
   12:00-13:21); left: es_placsp_agg, pl_atlas, ted. Change (backend/dgate/worker.py): `last_job_start` returns the last start
   that was not interrupted and the last that was; `catch_up_jobs` runs a job whose slot passed with no complete start since,
   an interrupted weekly or monthly one included; `close_interrupted_runs` notifies which jobs a restart cut short. The job
   is resumable (days done under the current rules fingerprint are skipped). Test:
   tests/integration/test_wp139.py::test_a_weekly_job_a_restart_cut_short_is_run_again_and_the_restart_says_so; the WP-114
   catch-up tests green.
   **Missed run, once.** Preferred: nothing to start. The first worker start with this branch runs it from its catch-up
   (job_run 28 is `interrupted` and the Sunday 12:00 slot has no complete start since), inside the worker, no second
   container. Without that deploy, the ops runner (not on a Sunday 12:00-15:00; one more 2 GB container beside the worker on a
   3.8 GB host without swap: check `free -m` first, nothing else heavy running):
   `cd /opt/dgate/infra && docker compose run --rm --no-deps worker python -m dgate.worker --once requalify`.
   Expected: about 1 to 2 hours if the rules fingerprint is still f705fe2225 (the five sources above skipped: 145 days marked;
   es_placsp_agg, pl_atlas and TED read, 30 days each), up to about 3 hours if a deploy since moved the fingerprint (every
   day read again; the five sources took 81 min on 25 Oct). Ends with `requalify_weekly: success ... <source> inserted/
   candidates`; exit 1 only if stored payloads could not be read. Note: the catch-up runs its jobs one after another, oldest
   slot first, beside the scheduler; a catch-up that includes the re-check holds any job due after it in that same catch-up
   for its 1-3 hours (the scheduled slots are not held).
5. **Buyer pages.** Probe from the laptop, 25 Oct 18:40 UTC (cold): `/v1/buyers/{slug}/profile` 6.88 s for
   6968-3-regionalna-baza-logistyczna, 1.77 s for 129783; the buyer's three tender lists 0.6-1.2 s each, `/suppliers`
   0.8-0.9 s. Cause (EXPLAIN on production): every statement of `stats.buyer_profile` (a dozen) repeated the buyer's scope
   with the collapse rules, 0.2-0.5 s to find the set each time; the amendment share was 3.3 s for the Czech ministry (268).
   Change: the notices are found once (`SELECT o.id ... WHERE scope AND collapse rules`), each figure counts over
   `o.id = ANY(ids)`. `tenders.collapse_clauses` itself is unchanged (WP-138's).
   Before / after on production (psql, read-only; the six main statements; after = the id set plus the six over it):

   | buyer | notices | before | after |
   |---|---|---|---|
   | 6968 (3 RBLog) | 4,780 | 1.64 s | 1.23 s |
   | 11870 (2 WOG) | 3,566 | 4.45 s | 0.52 s |
   | 268 (Czech MoD) | 8,694 | 4.86 s | 0.76 s |

   The remaining statements of the profile (the dated counts, the response window, the amendment total) read the same id
   list. Test: tests/integration/test_wp139.py::test_the_buyer_profile_reads_the_buyers_notices_once_with_the_same_figures
   (one statement reads the family; the WP-135 7310-shaped buyer's figures); test_wp135, test_wp96, test_stats green.
   **Word search, not changed** (tenders.py is WP-138's this round): `q=ammunition&status=all` 3.97 s cold, `q=fuel` page 2
   3.60 s (probe 18:40). EXPLAIN of the one read of the matches (`search_ids`): ammunition 5.0 s, fuel 2.1 s, both over
   `SEARCH_IDS_MAX` (5,000 matches): the trigram bitmap scans of the regular expressions alone are 2.0 s (ammunition) and
   0.9 s (fuel). Switching on `DGATE_SEARCH_IDS_MS` (WP-120's open item) would not help these words. What would: a stored
   match set per frequent word (renewed by the worker), or counting only the first page's worth cold. Open.

## CI items (added by the coordinator, round-11 GitHub runs of d2cb603)

1. **wp52b-api.spec.ts:134 (T16/T18/T11)** failed with "Test timeout of 60000ms exceeded" (run 40223247552): its own
   `expect.poll` waits up to 150 s for /data's 60 s refresh under the default 60 s test timeout. Change:
   `test.setTimeout(210_000)` in that test (the poll plus the checks after it); the assertions unchanged. Local: 12 passed.
2. **Web gated, wp122 on the billing-open build** (run 40223247542, 6 failed, desktop and mobile): the build had
   `NEXT_PUBLIC_BILLING_OPEN=1`, but the server that answered was the billing-closed one of the wp123 step. Its log:
   `next-billing.log: Error: listen EADDRINUSE: address already in use 127.0.0.1:3102`; at the end of the job GitHub killed two
   orphans `next-server (v15.5.27)`. `next start` hands the port to a child titled `next-server`, which
   `pkill -f 'next start'` does not match. Change (.github/workflows/web-gated.yml): `pkill -f 'next-server'` as well, a wait
   until 3102 and 3444 no longer answer, the billing-open server on a port of its own (3103, behind the same https proxy on
   3444 that the API's site URL names), and a check that fails the step at once unless /pricing carries a plan's button
   (`href="/signup?plan=pro&amp;billing=monthly"`). The specs unchanged. Local check of the same build: the guard matches,
   wp122 14 passed, 2 skipped (the billing-off tests).

## Overlaps

- backend/dgate/tenders.py: only the `SITEMAP_ID_SPAN` constant and its comment (WP-138 works in the same file: collapse
  rules, values, merges).
- backend/dgate/stats.py `buyer_profile`: calls `collapse_clauses` once instead of in every statement; the clauses unchanged.
- web/lib/fit.ts (WP-137): not touched; item 3 of the site reported to WP-137.

## Runs (test copy D:\DEFENCEGATE TESTS\wp139)

- ruff clean; unit suite 0 (31 s); integration suite 0 (829 s); tsc 0; lib checks 0 (wp139 included).
- Build 0; Playwright wp139, wp117, wp86, wp58, wp121, ux: 137 passed, 13 skipped (width-specific), 0 failed;
  wp52b-api 12 passed; wp122 on a billing-open build 14 passed, 2 skipped.
