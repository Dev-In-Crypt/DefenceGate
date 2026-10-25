-- WP-124 (25 October 2026): payments through Creem (creem.io), the merchant of record: Creem sells to
-- the customer, collects the payment and the VAT and issues the invoices. We hold no card data, no
-- address and no invoice: only which plan an account pays for, its state and Creem's own ids, so the
-- verified webhook events can be matched to the account. Built to docs/SECURITY_REQUIREMENTS.md B1-B5.
-- Additive and idempotent.

-- A checkout we created for an account (POST /v1/account/billing/checkout). `id` is our reference,
-- sent to Creem as request_id and in the metadata; `creem_checkout_id` is Creem's. An event is applied
-- only when it names a checkout of this table and the account and product of that checkout (B3: never
-- an e-mail address). A founding checkout opened in the last hour holds one of the 20 places.
CREATE TABLE IF NOT EXISTS billing_checkout (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id        uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    plan              text NOT NULL CHECK (plan IN ('pro', 'team', 'consultant', 'founding')),
    period            text NOT NULL CHECK (period IN ('monthly', 'yearly')),
    product_id        text NOT NULL,
    creem_checkout_id text UNIQUE,
    created_at        timestamptz NOT NULL DEFAULT now(),
    completed_at      timestamptz
);
CREATE INDEX IF NOT EXISTS billing_checkout_account ON billing_checkout (account_id, created_at);
CREATE INDEX IF NOT EXISTS billing_checkout_open_founding ON billing_checkout (created_at)
    WHERE plan = 'founding' AND completed_at IS NULL;

-- The subscription of an account, one row, written only by verified events (D3). `status` is Creem's
-- (active, trialing, past_due, unpaid, paused, scheduled_cancel, canceled, expired) or `disputed`;
-- what each one allows is billing.plan_in_force. `last_event_at` is the `created_at` of the newest
-- event applied: an older one that arrives later changes nothing (B2).
CREATE TABLE IF NOT EXISTS billing_subscription (
    account_id            uuid PRIMARY KEY REFERENCES app_user (id) ON DELETE CASCADE,
    plan                  text NOT NULL CHECK (plan IN ('pro', 'team', 'consultant', 'founding')),
    period                text NOT NULL CHECK (period IN ('monthly', 'yearly')),
    status                text NOT NULL,
    creem_customer_id     text,
    creem_subscription_id text UNIQUE,
    current_period_end    timestamptz,
    refunded_at           timestamptz,
    last_event_id         text NOT NULL,
    last_event_at         timestamptz NOT NULL,
    updated_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS billing_subscription_founding ON billing_subscription (plan, status);

-- B1: every event id seen, applied or not; a second delivery is acknowledged and ignored. No account
-- id and nothing from the payload but its type and time.
CREATE TABLE IF NOT EXISTS billing_event (
    event_id    text PRIMARY KEY,
    event_type  text NOT NULL,
    created_at  timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    outcome     text NOT NULL
);
CREATE INDEX IF NOT EXISTS billing_event_received ON billing_event (received_at);

-- As for the other account tables: the accounts role writes them, the public API role reads nothing,
-- the worker reads them (pg_dump, and the digest asks whether an account may have alerts).
REVOKE ALL ON billing_checkout, billing_subscription, billing_event FROM dgate_api, dgate_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON billing_checkout, billing_subscription, billing_event TO dgate_app;
GRANT SELECT ON billing_checkout, billing_subscription, billing_event TO dgate_worker;
