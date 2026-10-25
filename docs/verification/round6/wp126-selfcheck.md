# WP-126 self-check: small infrastructure and data follow-ups

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP126.md`. Branch `wp-wp126` from `integration` (9244638). Migration
0132. Production was read only (SELECTs through the postgres container in a `READ ONLY` transaction, 30 s timeout,
25 October 2026; production schema at 0128). Nothing deleted, nothing merged, no `opportunity_version` row written.

## 1. Security log kept 90 days

- Before: the accounts security log (`accounts._audit`, WP-123) went to the API's stderr, i.e. the `api` container's
  json-file log, rotated by size only (5 x 20 MB): no time limit (docs/DATA_PROTECTION.md said "open for the owner").
- Change, the way the proxy log is kept: with `DGATE_SECURITY_LOG` set (`config.security_log`), the `accounts` logger
  writes JSON lines (`ts` Unix seconds, level, text) to that file only and no longer to stdout
  (`accounts.security_log_to_file`, called at server start in `api._lifespan`; append mode, so the in-place cut is
  safe). Compose: `api` gets `DGATE_SECURITY_LOG=/var/log/dgate/security.log` and the volume `securitylog`
  (mount point created and owned by the image's user in `backend/Dockerfile`, like `/raw`); `logprune` mounts it too
  and runs `--dir /logs --days 14 --dir /security=90` (`--dir PATH=DAYS` is new: one service, each directory its own
  limit). Unset (development, tests), the log goes to stderr as before.
- Found while checking: `logprune` runs as root with every capability dropped, and root without `DAC_OVERRIDE` may not
  write a file owned by uid 10001 with mode 644 (EACCES, tried in Docker on the laptop). The service now has
  `cap_add: [DAC_OVERRIDE]`; it has no network, a read-only root file system and only the two log volumes. Smoke test
  (python:3.12-slim, the branch's code mounted read-only, the same user/caps/read-only flags): lines of 120 and 91 days
  cut, 89 and 1 kept, owner 10001 unchanged; a missing directory is reported and the next one still pruned.
- Tests: unit `test_logprune.py::test_each_directory_keeps_its_own_limit`,
  `::test_security_log_goes_to_its_file_as_lines_logprune_can_cut` (the event is a JSON line with `ts` in the file,
  nothing on stderr, cut after 91 days). The four existing logprune tests pass unchanged.
- Docs: DATA_PROTECTION.md, the security log row (90 days, the file, logprune) and the logs row. The privacy draft 1.7
  (docs/legal/drafts) already says 90 days; its note 2 ("the API's container log is rotated by size only") is now
  out of date but was not edited (legal wording is not this package's).
- After deploy: the old container log goes with the recreated `api` container. Check on the host (nothing run inside
  a container): `docker logs dgate-logprune-1 2>&1 | tail -2` shows `pass done /security: ...`.

## 2. Billing flag in the web build

- Before: `infra/build-web.sh` passed `DG_API_URL`, `NEXT_PUBLIC_SITE_URL` and `NEXT_TELEMETRY_DISABLED` only, so
  `NEXT_PUBLIC_BILLING_OPEN` (WP-122, read at build time) was always empty in a production build.
- Change: the build passes `-e NEXT_PUBLIC_BILLING_OPEN=...`, taken from the environment, else from `infra/.env`,
  else empty (off). `infra/.env.example` documents it (empty; a rebuild is needed to change it).
- Check: the resolution line run by `sh` with no file (empty), a file with `=1` (`1`), the environment set to `true`
  (`true`, before the file). No web code changed, so no web checks were run.

## 3. PLACSP award amounts under EUR 100

- Evidence (production, read-only): current EUR award rows under 100: PLACSP 431 contract (EUR 1.02-99.27, 298
  suppliers, EUR 14,375 in all) + 25 framework, TED 7 + 1. Of the 431, 416 have a procedure estimate of EUR 1,000 or
  more and 411 one over a hundred times the amount; 14 have none. Titles and amounts are unit prices, not placeholders
  (those are <= EUR 1 and already no value) and not unit errors: "zapatillas de deporte" 84.95 (estimate 648,000),
  "cazadora de trabajo" 61.90, "un minimo de 2000 cargadores" 28.00 (estimate 68,000, i.e. 34 a piece), catering
  45.72 a menu, maintenance 21.46 or 15.00 an hour, laundry 3.31 a load. Between 100 and 1,000: 351 contract rows,
  only 128 that far below their estimate (mixed; the owner's EUR 300 minor contract of WP-87 is real): they stand.
- Choice: no change to `suppliers.is_suspect` (its test pins "a PLACSP awarded EUR 48 is not a unit price"; tests are
  not weakened). The honest way, as for TED: the figure is set aside per award row and kept
  (`award.value_set_aside`, `value_set_aside_reason = 'unit_price'`, migration 0132), its `value_amount` emptied, kind
  and currency kept. `suppliers.value_of` then gives the row no value, so it is in no contract and no framework sum
  and counts as "without value"; the award page shows the winner without an amount.
- Rule: `award_value.placsp_unit_price` (over the placeholder, under `PLACSP_UNIT_PRICE_MAX` = 100), applied by the
  loader (`placsp_awards.read` -> `awards.Winner.value_set_aside`, written by `awards.store_notice`), so a re-read or a
  replay keeps it, and by the ops step for the rows held. A later read that states a real total puts it back.
- Ops: `python -m dgate.ops.award_values --no-fetch` step 6 (`run_unit_prices`); `--undo-unit-prices [--yes]` puts the
  amounts back. Also fixed: step 4 summed `float(value_amount)` and would fail on a set-aside row.
- Tests: unit `test_wp126.py` (the rule's edges; the reader sets 84.95 aside and keeps 300 and the placeholder as
  before); integration `test_wp126.py::test_the_ops_step_sets_placsp_unit_prices_aside_out_of_every_sum_and_the_undo_
  puts_them_back` (value_of gives none, PLACSP 300 and TED 48 untouched, second run 0, undo),
  `::test_the_loader_sets_a_unit_price_aside_on_every_read`.

## 4. Merge candidates for the held Polish numbers

- Before: WP-119's restore-ids could not restore 64 NIP+REGON pairs and 8 short REGONs: another live PL row holds the
  number.
- Change: `ops.org_repair --step held-ids` (after restore-ids): for each such number, the two live rows become a merge
  candidate through the existing path (`db.add_merge_candidate`): method `cleared_register_number`, confidence 0.90
  (below the 0.97 that `ops.accept_merge_candidates` accepts, so a person decides: most are public bodies, where a
  number proves one legal entity, not one buyer), evidence naming the kind, the cleared row, the holder and both names,
  never the number. Nothing is merged; a second run writes nothing. `restore_ids` and the new step share
  `_kept_number` and `_CLEARED`.
- Expected on production (read-only SQL equivalent, 25 Oct): `nip_regon_pair_held_by_another_row 64`,
  `unpadded_regon_held_by_another_row 8`, `candidate_pairs 70` (62 + 8: two pairs repeat), `candidate_pairs_new 70`;
  35 of the 70 pairs already have a pending candidate of another method (they get this row as well); no person rows,
  none suppressed. Examples: "gmina kolbiel" twice, "amw sinevia" / "amw sinevia spolka z ograniczona
  odpowiedzialnoscia", "politechnika gdanska wydzial inzynierii ladowej i srodowiska" / "politechnika gdanska",
  "zaklad karny" / "zaklad karny we wronki" (a generic name: a review case).
- Test: integration `test_wp126.py::test_a_cleared_number_another_live_row_holds_becomes_a_merge_candidate_and_
  nothing_is_merged`. WP-119's restore-ids test passes unchanged.

## 5. Deletion candidates

- `bindValue` / `readBind` (already listed by WP-123): evidence added (git grep: only their definitions and their own
  check lines). `app_login_token` added: no reader or writer in code, only migrations, the test truncate list, two
  account tests and the backup grant test; 0 rows on production. Nothing deleted.

## Ops to run on production (orchestrator), in order

1. Deploy with migration 0132 (additive) and recreate `api` and `logprune` (`up -d --build migrate api worker logprune`):
   the new volume and environment take effect only on a recreate.
2. `python -m dgate.ops.award_values --no-fetch` (report; step 6 expected `unit_prices_set_aside 457`:
   `_contract 431`, `_framework 25`, `_contract_superseded 1`, `_amount 15419.79`; steps 1-5 as WP-119 left them),
   then `--no-fetch --yes` (renews the supplier value orders).
3. After WP-119's `org_repair --step restore-ids --yes`: `python -m dgate.ops.org_repair --step held-ids` (report: as in
   item 4), then `--yes`.
4. The web image, when it is next built: `NEXT_PUBLIC_BILLING_OPEN` stays empty unless the owner sets it.

## Tests run (batched scope)

In `D:\DEFENCEGATE TESTS\wp126` (own venv, Postgres 17 on 55526, removed at the end): ruff clean; unit: the 14 files
of the touched modules (accounts, credentials, logprune, placsp awards and quality, award values of WP-81/95/103/108/
119, org identifiers WP-115/119, WP-123, WP-126): 395 passed; integration: the 22 files that touch the changed modules
(accounts x3, archive timeline, buyer families, PLACSP awards, twins and quality pipeline, repair_ted, suppression,
supplier map, WP-17/31/36/87/91/95/103/108/115/119/126): 346 passed in 183 s. Not the full suites. The backend image
was not built on the laptop (pip there needs the system certificates, `uv.toml`); compose rendered with `config`.

## Open items

- Privacy draft 1.7, note 2 (docs/legal/drafts): no longer true once deployed; for the owner with the draft.
- A unit price is kept but not shown (the award page gives the winner no amount); showing "unit price EUR 84.95" would
  be a web change.
- PLACSP amounts of EUR 100-1,000 far below their estimate (128 contract rows) stand: mixed by evidence.
- The 70 merge candidates wait for a person; `ops.accept_merge_candidates` does not take method `cleared_register_number`.
