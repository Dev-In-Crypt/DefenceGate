-- Archive timeline and call dates (data-quality plan of 12 October 2026, work package F).
-- Additive and idempotent: nothing is deleted and no existing row is rewritten.
--
-- 1. A fourth version-note kind, `remapped`.
--
--    A bulk correction re-derives status, value or dates from the payload a notice
--    already had: the source did not change, our reading of it did. The corrected
--    state is appended as a new version (the archive cannot be edited), and that
--    version is annotated `remapped` so it is not counted or listed as an
--    amendment by the notice's publisher. The three kinds of migration 0006 stay.
--    Dropping and re-creating the constraint changes a rule, not a row.
--
--      remapped   appended by a bulk re-derivation from the same source payload;
--                 the publisher did not amend anything
--
-- 2. `call.deadline_precision`: `date` when the source states the closing day and no
--    time (EU portal, NCBR at 00:00, French AID without an hour, BDNS), so the site
--    can print the date only and never claim a time the source did not state. The
--    deadline itself is stored as the end of that calendar day in the source's own
--    time zone, which keeps a call open through its last day.
--
-- 3. `opportunity.lot_count`: how many lots a notice has, where the source says. The
--    connector fills it (another work package); the column is created here as well,
--    IF NOT EXISTS, so the serving layer can read it whichever migration lands first.
--
-- 4. The Connecting Europe Facility as a seeded programme. Its military-mobility
--    topics ("Adaptation of the TEN-T to civilian-defence dual use") are in scope.

ALTER TABLE opportunity_version_note
    DROP CONSTRAINT IF EXISTS opportunity_version_note_kind_check;
ALTER TABLE opportunity_version_note
    ADD CONSTRAINT opportunity_version_note_kind_check
    CHECK (kind IN ('reread', 'out_of_order', 'correction', 'remapped'));

ALTER TABLE call ADD COLUMN IF NOT EXISTS deadline_precision TEXT;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'call_deadline_precision_check') THEN
        ALTER TABLE call ADD CONSTRAINT call_deadline_precision_check
            CHECK (deadline_precision IS NULL OR deadline_precision IN ('date', 'time'));
    END IF;
END
$$;

-- The Spanish register states `fechaFinSolicitud` as a day and nothing else, and has
-- been stored as the end of that day since it was first read: only the flag is new.
-- A flag on rows whose value is already right; no deadline is changed here.
UPDATE call
   SET deadline_precision = 'date'
  FROM source
 WHERE source.id = call.source_id AND source.code = 'es_bdns'
   AND call.deadline_at IS NOT NULL AND call.deadline_precision IS NULL;

ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS lot_count INTEGER;

INSERT INTO programme (code, name, period_start, period_end, legal_basis) VALUES
  ('CEF2027', 'Connecting Europe Facility (CEF)', '2021-01-01', '2027-12-31',
   'Regulation (EU) 2021/1153')
ON CONFLICT (code) DO NOTHING;
