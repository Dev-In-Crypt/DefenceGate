-- Which process opened an ingest run (internal audit M7, 14 October 2026).
--
-- `close_interrupted_runs` ran at every worker start and failed every run still
-- `running`, including the ones an operator's container (a backfill, a replay) had
-- open: until the run's own `finish_run` overwrote it, health and catch-up read a false
-- `failed`, and a catch-up could start a duplicate. The run now says whose it is:
-- `<kind>:<host>:<pid>`, kind `worker` for the scheduled worker and `cli` otherwise, and
-- start-up closes only its own kind (plus anything older than a day).
-- Additive; NULL on the runs that were written before.
ALTER TABLE ingest_run ADD COLUMN IF NOT EXISTS owner TEXT;
