-- Classification signals and buyer entities (data-quality work package E, 12 October 2026).
-- Additive and idempotent: columns, an index, and a backfill of two derived booleans.
-- Nothing is dropped, nothing is deleted, no archive row is touched.
--
-- 1. The military CPV as a signal of its own. `sig_cpv` has meant "a division-35
--    CPV, military or civil" since the start, and the `core` scope read it, which
--    put a municipality's fire extinguishers one clearance flag away from the
--    default list. `core` now reads sig_cpv_military; sig_cpv stays as it was and
--    still corroborates.
-- 2. `dual_use` and `buyer_class`: a military CPV bought by a municipality, a
--    hospital, a school or a fire brigade is labelled, not rewritten. The signal
--    columns keep what the source and the rules said.
-- 3. `sig_linked_defence`: the TED twin of a national defence notice.
-- 4. Buyer identifiers and merges. `organisation.national_reg_no` (unique per
--    country since 0001) was never filled; TED's `buyer-identifier` fills it. A
--    merge never deletes: the absorbed row stays, marked `merged_into` with the
--    method and confidence, and its aliases remember where they came from.

ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS buyer_identifier     TEXT;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS sig_cpv_military     BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS sig_cpv_adjacent     BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS sig_linked_defence   BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS dual_use             BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS buyer_class          TEXT;

ALTER TABLE organisation ADD COLUMN IF NOT EXISTS merged_into              BIGINT REFERENCES organisation(id);
ALTER TABLE organisation ADD COLUMN IF NOT EXISTS merge_method             TEXT;
ALTER TABLE organisation ADD COLUMN IF NOT EXISTS merge_confidence         NUMERIC(3,2);
ALTER TABLE organisation ADD COLUMN IF NOT EXISTS merged_at                TIMESTAMPTZ;
ALTER TABLE organisation ADD COLUMN IF NOT EXISTS identifier_method        TEXT;
ALTER TABLE organisation ADD COLUMN IF NOT EXISTS identifier_confidence    NUMERIC(3,2);
-- Why an organisation is on the defence buyer list: the seed file, or a rule
-- over its name (dgate/buyer_vocab.py) with the rule's label and confidence.
ALTER TABLE organisation ADD COLUMN IF NOT EXISTS defence_buyer_source     TEXT;
ALTER TABLE organisation ADD COLUMN IF NOT EXISTS defence_buyer_reason     TEXT;
ALTER TABLE organisation ADD COLUMN IF NOT EXISTS defence_buyer_confidence NUMERIC(3,2);

ALTER TABLE organisation_alias ADD COLUMN IF NOT EXISTS prev_organisation_id BIGINT REFERENCES organisation(id);

CREATE INDEX IF NOT EXISTS organisation_merged_into
    ON organisation (merged_into) WHERE merged_into IS NOT NULL;
-- The exact-name stage of resolution and the seeding of the buyer lists both ask
-- "this country, this normalised name"; on 281,000 organisations that was a scan
-- per question, and the derived list asks about two thousand names at every worker
-- start.
CREATE INDEX IF NOT EXISTS organisation_country_name
    ON organisation (country, lower(canonical_name));
CREATE INDEX IF NOT EXISTS opp_linked_defence
    ON opportunity (id) WHERE sig_linked_defence;

-- Backfill the two CPV booleans for rows that predate them. The same rule as
-- dgate.classify (groups 353 to 358 except the three civil exceptions, and the
-- four added exact codes); tests/unit/test_buyer_classes.py keeps the two in step.
-- Only ever sets TRUE, so a second run changes nothing.
UPDATE opportunity SET sig_cpv_adjacent = TRUE
 WHERE NOT sig_cpv_adjacent
   AND cpv_codes && ARRAY['45216200', '50640000', '75220000', '75221000']::text[];

UPDATE opportunity SET sig_cpv_military = TRUE
 WHERE NOT sig_cpv_military
   AND (sig_cpv_adjacent
        OR EXISTS (SELECT 1 FROM unnest(cpv_codes) c
                    WHERE c ~ '^35[3-8]'
                      AND c NOT IN ('35811100', '35811200', '35821000')));
