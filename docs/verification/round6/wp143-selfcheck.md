# WP-143 self-check: verification round 9 (system, site, data)

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP143.md` (items 1-9) and the coordinator's items 10-12. Branch `wp-wp143` from
`integration` (d3d6132 = production). Test copy `D:\DEFENCEGATE TESTS\wp143\` (own venv, Postgres `dgate-wp143` on 55543, removed
at the end). Production was only read: SELECT/EXPLAIN through psql in the postgres container (30 s statement timeout), the
Postgres and Caddy logs, `ls` of the log volume, and curl from the laptop at least 3 s apart (SQL files in `D:\DEFENCEGATE TESTS\wp143\prod\`). No migration.
No new ops module (item 1 uses the existing `ops.build_digest`).

## 1. URGENT: /digest.atom 502 since 26 Oct 12:56 UTC

**Before.** 3/3 502 after 5.2-6.1 s (r9-system probe-feeds.tsv; 13:14 UTC again 502 in 6.10 s). Postgres: the change statement
`WITH annotated AS MATERIALIZED` (changes.build_events) cancelled at 5 s, in pairs every 4 minutes from 12:36 to 13:32 UTC.

**Cause.** Not WP-142's route change (it only moved `generatedAt`). `digest_issue` was **empty** on production (0 rows): the daily
digest job stored the weeks at 11:00 (success, 20 s), and at 11:44 an organisation entry was added to `suppression` (entry 1,
reason natural_person, decided by `ops.person_rows`: WP-138's person rows), whose `drop_derived` deletes every stored issue.
`ops.suppress` rebuilds the digest after an entry; `ops.person_rows` did not. Nothing stored them again before the next daily run
(11:00 the next day; still 0 rows at 16:00 UTC), so every
request built each of its weeks on the spot (`weekly_digest.build_all`): the feed asks for 4 weeks at once, and a week's build
takes longer than the API's 5 s on production. The feed warmer of the web (`lib/feed-warm.ts`, `/digest.atom` every 4 minutes)
repeated it all afternoon (the pairs in the log). It worked in the morning because the weeks were stored then. The web's last
good copy did not help: the 12:32 deploy started a new build, whose copy store was empty.

**Change.** `ops.person_rows --yes` now rebuilds the digest after it adds or lifts an entry, as `ops.suppress` does. And, for any
other way the weeks go missing: `weekly_digest.missing_weeks`; worker job `digest_gaps` every hour at :05: when a week is missing it stores the
missing weeks (`refresh(recompute_last=0)`, eight a run, as the daily job); when none is missing it is one small query and writes
no job_run row. So a suppression entry costs at most an hour of on-the-spot builds instead of a day. WP-142's ETag rule is
untouched (the route is unchanged).

**Test.** `tests/integration/test_wp143.py::test_missing_digest_weeks_are_stored_again_within_the_hour` (empty table -> stored;
second run: "nothing missing", no job_run row; `suppress.drop_derived` -> stored again); `tests/unit/test_wp143.py::
test_the_digest_gaps_are_scheduled_hourly`.

**Every feed and CSV** (laptop, 26 Oct 13:14 UTC, one each): changes.atom 0.85 s, regulation.atom 0.46 s, calendar.ics 1.07 s,
sitemap.xml 0.30 s, tenders/export.csv 4.93 s (default) and 3.02 s (all): the CSV reads the API's export endpoint by cursor, a
page per statement, so its total is a sum of pages and no single statement is near the limit (it is not the digest's case).
funding.atom/ics/csv and market.csv answered in 0.3-0.5 s in the r9 probe. Only the digest built data per request.

**Ops now (before the deploy, the orchestrator):** store the weeks once, read-write, in a one-off worker container:
`docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps worker python -m dgate.ops.build_digest --yes`
Expected: `{'weeks': 7, 'built': 7, ...}` (2026-W37 .. W43), about a minute; then `/digest.atom` 200 within the web's 60 s cache.

## 2. Busy API after a deploy (105 x 503 at r13)

**Cause** (r9-system deploy503-layers.txt): `web/lib/api.ts http()` retried only a connection that never opened; the API's "busy"
answer (503, Retry-After 2, every one of its 24 connections taken) became an error page.

**Change.** (a) `http()` asks a "busy" answer (503 with Retry-After of at most 2 s) once more after that wait, inside the existing
15 s window; a statement time-out (503, Retry-After 5) is not retried (it would double the load). (b) `infra/warm-after-deploy.sh`:
the deploy's last step (docker-compose.yml deploy order, step 5) asks for the 19 pages and feeds visitors and crawlers open first,
one at a time, and exits 1 on a 5xx. (c) Worker: a scheduled job the start-up catch-up finds missed (requalify_weekly at r13,
started 20 s after the worker) waits `DGATE_CATCH_UP_JOBS_DELAY_SECONDS` (300) after the start; a slot that ran the job during
the wait is not run again.

**Test.** `e2e/wp143-api.spec.ts` (fake API: a notice that answers busy the first time renders 200 after >= 1.9 s and was asked
twice; a statement time-out is not waited for); `tests/unit/test_wp143.py` (the wait, no wait long after the start, a slot that
ran meanwhile).

## 3. Bot flood (09:12-09:32 UTC, 7,447 addresses)

**Change.** `web/gate.cjs`, started by the runtime image (`web/Dockerfile`: `CMD ["node", "gate.cjs"]`, which loads `server.js`):
a global limit on the anonymous page renders the web process works on at once. At most `DG_GATE_ACTIVE` (12) run; the next
`DG_GATE_QUEUE` (24) wait in order up to `DG_GATE_WAIT_MS` (5 s); anything beyond, or a wait past that, is answered at once with
503, `Retry-After: 30`, `no-store` (Caddy passes a 503 as it is; only a 500 is relabelled). Not counted: static files, requests from
the container itself (healthcheck, feed warmer), a request with the session cookie. Sizes in `infra/docker-compose.yml` (web
environment), so the owner can tune them without a build. No outside service. Sizing: 2 cores, API pool 24 connections, a page asks
the API 3-6 times; 12 renders at ~0.5 s are ~24 pages a second against ~4 a second in the busiest normal hour.

**Test.** `lib/wp143.check.ts` (two at once, one waits, the next refused at once with Retry-After 30 and no-store; the waiting one
starts when one ends; a wait past the limit is 503; a client that leaves the queue frees its place; static, loopback and session
not counted).

**Measured** (lab, laptop: `next start` of the local build behind the gate's wrapper, the e2e fake API behind a stand-in that
answers each call after 400 ms with at most 24 at once and a 3 s queue, then "busy", as production's API; open-loop crawler of
new `/tenders?q=` pages plus one visitor opening a tender page every second; scripts and outputs in `D:\DEFENCEGATE TESTS\wp143\lab\`):

| run | crawler pages answered | 2xx and their p50 / p95 | 503 | other errors | visitor |
| --- | --- | --- | --- | --- | --- |
| no gate, 25 pages/s, 60 s | 1,771 | 1,360, 5.13 / 8.65 s | 0 | 411 (500, Caddy makes them 503 after the wait) | 8 loads in 60 s, 6 ok, p95 20.5 s |
| gate 12/24, 25 pages/s, 60 s | 1,345 | 722, 2.98 / 3.14 s | 623 in ~10 ms | 0 | 47 loads, 5 ok (2.8 s), 42 quick 503 |
| no gate, 5 pages/s, 40 s | 197 | 197, 0.89 / 0.91 s | 0 | 0 | 21 of 21 ok, 0.90 s |
| gate 12/24, 5 pages/s, 40 s | 206 | 205, 0.89 / 0.91 s | 0 | 1 | 22 of 22 ok, 0.90 s |

So: at a normal rate the gate costs nothing; in a flood the pages it admits stay at the unloaded time instead of 5-20 s, nothing
waits until the 30 s proxy limit, and the excess costs about 10 ms each. It does **not** tell a visitor from the crawler: in a
flood a visitor is refused as often as the crawler is (quickly, with Retry-After, instead of slowly). Gate sizes 8 and 16 were
measured too (8: 526 ok at 2.9 s; 16: 743 ok at 2.4 s); 12 is between. The lab's API is a fixed delay, production's cost is CPU on
the same 2 cores, so the numbers are relative.

**What Cloudflare proxy mode (the owner's decision) would need from our side.** (1) Real client address: Caddy must take the
address from `CF-Connecting-IP` (or `X-Forwarded-For`) only when the connection comes from Cloudflare's published ranges:
`servers { trusted_proxies static <Cloudflare IPv4/IPv6 ranges> ; client_ip_headers CF-Connecting-IP }` in the global block, so
the API's per-address rate limit, the access log and the visit counter keep seeing visitors, not 15 Cloudflare addresses; the
ranges change rarely but must be refreshed. (2) Origin locked to Cloudflare: the firewall (or Caddy) accepts 80/443 only from those
ranges, else the flood goes around it to the server's address. (3) TLS "Full (strict)": keep Caddy's Let's Encrypt certificate
(or a Cloudflare origin certificate) and set Cloudflare to Full (strict), never Flexible (plain http to us). HSTS stays.
(4) Caching: our pages send their own Cache-Control; Cloudflare must not cache HTML of signed-in users (the session cookie is
`__Host-dg_session`; a cache rule "bypass on cookie"), feeds and CSVs keep their ETag. (5) The bot rule itself: a managed challenge
for clients without a cookie on deep pages (`/tenders/*`, `/organisations*`, `/projects/*`), with verified search bots allowed.
(6) Privacy: Cloudflare (US company) would see every page request; the privacy notice and /data/sovereignty must say so
before it is switched on (the owner's text). DNS is already at Cloudflare (DNS only).

## 4. API statements cut at 5 s (148 vs 0 in round 8)

**Before.** Postgres log, 25 Oct 19:30 - 26 Oct 13:35 UTC, API statements cancelled at 5 s (not the time box), by statement and
hour (read on the server, grep of `docker logs`):

| statement | where | count | when |
| --- | --- | --- | --- |
| `WITH annotated AS MATERIALIZED` | `changes.build_events` | 76 | 12 at 09 (flood, /changes windows), 8 at 11, 26 at 12, 19 at 13: from 11:44 the digest's on-the-spot builds, in pairs every 4 minutes (the web's feed warmer) |
| (multi-line) open counts per buyer family | `tenders._open_sql` (`family_base`) | ~29 | 07-09 (flood) |
| `WITH base AS` | `suppliers.py` aggregation | 22 | 14 at 08 (PerplexityBot on filtered supplier views, before robots.txt `Disallow: /*?` was read) |
| `SELECT DISTINCT v.opportunity_id` | `stats.py` version counts | 7 | 07-09 |
| tender select | `TENDER_SELECT` | 7 | 07-09 |
| `WITH r AS MATERIALIZED`, `SELECT count(*)`, market by month, buyer names `DISTINCT ON`, `WITH mine` | suppliers, stats, market | 13 | 07-09 and the 12:33 deploy |

**Ours, fixed:** the largest family, the digest's builds (item 1): with the weeks stored none runs on a request. **Load, not a
statement to change:** the rest fell in the flood hours (77 at 08-09 UTC) and the 12:33 deploy; `_open_sql` run alone on a quiet
server: 3.46 s cold, 0.92 s warm (EXPLAIN ANALYZE, a seq scan of the open notices with the effective-status function per row); a
variant with an explicit `status = 'open'` on the partial index `opp_open_candidates` was slower (1.6-1.8 s: the cost is the
per-row function, not the scan), so it is unchanged; a failed background renewal keeps the old value (`stats.cached_stale`). The
gate (item 3) bounds how many such renders run at once.

**Change.** Every API connection now carries its route family as application name (`db.APP_NAME`, set per request by
`api._NameConnections`; e.g. `dgate-api /v1/tenders/{id}/versions`), so the next audit's log names the endpoint of each time-out
instead of `app=[unknown]`; the time box keeps `dgate-timebox`. No extra statement (a connection is opened per request; the name
is a connect parameter). **Test.** `tests/unit/test_wp143.py::test_an_api_connection_is_named_by_its_route_family`.

## 5. Access log kept ~13 h

**Before.** `roll_size 50MiB`, `roll_keep 10`: the oldest line 25 Oct 23:29 (r9-system). On disk (`ls` of the volume, 13:21 UTC):
ten rolled files of 2.2-2.5 MB each (Caddy gzips a rolled file), one every 1.2-1.3 h, 68 MB for the whole volume.

**Change.** `infra/caddy/Caddyfile`: `roll_keep 300` for the access log: 14 days x 24 h / 1.3 h = 260 files at today's rate,
about 0.75 GB compressed (1.5 GB at twice the rate; 13 GB free). `roll_keep_for 336h` and logprune (14 days) still remove
anything older. Validated with `caddy validate` in the caddy:2 image. Needs `sh infra/caddy-reload.sh` at the deploy.

## 6. First frequent-word search 2.3-5.5 s

**Before** (r9-system): "fuel" all 3.41 s cold in the API, 5.55 s for the page; drone 4.49 s; ammunition 3.08-4.22 s cold, warm
0.29-0.38 s. The stored set is read in 4 ms (pg_stat_statements); the list statement after it took 4.2 s on average, the scope
counts 1.34-2.58 s cold. The web asks for a searched list with `no-store`, so its own cache plays no part: the page is the API
time plus about a second of render; the API keeps an answer 60 s, so a word asked every few minutes is cold almost every time.

**Change.** `ops/warm_lists.views`: for each frequent search word (`tenders.search_set_words`, 14), the first page (10, the site's
size) and the scope counts, status closed and all, are kept in `list_snapshot` like the plain lists (56 views; the API reads a
snapshot for any non-open view, `_kept_in_snapshot`). Open lists stay live (counts of the same moment). A first load of those
words is then a snapshot read; another spelling, page 2 or a country filter run live as before. Cost: 56 more views in the
4-hourly warm run, about 2-4 minutes of one core. **Stamping:** `refresh_search_sets` no longer stores a set of 0 ids (and
deletes an older one); its live query finds nothing quickly; the report counts them as `search_sets_empty`.

**Test.** `tests/integration/test_wp143.py::test_the_first_page_of_a_frequent_search_word_is_kept_with_the_warm_lists`;
`tests/integration/test_wp142.py` line 39 now expects `written + empty == search_sets` (the empty set is no longer stored, which
is what this item asks). **After:** measurable on production after the deploy and the first warm run (every 4 hours at :50 from 01:50
UTC, or `python -m dgate.ops.warm_lists --yes`).

## 7. Site texts on the mail provider

**Before.** /alerts: sign-in opens "once we have chosen a provider"; /data/sovereignty: "the mail provider will be named in the
privacy notice and here", and no row for it, while privacy 1.7 names Brevo (Sendinblue SAS, France).

**Change.** /alerts: "sign-in is not open yet: it opens soon" (the /signin wording). /data/sovereignty: a row "Account mail"
(Brevo (Sendinblue SAS), France, In the EU: Yes; what it receives; no account mail until sign-in opens), the closing line says
the same, the lead and description name the row. Privacy and terms untouched.

**Test.** `e2e/wp143.spec.ts`.

## 8. Buyer 9421 / 283618: neither opens

**Finding: not a resolver defect; no change.** 283618 is merged into 9421 (`person_review`), and `dgate_live_org` resolves it to
9421, so both answer what 9421 answers. 9421 ("Dyrektor Urzędu Morskiego w Gdyni") holds one defence notice, 40319 (TED
122655-2017, a command and control system bought by the maritime office in 2017): military CPV, `dual_use` true, buyer class
"other", no legal basis. That is in neither the core nor the supply scope, so it is outside the default scope the buyer pages
and counts are of (WP-96); a buyer with no notice in that scope has no page by design (`buyers_with_page`), and the notice's
page names the buyer without a link (`/v1/tenders/40319`: buyerSlug null), so no link leads to the 404. The notice is listed
under "All" (`/v1/tenders?buyer=9421&scope=all`). A page for such buyers is a product decision (its counts would be 0 in the
default scope). Seen in passing: the notice's `scope` field says "supply" (`api.row_scope` has only two values) although the
scope filter does not count it as supply; a later package can give `row_scope` a third value.

## 9. Call 114: the blocked reason

**Change.** `verdict.py` and `lib/fit.ts` (`seap_support.only`): "Only a SEAP may apply to this call: an established one, or one
being established whose application has already been submitted to the Commission." (the rule EDIP-SEAP-APPLICANT already says
so; the document's who-may-apply row too). The badge title is unchanged ("Blocked by: an established SEAP", the rule's title in
the requirements seed and in the recorded API answers of wp102-pairs). `tests/unit/test_wp141.py` and `lib/wp141.check.ts`
expect the new sentence; `web/lib/data/wp93-pairs.json` expected lines recomputed (`python -m tests.wp93_golden derive`: 10 lines,
the 114 reason only; "after: 58/58 checkable correct"); wp102-pairs unchanged.

## 10. A unit price in the version history (coordinator, r9-data)

**Before.** 178210: "Corrected 13 Oct 2026: Estimated value EUR 94.27 added"; 187 of the 318 unit_price rows have such a version.

**Change.** `TIMELINE_SQL` reads the row's `value_kind`; `timeline()` labels a value line of a unit-price notice "Unit price (not
the contract value)". One place: /versions, /changes and the digest read the same lines.

**Test.** `tests/unit/test_wp143.py::test_a_unit_price_is_not_called_the_estimated_value_in_the_history`.

## 11. EDIP 116/117: the stored Ukraine flag stays unknown (no change)

`open_to_ukraine` says whether Ukrainian entities may **take part**; for EDIP, Ukraine takes part in other roles (a SEAP member, a
state that designates a procurement agent), and no sentence of these calls says whether a Ukrainian entity may apply, so the flag
is unknown by rule (`ukraine.decide`, V2-B9/V3-A: no flag stronger than the documents). What the page answers since WP-132/141
is narrower and certain: entities established in Ukraine cannot **receive EDIP funding** (Regulation (EU) 2025/2643, Articles 9(1)
and 2), stated with that evidence under reason `programme_rule`. The two agree; turning the flag into "no" would say more than
the documents. If the owner wants the filter to treat EDIP as closed to Ukraine, it is one line in `ukraine.decide` and the daily
`cascade_flags` job writes it (expected: the EDIP calls with reason programme_rule, 116 and 117 among them).

## 12. Twin gmina names (coordinator, merge review 2)

**Change.** `ops/org_repair._PL_TWIN_GMINAS` + "gmina stezyca" (kartuski and rycki; NIP 589... and 506...).
**Test.** `tests/unit/test_wp143.py::test_stezyca_is_a_twin_gmina_name_and_its_rows_join_only_by_a_number`.

**The full list.** No register of gmina names (TERYT) is in the repository or the database, so the list could not be checked
against a primary source. From the database (26 Oct): 91 "gmina X" names held by live rows with two or more 10-digit NIPs, 52 of
them with NIPs of two different tax-office prefixes (a strong sign of two bodies): biskupiec, bobrowniki, brzeziny, chmielnik,
czarna, czernichow, dabrowa, debno, debowiec, dobra, i miasto nowe skalmierzyce, i miasto rudnik nad sanem, jablonna, jemielno,
klodawa, kolbiel, konopnica, krasne, lagow, lipno, michalowice, moszczenica, nasielsk, obryte, olesno, olszanka, olszyna, opatow,
osieczna, osiek, piaski, pniewy, radkow, radlow, rogowo, rogozno, rybno, rzgow, slawno, slubice, stezyca, szydlowo, tarnowskie
gory, trawniki, tykocin, ujazd, wierzbica, wilkow, wisniowa, wroblew, zakrzew, zorawina. Most are twin names; some are one body
with a mistyped number (tarnowskie gory, tykocin, nasielsk). They are not added without a check: a review package should check
them against TERYT (GUS) and add the twins.

**Generic PSP rows (report only).** Rows whose notices carry only a bare generic buyer name (no town): 13952 and 184800 hold the
same 9 notices "Komenda Powiatowa Państwowej Straży Pożarnej" (titles name at least Głubczyce and Świebodzin), 14912 and 174324
the same 11-12 "Komenda Miejska PSP" (one names Nowy Sącz), 17883 "jednostka wojskowa" 17 notices, 7906 a bare "gminny ośrodek
pomocy społecznej" 1 notice (Komenda Główna Policji/PSP are one national body each and fine). So about 6 rows and about 50
notices, all PL. The notices have no buyer identifier; the town is only in the title or description. Suggested fix (later
package): a bare generic name (`org_repair.ambiguous_name`) never resolves to a row that carries a town, and its notices are
re-attached by the town their title or description names (or kept on one generic row marked "unit not identified"); the pl_atlas
/ pl_ezam same-notice-number rule proves one notice, never one body.

## 13. A buyer withheld as a natural person (owner, 26 October 2026)

**Before.** 159048 (WP-138 `ops.person_rows`: suppression reason natural_person, nobody asked): its notices name the buyer "Name
withheld on request"; `/v1/buyers/159048` 410 "removed on request"; the page "Removed on request".

**Change.** The words "Name not shown: it identifies a private person." (`suppress.PERSON_NAME`, `lib/api.ts PERSON_NOT_SHOWN`)
for a withheld buyer whose organisation row is a natural person (`organisation.individual_reason`, which person_rows sets; read
there because the API role may not read `suppression`): the tender's buyer line and every list built from it (`tenders.to_tender`:
lists, detail, changes, digest, CSV, feeds), `/v1/opportunities` and its version snapshots, the supplier pages' award rows
(`suppliers._award_rows`, `withheld_buyer_name`). The buyer page and its profile endpoint: **410 kept** (the page is gone and not
indexed), with the owner's words as its detail; the site's buyer page reads the detail (`whenRemovedOrPerson`) and shows "Name
not shown" with that sentence, noindex, naming nobody. **A real request** (`ops.suppress add`, which never sets
`individual_reason`) keeps "Name withheld on request" / "removed on request": that path exists and is unchanged. Not changed:
the network pages, where a directory individual was already "Name not shown" (`INDIVIDUAL_NAME`), and stored digest weeks built
before the change keep the old words until rebuilt (the notice of 159048, TED 495013-2020, is in none).

**Test.** `tests/integration/test_wp143.py::test_a_buyer_withheld_as_a_person_is_said_so_and_one_removed_on_request_keeps_its_words`
(tender, list, buyer 410 detail, /v1/opportunities; the request case beside it); `e2e/wp143-api.spec.ts` (the buyer page of each
case against the fake API); `lib/wp143.check.ts` (the same sentence in API and site, shown unchanged by `displayName`).

## Runs

In `D:\DEFENCEGATE TESTS\wp143\` on the final tree (production SQL and EXPLAIN files in `prod\`, lab in `lab\`):

- ruff: clean. Unit: **4081 passed** (`unit.log`).
- Integration (fresh Postgres, item 13 included): **1563 passed** in one run; after the last change (person_rows rebuilds the
  digest) test_wp138, test_wp143 and test_suppression again: 19 passed.
- tsc: clean. Lib checks (`node scripts/run-checks.mjs`): **all green** (wp93 after its expected lines were recomputed; wp141; wp143).
- Build: ok. Playwright (lock held): wp143, wp143-api, wp141, wp102, wp63, digest, wp142, wp36, wp131, wp127-api, wp52b-api,
  wp132-api: **95 passed**, 7 skipped (the mobile skips those specs declare); after item 13: wp143, wp143-api, wp121, wp133, wp111,
  routes, wp63, wp141, wp127-api: 113 passed and the busy test failed 2/2 because a fixed notice id was already in the build's fetch
  cache from the first run (the test, not the code: ids are random now); wp143-api `--repeat-each=3`: **18 passed**.
- `caddy validate` (caddy:2) of `infra/caddy/Caddyfile`: valid.
- `node gate.cjs` with a stub `server.js` (limit 1, no queue): two outside requests at once -> 200 and 503; loopback -> 200.

## Deploy and ops (the orchestrator)

1. Now, before the deploy: `... run --rm --no-deps worker python -m dgate.ops.build_digest --yes` (item 1; expected 7 weeks built).
2. Deploy order as in `infra/docker-compose.yml`: build images (web too: `web/Dockerfile` now starts `gate.cjs`) ->
   `sh infra/caddy-reload.sh` (roll_keep 300) -> migrate (no new migration) -> api worker -> web -> **new step 5:**
   `sh infra/warm-after-deploy.sh`.
3. After the deploy: check `docker logs dgate-web-1 | grep gate:` (a line per minute only when it refused something) and, in the
   Postgres log, that API lines now say `app=dgate-api /v1/...`.

## Open for the owner

- Bot protection that tells a visitor from a crawler needs a front service (item 3: what Cloudflare proxy mode needs from us).
- Item 8: whether a buyer whose only notices are outside the default scope should have a page.
- Item 11: whether "open to Ukraine" should be "no" for EDIP calls (one line), or stay unknown as the documents say.
- Item 12: the 52 gmina names to check against TERYT; the generic PSP rows (about 6 rows, about 50 notices) for a later package.
