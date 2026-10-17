-- Pre-computed list responses (16-17 October 2026, speed). The closed and the "all" tender
-- lists cost 2.7 to 3.3 s on a cold read (a quarter of a million notices, sorted and
-- collapsed), and the API role's budget is 5 s, so a busy host turned them into a 503. The
-- worker computes the handful of views people open (status closed or all, every country,
-- the first three pages, and the scope counts beside them) every four hours and keeps the
-- response here; the API reads one row by key when its own memory has no answer.
-- Derived, replaceable data: emptying the table only makes those views slow again.
CREATE TABLE IF NOT EXISTS list_snapshot (
    key          TEXT PRIMARY KEY,
    body         JSONB NOT NULL,
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT ON list_snapshot TO dgate_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON list_snapshot TO dgate_worker;
