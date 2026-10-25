-- WP-126 (25 October 2026). Additive and idempotent: two nullable columns on `award`, nothing rewritten.
--
-- award.value_set_aside          a PLACSP awarded amount set aside as a unit price (`award_value.placsp_unit_price`:
--                                over EUR 1, under EUR 100: a pair of shoes, a menu, an hour), kept as the source
--                                stated it; `value_amount` is then empty, so the row is in no sum
-- award.value_set_aside_reason   why: `unit_price`
--
-- The loader (`placsp_awards.read`) sets them on every read; `python -m dgate.ops.award_values --no-fetch` (step 6)
-- sets them on the rows already held, and `--undo-unit-prices` puts the amounts back.

ALTER TABLE award ADD COLUMN IF NOT EXISTS value_set_aside NUMERIC(18, 2);
ALTER TABLE award ADD COLUMN IF NOT EXISTS value_set_aside_reason TEXT;
