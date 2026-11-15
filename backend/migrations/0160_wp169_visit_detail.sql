-- WP-169: the visit counter's detail, written only while DGATE_STATS_DETAIL=1 (accounts._count_hits).
-- `route` stays the page key (`/tenders/[slug]`); `path` is the exact public path without the query (empty when not kept),
-- `country` the two-letter code Cloudflare assigns (empty when not kept). Still aggregates: one row per day and key, no
-- address, no identifier, no user agent. Rows made before this have both empty, which is what the counter writes with the
-- switch off. Growth is capped in accounts.py (a row ceiling per day, and paths and referrer hosts with few views folded
-- after 30 days, `fold_old_hits`). The grants of 0036 (dgate_app reads and writes, dgate_worker reads) cover the new columns.
ALTER TABLE app_hit_daily ADD COLUMN IF NOT EXISTS path text NOT NULL DEFAULT '';
ALTER TABLE app_hit_daily ADD COLUMN IF NOT EXISTS country text NOT NULL DEFAULT '';
ALTER TABLE app_hit_daily DROP CONSTRAINT IF EXISTS app_hit_daily_pkey;
ALTER TABLE app_hit_daily ADD PRIMARY KEY (day, route, path, referrer, device, country);
