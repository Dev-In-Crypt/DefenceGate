-- The demand map (WP-66, `dgate/demand.py`): which defence-scope notices carry a CPV code under a given
-- division, group, class or category. Additive and idempotent: a function and an index, nothing dropped.
--
-- `dgate_cpv_heads(codes)` is every leading part of 2 to 8 digits of every code of a notice: 34352100 gives
-- 34, 343, 3435, 34352, 343521, 3435210, 34352100. A prefix question ("anything under 343") is then an array
-- overlap, `dgate_cpv_heads(o.cpv_codes) && ARRAY['343']`, which the GIN index below answers. The existing
-- `opp_cpv` index is on the codes themselves and answers only exact codes. Measured on production on
-- 22 October 2026 without this index: 1.47 s warm for six prefixes over five countries and three years, the
-- unnest of every candidate row's codes (177,070 rows) being the cost.
--
-- Partial on the defence scope, as every list index is: 388,802 rows, 2.1 codes each on average.
-- On production the orchestrator creates the function and then the index CONCURRENTLY first (no write lock on
-- `opportunity` while a load runs); IF NOT EXISTS then makes the index statement a no-op there:
--   CREATE INDEX CONCURRENTLY IF NOT EXISTS opp_cpv_heads ON opportunity USING gin (dgate_cpv_heads(cpv_codes)) WHERE is_defence AND NOT suppressed;
CREATE OR REPLACE FUNCTION dgate_cpv_heads(codes text[]) RETURNS text[]
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $f$
    SELECT COALESCE(array_agg(DISTINCT left(c, n)), '{}')
      FROM unnest(codes) AS c, generate_series(2, 8) AS n
     WHERE length(c) >= n
$f$;

CREATE INDEX IF NOT EXISTS opp_cpv_heads ON opportunity USING gin (dgate_cpv_heads(cpv_codes))
    WHERE is_defence AND NOT suppressed;
