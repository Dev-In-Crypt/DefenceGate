-- Compacting one-object-per-notice payloads into bundles.
--
-- The TED history was first written one object per notice, 4.8 million of them,
-- which object storage bills as 4.8 million writes and about 55 GB. Compaction
-- rewrites them as day-sized gzipped bundles and then deletes the originals.
-- Two things make the deletion safe rather than hopeful.
--
-- An index on the keys still written one object at a time, so that "does any
-- row still point at this object?" is a lookup and not a scan of nine million
-- rows. Partial: a compacted row leaves the index as its key gains a #line,
-- so the index shrinks to nothing as the work it serves is done.
--
-- A journal of objects waiting to be deleted, written in the same transaction
-- that repoints the rows. Deletion happens after that commit; if the process
-- dies in between, the journal says exactly what is left to delete, instead of
-- leaving orphans nobody knows about.

CREATE INDEX IF NOT EXISTS raw_plain_key ON raw_ingest (storage_key)
    WHERE storage_key NOT LIKE '%#%';

CREATE TABLE IF NOT EXISTS compaction_pending (
    storage_key text        PRIMARY KEY,
    bundle      text        NOT NULL,
    queued_at   timestamptz NOT NULL DEFAULT clock_timestamp()
);

COMMENT ON TABLE compaction_pending IS
    'Objects already copied into a verified bundle, repointed, and awaiting deletion.';
