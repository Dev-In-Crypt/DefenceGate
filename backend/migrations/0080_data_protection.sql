-- WP-39 (verify2-abuse, 18 October 2026): two flags that let the public read side leave out what it must not show.
--
--   organisation.individual_reason   why the organisation is treated as a natural person (a sole trader or a
--                                    freelancer registered under their own name in CORDIS or an EDF factsheet).
--                                    NULL = not one. Set by `dgate.individuals.mark_individuals` (run with every
--                                    directory refresh); nothing is deleted: the row, its participations and its
--                                    aliases stay, the directory, the profile (410), the partner lists, the
--                                    project member lists and the sitemap do not show it.
--   award.excluded_reason            why a winner string of a TED result notice is no supplier (a placeholder, a
--                                    consortium written as one name, garbled text, contact details in the name).
--                                    NULL = a supplier. Set by `dgate.ops.clean_suppliers` for rows stored before
--                                    the loader refused them (N8). The row is kept; every supplier query skips it.
--
-- `organisation_merged_live.suppressed` is the flag of the merged-away row itself ("a takedown aimed at a
-- duplicate must not resurface through the row it was merged into", 0068); an individual merged away is the
-- same: the view now reports either.

ALTER TABLE organisation ADD COLUMN IF NOT EXISTS individual_reason text;
ALTER TABLE award ADD COLUMN IF NOT EXISTS excluded_reason text;

CREATE OR REPLACE VIEW organisation_merged_live AS
    WITH RECURSIVE chain(id, live_id, depth, suppressed) AS (
        SELECT id, merged_into, 1, (suppressed OR individual_reason IS NOT NULL)
          FROM organisation WHERE merged_into IS NOT NULL
        UNION ALL
        SELECT c.id, o.merged_into, c.depth + 1, c.suppressed
          FROM chain c JOIN organisation o ON o.id = c.live_id
         WHERE o.merged_into IS NOT NULL AND c.depth < 8)
    SELECT DISTINCT ON (id) id, live_id, suppressed FROM chain ORDER BY id, depth DESC;

-- A suppression must reach what was derived from the organisation (verify2-abuse N3): the directory table
-- `organisation_network` (the list, its count, the sitemap slugs and, since WP-39, the partner lists) is
-- rebuilt only after a CORDIS or EDF load, so a removal left the name, country, project count and EU amount
-- there for up to a month. As with the buyer families (0055), the flag itself deletes the rows, whoever sets
-- it. The whole merge family goes: the live row counts the participations of the one that was suppressed, and
-- the next rebuild writes it again without them.
CREATE OR REPLACE FUNCTION dgate_network_drop_suppressed() RETURNS trigger AS $$
BEGIN
    DELETE FROM organisation_network
     WHERE organisation_id = ANY(dgate_merged_in(dgate_live_org(NEW.id)));
    RETURN NULL;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS organisation_network_drop ON organisation;
CREATE TRIGGER organisation_network_drop AFTER UPDATE OF suppressed ON organisation
    FOR EACH ROW WHEN (NEW.suppressed) EXECUTE FUNCTION dgate_network_drop_suppressed();
