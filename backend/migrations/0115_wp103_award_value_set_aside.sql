-- WP-103 (persona round of 24 October 2026): an award figure set aside as implausible. Additive and idempotent: one
-- nullable column, nothing dropped or rewritten.
--
--   award_notice.value_set_aside   the figure a TED result notice states that its own estimate puts over a hundred
--                                  times lower (a billion or more: an entry in the wrong unit, `award_value.contradicted`).
--                                  The notice's value is then its estimate, kind `estimate`, never summed as a contract
--                                  and out of the supplier value orders; the page says what was published and why it is
--                                  not used. World Aviation 220199-2026: EUR 7,274,615,930 for a lot estimated at
--                                  EUR 7,317,073.17.
--
-- Filled for new loads by the loader; for the notices held by
--     python -m dgate.ops.award_values --no-fetch          (report)  /  --no-fetch --yes   (write)
-- The grants of 0079 are table grants and cover the new column.

ALTER TABLE award_notice ADD COLUMN IF NOT EXISTS value_set_aside NUMERIC(18, 2);
