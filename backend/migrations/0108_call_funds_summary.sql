-- WP-92 (23 October 2026). Additive and idempotent: nullable columns on `call`, nothing dropped or rewritten here.
--
--   call.funds_summary            What the call funds: at most three sentences of the EU portal topic description's
--                                 Objective / Expected outcome sections that pass the commercial filter of
--                                 dgate/topic_summary.py (no figure, no specification word, no named system,
--                                 unclassified dropped). NULL when nothing passes. The full description stays in the
--                                 raw store only. Filled by the topic-details step on its normal runs; the calls read
--                                 before it are filled from the raw store, which downloads nothing:
--                                     python -m dgate.ops.funds_summary          (report)
--                                     python -m dgate.ops.funds_summary --yes
--   call.who_may_apply_doc        'public' or 'companies' where the call's own eligibility facts (call document or the
--                                 topic's own conditions, call_eligibility) state who may apply; NULL otherwise, and the
--                                 list badge falls back to the programme rules (funding.WHO_MAY_APPLY).
--   call.sme_only                 TRUE where those facts state the call is reserved for SMEs.
--   call.who_may_apply_evidence   the verified quote the two rest on.
-- Filled nightly by the cascade-flags job (dgate/who_apply.py), and by `python -m dgate.ops.cascade_flags --yes`.
-- The grants on `call` (0024 onwards) are table grants and cover the new columns.

ALTER TABLE call ADD COLUMN IF NOT EXISTS funds_summary TEXT;
ALTER TABLE call ADD COLUMN IF NOT EXISTS who_may_apply_doc TEXT
    CHECK (who_may_apply_doc IN ('public', 'companies'));
ALTER TABLE call ADD COLUMN IF NOT EXISTS sme_only BOOLEAN;
ALTER TABLE call ADD COLUMN IF NOT EXISTS who_may_apply_evidence TEXT;
