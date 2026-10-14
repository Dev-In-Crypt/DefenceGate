-- The nightly backup failed on 14 October 2026 with "permission denied for table
-- app_login_token": pg_dump runs as dgate_worker, and migration 0027 took every
-- privilege on the account tables away from that role except what the digest job needs.
-- A backup that cannot read a table is not a backup of it.
--
-- The worker role gets SELECT (and only SELECT) on the account tables. What this exposes
-- to a compromise of the worker: e-mail addresses (already readable through app_user),
-- token and session hashes (never the secrets themselves), the throttle log and the
-- visit counters. The dump is encrypted before it leaves the host (docs/RUNBOOK.md,
-- backups) and the account tables are listed in docs/DATA_PROTECTION.md.
--
-- Written as "every table" so that a table a later migration adds and revokes for
-- hardening cannot silently drop out of the backup again; the integration test
-- test_the_worker_role_can_read_every_table_so_pg_dump_can fails if one does.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dgate_worker;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO dgate_worker;
