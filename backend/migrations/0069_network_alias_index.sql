-- WP-28: the profile lists the names an organisation is known by (`organisation_alias.organisation_id = ANY(...)`).
-- The table had no index on that column: 432,000 rows were read for every profile (26 s on a loaded host with the
-- family computed per row, 0.3 s with it as a parameter). Plain CREATE INDEX: the table is small enough that the
-- write lock lasts about a second; on production it may be created CONCURRENTLY beforehand (IF NOT EXISTS keeps this idempotent).
CREATE INDEX IF NOT EXISTS organisation_alias_org ON organisation_alias (organisation_id);
