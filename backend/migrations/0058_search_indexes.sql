-- Text search over closed notices (17 October 2026). The tender search is
-- (title_en OR title_original OR buyer name OR notice number); only the two titles were
-- indexed, so the OR could not use an index and read every row with three folding calls:
-- `status=closed&q=armoured` took over five seconds and came back as a 503. The buyer name
-- (folded, as the titles are) and the notice number now have trigram indexes too: 0.6 s.
-- Created CONCURRENTLY on production before this migration ran; IF NOT EXISTS keeps it idempotent.
CREATE INDEX IF NOT EXISTS opp_buyer_name_fold
    ON opportunity USING gin (dg_fold(buyer_name_raw) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS opp_native_id_trgm
    ON opportunity USING gin (native_id gin_trgm_ops);
