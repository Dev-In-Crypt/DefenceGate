-- WP-169: the visit counter's detail, written only while DGATE_STATS_DETAIL=1 (accounts._count_hits).
-- `route` stays the page key (`/tenders/[slug]`); `path` is the exact public path without the query (empty when not kept).
-- Rows made before this have it empty, which is what the counter writes with the switch off. Growth is capped in accounts.py
-- (a row ceiling per day, and paths and referrer hosts with few views folded after 30 days, `fold_old_hits`). The grants of
-- 0036 (dgate_app reads and writes) and 0042 (dgate_worker reads) cover the new column.
ALTER TABLE app_hit_daily ADD COLUMN IF NOT EXISTS path text NOT NULL DEFAULT '';
ALTER TABLE app_hit_daily DROP CONSTRAINT IF EXISTS app_hit_daily_pkey;
ALTER TABLE app_hit_daily ADD PRIMARY KEY (day, route, path, referrer, device);

-- The country Cloudflare assigns (CF-IPCountry), as its own daily total: never in a row with the page, the referrer or the
-- device, so no combination of them with a country is stored (a quiet day's row of one view would be too close to a visitor).
-- At most one row per day and code.
CREATE TABLE IF NOT EXISTS app_hit_country_daily (
    day      date NOT NULL,
    country  text NOT NULL CHECK (country ~ '^[A-Z][A-Z0-9]$'),
    hits     integer NOT NULL DEFAULT 0,
    PRIMARY KEY (day, country)
);
REVOKE ALL ON app_hit_country_daily FROM dgate_api, dgate_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON app_hit_country_daily TO dgate_app;
GRANT SELECT ON app_hit_country_daily TO dgate_worker;
