-- WP-115 (24 October 2026): organisation identifiers and buyer records.
--
-- 1. organisation_repair: what a correction changed on an organisation row, so it can be undone. A cleared
--    false registration number keeps its value here (case references, never a person's number: those are not
--    cleared but refused at the boundary); a merged_into pointer moved to the end of a chain keeps the old one.
--    A removed contact block is logged without its value (personal data is not kept, so that one has no undo).
-- 2. An index on opportunity(buyer_org_id) over every notice. The only one was partial (WHERE is_defence), so
--    "does this organisation publish any notice" was a sequential read of 394,000 rows per organisation:
--    ops.accept_merge_candidates' detail query ran 44 times at 5.5 min mean, 12 min max (coverage audit).
--    About 9 MB. On production the orchestrator creates it CONCURRENTLY first, which makes this a no-op:
--      CREATE INDEX CONCURRENTLY IF NOT EXISTS opp_buyer_org_all ON opportunity (buyer_org_id);

CREATE TABLE IF NOT EXISTS organisation_repair (
    id              BIGSERIAL PRIMARY KEY,
    organisation_id BIGINT NOT NULL REFERENCES organisation(id),
    action          TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    method          TEXT NOT NULL,
    detected_by     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS organisation_repair_org ON organisation_repair (organisation_id);
CREATE INDEX IF NOT EXISTS organisation_repair_action ON organisation_repair (action, old_value);

CREATE INDEX IF NOT EXISTS opp_buyer_org_all ON opportunity (buyer_org_id);
