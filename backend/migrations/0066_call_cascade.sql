-- Cascade funding (financial support to third parties, FSTP) as a derived flag on the call
-- (WP-31, 17 October 2026). Additive and idempotent.
--
-- `cascade` is TRUE or FALSE only where something we hold says so, and NULL where nothing does
-- ("not determined" is not "no"). `cascade_reason` says how it was decided and
-- `cascade_evidence` is the sentence it rests on:
--   call_document   a verified fact `cascade_funding` read from the call document
--   topic_text      the same fact read from the topic's own conditions text
--   call_text       a sentence of the call's conditions text that states it
--   call_document_other_topic  the document allows it for other topics only
--   not_stated      nothing states it (the mention is only the title of an annex or a guide)
-- The work programme's general annexes never decide it: whether a call has FSTP is that call's own rule.
-- Filled by `dgate.ops.cascade_flags` (nightly in the worker); derived data, replaceable.
ALTER TABLE call ADD COLUMN IF NOT EXISTS cascade BOOLEAN;
ALTER TABLE call ADD COLUMN IF NOT EXISTS cascade_reason TEXT;
ALTER TABLE call ADD COLUMN IF NOT EXISTS cascade_evidence TEXT;
ALTER TABLE call ADD COLUMN IF NOT EXISTS cascade_decided_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS call_cascade ON call (cascade) WHERE cascade IS TRUE;
