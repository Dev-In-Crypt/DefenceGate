# WP-163 self-check: database restore drill

Branch `wp-wp163` from `integration` 2e2af81 (= production). Test copy `D:\DEFENCEGATE TESTS\wp163\` (own Postgres
`dgate-wp163`, 127.0.0.1:56163, removed at the end). Production: one scp download of the backup files and read-only
SELECTs through the postgres container (`default_transaction_read_only = on`, `statement_timeout = '30s'`); nothing written
on the server. The private key was passed by path to `backup_keys decrypt`, read in place, never printed or copied.
Runbook: `docs/RESTORE.md`.

## Steps and times (31 Oct 2026, laptop)

| Step | What | Time | Result |
|---|---|---|---|
| 1 | scp `dgate-20261031T132949Z.sql.gz.enc` (1,214,648,667 B) and manifest from `dgate_backups` | 52 s | ok |
| 2 | `backup_keys decrypt` (manifest size + sha256, every frame authenticated) | 3 s | `manifest ok`, 1,214,623,801 B gzip |
| 3a | restore through the filter into a fresh Postgres 17.11 | 1 s | **refused, line 26: extension 'pg_stat_statements' is not allowed** (finding 1) |
| 3b | same, after the fix | 390 s | ok, psql exit 0 |
| 4a | `python -m dgate.migrate` (the deploy's step) on the restored copy | 4.6 s | **failed: role "dgate_api" does not exist** on 0154's GRANT (finding 2) |
| 4b | same, after the fix: 109 privilege statements replayed, 0154 applied, three passwords set | 0.7 s | ok |
| 5 | verification below | ~5 min | all pass |

## Findings and fixes

1. **The restore filter refused production's own dump.** Production preloads `pg_stat_statements` (WP-114,
   `infra/docker-compose.yml`) and every dump since starts with `CREATE EXTENSION IF NOT EXISTS pg_stat_statements`;
   `backup.SAFE_EXTENSIONS` did not list it, so `--verify` with a key and any filtered restore failed at line 26 (the
   server-side verify is structural and never saw it). Fix: `backend/dgate/ops/backup.py` `SAFE_EXTENSIONS` +
   `pg_stat_statements` (a stock statistics extension; no file, network or code access). Test:
   `tests/unit/test_backup_encryption.py::test_the_extensions_a_production_dump_creates_pass`.
2. **Roles and grants were lost on a restore.** Dumps are `--no-owner --no-privileges` and roles are cluster objects:
   a restored copy had role `dgate` only and zero grants (`privileges-restored-before.txt`: no `rel`/`col`/`schema`/
   `default` row). `migrate` only set passwords, and only for roles that existed; the first pending migration with a
   GRANT then failed. Fix (`backend/dgate/migrate.py`): `reapply_privileges` replays, in migration order and in one
   transaction, every role-creating DO block, `ALTER ROLE`, `GRANT`, `REVOKE` and `ALTER DEFAULT PRIVILEGES` of the
   migrations already applied (`privilege_statements`, a small top-level SQL splitter that keeps strings, quoted names
   and dollar bodies whole and drops comments); `migrate()` runs it before the pending migrations, then the passwords as
   before. Idempotent: on production it re-grants what is there (same final state, one transaction; 0.7 s on the full
   copy including 0154). No migration number used. Test: `tests/integration/test_restore_privileges_wp163.py`: a
   scratch database at the version before the last, the service roles renamed away (so no role of those names and no
   grant exists, as after a restore on a new server), one `migrate.migrate()` must apply the last migration and end with
   exactly the session database's grants and role settings (rel, column, schema, default ACLs; superuser/createdb/
   connection limit/settings), a second replay changes nothing, `dgate_api` reads with 5 s and is refused an UPDATE in a
   read-write transaction, `dgate_worker` updates, reads `app_user`, is refused `DELETE FROM project` (0060's REVOKE,
   order-sensitive). The original roles are renamed back in a finally. Plus a test that the statements are found in
   order (0027 GRANT before 0036 REVOKE) and contain no comments.
3. **A filtered restore had no command.** `backup_keys sql --in X.sql.gz` writes the decrypted dump's SQL through
   `filter_dump` to stdout (pipe into psql; a refused line stops the stream before psql sees it, exit 1). Used in the
   drill and the runbook (`backend/dgate/ops/backup_keys.py`).

## Verification (restored copy vs production read-only)

- `schema_migrations`: restored 111 rows, max 151 (= manifest); after `migrate` 114, max 154 = production.
- Row counts, every table (`counts.sql`, exact `count(*)` per table; production read 15:03 UTC, about 1.5 h after the
  dump): 85 tables on both sides after `migrate` (82 before it; `report_logo`, `sell_profile`, `sell_report_use` are
  0154's, created by migrate, 0 rows on production too). **No table missing on the restored side, none smaller on
  production than in the dump**: 79 tables equal; production ahead on `raw_ingest` +71,839, `ted_repair_marker` +70,000 (the running
  repair job), `job_run` +9, `organisation_alias` +5, `ingest_run` +2, `organisation_merge_candidate` +1. Equal for
  the core: opportunity 395,783, opportunity_version 841,434, organisation 437,997, award 49,782, participation 386,229.
- Archive guard: both triggers present and enabled (same as production); on the restored copy an `UPDATE raw_hash`
  is refused ("only valid_to may be updated"), `DELETE` refused, `TRUNCATE` refused; 841,434 versions after.
- Sample: 198 opportunities (`id % 2000 = 7`) and 211 versions (`id % 4000 = 7`), md5 of each row (versions without
  `valid_to`): versions 211/211 equal; opportunities 191/198 equal, the 7 others differ only in the non-versioned
  `contract_*` columns that the WP-159/160 period refetch is filling on production since the dump.
- Roles and grants: `privileges.sql` (the test's query plus roles and owners) on production and on the restored copy
  after `migrate`: 572 lines each, **identical** (`diff` empty): 551 table/view/sequence grants, 2 column grants, schema
  usage, 8 default ACLs, the four roles with the same flags, connection limits and settings, every object owned by
  `dgate`.
- As the roles on the restored copy: `dgate_api` reads (395,783), `statement_timeout` 5s, UPDATE refused "permission
  denied" even in `BEGIN READ WRITE`, read-only default refuses too, `app_user` refused; `dgate_worker` UPDATE 18 ok,
  `ALTER TABLE` refused (must be owner), `TRUNCATE opportunity_version` refused, 0 tables it cannot read; `dgate_app`
  reads `app_user`.
- API (`uvicorn dgate.api:app`, `DGATE_DSN` = dgate_api, `DGATE_APP_DSN` = dgate_app, against the restored copy):
  `/v1/health` 200 status ok, `/v1/tenders` 200, `/v1/tenders?country=ES&page=2` 200, `/v1/buyers` 200,
  `/v1/opportunities?limit=3` 200, `/v1/opportunities/136007` and `/versions` 200, `/v1/funding` 200, `/v1/calls` 200
  (`?limit=` on tenders/buyers is a 422 by design: unknown parameter).

Evidence files in `D:\DEFENCEGATE TESTS\wp163\`: `t-*.txt` (times), `counts-prod.txt`, `counts-restored*.txt`,
`compare.txt`, `privileges-prod.txt`, `privileges-restored-before.txt`, `privileges-restored-after.txt`,
`checks-restored.txt`, `sample-*.txt`, `sd-*.txt`, `roles-check.txt`, `api-results.txt`, `migrate.log`.

## Tests

- ruff clean. Unit `test_backup_encryption.py` + `test_migrate.py`: 78 passed. Integration (restore privileges,
  security hardening, accounts, backup freshness): 97 passed. Because `migrate` is shared, the full suites ran once
  too: unit 4,208 passed (one test first failed only because `.github` was not yet in the test copy; passed after the
  copy), integration 1,660 passed in 17 min 49 s, on a fresh `dgate-wp163` (no production data), removed afterwards.

## Cleanup

Deleted after the verification: the decrypted `dgate-20261031T132949Z.sql.gz`, the encrypted `.sql.gz.enc` and the
`.manifest.json`; the restored container `dgate-wp163` with its volume (`docker rm -f -v`; `docker volume rm` then
answers "no such volume"). `D:\DEFENCEGATE TESTS\wp163\restore\` is empty (`ls -la`: only `.` and `..`); no
`dgate-2026*` or `*.partial` file anywhere under `D:\DEFENCEGATE TESTS\wp163\`. The container used afterwards for the
test suites (fresh, no production data) is removed at the end too.

## For the orchestrator

- Deploy as usual: `migrate` now also replays the privilege statements (log line `roles and grants: N statements
  re-applied`); no migration, no ops step. Files: `backend/dgate/migrate.py`, `backend/dgate/ops/backup.py`,
  `backend/dgate/ops/backup_keys.py`, two tests, `docs/RESTORE.md`, this file.
- Open: the gap after a dump's time is not recovered by a restore (raw store replay not drilled); the server-side weekly
  verify cannot catch a filter refusal (no key there), so a periodic laptop drill (`backup --verify --offsite` with the
  key) is the real check.
