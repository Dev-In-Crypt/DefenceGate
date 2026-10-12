-- Where a PLACSP live walk must reach back to.
--
-- The feed has no date parameter; it is a chain of files walked from the newest
-- backwards, and a fixed page count is all that said how far. When the provider
-- froze for four days and then published 8,272 entries at once (9 October 2026),
-- the burst took 17 of the 20 pages and a longer freeze would have pushed its
-- oldest entries beyond the walk, unread and unremarked.
--
-- A run that completed its walk now records the timestamp of the newest entry it
-- saw, and the next run walks until a page's oldest entry is no newer than that.
-- A run that stopped short of its target (page cap, refused link) or failed leaves
-- the column empty, so the mark that stands is always one every older entry lies
-- behind, and the gap stays the next run's to close.
--
-- Additive and nullable: existing rows and the other sources are unaffected.

ALTER TABLE ingest_run ADD COLUMN IF NOT EXISTS newest_entry_at timestamptz;

COMMENT ON COLUMN ingest_run.newest_entry_at IS
    'PLACSP live walks: the newest atom:updated the run saw, set only when the walk reached the previous run''s mark.';
