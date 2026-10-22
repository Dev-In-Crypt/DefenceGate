# WP-75 self-check: a fast supplier map with the PLACSP winners switched on

Branch `wp-wp75` (from `integration` 9db8daf = production). Builder's own check; an independent verifier checks
again. Tests ran locally in `D:\DEFENCEGATE TESTS\wp75` (own venv by uv, throwaway Postgres 17 container
`dgate-wp75`, port 55475). Production was only read: `SELECT`s and `EXPLAIN ANALYZE` with `statement_timeout`
30 s; the stored pairs were simulated by a session `TEMP` table (`award_twin_mat`, dropped with the session;
nothing persistent was created or written on production).

## Where the time went (production, 22 October 2026)

`EXPLAIN ANALYZE SELECT count(*) FROM award_twin`: **5.0 s plain, 10.0 s instrumented**, for 1,105 pairs. The view
self-joins the 45,124 current awards on the procedure identifier (212,722 candidate pairs, procedures with many
lots and winners) and joins the twin link with an `OR` (`t.opportunity_id = r.id OR t.procedure_identifier =
r.procedure_identifier`), which the planner can only run as a nested loop: 38 million rows filtered, 8.3 s of
the 10. With the switch on, **every** statement of the map reads the view (`NOT_TWIN` in `scope()`): the list
runs two, the summary five, a profile nine and the profile's provenance one more. Each statement alone took
5.5 to 7.6 s, over the API's 5 s budget. With the pairs precomputed, the rest of each statement is 0.15 to 0.35 s
(the per-award lookup of the notice's scope: 44,063 awards, 13,483 in scope).

## Design

| Piece | What | Why |
|---|---|---|
| `migrations/0098_award_twin_set.sql` | table `award_twin_set (award_id, preferred_id, procedure_method, winner_method)`, PK (award_id, preferred_id), index on preferred_id; filled from the view in the migration; `SELECT` to `dgate_api`, `SELECT, INSERT, DELETE` to `dgate_worker` | the twin pairs stored. A table, not a materialised view: `REFRESH MATERIALIZED VIEW` needs the owner role, which the worker is not; the pattern of `organisation_network` (0068) |
| `awards.refresh_award_twins(conn)` | `LOCK ... IN EXCLUSIVE MODE` (readers pass, a second refresh waits), `DELETE`, `INSERT ... SELECT FROM award_twin`, in the caller's transaction | a reader sees the old pairs or the new ones; two refreshes cannot collide on the PK |
| refresh points | `awards.run_awards` (TED winners), `pipeline._ingest_placsp` when an award loader read payloads (nightly walk, archive loader; not for land-only walks), `placsp_awards.replay_from_store`, worker `job_link_twins` (daily 09:15, after the ingests), worker `job_warm_lists` (four-hourly; covers organisation merges and anything else) | "after award loads and nightly" |
| `ops/supplier_twins --refresh [--yes]` | dry run: stored, view, differing pairs; `--yes` rewrites | a scripted refresh for a load run by hand |
| `suppliers.NOT_TWIN` and the profile's provenance | read `award_twin_set`; the preferred row is still checked live under the full scope (suppression, natural persons, superseded) and the provenance row must be current, as in the view | semantics unchanged except the pairing's age (below) |
| `/v1/suppliers/summary` | one statement with `GROUPING SETS ((), division, country, (division, country))` instead of five scans; the groups count rows with a CPV only (`FILTER`), as the five statements' `WHERE a.cpv_main IS NOT NULL` did | 1.5 s of five scans became 0.33 s |
| profile (`get_supplier`) | `a.organisation_id = ANY(ARRAY(org, ids merged into it))` added to `org.id = org` (a redundant, index-usable predicate) | each of the nine statements read every award (0.1 s); now 20 ms |
| list's shown spelling (`SHOWN`) | `= ANY(ARRAY(...))` instead of `= m.id OR IN (...)` | the OR scanned the award table once per row of the page (113 ms of 430) |

Not done, on purpose: no `list_snapshot` of the supplier views. The worker container does not carry
`DGATE_PLACSP_AWARDS_PUBLIC` (infra/docker-compose.yml sets it on `api` only), so a snapshot the worker computed
would be the switch-off answer served to a switch-on API. Live statements are under a second without it.

Staleness (the one semantic difference): the pairing is recomputed at the refresh points above. A twin link
made by hand outside `job_link_twins`, or an organisation merge, reaches the map at the next refresh (at most four
hours, the warm-lists slot), or at once with `ops/supplier_twins --refresh --yes`. Suppression, scope, natural
persons and superseded rows are read live, as before. Switch off: the map never reads the pairs (`NOT_PLACSP`),
so the answer is the same as today; the summary and profile rewrites apply either way and were proved equal
(tests and production diff below).

## Timings (production, read-only; first run of each statement in a session)

Before = the statements of `integration` (view); after = the statements of this branch against the stored pairs.

| Endpoint (switch on) | Statements | Before | After |
|---|---|---|---|
| `/v1/suppliers` | list | 6.3 s | **0.31 s** |
| `/v1/suppliers?country=ES` | group size + list | 5.6 + 6.2 s | **0.17 + 0.19 = 0.36 s** |
| `/v1/suppliers/summary` | 5 scans + persons + PLACSP note (before); 1 scan + persons + note (after) | 6.4 + 6.0 + 7.4 + 6.8 + ~6 + 0.22 + 0.29 s | **0.33 + 0.17 + 0.15 = 0.65 s** |
| `/v1/suppliers/406963-...` (top ES supplier, 243 rows) | 9 statements + provenance | 5.9 to 14.1 s each | **19 to 25 ms each, about 0.2 s** |
| refresh (`award_twin` read once) | | | 5.0 s, in the worker or the loader |

`ops/supplier_twins --time` (in-process, through the API code) could not be run: it needs the table on
production. It is the first check after the deploy (below).

## Results identical (production, read-only)

Old statements (view, old `SHOWN`, five summary scans, profile without the index predicate) against the new ones
(stored pairs from the view in a `TEMP` table, new code), `EXCEPT ALL` both ways:

| Compared | Old rows | New rows | Only old | Only new |
|---|---|---|---|---|
| list, top 100 with totals and shown names | 100 | 100 | 0 | 0 |
| list `country=ES`, top 100 | 100 | 100 | 0 | 0 |
| summary: head, every CPV, country and cell group | 580 | 580 | 0 | 0 |
| profile rows of supplier 406963 | 243 | 243 | 0 | 0 |

## Tests (`tests/integration/test_placsp_award_twins.py`)

- `test_the_stored_pairs_are_the_view_and_the_map_reads_the_same_from_either`: every kind of pair (procedure id
  with one organisation, procedure id with one number on two organisations, the twin link without an
  identifier) beside three TED-only suppliers; the stored pairs equal the view, and list, summary and every profile
  are identical when `NOT_TWIN` reads the view instead (7 suppliers, 7 awards, every twin once).
- `test_the_summary_in_one_pass_says_what_the_five_statements_said`: the five statements of before, copied into
  the test, against the endpoint, switch off and on, with a row without a CPV.
- `test_a_merged_supplier_is_one_profile_read_by_index`: an organisation merged into another: both awards on one
  profile and one list row, the merged slug answers the same profile.
- `test_the_four_hourly_job_brings_the_pairs_up_to_date`, `test_the_scripted_refresh_says_what_differs_and_writes_only_with_yes`.
- Changed: `test_a_twin_link_without_a_procedure_identifier_is_the_same_procedure` simulates `ops/link_twins` by an
  `UPDATE`; it now runs the daily twin job before the switch, and asserts the pairs are empty before it and equal
  to the view after. Its assertion (one award) is unchanged.
- `tests/conftest.py`: `award_twin_set` truncated between tests.

Runs on the final code (`D:\DEFENCEGATE TESTS\wp75`): `ruff check .` all checks passed; unit `pytest` 3061
passed; integration `pytest -m integration` 1179 passed, 0 failed (8 min 47 s).

## Production commands (for the orchestrator)

1. Deploy the branch (migration 0098 runs with the others): about 5 s, 1,105 rows, under 1 MB.
2. Check: `docker exec dgate-worker-1 python -m dgate.ops.supplier_twins --refresh` must say
   `differ 0` (stored = view). If not: `... --refresh --yes`.
3. Time with the switch on, in-process (the running API untouched):
   `docker exec dgate-api-1 python -m dgate.ops.supplier_twins --time`. Expected under 1 s each for
   `/v1/suppliers`, `?country=ES`, `/summary` and the profile it picks.
4. Worker: no new job and no new schedule; the restarted worker refreshes in `link-twins` (09:15 UTC) and
   `warm-lists` (hh:50, every four hours), and every award load refreshes itself.
5. Then, an owner decision as before: `DGATE_PLACSP_AWARDS_PUBLIC=true` on the API.

Rollback: revert the commit and redeploy; the map reads the view again (slow with the switch on, as today; switch
off unaffected). The table is derived and may stay; `DROP TABLE award_twin_set` if wanted (no entity or
archive data in it).

## Self-review

Hostile read of the diff: 2 issues found and fixed. (1) The profile's provenance read the stored pairs without the
view's "current rows" condition, so a pair whose hidden row was superseded after the last refresh would have
been listed; it now checks `superseded_at` and `excluded_reason` live. (2) Two concurrent refreshes (a loader and
a job) would have collided on the primary key; the refresh takes an `EXCLUSIVE` lock (readers unaffected).

Not checked: the timing through the API process on production (needs the deploy, step 3); the noise of a busy
server (one repeat of the one-pass summary took 0.94 s during the history load).

Scratch: local only, `D:\DEFENCEGATE TESTS\wp75` and container `dgate-wp75` (removed after the run). Nothing on
the server.
