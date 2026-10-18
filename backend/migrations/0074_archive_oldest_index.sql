-- /v1/health reports the oldest observation of the archive. `min(observed_at)` read every
-- version (a parallel scan of 650k rows, 3.5 to 5.2 s on production on 17 October 2026, over
-- the API role's 5 s budget on a busy host). The only index on `observed_at`, `oppver_observed`
-- (0046), leaves out first versions, so it cannot answer it. A plain index makes the minimum an
-- index read. Additive and idempotent; writes no row. Like 0046 it holds a write lock on
-- opportunity_version while it builds (a few seconds at this size, about 15 MB).
CREATE INDEX IF NOT EXISTS oppver_observed_all ON opportunity_version (observed_at);
