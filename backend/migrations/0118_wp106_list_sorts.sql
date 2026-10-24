-- WP-106 (24 October 2026): the tenders list sorted by value and by code (dgate/tenders.py ORDER_VALUE_DESC,
-- ORDER_CPV_ASC), over the rows a list can show, so a page of any depth is a walk along the index that stops after
-- `offset + limit` rows, as the deadline orders of migration 0091 are. The expressions are the ORDER BY's own (a value
-- of 1 or less is a placeholder, "not stated": no currency and no amount in the order).
-- Additive and idempotent.

CREATE INDEX IF NOT EXISTS opp_list_value_desc
    ON opportunity (((CASE WHEN value_amount > 1 THEN value_currency END) IS DISTINCT FROM 'EUR'),
                    (CASE WHEN value_amount > 1 THEN value_currency END) ASC NULLS LAST,
                    (CASE WHEN value_amount > 1 THEN value_amount END) DESC NULLS LAST, id DESC)
    WHERE is_defence AND NOT suppressed;

CREATE INDEX IF NOT EXISTS opp_list_cpv_asc
    ON opportunity ((cpv_codes[1]) ASC NULLS LAST, id ASC)
    WHERE is_defence AND NOT suppressed;

ANALYZE opportunity;
