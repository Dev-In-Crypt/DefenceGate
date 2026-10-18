-- Layer 2, the read side (WP-28, 17 October 2026): organisation directory and profiles, project pages.
-- Additive and idempotent. Nothing is dropped, nothing in an entity or archive table is deleted.
--
--   dgate_live_org(id)       the organisation a row stands for now: follows `merged_into` to its end
--                            (at most 8 hops, as db._live). Participations are NOT re-pointed by a merge, so every
--                            reader of the network resolves through this.
--   dgate_merged_in(id)      the organisation and every organisation merged into it (the ids whose
--                            participations belong to it).
--   organisation_merged_live the 500-odd merged organisations with their live id: a set query joins this
--                            small view instead of calling the function once per participation row.
--   organisation_network     one row per LIVE organisation that took part in a project, with the headline
--                            figures of the directory. DERIVED and replaceable (like list_snapshot): the
--                            directory aggregate over `participation` took 2.2 s on a production-sized copy
--                            (400,000 participations, 450,000 organisations), against a 5 s budget and 1.5 s
--                            for this page. `networks.refresh_organisation_network()` rebuilds it after
--                            every load; the profile page reads the participations themselves, so its
--                            figures are never behind.

CREATE OR REPLACE FUNCTION dgate_live_org(org BIGINT) RETURNS BIGINT
    LANGUAGE sql STABLE AS $$
    WITH RECURSIVE chain(id, depth) AS (
        SELECT org, 0
        UNION ALL
        SELECT o.merged_into, c.depth + 1
          FROM chain c JOIN organisation o ON o.id = c.id
         WHERE o.merged_into IS NOT NULL AND c.depth < 8)
    SELECT id FROM chain ORDER BY depth DESC LIMIT 1
$$;

CREATE OR REPLACE FUNCTION dgate_merged_in(org BIGINT) RETURNS BIGINT[]
    LANGUAGE sql STABLE AS $$
    WITH RECURSIVE m(id, depth) AS (
        SELECT org, 0
        UNION ALL
        SELECT o.id, m.depth + 1
          FROM m JOIN organisation o ON o.merged_into = m.id
         WHERE m.depth < 8)
    SELECT array_agg(DISTINCT id) FROM m
$$;

-- Set-based, not `dgate_live_org(id)` per row: the function is a recursive query, and calling it for each of
-- the merged organisations cost 0.2 to 0.3 s in every query that joined the view.
-- `suppressed` is the flag of the merged-away row itself: a takedown aimed at a duplicate row must not resurface
-- through the row it was merged into.
CREATE OR REPLACE VIEW organisation_merged_live AS
    WITH RECURSIVE chain(id, live_id, depth, suppressed) AS (
        SELECT id, merged_into, 1, suppressed FROM organisation WHERE merged_into IS NOT NULL
        UNION ALL
        SELECT c.id, o.merged_into, c.depth + 1, c.suppressed
          FROM chain c JOIN organisation o ON o.id = c.live_id
         WHERE o.merged_into IS NOT NULL AND c.depth < 8)
    SELECT DISTINCT ON (id) id, live_id, suppressed FROM chain ORDER BY id, depth DESC;

CREATE TABLE IF NOT EXISTS organisation_network (
    organisation_id BIGINT PRIMARY KEY REFERENCES organisation(id),
    name            TEXT NOT NULL,                 -- as the sources state it (display name, else the key)
    country         CHAR(2) NOT NULL,
    projects        INT NOT NULL,                  -- distinct projects with an active participation
    coordinated     INT NOT NULL,                  -- of which as coordinator
    eu_contribution NUMERIC(16,2),                 -- EUR; CORDIS only, the EDF factsheets give none per entity
    first_year      SMALLINT,
    last_year       SMALLINT,
    programmes      TEXT[] NOT NULL DEFAULT '{}',  -- programme codes of those projects
    roles           TEXT[] NOT NULL DEFAULT '{}',  -- roles it held in them
    refreshed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS organisation_network_rank
    ON organisation_network (projects DESC, organisation_id);
CREATE INDEX IF NOT EXISTS organisation_network_name
    ON organisation_network (name, organisation_id);
CREATE INDEX IF NOT EXISTS organisation_network_country
    ON organisation_network (country, projects DESC, organisation_id);
-- The same folded, word-initial search as the tender and buyer lists (migrations 0054, 0058).
CREATE INDEX IF NOT EXISTS organisation_network_name_fold
    ON organisation_network USING gin (dg_fold(name) gin_trgm_ops);

GRANT SELECT ON organisation_network, organisation_merged_live TO dgate_api;
-- Derived data: the worker may replace it (DELETE for rows of an organisation that has left the network).
GRANT SELECT, INSERT, UPDATE, DELETE ON organisation_network TO dgate_worker;
GRANT SELECT ON organisation_merged_live TO dgate_worker;
