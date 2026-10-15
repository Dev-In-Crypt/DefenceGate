-- /v1/changes (WP-10): the amendments of the last 14 days.
--
-- The query reads archive versions observed in a recent window. The table has no index on
-- `observed_at` (only (opportunity_id, version) and (opportunity_id, valid_from)), so it
-- reads every version and discards the old ones: 0.4-1.4 s for 544k versions on 15 October
-- 2026 (EXPLAIN ANALYZE on production, read-only), growing with the archive. This partial
-- covering index serves the window alone. Only versions after the first can be amendments,
-- so first versions (the larger share) are left out; `id`, `opportunity_id` and
-- `changed_fields` are carried so the scan is an index scan.
--
-- Measured on a synthetic table of the same size (a window of 2.4k real amendments after the
-- bulk re-derivation has left it): the version side goes from 245 ms to 3 ms and the planner
-- chooses the index by itself. While the 273k re-derived versions of 12-13 October are in the
-- window the planner keeps a sequential scan, as it should, and the index costs nothing.
--
-- Additive and idempotent; writes no row. A plain CREATE INDEX holds a write lock on
-- opportunity_version while it builds (a few seconds at this size).

CREATE INDEX IF NOT EXISTS oppver_observed
    ON opportunity_version (observed_at)
    INCLUDE (id, opportunity_id, changed_fields)
    WHERE version > 1;
