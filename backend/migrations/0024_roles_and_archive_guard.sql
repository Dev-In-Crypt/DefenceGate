-- Least privilege for the public API and the worker, and a wider archive guard.
-- Found by the security review of 12 October 2026 (docs/SECURITY_REVIEW_2026-10-12.md):
-- the API, the worker and the migrator all connected as one Postgres superuser, so
-- any injection or code-execution bug in an anonymous endpoint was full control,
-- including switching the archive trigger off.
--
-- dgate_api     SELECT only; read-only transactions; a 5 s statement budget; 30
--               connections at most. What a public, unauthenticated process needs.
-- dgate_worker  Reads and writes rows, nothing else: no DDL, no TRUNCATE, not a
--               superuser. CREATEDB only so the weekly restore check can build and
--               drop its own scratch database.
-- The owner role stays with `migrate` and is not used by a running service.
--
-- Roles are created without a login; dgate.migrate gives them one when
-- DGATE_API_PASSWORD / DGATE_WORKER_PASSWORD are set, so no password is in SQL.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dgate_api') THEN
        CREATE ROLE dgate_api NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dgate_worker') THEN
        CREATE ROLE dgate_worker NOLOGIN CREATEDB;
    END IF;
END
$$;

ALTER ROLE dgate_api SET statement_timeout = '5s';
ALTER ROLE dgate_api SET default_transaction_read_only = on;
ALTER ROLE dgate_api SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE dgate_api CONNECTION LIMIT 30;

ALTER ROLE dgate_worker SET idle_in_transaction_session_timeout = '30min';

GRANT USAGE ON SCHEMA public TO dgate_api, dgate_worker;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dgate_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO dgate_worker;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO dgate_worker;

-- Tables a later migration creates are covered without remembering to grant.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO dgate_api;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dgate_worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO dgate_worker;

-- The row trigger of 0001 refuses UPDATE and DELETE; TRUNCATE is a statement and
-- slipped past it. Refused here too. The bypass is a session setting so that the
-- test suite, which starts every test from empty tables, and a deliberate restore
-- can say so out loud; the roles above have no TRUNCATE privilege at all, which is
-- the protection that matters.
CREATE OR REPLACE FUNCTION archive_no_truncate() RETURNS trigger AS $$
BEGIN
    IF current_setting('dgate.allow_truncate', true) IS DISTINCT FROM 'on' THEN
        RAISE EXCEPTION '% is append-only: TRUNCATE is not permitted', TG_TABLE_NAME;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS opportunity_version_no_truncate ON opportunity_version;
CREATE TRIGGER opportunity_version_no_truncate
    BEFORE TRUNCATE ON opportunity_version
    FOR EACH STATEMENT EXECUTE FUNCTION archive_no_truncate();

-- A version cannot close before it opens. Existing rows were checked: none
-- violates it (148,940 rows, 11 October 2026).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'opportunity_version_interval') THEN
        ALTER TABLE opportunity_version
            ADD CONSTRAINT opportunity_version_interval
            CHECK (valid_to IS NULL OR valid_to > valid_from);
    END IF;
END
$$;
