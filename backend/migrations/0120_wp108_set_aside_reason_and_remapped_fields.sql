-- WP-108 (persona round 4, 24 October 2026). Additive and idempotent: two nullable columns, one note kind more; nothing
-- dropped or rewritten except the kind check, which is widened.
--
-- 1. award_notice.value_set_aside_reason   why `value_set_aside` was set aside (`award_value.SET_ASIDE_REASONS`):
--      estimate    over a hundred times the notice's own estimate (WP-103: World Aviation 220199-2026)
--      lots        over a hundred times, or exactly a thousand times, the sum of the notice's own lot or tender values
--                  (FASER 394720-2025: PLN 7,247,040,000 for tenders summing to PLN 7,247,040)
--      procedure   the same against the value another notice of the same procedure states (Imprensa Nacional Casa da
--                  Moeda 499753-2026: EUR 1,159,000,000 for a procedure estimated at EUR 1,450,000)
--    The rows WP-103 set aside were all of the first kind.
--
-- 2. opportunity_version_note.fields and the kind `remapped_fields`: a version in which some fields are DefenceGate's
--    own corrected reading and the rest a real change (persona p10, videoscopio 2812, 15 October 2026: value / 1.21,
--    legal basis and publication date back from the mapping of 12 October, and the status Open -> Awarded from the
--    buyer's award). `fields` lists the corrected fields; the version stays as written (notes only, never an update).
--    Readers that do not know the kind read the version as before, a change.

ALTER TABLE award_notice ADD COLUMN IF NOT EXISTS value_set_aside_reason TEXT;
UPDATE award_notice SET value_set_aside_reason = 'estimate'
 WHERE value_set_aside IS NOT NULL AND value_set_aside_reason IS NULL;

ALTER TABLE opportunity_version_note ADD COLUMN IF NOT EXISTS fields TEXT[];

DO $$
DECLARE
    old_check TEXT;
BEGIN
    FOR old_check IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'opportunity_version_note'::regclass AND contype = 'c'
           AND pg_get_constraintdef(oid) LIKE '%kind%'
           AND pg_get_constraintdef(oid) NOT LIKE '%remapped_fields%'
    LOOP
        EXECUTE format('ALTER TABLE opportunity_version_note DROP CONSTRAINT %I', old_check);
    END LOOP;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'opportunity_version_note'::regclass AND contype = 'c'
                      AND pg_get_constraintdef(oid) LIKE '%remapped_fields%') THEN
        ALTER TABLE opportunity_version_note ADD CONSTRAINT opportunity_version_note_kind_check
            CHECK (kind IN ('reread', 'out_of_order', 'correction', 'remapped', 'history', 'remapped_fields'));
    END IF;
END $$;
