-- WP-159 (30 October 2026): the contract period a notice states, and two source licence texts. Additive and idempotent.
--
-- The buyer's stated period, from the notice itself (normalise.contract_period): eForms BT-536 start, BT-537 end,
-- BT-36 duration, BT-57/58 renewal (TED, BKMS, BOAMP eForms), PLACSP's PlannedPeriod and ContractExtension. Several
-- lots: the earliest start, the latest end, the longest duration as stated, the most renewals. Never a forecast.
--
--   contract_start          date the contract starts, as stated
--   contract_end            date it ends, as stated
--   contract_duration       the duration as stated (a whole number of contract_duration_unit)
--   contract_duration_unit  DAY | WEEK | MONTH | YEAR
--   contract_renewal        TRUE when a renewal or extension is stated; NULL when nothing is said
--   contract_renewals_max   the most renewals the notice allows (BT-58)
--
-- Attributes, not version-worthy: not in VERSIONED_FIELDS, so stating one writes no version (db.upsert_opportunity).
-- New notices get them from the mappers; the stored ones from `python -m dgate.ops.contract_periods` (raw store,
-- BKMS and BOAMP), `ops.repair_ted --refetch` (TED) and a PLACSP archive replay. The checks are NOT VALID: the
-- columns are new, so there is nothing to scan, and every write from now on is checked.
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS contract_start DATE;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS contract_end DATE;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS contract_duration INTEGER;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS contract_duration_unit TEXT;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS contract_renewal BOOLEAN;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS contract_renewals_max SMALLINT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'opportunity_contract_period_check') THEN
        ALTER TABLE opportunity ADD CONSTRAINT opportunity_contract_period_check CHECK (
            (contract_duration IS NULL OR contract_duration > 0)
            AND (contract_duration_unit IS NULL OR contract_duration_unit IN ('DAY', 'WEEK', 'MONTH', 'YEAR'))
            AND (contract_duration IS NULL) = (contract_duration_unit IS NULL)
            AND (contract_renewals_max IS NULL OR contract_renewals_max >= 0)) NOT VALID;
    END IF;
END
$$;

-- docs/research/DATA_LICENCES_2026-10-27.md ("Database rows that no longer match this reading"): both operators publish
-- their data as CC0. Vinnova's text was corrected by 0026; set again here so a database that missed it agrees. BKMS
-- stays inactive with commercial_ok NULL: switching it on is the owner's decision (GDPR items open).
UPDATE source
   SET licence = 'CC0 (Vinnova open data: free use without fees or other restrictions)',
       attribution = 'Källa: Vinnova, öppna data (CC0)'
 WHERE code = 'se_vinnova'
   AND licence IS DISTINCT FROM 'CC0 (Vinnova open data: free use without fees or other restrictions)';

UPDATE source
   SET licence = 'CC0 1.0 (Open-Data-Richtlinie of oeffentlichevergabe.de, section 4: Creative Commons CC Zero)'
 WHERE code = 'de_bkms'
   AND licence IS DISTINCT FROM 'CC0 1.0 (Open-Data-Richtlinie of oeffentlichevergabe.de, section 4: Creative Commons CC Zero)';
