-- BOAMP: the link from a rectificatif to the notice it corrects, and the
-- marker a historical load leaves when the source stops it.
--
-- 1. related_native_id. A BOAMP "(rectificatif)" is a separate notice with its
--    own identifier that repeats the whole notice, and the record's own
--    `annonce_lie` column names the notice it corrects. 198 of the 4,185 French
--    defence rows are such notices, and each is listed next to its parent as if
--    it were a second tender (audit of 12 October 2026, finding F10). The column
--    holds the parent's native_id, within the same source. It is a link, not a
--    version-worthy fact: not in VERSIONED_FIELDS, and left out of the archived
--    payload while empty so no existing content hash moves.
--
-- 2. backfill_stop. The French history stopped on 23 September 2026 at HTTP 429
--    and was never resumed, so 1,534 official defence notices from 17 November
--    2020 to 20 September 2026 are missing (finding F14). backfill_day already
--    records which days finished, which is what makes a rerun continue where it
--    stopped; this records *why and until when* a run stopped, so the next run
--    does not walk straight back into the same rate limit. One row per source,
--    overwritten by the latest stop. Not ingest_run, for the reason stated in
--    0009: a history run must not look like daily collection.
--
-- Additive and idempotent.
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS related_native_id TEXT;

CREATE INDEX IF NOT EXISTS opp_related_native_id
    ON opportunity (source_id, related_native_id) WHERE related_native_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS backfill_stop (
    source_code  text        PRIMARY KEY,
    day          date,                       -- the day that was being loaded; it is not marked done
    reason       text        NOT NULL,
    stopped_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    resume_after timestamptz NOT NULL DEFAULT clock_timestamp()
);

COMMENT ON TABLE backfill_stop IS
    'The last time a historical load of a source was stopped by the source (HTTP 429/403) and when it may resume.';
