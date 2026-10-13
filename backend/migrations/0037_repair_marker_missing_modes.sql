-- `python -m dgate.ops.repair_ted` records, besides the notices it did, the ones it could
-- not do: a --refetch notice TED did not return (`refetch-missing`) and a --from-raw
-- notice with no stored payload for its current version (`raw-missing`). Without that a
-- run with --limit took the same first N notices again and again, and never reached the
-- rest. It also runs again after the mapper changed again as `--epoch N`, whose markers
-- are `raw#2`, `refetch#2-missing`, ... so that no marker has to be deleted.
--
-- The marker's mode column allowed exactly the two modes it was built with. The CHECK
-- is replaced by one that also lists the new ones (a relaxation: every row already there
-- still satisfies it). Idempotent: whatever CHECK on `mode` is there is replaced.
DO $$
DECLARE
    old_check TEXT;
BEGIN
    FOR old_check IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'ted_repair_marker'::regclass AND contype = 'c'
           AND pg_get_constraintdef(oid) LIKE '%mode%'
    LOOP
        EXECUTE format('ALTER TABLE ted_repair_marker DROP CONSTRAINT %I', old_check);
    END LOOP;
    ALTER TABLE ted_repair_marker ADD CONSTRAINT ted_repair_marker_mode_check_v2
        CHECK (mode ~ '^(raw|refetch)(#[0-9]{1,3})?(-missing)?$');
END $$;
