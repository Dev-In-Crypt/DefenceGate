-- The `consortium.changed` event (WP-26, plan M2-05): two consecutive snapshots of one project
-- that differ give exactly one row here. It holds the difference, not a copy of the snapshots.
-- No webhook sends it yet (no accounts, no mail relay); the row is the event.
CREATE TABLE IF NOT EXISTS consortium_change (
    id                 BIGSERIAL PRIMARY KEY,
    project_id         BIGINT NOT NULL REFERENCES project(id),
    snapshot_id        BIGINT NOT NULL UNIQUE REFERENCES consortium_snapshot(id),
    prev_snapshot_id   BIGINT NOT NULL REFERENCES consortium_snapshot(id),
    observed_at        DATE NOT NULL,
    added_org_ids      BIGINT[] NOT NULL DEFAULT '{}',
    removed_org_ids    BIGINT[] NOT NULL DEFAULT '{}',
    coordinator_before BIGINT,
    coordinator_after  BIGINT
);
CREATE INDEX IF NOT EXISTS consortium_change_project ON consortium_change (project_id, observed_at);

GRANT SELECT ON consortium_change TO dgate_api;
GRANT SELECT, INSERT, UPDATE ON consortium_change TO dgate_worker;
REVOKE DELETE ON consortium_change FROM dgate_worker;
