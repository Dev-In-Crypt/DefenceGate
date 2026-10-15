-- Nightly completeness controls (WP-15, 15 October 2026).
--
-- The three national sources that publish their own day total (BZP `X-Pagination`,
-- BOAMP `total_count`, TenderNed `totalElements`) are checked against what a run
-- landed for each complete publication day. The comparison goes on the run
-- (`ingest_run.detail`, JSONB) so /v1/health can show it; the weekly Atlas and the
-- daily PLACSP controls keep their last answer in `control_check`, one row each, so
-- an alert repeats at a set interval and a change is recognised as a change.
-- Additive and idempotent.
ALTER TABLE ingest_run ADD COLUMN IF NOT EXISTS detail JSONB;

CREATE TABLE IF NOT EXISTS control_check (
    control     TEXT PRIMARY KEY,                  -- atlas_zenodo | placsp_links
    status      TEXT NOT NULL CHECK (status IN ('ok', 'alert', 'unknown')),
    checked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    state       JSONB NOT NULL DEFAULT '{}'::jsonb, -- what was seen (version, checksums)
    detail      JSONB NOT NULL DEFAULT '{}'::jsonb, -- the metrics shown on /v1/health
    alerted_at  TIMESTAMPTZ
);

GRANT SELECT ON control_check TO dgate_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON control_check TO dgate_worker;
