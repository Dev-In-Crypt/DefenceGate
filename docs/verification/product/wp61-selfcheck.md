# WP-61 self-check: PLACSP awards counted once, collected nightly, ready for the public switch (21 October 2026)

Implementer's own check, before the independent verifier. Branch `wp-wp61` from `integration` at 8ef8b7c (WP-60
included). Tests ran locally in `D:\DEFENCEGATE TESTS\wp61` (own venv, throwaway Postgres 17 container `dgate-wp61`,
port 55461). Production was only read: short `SELECT`s and `EXPLAIN ANALYZE` in read-only transactions with
`statement_timeout` 30 s (05:50 to 07:00 UTC, before the archive load of 08:30), and one read of the landed 2026-09
award payloads through the raw store in `dgate-worker-1`. Nothing was written, deployed or restarted; the
`dgate-placsp-awards` container was not touched; no request went to PLACSP or TED.

## What was built

| File | What |
|---|---|
| `backend/migrations/0093_award_twins.sql` | function `dgate_ident_key` (comparable tax number, `ESA28599033` = `A28599033`) and view `award_twin(award_id, preferred_id, procedure_method, winner_method)`; grants to `dgate_api`, `dgate_worker` |
| `backend/dgate/suppliers.py` | `scope()` with the switch on adds `NOT_TWIN`: a row is left out when the view names a preferred row that the map itself serves. Per notice `source` and `alsoPublished`; summary `sources` (PLACSP attribution and `lastUpdated`), `coverage` naming PLACSP; profile `attribution` with the date of last update; persons counted once per procedure; the PLACSP spelling of a name not shown while the switch is off (`shown()`) |
| `backend/dgate/sources/placsp.py` | `fetch_live(with_results=True)` yields `(opportunity, award payload)` like `fetch_archive` |
| `backend/dgate/pipeline.py` | `run_placsp_live`: the nightly walk, and the monthly archive it reads when the feed is frozen, pass `awards=placsp_awards.Loader` (the archive loader's code path) |
| `backend/dgate/worker.py`, `config.py` | `placsp_awards_catchup` / `job_placsp_awards_catchup` (`--once placsp-awards-catchup`): last month's archive through `ops/placsp_archives.run`; scheduled on the 3rd at 12:00 UTC only with `DGATE_PLACSP_AWARDS_CATCHUP=true` (default false); a stopped or failed month makes the job fail |
| `backend/dgate/ops/supplier_twins.py` | read-only report: twins per method, rows left out per source, pairs filed under two CPV divisions, single-winner pairs not matched; `--time` times the endpoints with the switch on in-process |
| `infra/docker-compose.yml` | `DGATE_PLACSP_AWARDS_PUBLIC` (api) and `DGATE_PLACSP_AWARDS_CATCHUP` (worker) passed through, both default `false` |
| `web/lib/supplier-sources.ts`, `wp61.check.ts`, `types.ts`, `mock/suppliers.ts`, `app/(public)/suppliers/page.tsx`, `[slug]/page.tsx` | coverage card, lead and empty state name PLACSP only when the summary lists it; PLACSP credit with its date under the counts; per-notice source label and "Also published in TED ... (counted once)" |
| `docs/design/API_CONTRACT.md`, `docs/sources/es_placsp.md` | the new fields; how each reuse condition is met |

## The model, and why

**A view, not a `duplicate_of` column and not a per-query dedupe.** The twin link (`ops/link_twins`, daily, after the
ingests) and the resolution (merges from the review queue) change after an award is loaded; a stored mark would go
stale until something rewrote it, and would need a backfill on production while the archive load runs. The view is
always the current answer, needs no production write (deploying is enough), and every supplier query already goes
through `scope()`, so one clause covers list, profile (wins by year, by CPV, buyers), summary and its groups.

Rule (one logical award): the same **procedure** (same eForms procedure identifier on both notices; or the PLACSP row's
`ted_ref` names the TED notice or a TED notice of the same procedure) and the same **winner** (one organisation after
merges, from the resolution cascade; or the same tax number on both rows), at least one row PLACSP's. Preferred: the row
that states a usable number, then TED's, then the newer row. Both rows stay; the other publication is listed under the
one shown (`alsoPublished`).

**Lot and value are not matched** (a deviation from the brief, stated here): `award` stores neither (WP-37; the PLACSP
value per lot stays in the landed payload), and the notices' own values disagree on true pairs. Measured on production
on 384 TED-result/PLACSP pairs of one procedure: ratio TED value / PLACSP value at the 5th, 25th, 50th, 75th, 95th
percentile 0.02, 0.18, 0.68, 1.00, 1.08; 133 of 372 pairs with both values more than 3x apart, 75 more than 10x
(PLACSP states the budget of the folder, TED the awarded value of the notice). A value tolerance would split true
pairs; the procedure identifier and the winner decide.

## Measured on production (read-only, 21 October 2026, before the archive load)

| Measure | Value |
|---|---|
| award rows | 9,826, all TED (no PLACSP award row yet: the pilot was land-only) |
| TED result notices of ES buyers whose winners we hold | 534, all with a procedure identifier |
| TED result notices sharing their procedure identifier with a PLACSP row | 373 (with 307 PLACSP rows; 1,083 TED award rows) |
| pairs found by procedure identifier / by `ted_ref` / by `ted_ref` to another TED notice of the procedure | 384 / 232 / 374: the identifier finds every pair the other two find |
| TED notices per PLACSP row | 1: 272, 2: 22, 3 to 12: 13 (lots awarded in several result notices) |
| PLACSP rows per TED notice | 1: 362, 2: 11 |
| PLACSP twin links (`ted_ref`) | 1,783 by procedure identifier, 1,264 by the heuristic; the heuristic links add no pair with a TED result notice |

**Winner match on real payloads** (the 2026-09 landed payloads; `twins_probe` in the scratchpad, read-only): 42 PLACSP
folders with 60 TED result notices of the same procedure, 545 TED winner rows (first landed payload per folder). 493 have
the same winner in the PLACSP payload by normalised name or number (the rule above, before resolution), 52 do not: a
framework folder whose first landed payload names other lots' winners, and RotorSky GmbH, which the PLACSP entry does
not name. None of the 52 is a PLACSP winner spelled differently, so none would be counted twice.

Sample read by hand (21 TED winner rows, by `md5(folder)`): 20 matched pairs, each the same company with the same
number on both sides (Fabrica de Municiones de Granada S.L. B88295209; Imesapi S.A. A28010478; MEYRIN SL B30652911;
FLIGHTSAFETY INTERNATIONAL S.A.R.L., ANSETT AVIATION ITALIA, CSA CONSULTORIAS Y SOLUCIONES AERONAUTICAS S A, Helisim SAS,
CINETIC PLUS SL, AIRBUS DEFENCE AND SPACE S.A.U in one framework; CAMUYDE, S.L.; FLUIDMECANICA SUR S.L.; Suyfa Defence,
S.L. in four TED result notices of one folder; COMERCIAL HERNANDO MORENO-COHEMO, S.L.U.; ABB Marina y Puertos en
España; EPICOM, S.A.; SANCHEZ SUR SL; GAUZON IBERICA, S.L.U.): **yes** for all 20. RotorSky GmbH not matched: **yes,
correctly** (another winner). In these pairs both sides state the number, so the TED row stands for the award and the
PLACSP row is listed under it.

**Timing** (production, read-only, the view inlined as a subquery since 0093 is not applied there; 9,687 current award
rows): the summary's head query with the switch on 297 to 427 ms against 87 ms with it off. The plan is a hashed
`NOT IN` subplan (the view read once per query). The estimates are off because `award.superseded_at` (0092) has no
statistics yet (57 estimated, 9,687 read); `ANALYZE award` after the load fixes that. Under the API role's 5 s budget;
the list is cached 5 minutes and the summary 30. **Not measured at the post-load volume** (about 50,000 to 65,000 award
rows): `ops/supplier_twins --time` below does it.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| 1. An award in TED and PLACSP counts once (twin link, procedure, winner via the cascade), preferring the record with a number, both references kept | **met; lot and value not used (see above)** | integration `test_one_award_in_ted_and_placsp_counts_once_and_the_numbered_record_stands_for_it` (list, byYear, byCpv, buyers, summary each 1; PLACSP row shown, TED in `alsoPublished`), `test_the_ted_record_stands_for_the_award_when_it_states_a_number_too`, `test_one_number_on_two_organisations_is_one_winner`, `test_another_winner_of_the_same_procedure_is_another_award`, `test_two_ted_result_notices_and_the_numbered_placsp_folder_are_one_award`, `test_a_twin_link_without_a_procedure_identifier_is_the_same_procedure`, `test_a_twin_the_map_does_not_serve_does_not_hide_the_other`. Without `NOT_TWIN` six of them fail (checked by removing it) |
| Model decided and justified; migration after 0092 | **met** | 0093, view; above |
| Measured with read-only SQL on production | **met (before the load)** | above; after the load: commands below |
| 2. Nightly live connector lands and loads award payloads with the archive loader's code path, idempotent, persons stripped before landing, re-read on a winner change | **met** | `test_the_nightly_walk_lands_and_loads_the_award_results_like_the_archive_loader` (live feed served by a stand-in: winner loaded, person not in the store, second night writes nothing, a new winner supersedes the old one); unit `test_the_live_walk_and_its_archive_cover_collect_the_award_results` |
| Added to the worker job | **met** | `placsp_daily` runs `run_placsp_live`, which now loads awards; no extra request to PLACSP |
| Monthly archive catch-up, disabled by default, how to enable documented | **met** | `job_placsp_awards_catchup`; units `test_the_placsp_award_catchup_is_off_unless_switched_on`, `test_the_catchup_reads_last_months_archive_and_is_not_green_when_stopped`; `DGATE_PLACSP_AWARDS_CATCHUP=true` (compose, `docs/sources/es_placsp.md`) |
| 3. Switch on: supplier pages/API show PLACSP winners deduplicated, with attribution per the terms, persons only counted, coverage text names Spain's national portal | **met** | `test_natural_persons_are_counted_once_and_never_shown_and_placsp_is_attributed` (no person's name or masked NIF in any answer; one person counted once across the two publications; "Origen de los datos: Ministerio de Hacienda ..." and the date 2026-09-20 in summary and profile; coverage names PLACSP); web `coverageText`, `placspCredit` and `wp61.check.ts` |
| Switch off: nothing changes (both tested) | **met** | `test_one_award_...`: the whole list, summary and every profile are identical before and after the PLACSP rows are loaded; `test_a_supplier_only_in_placsp_is_not_served_while_the_switch_is_off` (404); `test_the_placsp_spelling_of_a_ted_supplier_is_not_shown_while_the_switch_is_off` (this was a leak of WP-60's code: the shown spelling counted PLACSP rows); web check: TED-only text without a PLACSP source |
| ruff, unit, full integration locally; web tsc, checks, `next build`, Playwright | see "Test runs" | |

## Test runs (local)

All on the final code of the branch, in `D:\DEFENCEGATE TESTS\wp61`:

| Check | Result |
|---|---|
| `ruff check .` | clean |
| unit suite (`pytest`, integration deselected as `addopts` says) | exit 0 |
| integration suite (`pytest -m integration`, `DGATE_TEST_DSN` on `dgate-wp61`) | exit 0, the whole suite (also green before the change: baseline run) |
| web `npx tsc --noEmit` | clean |
| web `npm run check` | every `lib/*.check.ts` ok, `wp61.check.ts` included |
| web `npx next build` (mock env of `.github/workflows/web.yml`, `TZ=UTC`) | exit 0 |
| web `npx playwright test` (same env, `E2E_PACE_MS=0`) | 448 passed, 40 skipped, 0 failed |

Tests added: 12 integration (`tests/integration/test_placsp_award_twins.py`), 3 unit (`test_worker.py` x2,
`test_placsp_stale.py` x1), one web self-check (`lib/wp61.check.ts`). Changed: the fakes of `fetch_live`,
`fetch_archive` and `_ingest_placsp` in `test_placsp_stale.py` / `test_placsp_quality.py` accept the new keyword
arguments (`**kw`); the CLI job list of `test_every_job_is_reachable_from_the_cli` gained `placsp-awards-catchup`.
No test was removed or weakened.

Mutation checks: with `NOT_TWIN` removed from `scope()` six twin tests fail; with the PLACSP filter removed from the
shown spelling, the spelling test fails; with the persons summed instead of taken per procedure, the persons test
fails.

## Hostile review of the diff

Issues found and fixed: 6.
1. The supplier list's shown spelling (`SHOWN`) read every award row, so after tonight's load a TED supplier could be
   shown in a PLACSP spelling while the switch is off: now PLACSP rows are left out of it unless on (test above).
2. `skippedNaturalPersons` would have counted a person twice when both publications skip them: per procedure, the
   larger count.
3. The coverage text and `sources` would have named PLACSP as soon as the switch was on, with no PLACSP row behind it:
   both now follow the presence of a PLACSP award result.
4. A twin whose preferred row is not served (removed on request, out of scope, superseded) would have hidden the other
   copy: the preferred row must pass the map's own scope (`_as_preferred(SCOPE)`; test above).
5. A provenance reference could name a notice removed on request: `alsoPublished` leaves those out.
6. January: the catch-up's December lives in the annual archive, whose done-mark (1 January) is January's and would
   skip it: the unit is walked from 1 December and marked as December.

Known limits, not fixed:
- A CPV or country filter finds a twin award under the preferred row's CPV division and country only (the two rows can
  file it differently). `ops/supplier_twins` counts these pairs (`cpv_division_differs`).
- Two TED result notices of one procedure stay two TED wins when the TED row is preferred (as today); when the
  numbered PLACSP row is preferred they become one. The rule is per pair, not per procedure.
- A winner the cascade put on two organisations without a shared number is not matched (no fuzzy matching, by the
  project rule). `single_winner_pairs_not_matched` counts the candidates for a person to read.
- `noticesRead` counts both publications of a procedure (it counts notices read, not awards).
- The web fetches the summary on every `/suppliers` page (cached) to word the coverage card; with the API down the
  card falls back to the TED-only text.
- The catch-up of December downloads the annual archive (up to 2 GB) once a year.

## Commands for the orchestrator (production), after the archive load has finished

1. Deploy the branch as usual (merge to `integration`/`main`, then on the server
   `cd /opt/dgate && git pull --ff-only && docker compose -f infra/docker-compose.yml --env-file infra/.env up -d --build migrate api worker`, plus the web service by the usual route).
   The migrate service applies **0093** (a function and a view: instant, no rows). With the switch off nothing visible
   changes. From the next 06:30 UTC run the nightly walk loads the award results of the entries it reads.
2. Statistics for the new column and the grown table (read-only for data; a maintenance command):
   `docker exec dgate-postgres-1 psql -U dgate -d dgate -c "ANALYZE award; ANALYZE award_notice;"`
3. Read-only report and timings with the switch on, in-process in the API container (its role reads only):
   ```
   docker exec dgate-api-1 python -m dgate.ops.supplier_twins --time
   ```
   Expected: `twins` of the order of 1,000 to 3,000 pairs, most `procedure_id`/`organisation`; `dropped_by_source`
   both `ted` and `es_placsp`; `single_winner_pairs_not_matched` small (read 15 by hand); timings under 2 s each.
4. Nightly check (the morning after the deploy):
   ```
   docker logs dgate-worker-1 --since 24h | grep "es_placsp-live awards"
   docker exec -i dgate-postgres-1 psql -U dgate -d dgate -c "SET default_transaction_read_only=on; SELECT count(*) FROM raw_ingest WHERE source_id=(SELECT id FROM source WHERE code='es_placsp_awards') AND fetched_at > now() - interval '1 day';"
   ```
   Expected: a log line with `payloads_read` / `payloads_unchanged` counts, and some tens to a few hundred payloads landed.
5. Owner decisions, not run by anyone yet:
   - publish the PLACSP winners: `DGATE_PLACSP_AWARDS_PUBLIC=true` in `infra/.env`, then
     `docker compose -f infra/docker-compose.yml --env-file infra/.env up -d api` (restarting the API also empties its list cache);
   - the monthly safety net: `DGATE_PLACSP_AWARDS_CATCHUP=true` in `infra/.env`, then `up -d worker`
     (`docker exec dgate-worker-1 python -m dgate.worker --list` shows `placsp_awards_monthly day 3, 12:00 UTC`).

## Scratch

Local only: `D:\DEFENCEGATE TESTS\wp61` (venv, copy of the branch, `node_modules`, logs) and the container
`dgate-wp61`; delete after the merge. Nothing was created on the server; the probe scripts live in the session
scratchpad.
