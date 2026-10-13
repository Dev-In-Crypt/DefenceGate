-- The market overview (`/v1/stats/market`) counts core-scope notices by publication
-- month, country and source over 12 to 36 months. Through `opp_published` that was a
-- bitmap heap scan of every notice published in the window, whatever its scope: 99,000
-- rows read to count 25,000 (3.8 s with a cold cache on 13 October 2026, against the
-- API role's 5 s budget).
--
-- A partial index holding only the core-scope rows (the same predicate `CORE_SQL` and the
-- tenders list use), in publication order, carrying the three columns those counts group
-- by. Additive; writes nothing; a second run does nothing.
--
-- `cpv_codes` is deliberately not included: it is an array a notice with hundreds of lots
-- can make longer than an index entry may be.
CREATE INDEX IF NOT EXISTS opp_core_published
    ON opportunity (published_at)
    INCLUDE (source_id, country, deadline_at)
    WHERE is_defence AND (sig_legal_basis OR (sig_cpv_military AND NOT dual_use));
