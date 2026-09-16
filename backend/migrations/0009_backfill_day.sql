-- Progress of a historical load, one row per publication day.
--
-- The TED search API serves back to 2017, about seven million notices. That is
-- a load measured in days, not minutes, so it has to be resumable at whatever
-- point it stopped -- a restart, a network outage, a full disk. A day is the
-- unit because it is the unit the query asks for: a day either completed or it
-- did not, and a day that did not is simply asked for again.
--
-- Deliberately not ingest_run rows. Catch-up decides whether a source is fresh
-- from its last successful run, and a run that collected 3 June 2019 says
-- nothing about today; writing history into ingest_run would tell the worker
-- that daily collection had happened when it had not.

CREATE TABLE IF NOT EXISTS backfill_day (
    source_code text        NOT NULL,
    day         date        NOT NULL,
    notices     integer     NOT NULL DEFAULT 0,
    finished_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (source_code, day)
);

COMMENT ON TABLE backfill_day IS
    'One row per publication day fully loaded by a historical backfill.';
