-- Resume marker of `python -m dgate.ops.remap_source`: one row per notice already
-- brought in line with the mappers of 12 October 2026, so an interrupted run resumes
-- and a second run writes nothing. Additive; nothing in it is a fact about a notice.
CREATE TABLE IF NOT EXISTS remap_marker (
    source_code TEXT NOT NULL,
    native_id   TEXT NOT NULL,
    version     INTEGER,
    done_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (source_code, native_id)
);
