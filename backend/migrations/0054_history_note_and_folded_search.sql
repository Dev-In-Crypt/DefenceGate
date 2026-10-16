-- WP-20 (UX walk-throughs of 16 October 2026). Additive and idempotent; no row is rewritten.
--
-- 1. A fifth version-note kind, `history`.
--
--    A history load, the replay of an archive, a re-qualification or a backfill reads the
--    past: the version it writes records a change the publisher really made, but observed_at
--    is the day we read it. /v1/changes then listed "11,231 amendments in 14 days" that were
--    deadline moves of 2022. Such a version is annotated `history` when it is written (the
--    commands wrap themselves in `db.historical_load`) and `dgate.ops.tag_history` annotates
--    the ones written before this migration. The readers leave a `history` version out of the
--    changes page, the feeds, the digests and every amendment count; the tender page still
--    lists it, marked as an earlier change.
--
--      history   written by a command that loads the past; the change is older than the
--                observation
--
-- 2. Search that folds accents and punctuation both ways.
--
--    `dg_fold(text)` lower-cases, folds the accented Latin letters (and the letters NFKD does
--    not decompose: ł, ø, ß, đ, æ, œ ...) to their base letters, turns hyphens, slashes and
--    punctuation into single spaces, and puts one space in front, so that "Ausrüstung",
--    "Ausrustung" and "AUSRÜSTUNG" are one word and "off-road" and "off road" are one phrase.
--    `dg_word_pattern(text)` is the LIKE pattern of a search word that must begin a word
--    ('% word%'), with LIKE's own characters escaped. Both are IMMUTABLE so a trigram index can
--    be built over them; the query folds its input with the same SQL function, so the two
--    sides cannot disagree about a character. Letters outside the list (Cyrillic, Greek) are
--    only lower-cased, as before.

DO $$
DECLARE
    old_check TEXT;
BEGIN
    FOR old_check IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'opportunity_version_note'::regclass AND contype = 'c'
           AND pg_get_constraintdef(oid) LIKE '%kind%'
           AND pg_get_constraintdef(oid) NOT LIKE '%history%'
    LOOP
        EXECUTE format('ALTER TABLE opportunity_version_note DROP CONSTRAINT %I', old_check);
    END LOOP;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'opportunity_version_note'::regclass AND contype = 'c'
                      AND pg_get_constraintdef(oid) LIKE '%history%') THEN
        ALTER TABLE opportunity_version_note ADD CONSTRAINT opportunity_version_note_kind_check
            CHECK (kind IN ('reread', 'out_of_order', 'correction', 'remapped', 'history'));
    END IF;
END $$;

CREATE OR REPLACE FUNCTION dg_fold(t text) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $f$
    SELECT ' ' || btrim(regexp_replace(
        replace(replace(replace(replace(replace(replace(replace(
            translate(lower(coalesce(t, '')),
                'àáâãäåāăąçćĉċčďđèéêëēĕėęěĝğġģĥħìíîïĩīĭįıĵķĺļľŀłñńņňòóôõöøōŏőŕŗřśŝşšţťŧùúûüũūŭůűųŵýÿŷźżž',
                'aaaaaaaaacccccddeeeeeeeeegggghhiiiiiiiiijklllllnnnnooooooooorrrsssstttuuuuuuuuuuwyyyzzz'),
            'ß', 'ss'), 'æ', 'ae'), 'œ', 'oe'), 'þ', 'th'), 'ð', 'd'), 'ș', 's'), 'ț', 't'),
        $r$[\s\-–—/_.,;:()"'’]+$r$, ' ', 'g'))
$f$;

CREATE OR REPLACE FUNCTION dg_word_pattern(t text) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $f$
    SELECT '%' || replace(replace(replace(dg_fold(t), '\', '\\'), '%', '\%'), '_', '\_') || '%'
$f$;

CREATE INDEX IF NOT EXISTS opp_title_en_fold
    ON opportunity USING gin (dg_fold(title_en) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS opp_title_original_fold
    ON opportunity USING gin (dg_fold(title_original) gin_trgm_ops);
