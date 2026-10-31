# Restoring the database from a backup

Drilled end to end on 31 October 2026 (WP-163) with production's pre-deploy dump
`dgate-20261031T132949Z.sql.gz.enc` (1.21 GB encrypted, 111 migrations), restored on the laptop into a
fresh Postgres 17 container. Evidence: `docs/verification/features/wp163-selfcheck.md`.

## What a dump is, and what it is not

- `python -m dgate.ops.backup` (worker, nightly 02:00 UTC and before each deploy) runs
  `pg_dump --no-owner --no-privileges` as `dgate_worker`, gzips it and encrypts it (AES-256-GCM, data
  key wrapped with RSA-OAEP under the public key). File and manifest sit in the `dgate_backups` volume
  (`/var/lib/docker/volumes/dgate_backups/_data/` on the host) and are shipped to the Storage Box.
- A dump holds every table, index, trigger (the archive guard included) and sequence position.
- A dump does **not** hold roles (cluster objects) or grants (`--no-privileges`). Since WP-163 `migrate`
  rebuilds both: before the pending migrations it replays, in order, every role and privilege statement
  of the migrations already applied (`dgate.migrate.reapply_privileges`), then applies the pending ones,
  then sets the role passwords from `infra/.env`. So **a restore always ends with `migrate`**. Before
  WP-163 the first `migrate` on a restored copy failed: `role "dgate_api" does not exist`.

## What needs the laptop

Only decryption. The private key is `C:\Users\DEV\dgate-keys\backup-private.pem` on the owner's laptop,
never on the server, the Storage Box or in the repository. Pass its path to the command; never copy,
print or move it. Everything else runs on the server.

## The commands

Laptop, PowerShell for the venv, Git Bash for the pipes (PowerShell 5.1 corrupts binary pipes).
`D:\restore` stands for an empty working folder; `HOST` for the server (`root@2.29.42.177`).

| Step | Command | Drill time |
|---|---|---|
| 1. Fetch the dump and its manifest (read-only on the server) | `scp -i ~/.ssh/hetzner_key HOST:/var/lib/docker/volumes/dgate_backups/_data/dgate-STAMP.manifest.json HOST:/var/lib/docker/volumes/dgate_backups/_data/dgate-STAMP.sql.gz.enc /d/restore/` | 52 s (1.21 GB) |
| 2. Decrypt: checks the manifest (size, sha256), authenticates every frame, writes nothing unless all of it verified | `python -m dgate.ops.backup_keys decrypt --private-key C:/Users/DEV/dgate-keys/backup-private.pem --in /d/restore/dgate-STAMP.sql.gz.enc --out /d/restore/dgate-STAMP.sql.gz` | 3 s |
| 3. Restore into an EMPTY database, through the restore filter (psql never sees a meta-command or a statement pg_dump does not write; a refused line stops the stream, then drop the half-restored database) | `python -m dgate.ops.backup_keys sql --in /d/restore/dgate-STAMP.sql.gz \| <psql into the target, below>` | 390 s (indexes included) |
| 4. Roles, grants, pending migrations, passwords | the deploy's `migrate` (below) | 0.7 s |
| 5. Verify | below | a few minutes |
| 6. Delete the decrypted and the encrypted copy on the laptop | `rm /d/restore/dgate-STAMP.*` | |

The psql of step 3 is always `psql -U dgate -d <target> --no-psqlrc --quiet -v ON_ERROR_STOP=1 -o /dev/null`,
run as `dgate` (the owner role production's objects belong to; with `--no-owner` whoever restores owns
everything, so it must be `dgate`).

If the host is gone, the same files are on the Storage Box (shipped copy, `python -m dgate.ops.backup
--list-offsite` on a machine with the store settings). The weekly check can also prove the shipped copy:
`DGATE_BACKUP_PRIVATE_KEY_FILE=<key path> python -m dgate.ops.backup --verify --offsite` on the laptop
restores it into a scratch database and drops it.

### Drill (laptop only, proves the dump)

```bash
docker run -d --name dgate-restore -e POSTGRES_PASSWORD=<local> -e POSTGRES_USER=dgate -e POSTGRES_DB=dgate -p 127.0.0.1:56163:5432 postgres:17
python -m dgate.ops.backup_keys sql --in /d/restore/dgate-STAMP.sql.gz \
  | docker exec -i dgate-restore psql -U dgate -d dgate --no-psqlrc --quiet -v ON_ERROR_STOP=1 -o /dev/null
DGATE_DSN=postgresql://dgate:<local>@127.0.0.1:56163/dgate DGATE_API_PASSWORD=<local> DGATE_WORKER_PASSWORD=<local> \
  DGATE_APP_PASSWORD=<local> python -m dgate.migrate
# verify (below), then: docker rm -f -v dgate-restore
```

### Switching production to a restored database

Same server, database damaged or wrong (restore beside it, swap names, keep the old one for rollback;
needs free disk about the size of the database, 6 GB on 31 Oct 2026):

```bash
C="docker compose -f infra/docker-compose.yml --env-file infra/.env"     # on the server, in /opt/dgate
$C stop web worker api                                                   # nothing writes during the swap
docker exec dgate-postgres-1 psql -U dgate -d postgres -c 'CREATE DATABASE dgate_restored'
# laptop: decrypted SQL straight over ssh, never written on the server
python -m dgate.ops.backup_keys sql --in /d/restore/dgate-STAMP.sql.gz \
  | ssh -i ~/.ssh/hetzner_key root@2.29.42.177 "docker exec -i dgate-postgres-1 psql -U dgate -d dgate_restored --no-psqlrc --quiet -v ON_ERROR_STOP=1 -o /dev/null"
# server: swap (no session may be connected to either database)
docker exec dgate-postgres-1 psql -U dgate -d postgres -c 'ALTER DATABASE dgate RENAME TO dgate_broken' -c 'ALTER DATABASE dgate_restored RENAME TO dgate'
$C up -d --no-build migrate                                              # roles, grants, pending migrations, passwords
# verify (below), then start as in a deploy:
$C up -d --no-build --wait api worker && $C --profile web up -d --no-build --no-deps --wait web
```

`dgate_broken` stays until the owner decides; dropping it is the owner's call.

New server (host lost): bring up `postgres` only from a fresh `pgdata` volume (`$C up -d postgres`; the
compose file preloads `pg_stat_statements`, which the dump creates), restore into its empty `dgate`
database with the ssh pipe above, then `$C up -d --no-build migrate` and the rest as in a deploy.

Everything written after the dump's time is not in it. The raw payload store survives separately
(`dgate.reprocess --from-store` rebuilds the serving layer from it); recovering the gap that way was not
part of this drill.

## Verify

1. `SELECT count(*), max(version) FROM schema_migrations` equals the manifest's `schema_migrations`
   before `migrate`, and the code's latest migration after it.
2. Row counts of every table against production (or the manifest's time): the read-only script
   (`SET default_transaction_read_only = on; SET statement_timeout = '30s'`, one `count(*)` per table
   through `query_to_xml`) as used in the drill. No table may be missing or larger on production than
   restored minus what production has written since.
3. The archive guard: `pg_trigger` on `opportunity_version` lists `opportunity_version_append_only` and
   `opportunity_version_no_truncate`; an `UPDATE` of anything but `valid_to`, a `DELETE` and a
   `TRUNCATE` are each refused (inside `BEGIN ... ROLLBACK`).
4. Roles and grants identical to production: run the query below on both and `diff` the outputs (it is
   the query of `backend/tests/integration/test_restore_privileges_wp163.py`).
5. As the roles: `dgate_api` reads, has `statement_timeout` 5s and cannot write even in a read-write
   transaction (permission denied); `dgate_worker` updates rows, cannot `ALTER` or `TRUNCATE`, and can
   read every table (pg_dump); `dgate_app` reads the account tables.
6. The API against the restored database answers `/v1/health` (status ok), `/v1/tenders`,
   `/v1/buyers`, `/v1/opportunities`, `/v1/opportunities/{id}/versions`, `/v1/funding`.

```sql
SET default_transaction_read_only = on;
SELECT * FROM (
SELECT 'rel' AS kind, c.relname AS obj, a.grantee::regrole::text AS who, a.privilege_type AS priv
  FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a WHERE c.relnamespace = 'public'::regnamespace
UNION ALL
SELECT 'col', c.relname || '.' || t.attname, a.grantee::regrole::text, a.privilege_type
  FROM pg_attribute t JOIN pg_class c ON c.oid = t.attrelid CROSS JOIN LATERAL aclexplode(t.attacl) a
 WHERE c.relnamespace = 'public'::regnamespace
UNION ALL
SELECT 'schema', n.nspname, a.grantee::regrole::text, a.privilege_type
  FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a WHERE n.nspname = 'public'
UNION ALL
SELECT 'default:' || d.defaclobjtype::text, d.defaclnamespace::regnamespace::text, a.grantee::regrole::text,
       a.privilege_type
  FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) a
) p WHERE who IN ('dgate_api', 'dgate_worker', 'dgate_app') ORDER BY 1, 2, 3, 4;
SELECT 'role', r.rolname, r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolcanlogin, r.rolconnlimit,
       (SELECT array_agg(c ORDER BY c) FROM pg_db_role_setting s, unnest(s.setconfig) c
         WHERE s.setrole = r.oid AND s.setdatabase = 0)
  FROM pg_roles r WHERE r.rolname LIKE 'dgate%' ORDER BY 2;
SELECT 'owner', relkind, pg_get_userbyid(relowner), count(*) FROM pg_class
 WHERE relnamespace = 'public'::regnamespace GROUP BY 2, 3 ORDER BY 2, 3;
```
