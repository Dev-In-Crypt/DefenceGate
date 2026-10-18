-- "Open to Ukrainian participants" as a derived flag on the call (WP-36, 18 October 2026).
-- Additive and idempotent. The pattern of 0066 (cascade).
--
-- `open_to_ukraine` is TRUE or FALSE only where something we hold says so, and NULL where nothing
-- does ("unknown" is not "no"). `open_to_ukraine_reason` says how it was decided and
-- `open_to_ukraine_evidence` is the sentence it rests on:
--   call_document   the verified fact `eligible_countries` read from the call document
--   topic_text      the same fact read from the topic's own conditions text
--   call_text       a sentence of the call's conditions text that names Ukraine
--   programme_rule  the regime's own Regulation decides (EDIP Ukraine Support Instrument: yes;
--                   EDIP Programme: no)
--   edf_association_unconfirmed  an EDF call; Ukraine's association to the EDF has no primary text
--                   we could read that says it is in force: unknown
--   not_stated      nothing states it: unknown
-- Filled by `dgate.ops.ukraine_flags` (nightly in the worker, after the cascade flags); derived
-- data, replaceable.
ALTER TABLE call ADD COLUMN IF NOT EXISTS open_to_ukraine BOOLEAN;
ALTER TABLE call ADD COLUMN IF NOT EXISTS open_to_ukraine_reason TEXT;
ALTER TABLE call ADD COLUMN IF NOT EXISTS open_to_ukraine_evidence TEXT;
ALTER TABLE call ADD COLUMN IF NOT EXISTS open_to_ukraine_decided_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS call_open_to_ukraine ON call (open_to_ukraine) WHERE open_to_ukraine IS TRUE;
