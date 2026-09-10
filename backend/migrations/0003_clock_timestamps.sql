-- Record when a thing actually happened, not when its transaction opened.
--
-- `now()` is transaction-scoped in Postgres: every call inside one transaction
-- returns the same instant, the moment the transaction began. Ingestion runs
-- inside a long transaction by design -- land raw, normalise, classify, archive,
-- committing periodically -- so every row written by a run was being stamped
-- with a single timestamp taken before any of the work happened.
--
-- Measured on 10 September 2026: a PLACSP run that had been going for forty
-- minutes and had written 1,938 payloads carried a finished_at three seconds
-- after its started_at. Every duration in the operational history was a
-- fiction, and a source gradually slowing down could never have shown up in it.
--
-- It matters most for observed_at. The archive's claim is that it records when
-- we first saw a notice say something; with now(), thousands of notices
-- observed across half an hour all claimed the same instant, and that instant
-- was not one at which any of them had been observed.
--
-- clock_timestamp() reads the wall clock at the moment of the call. Existing
-- rows are left as they are: they are wrong, but they are what was recorded,
-- and this archive does not rewrite history it has already written down.

ALTER TABLE ingest_run          ALTER COLUMN started_at  SET DEFAULT clock_timestamp();
ALTER TABLE raw_ingest          ALTER COLUMN fetched_at  SET DEFAULT clock_timestamp();
ALTER TABLE opportunity_version ALTER COLUMN observed_at SET DEFAULT clock_timestamp();
ALTER TABLE opportunity_version ALTER COLUMN valid_from  SET DEFAULT clock_timestamp();
