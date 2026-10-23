-- What kind of amount an award value is, the framework a call-off is based on, and the other buyers of a joint
-- procurement (WP-95, persona round of 23 October 2026, findings A1.1 and A1.4). Additive and idempotent: nullable
-- columns and checks, nothing dropped or rewritten here.
--
--   award.value_kind            the kind of award.value_amount (dgate/award_value.py): contract (the contract
--                               awarded, a call-off included), framework (a framework agreement's or dynamic
--                               purchasing system's ceiling) or estimate (the buyer's estimate, where the award states
--                               no value). TED rows now carry their notice's value too, where the notice names one
--                               winner. NULL: not derived yet; the supplier map then reads the value as before WP-95
--                               (`suppliers.value_of`).
--   award_notice.value_amount   a TED result notice's own value (every winner together) and its currency and kind,
--   award_notice.value_currency for the notice's page ("Awarded value", "Framework ceiling", "Estimated value").
--   award_notice.value_kind
--   award_notice.framework_id   the notice of the framework agreement a call-off states it is based on (a PLACSP title
--                               quoting the framework's file number).
--   opportunity.other_buyers    the buyers of a joint procurement after the first, as the notice names them (TED's
--                               buyer-name list). Not versioned, like notice_subtype.
--
-- Filled for new loads by the loaders; for the rows held by
--     python -m dgate.ops.award_values            (report)  /  --yes   (write)
--     python -m dgate.ops.co_buyers               (report)  /  --yes   (write)
-- The grants of 0079 are table grants and cover the new columns.

ALTER TABLE award ADD COLUMN IF NOT EXISTS value_kind TEXT;
ALTER TABLE award_notice ADD COLUMN IF NOT EXISTS value_amount NUMERIC(18, 2);
ALTER TABLE award_notice ADD COLUMN IF NOT EXISTS value_currency TEXT;
ALTER TABLE award_notice ADD COLUMN IF NOT EXISTS value_kind TEXT;
ALTER TABLE award_notice ADD COLUMN IF NOT EXISTS framework_id BIGINT;
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS other_buyers TEXT[];

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'award_value_kind_check') THEN
        ALTER TABLE award ADD CONSTRAINT award_value_kind_check
            CHECK (value_kind IN ('contract', 'framework', 'estimate'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'award_notice_value_kind_check') THEN
        ALTER TABLE award_notice ADD CONSTRAINT award_notice_value_kind_check
            CHECK (value_kind IN ('contract', 'framework', 'estimate'));
    END IF;
END
$$;
