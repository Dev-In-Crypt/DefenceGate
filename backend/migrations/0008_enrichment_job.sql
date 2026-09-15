-- The enrichment queue (plan M1-04, table from section 4.3).
--
-- Postgres is the queue, as the plan requires: no queue infrastructure, and a
-- job is a row that survives a restart. One row per (entity, task, input_hash),
-- so the same input can never be queued twice; a changed notice produces a new
-- input hash and therefore a new job, and an unchanged one produces none.
--
-- Only enrichment_job is created here. Section 4.3 also lists the notification
-- outbox and webhook tables; they belong to the alerting tasks (M1-26 to M1-28)
-- and are added with them.

CREATE TABLE IF NOT EXISTS enrichment_job (
    id           BIGSERIAL PRIMARY KEY,
    entity_type  TEXT NOT NULL,
    entity_id    BIGINT NOT NULL,
    task         TEXT NOT NULL,
    input_hash   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'batched', 'done', 'failed')),
    batch_id     TEXT,
    attempts     INT NOT NULL DEFAULT 0,
    last_error   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at  TIMESTAMPTZ,
    UNIQUE (entity_type, entity_id, task, input_hash)
);

CREATE INDEX IF NOT EXISTS enrichment_job_status_idx ON enrichment_job (task, status);
CREATE INDEX IF NOT EXISTS enrichment_job_batch_idx ON enrichment_job (batch_id)
    WHERE batch_id IS NOT NULL;

-- Results are looked up by what was sent, whichever notice sent it: identical
-- input on two notices must be paid for once.
CREATE INDEX IF NOT EXISTS enrichment_task_input_idx ON enrichment (task, input_hash);
