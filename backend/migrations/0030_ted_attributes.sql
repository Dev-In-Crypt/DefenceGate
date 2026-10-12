-- TED mapping corrections of 12 October 2026 (docs/DATA_QUALITY_PLAN_2026-10-12.md,
-- findings F1 to F6 and F17). Additive and idempotent; nothing is removed.
--
-- Four attributes of a TED notice that the serving row did not carry:
--
--   notice_subtype        TED's own subtype ("16", "29", "E4"). It used to sit in
--                         procedure_type, where the API hides digits, so 101,603 of
--                         101,843 notices showed no procedure. procedure_type now
--                         holds the procedure TED names (open, restricted,
--                         neg-w-call, ...).
--   procedure_identifier  The procedure a notice belongs to. A re-publication or a
--                         corrigendum gets a new publication number but keeps it,
--                         which is how 555 rows in 224 groups are seen as one.
--   lot_count             How many lots the notice lists.
--   value_kind            Which of TED's value fields value_amount came from:
--                         total | estimated | lot_sum | first_lot.
--
-- None of them is version-worthy: they are not in VERSIONED_FIELDS and a change
-- to one writes no version. They are filled by `python -m dgate.ops.repair_ted`
-- for the notices already stored, and by the mapper for every new one.
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS notice_subtype       TEXT;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS procedure_identifier TEXT;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS lot_count            INT;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS value_kind           TEXT;

CREATE INDEX IF NOT EXISTS opp_procedure_identifier
    ON opportunity (procedure_identifier) WHERE procedure_identifier IS NOT NULL;

-- A bulk correction of our own mapping is annotated `remapped`, so that it is not
-- counted as an amendment by the source (migration 0006 explains the notes).
-- The constraint is widened only when it does not already allow the kind, so this
-- is safe to run before or after the same widening elsewhere.
DO $$
DECLARE
    existing TEXT;
BEGIN
    SELECT conname INTO existing
      FROM pg_constraint
     WHERE conrelid = 'opportunity_version_note'::regclass
       AND contype = 'c'
       AND pg_get_constraintdef(oid) LIKE '%correction%'
       AND pg_get_constraintdef(oid) NOT LIKE '%remapped%'
     LIMIT 1;
    IF existing IS NOT NULL THEN
        EXECUTE format('ALTER TABLE opportunity_version_note DROP CONSTRAINT %I', existing);
        ALTER TABLE opportunity_version_note
            ADD CONSTRAINT opportunity_version_note_kind_check
            CHECK (kind IN ('reread', 'out_of_order', 'correction', 'remapped'));
    END IF;
END
$$;

-- What `dgate.ops.repair_ted` has already done, per notice and mode, so an
-- interrupted run resumes where it stopped and a second run costs nothing.
CREATE TABLE IF NOT EXISTS ted_repair_marker (
    native_id  TEXT        NOT NULL,
    mode       TEXT        NOT NULL CHECK (mode IN ('raw', 'refetch')),
    done_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    version    INT,                 -- the version the repair wrote, if it wrote one
    PRIMARY KEY (native_id, mode)
);
