-- WP-162 (31 October 2026): the "Who to sell to" supplier report (dgate/sell_report.py). Additive and idempotent.

-- One row per report an account generated: when, and for a report on a company in our data (mode A) which company. Nothing
-- of a form (mode B) is here: the count is all that is kept of a report made without consent.
CREATE TABLE IF NOT EXISTS sell_report_use (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id     uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    month          date NOT NULL CHECK (extract(day FROM month) = 1),
    org_id         bigint,
    association_id uuid REFERENCES association (id) ON DELETE SET NULL,     -- drawn on the association's yearly pool
    used_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sell_report_use_account ON sell_report_use (account_id, month);
CREATE INDEX IF NOT EXISTS sell_report_use_association ON sell_report_use (association_id, month) WHERE association_id IS NOT NULL;
-- a company's report counts once a month, as the company report does
CREATE UNIQUE INDEX IF NOT EXISTS sell_report_use_org ON sell_report_use (account_id, month, org_id) WHERE org_id IS NOT NULL;

-- The form of a report, kept only when the account ticked the consent box; one per account, replaced by the next one,
-- deleted by the account (DELETE /v1/account/sell-report/profile) or with the account. Commercial data the account typed:
-- company name, country, CPV and NACE codes, certificates declared, the export and classified-work answers.
CREATE TABLE IF NOT EXISTS sell_profile (
    account_id uuid PRIMARY KEY REFERENCES app_user (id) ON DELETE CASCADE,
    body       jsonb NOT NULL CHECK (octet_length(body::text) <= 4096),
    saved_at   timestamptz NOT NULL DEFAULT now()
);

-- The Consultant's logo for the cover of its reports (`branded_reports`): a PNG or JPEG of at most 10 KB, checked by its
-- first bytes in sell_report.put_logo. Its own table, so that the session read (`SELECT u.*`) does not carry it.
CREATE TABLE IF NOT EXISTS report_logo (
    account_id uuid PRIMARY KEY REFERENCES app_user (id) ON DELETE CASCADE,
    type       text NOT NULL CHECK (type IN ('image/png', 'image/jpeg')),
    data       bytea NOT NULL CHECK (octet_length(data) BETWEEN 1 AND 10240),
    set_at     timestamptz NOT NULL DEFAULT now()
);

-- The cluster licence's pool: supplier reports a calendar year for all the association's members together, set per contract
-- by the operator (python -m dgate.ops.association --reports N). NULL: no pool, the members' plan decides.
ALTER TABLE association ADD COLUMN IF NOT EXISTS sell_reports_per_year integer CHECK (sell_reports_per_year BETWEEN 0 AND 1000);

-- As for the other account tables: the accounts role writes them, the public API role reads nothing, the worker reads them
-- (pg_dump).
REVOKE ALL ON sell_report_use, sell_profile, report_logo FROM dgate_api, dgate_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON sell_report_use, sell_profile, report_logo TO dgate_app;
GRANT SELECT ON sell_report_use, sell_profile, report_logo TO dgate_worker;
