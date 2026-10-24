-- WP-98 (persona round of 23 October 2026, section C): the company search of /v1/suppliers (and of the global search)
-- finds the companies by name first and reads the award set for them only (`suppliers._filters`). The two names it
-- reads, folded as every search folds them (`dg_fold`, migration 0054), get trigram indexes like the tender titles
-- (0054) and the buyer names (0058). Additive and idempotent; no row is written. On production create them
-- CONCURRENTLY before this migration runs (IF NOT EXISTS then keeps it a no-op):
--   CREATE INDEX CONCURRENTLY IF NOT EXISTS organisation_name_fold ON organisation USING gin (dg_fold(canonical_name) gin_trgm_ops);
--   CREATE INDEX CONCURRENTLY IF NOT EXISTS award_name_fold ON award USING gin (dg_fold(name_as_stated) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS organisation_name_fold
    ON organisation USING gin (dg_fold(canonical_name) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS award_name_fold
    ON award USING gin (dg_fold(name_as_stated) gin_trgm_ops);
