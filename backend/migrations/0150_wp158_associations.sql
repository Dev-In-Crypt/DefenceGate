-- WP-158 (30 October 2026): the cluster licence. An association (a cluster, a trade body) holds a licence agreed outside the
-- plans; its members' accounts get the Pro features and its admin's account the Team features (billing.plan_in_force), and
-- members who opt in get the weekly digest by e-mail under the association's name (dgate/associations.py). Only
-- `python -m dgate.ops.association` creates, licenses and fills an association. Additive and idempotent.

CREATE TABLE IF NOT EXISTS association (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name         text NOT NULL UNIQUE CHECK (name ~ '^[a-z0-9][a-z0-9-]{1,59}$'),        -- the operator's key
    display_name text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 80),           -- in the mail's sender and heading
    licensed_at  timestamptz,                                                           -- NULL: no licence (none, or withdrawn)
    -- SECURITY_REQUIREMENTS D3: a grant made by hand is dated, reasoned and expiring. The licence ends by itself at
    -- `licensed_until`; the reason is the operator's reference to the agreement (commercial text, no person named).
    licensed_until timestamptz,
    licence_reason text CHECK (length(licence_reason) BETWEEN 1 AND 200),
    seat_cap     integer NOT NULL DEFAULT 50 CHECK (seat_cap BETWEEN 1 AND 50),
    admin_id     uuid REFERENCES app_user (id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CHECK (licensed_at IS NULL OR (licensed_until > licensed_at AND licence_reason IS NOT NULL))
);

-- One association per account. The digest choice is the member's own; `unsubscribe_token` is the random part of the link in
-- each digest mail (two random UUIDs, 244 random bits; it can only switch that mail off), `digest_last_week` the ISO week last mailed (one mail a week, and a
-- failed send is tried again by the next run).
CREATE TABLE IF NOT EXISTS association_member (
    account_id        uuid PRIMARY KEY REFERENCES app_user (id) ON DELETE CASCADE,
    association_id    uuid NOT NULL REFERENCES association (id) ON DELETE CASCADE,
    added_at          timestamptz NOT NULL DEFAULT now(),
    digest            boolean NOT NULL DEFAULT false,
    digest_country    text CHECK (digest_country ~ '^[A-Z]{2}$'),
    digest_cpv        text[] NOT NULL DEFAULT '{}' CHECK (cardinality(digest_cpv) <= 20),
    digest_last_week  text CHECK (digest_last_week ~ '^\d{4}-W\d{2}$'),
    unsubscribe_token text NOT NULL UNIQUE DEFAULT replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '')
);
CREATE INDEX IF NOT EXISTS association_member_association ON association_member (association_id);

-- As for the other account tables: the accounts role writes them, the public API role reads nothing, the worker reads them
-- (pg_dump) and moves the digest week on.
REVOKE ALL ON association, association_member FROM dgate_api, dgate_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON association, association_member TO dgate_app;
GRANT SELECT ON association, association_member TO dgate_worker;
GRANT UPDATE (digest_last_week) ON association_member TO dgate_worker;
