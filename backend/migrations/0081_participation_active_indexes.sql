-- WP-39 (verify2-abuse N4): the cold cost of the organisation partner tab.
--
-- The tab for the biggest organisation (CNRS, 4,336 projects, 9,663 partners) took 1.3-5.0 s cold on the
-- production host (the API role's budget is 5 s). It reads, for every project of the organisation, the other
-- active participants: `participation` through its unique (project_id, organisation_id) index, then the heap
-- row for `active`. These two partial indexes hold exactly the active rows with the columns the query needs, so
-- both reads are index-only. Measured on a copy of the production tables (386,193 participations, 12 MB each):
-- pages read from disk for the same query 9,835 -> 1,446 (the other 4,000 less come from joining the narrow
-- `organisation_network` instead of `organisation`, see `network_api._partner_ctes`); warm 264 ms -> 197 ms.
-- Index-only scans need the visibility map: the table changes only in the monthly loads, which autovacuum
-- follows.

CREATE INDEX IF NOT EXISTS participation_active_project
    ON participation (project_id) INCLUDE (organisation_id) WHERE active;
CREATE INDEX IF NOT EXISTS participation_active_org
    ON participation (organisation_id) INCLUDE (project_id) WHERE active;
ANALYZE participation;
