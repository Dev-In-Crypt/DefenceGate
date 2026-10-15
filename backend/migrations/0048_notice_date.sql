-- WP-12 (15 October 2026): the entry's own notice date, kept apart from the publication date.
--
-- 12 % to 39 % of the PLACSP rows are folders whose stored entry is an award, a formalisation
-- or a cancellation: no call notice, so no publication date (`published_at` NULL). The date
-- the entry itself carries is a fact too, and it is not a publication date; it is stored and
-- served as its own labelled field.
--
--   notice_date   the date of the notice this version was read from
--   notice_kind   what that notice is: call | prior | award | formalisation |
--                 cancellation | update
--
-- Attributes, not version-worthy: not in VERSIONED_FIELDS, so a change to one writes no
-- version. Filled by the mapper for new entries and by
-- `python -m dgate.ops.remap_source --source es_placsp --epoch 2` for the stored ones.
-- Additive and idempotent.
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS notice_date DATE;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS notice_kind TEXT;
