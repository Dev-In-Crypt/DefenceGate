-- Backup freshness, readable by the public API without it seeing the backup volume.
-- The worker (which holds the volume and the object-store credentials) writes the
-- newest dump's time here every hour; /v1/health reads it and reports the age, never
-- a file name or a path. Found 14 October 2026: no usable dump for 47 hours went
-- unnoticed because nothing measured the age, only whether a job had failed.
CREATE TABLE IF NOT EXISTS backup_status (
    kind        TEXT PRIMARY KEY CHECK (kind IN ('local', 'offsite')),
    newest_at   TIMESTAMPTZ,            -- when the newest dump of that kind was taken
    checked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    alerted_at  TIMESTAMPTZ             -- last time the operator was told it is stale
);

GRANT SELECT ON backup_status TO dgate_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON backup_status TO dgate_worker;
