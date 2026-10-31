-- WP-160 (31 October 2026): contracts ending soon. Additive and idempotent.
--
-- The list of contracts ending within 3, 6 or 12 months (dgate/expiring.py) walks this index: the expression is
-- `expiring.end_sql("")`, the one end-date rule (stated end, else start + duration, else for an award notice its
-- publication date + duration, labelled "estimated"), and a test holds the two equal. Partial: only the defence rows the
-- site lists that have an end, a few per cent of the table.
CREATE INDEX IF NOT EXISTS opp_contract_end
    ON opportunity ((COALESCE(contract_end, (COALESCE(contract_start, CASE WHEN status = 'awarded' THEN published_at END) + CASE WHEN contract_duration_unit = 'DAY' AND contract_duration <= 36600 THEN make_interval(days => contract_duration) WHEN contract_duration_unit = 'WEEK' AND contract_duration <= 5220 THEN make_interval(weeks => contract_duration) WHEN contract_duration_unit = 'MONTH' AND contract_duration <= 1200 THEN make_interval(months => contract_duration) WHEN contract_duration_unit = 'YEAR' AND contract_duration <= 100 THEN make_interval(years => contract_duration) END)::date)))
    WHERE is_defence AND NOT suppressed
      AND COALESCE(contract_end, (COALESCE(contract_start, CASE WHEN status = 'awarded' THEN published_at END) + CASE WHEN contract_duration_unit = 'DAY' AND contract_duration <= 36600 THEN make_interval(days => contract_duration) WHEN contract_duration_unit = 'WEEK' AND contract_duration <= 5220 THEN make_interval(weeks => contract_duration) WHEN contract_duration_unit = 'MONTH' AND contract_duration <= 1200 THEN make_interval(months => contract_duration) WHEN contract_duration_unit = 'YEAR' AND contract_duration <= 100 THEN make_interval(years => contract_duration) END)::date) IS NOT NULL;

-- A saved search of kind `ending` (accounts.clean_filters: country, cpv, buyer, within, estimated): its alert reports the
-- contracts that newly enter its window (ops/digest.py, `expiring.entered`). Pro (`expiring_contracts`).
ALTER TABLE app_saved_search DROP CONSTRAINT IF EXISTS app_saved_search_kind_check;
ALTER TABLE app_saved_search ADD CONSTRAINT app_saved_search_kind_check CHECK (kind IN ('tender', 'call', 'ending'));

ANALYZE opportunity;
