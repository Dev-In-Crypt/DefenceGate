-- Account hardening, from the independent security review of the account system
-- (13 October 2026, findings H2 and M4). Additive and idempotent.
--
-- H2: the sign-in throttle prunes rows older than a day at the start of the request path,
-- by time; the index makes that a range scan instead of a pass over the table.
CREATE INDEX IF NOT EXISTS app_auth_event_at ON app_auth_event (at);

-- M4: `dgate_app` is the role the account endpoints connect as. Migration 0027 gave it
-- SELECT on every table, present and future, "to build dashboards". That makes a single
-- injection or logic bug in the account code a read of everything the archive holds:
-- raw_ingest (payloads with contact data landed before the sweeps), ingest_run,
-- schema_migrations, the enrichment tables. It reads exactly the tables the dashboard and
-- the hydrated lists read (accounts.py through tenders.py, funding.py and the helpers they
-- call), and its own app_* tables. Nothing else.
REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM dgate_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM dgate_app;

-- What the account code reads of the public data.
GRANT SELECT ON opportunity, opportunity_version, opportunity_version_note,
                call, programme, source, organisation TO dgate_app;

-- Its own tables: the REVOKE above took SELECT back with the rest, and 0027 granted the
-- write privileges, which stay.
GRANT SELECT, INSERT, UPDATE, DELETE ON app_user, app_login_token, app_session, app_auth_event,
    app_disposable_domain, app_saved_search, app_shortlist, app_follow, app_hit_daily TO dgate_app;
