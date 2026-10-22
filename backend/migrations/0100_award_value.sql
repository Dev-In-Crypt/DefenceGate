-- The awarded amount of a PLACSP winner (WP-81, 22 October 2026). Additive and idempotent: two nullable columns,
-- nothing dropped, nothing rewritten here.
--
--   award.value_amount     PLACSP: the importe de adjudicación WITHOUT VAT (`TaxExclusiveAmount` of the result's
--                          `AwardedTenderedProject/LegalMonetaryTotal`; `PayableAmount`, with VAT, is not used),
--                          summed over the results (lots) of the folder that name this one winner. A result naming
--                          several winners (a natural person among them counts) is attributed to none. NULL when no
--                          such result states an amount above the placeholder, or when the lots state two currencies.
--   award.value_currency   its currency (`currencyID`).
--
-- TED rows leave both empty: a TED notice's value stays on `opportunity` (`value_kind`), as before.
-- The amounts are in the landed award payloads since WP-60 (`placsp_awards`); the rows already held are filled
-- by replaying the store, which downloads nothing:
--     python -m dgate.ops.placsp_archives --from-store          (dry run, rolled back)
--     python -m dgate.ops.placsp_archives --from-store --yes
-- The grants of 0079 are table grants and cover the new columns.

ALTER TABLE award ADD COLUMN IF NOT EXISTS value_amount NUMERIC(18, 2);
ALTER TABLE award ADD COLUMN IF NOT EXISTS value_currency TEXT;
