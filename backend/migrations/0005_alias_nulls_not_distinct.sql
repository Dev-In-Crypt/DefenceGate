-- Make re-seeding the defence buyer list genuinely idempotent.
--
-- organisation_alias carried UNIQUE (normalised_name, country_hint, source_id).
-- Seeded aliases have no source, so source_id is NULL, and in a unique
-- constraint NULL is distinct from NULL: every row with a NULL passes. The
-- seeder's ON CONFLICT DO NOTHING therefore never fired, and each run added a
-- fresh copy of every seeded alias. Measured on 13 September 2026: a second
-- run turned 20 alias rows into 40. It went unnoticed until the worker started
-- seeding on every start, which would have grown the table without limit.
--
-- The duplicates removed below are exact copies -- same name, country, source
-- and organisation -- verified before this was written: no group pointed at two
-- different organisations. The guard makes this migration refuse to run if that
-- is ever not true, because deleting one of two disagreeing aliases would be a
-- silent entity-resolution decision, and those are never made silently here.

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM organisation_alias
     GROUP BY normalised_name, country_hint, source_id
    HAVING count(DISTINCT organisation_id) > 1
  ) THEN
    RAISE EXCEPTION 'organisation_alias has aliases that map one name to different '
                    'organisations; resolve them by hand before applying 0005';
  END IF;
END $$;

DELETE FROM organisation_alias a
 USING organisation_alias b
 WHERE a.id > b.id
   AND a.normalised_name = b.normalised_name
   AND a.country_hint IS NOT DISTINCT FROM b.country_hint
   AND a.source_id    IS NOT DISTINCT FROM b.source_id
   AND a.organisation_id = b.organisation_id;

ALTER TABLE organisation_alias
  DROP CONSTRAINT IF EXISTS organisation_alias_normalised_name_country_hint_source_id_key;

-- NULLS NOT DISTINCT (Postgres 15+) is the whole fix: two seeded aliases for the
-- same name and country now collide, as they always should have.
CREATE UNIQUE INDEX IF NOT EXISTS organisation_alias_name_country_source_uq
    ON organisation_alias (normalised_name, country_hint, source_id) NULLS NOT DISTINCT;
