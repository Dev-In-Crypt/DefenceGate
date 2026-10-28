-- WP-155 (28 October 2026): the owner's plan split. Additive and idempotent.

-- The company reports an account opened, one row per company and calendar month (UTC): what REPORTS_PER_MONTH is
-- counted against (dgate/competition.py open_report). The same company again in the same month is the same row. Goes
-- with the account (ON DELETE CASCADE); an old month is never read again and is pruned with the account housekeeping.
CREATE TABLE IF NOT EXISTS company_report_open (
    account_id uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    month      date NOT NULL CHECK (extract(day FROM month) = 1),
    org_id     bigint NOT NULL,
    opened_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, month, org_id)
);

-- The account holder's own text for the head of its company reports (Consultant, `branded_reports`): plain text, at
-- most 80 characters, no file. NULL: none.
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS report_name text CHECK (char_length(report_name) BETWEEN 1 AND 80);

-- The data API licence: a contract outside the plans, granted and withdrawn by the operator only
-- (python -m dgate.ops.api_licence). Without it no key is issued and a key already issued is refused.
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS api_licensed_at timestamptz;

-- As for the other account tables: the accounts role writes it, the public API role reads nothing, the worker reads it
-- (pg_dump).
REVOKE ALL ON company_report_open FROM dgate_api, dgate_worker;
GRANT SELECT, INSERT, DELETE ON company_report_open TO dgate_app;
GRANT SELECT ON company_report_open TO dgate_worker;
