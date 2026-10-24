-- WP-114 (coverage audit of 24 October 2026): scheduled jobs leave a record, a data check in alert says since when, and
-- the raw record of a notice is found by index.
--
-- 1. job_run: one row per run of a scheduled job (worker.run_job), started and finished. The job history was only in
--    the container log, which a redeploy erases (logs of 24 Oct began at the 15:53 restart), and the start-up catch-up
--    covered the ingest jobs only, so a restart silently skipped ted_awards, digest, warm_lists and the other daily jobs
--    until the next day. The catch-up now reads this table (worker.catch_up_jobs) and /v1/health shows the last run of
--    each job. Derived operational data, not the archive: rows may be pruned.
CREATE TABLE IF NOT EXISTS job_run (
    id           BIGSERIAL PRIMARY KEY,
    job          TEXT NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    status       TEXT NOT NULL DEFAULT 'running'
                 CHECK (status IN ('running', 'success', 'partial', 'failed', 'interrupted')),
    detail       TEXT,
    -- the kind of process that ran it (db.RUN_KIND: `worker`, or `once-<job>` for a one-off container): a worker that
    -- starts closes only the scheduled worker's own runs as interrupted
    owner        TEXT
);
CREATE INDEX IF NOT EXISTS job_run_job_started ON job_run (job, started_at DESC);

GRANT SELECT ON job_run TO dgate_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON job_run TO dgate_worker;
GRANT USAGE ON SEQUENCE job_run_id_seq TO dgate_worker;

-- 2. Since when a control has been in alert (ops/controls._save keeps the first checked_at of an unbroken alert). Unknown
--    for an alert raised before this column existed: left empty, the sentence then names no time.
ALTER TABLE control_check ADD COLUMN IF NOT EXISTS alert_since TIMESTAMPTZ;

-- 3. The raw record of a notice by (source, native id): 'SELECT r.storage_key ... WHERE s.code = $1 AND r.native_id = $2'
--    read the 3.2 GB table sequentially, 9.5-13.3 s a lookup (pg_stat_statements, 24 Oct). About 15 million rows: on
--    production the orchestrator builds it CONCURRENTLY first (no write lock while a load runs; a few minutes, within
--    maintenance_work_mem 128MB); IF NOT EXISTS then makes this statement a no-op there:
--      CREATE INDEX CONCURRENTLY IF NOT EXISTS raw_source_native ON raw_ingest (source_id, native_id);
CREATE INDEX IF NOT EXISTS raw_source_native ON raw_ingest (source_id, native_id);

-- 4. raw_ingest had never been analysed (n_live_tup 937,926 against 15.3 million rows): the planner's estimates for it
--    were a sixteenth of the truth. ANALYZE reads a sample (30,000 rows), seconds.
ANALYZE raw_ingest;
