-- Re-normalise stored organisation names after normalise_org_name() learned to
-- transliterate letters that NFKD does not decompose (Polish ł, Danish ø,
-- German ß, and the rest of _TRANSLITERATE in dgate/normalise.py).
--
-- Before this, "Oddział ... w Białymstoku" from Atlas Przetargow and "Oddzial
-- ... w Bialymstoku" from TED resolved to two organisations. Rewriting the
-- stored names lets new ingests find the existing rows again. It does not, and
-- must not, merge the duplicates that already exist: entity resolution never
-- merges without a stored method and confidence, and a merge would have to
-- repoint opportunity.buyer_org_id underneath an archive whose history refers
-- to the old id. Collisions are written to organisation_merge_candidate for a
-- person to decide.
--
-- What is re-normalised is the stored normal form, not the raw name: organisation
-- has no raw name, and the alias normal form is what lookups match against. The
-- stored form is already lowercased, punctuation-collapsed and legal-form
-- stripped, so the new form is: transliterate, then strip legal forms again,
-- because a token such as "społka akcyjna" only becomes a legal form once ł is
-- l. Only rows that contain one of the transliterated letters are touched.
--
-- Safe to run again: a second pass finds nothing to transliterate. The
-- integration suite re-executes this file against rows written in the old form
-- and checks the result against the Python normaliser.
--
-- opportunity_version is not read or written here.

CREATE TABLE IF NOT EXISTS organisation_merge_candidate (
    id                BIGSERIAL PRIMARY KEY,
    organisation_id   BIGINT NOT NULL REFERENCES organisation(id),
    candidate_org_id  BIGINT NOT NULL REFERENCES organisation(id),
    match_method      TEXT NOT NULL,
    confidence        NUMERIC(3,2) NOT NULL,
    evidence          TEXT NOT NULL,
    -- pending | merged | rejected; nothing but a reviewer moves it off pending
    status            TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'merged', 'rejected')),
    detected_by       TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at        TIMESTAMPTZ,
    CHECK (organisation_id < candidate_org_id),
    UNIQUE (organisation_id, candidate_org_id, match_method)
);

CREATE INDEX IF NOT EXISTS merge_candidate_pending
    ON organisation_merge_candidate (status) WHERE status = 'pending';

-- The same table as _TRANSLITERATE. Kept temporary so the schema does not grow a
-- second normaliser that could drift from the Python one.
CREATE OR REPLACE FUNCTION pg_temp.dgate_transliterate(s TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT replace(replace(replace(replace(replace(replace(replace(replace(
           translate(s, 'łŁøØđĐħĦðÐı', 'llooddhhddi'),
           'ß', 'ss'), 'ẞ', 'ss'),
           'æ', 'ae'), 'Æ', 'ae'),
           'œ', 'oe'), 'Œ', 'oe'),
           'þ', 'th'), 'Þ', 'th')
$$;

-- _LEGAL_FORMS, longest first as in the Python loop, and only the forms that can
-- still occur in a stored name: stored names have no dots, commas or slashes left.
CREATE OR REPLACE FUNCTION pg_temp.dgate_renormalise(s TEXT) RETURNS TEXT
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    form TEXT;
BEGIN
    s := pg_temp.dgate_transliterate(s);
    FOREACH form IN ARRAY ARRAY[
        'sociedad limitada', 'sociedad anonima', 'spolka akcyjna', 'unipessoal',
        'sp z oo', 'limited', 'gmbh', 'corp', 'sarl', 'sasu', 'eurl', 'ohg',
        'mbh', 'srl', 'spa', 'uab', 'oyj', 'aps', 'tov', 'pat', 'fop', 'ltd',
        'plc', 'llc', 'inc', 'sas', 'lda', 'sro', 'sa', 'sl', 'ag', 'kg', 'bv',
        'nv', 'ab', 'as', 'oy']
    LOOP
        s := regexp_replace(s, '(^|\s)' || form || '(\s|$)', ' ', 'g');
    END LOOP;
    RETURN btrim(regexp_replace(s, '\s+', ' ', 'g'));
END
$$;

-- ------------------------------------------------------------ organisation

CREATE TEMP TABLE org_renamed ON COMMIT DROP AS
SELECT id, country, canonical_name AS old_name,
       pg_temp.dgate_renormalise(canonical_name) AS new_name
  FROM organisation
 WHERE pg_temp.dgate_transliterate(canonical_name) <> canonical_name;

UPDATE organisation o
   SET canonical_name = r.new_name
  FROM org_renamed r
 WHERE o.id = r.id AND r.new_name <> '';

-- Two organisations in one country now sharing a canonical name, at least one of
-- them renamed here. 0.90: the exact-name stage would have linked them at 0.95
-- had the normaliser been right, less a margin because the old rows may have been
-- seeded or corrected by hand under the name they carry.
INSERT INTO organisation_merge_candidate
    (organisation_id, candidate_org_id, match_method, confidence, evidence, detected_by)
SELECT DISTINCT ON (LEAST(r.id, o.id), GREATEST(r.id, o.id))
       LEAST(r.id, o.id), GREATEST(r.id, o.id),
       'transliteration_fold', 0.90,
       format('canonical_name %L and %L both normalise to %L in %s',
              r.old_name,
              COALESCE((SELECT old_name FROM org_renamed x WHERE x.id = o.id), o.canonical_name),
              r.new_name, r.country),
       '0005_transliterate_org_names'
  FROM org_renamed r
  JOIN organisation o
    ON o.country = r.country AND o.canonical_name = r.new_name AND o.id <> r.id
 WHERE r.new_name <> ''
 ORDER BY LEAST(r.id, o.id), GREATEST(r.id, o.id)
ON CONFLICT (organisation_id, candidate_org_id, match_method) DO NOTHING;

-- ------------------------------------------------------ organisation_alias

CREATE TEMP TABLE alias_renamed ON COMMIT DROP AS
SELECT a.id, a.organisation_id, a.country_hint, a.source_id,
       a.normalised_name AS old_name,
       pg_temp.dgate_renormalise(a.normalised_name) AS new_name
  FROM organisation_alias a
 WHERE pg_temp.dgate_transliterate(a.normalised_name) <> a.normalised_name;

-- The unique key is (normalised_name, country_hint, source_id). An alias can only
-- take its new name if no other row holds that key afterwards: not an untouched
-- row that already had it, and not an earlier renamed row claiming it too. NULLs
-- are distinct in that index, so rows with a NULL country_hint or source_id never
-- collide and are always renamed.
CREATE TEMP TABLE alias_blocked ON COMMIT DROP AS
SELECT r.id, r.organisation_id, r.old_name, r.new_name, r.country_hint,
       holder.id AS holder_alias_id, holder.organisation_id AS holder_org_id
  FROM alias_renamed r
  JOIN LATERAL (
        -- an untouched row with the key wins over an earlier renamed one, since
        -- that renamed row is then blocked as well
        SELECT 0 AS rank, a.id, a.organisation_id
          FROM organisation_alias a
         WHERE a.normalised_name = r.new_name
           AND a.country_hint = r.country_hint
           AND a.source_id = r.source_id
           AND a.id NOT IN (SELECT id FROM alias_renamed)
        UNION ALL
        SELECT 1, r2.id, r2.organisation_id
          FROM alias_renamed r2
         WHERE r2.new_name = r.new_name
           AND r2.country_hint = r.country_hint
           AND r2.source_id = r.source_id
           AND r2.id < r.id
         ORDER BY 1, 2
         LIMIT 1
       ) holder ON TRUE
 WHERE r.new_name <> '';

-- A blocked alias keeps its old normal form. The row is not deleted, because its
-- raw_name is a name variant and aliases are kept forever; it simply stops
-- matching, and the holder row answers the lookup instead. When the holder points
-- at a different organisation, that is a merge question for a person.
UPDATE organisation_alias a
   SET normalised_name = r.new_name
  FROM alias_renamed r
 WHERE a.id = r.id
   AND r.new_name <> ''
   AND r.id NOT IN (SELECT id FROM alias_blocked);

INSERT INTO organisation_merge_candidate
    (organisation_id, candidate_org_id, match_method, confidence, evidence, detected_by)
SELECT DISTINCT ON (LEAST(b.organisation_id, b.holder_org_id),
                    GREATEST(b.organisation_id, b.holder_org_id))
       LEAST(b.organisation_id, b.holder_org_id),
       GREATEST(b.organisation_id, b.holder_org_id),
       'alias_transliteration_fold', 0.90,
       format('alias %s (%L) and alias %s both normalise to %L in %s; alias %s left unchanged',
              b.id, b.old_name, b.holder_alias_id, b.new_name, b.country_hint, b.id),
       '0005_transliterate_org_names'
  FROM alias_blocked b
 WHERE b.organisation_id <> b.holder_org_id
 ORDER BY LEAST(b.organisation_id, b.holder_org_id),
          GREATEST(b.organisation_id, b.holder_org_id), b.id
ON CONFLICT (organisation_id, candidate_org_id, match_method) DO NOTHING;

DO $$
DECLARE
    n_org INT; n_alias INT; n_blocked INT; n_pending INT;
BEGIN
    SELECT count(*) INTO n_org FROM org_renamed WHERE new_name <> '';
    SELECT count(*) INTO n_alias FROM alias_renamed WHERE new_name <> '';
    SELECT count(*) INTO n_blocked FROM alias_blocked;
    SELECT count(*) INTO n_pending FROM organisation_merge_candidate
     WHERE detected_by = '0005_transliterate_org_names' AND status = 'pending';
    RAISE NOTICE '0005: % organisation name(s) and % alias(es) re-normalised, '
                 '% alias(es) left in old form on key collision, '
                 '% merge candidate(s) pending review',
                 n_org, n_alias - n_blocked, n_blocked, n_pending;
END
$$;
