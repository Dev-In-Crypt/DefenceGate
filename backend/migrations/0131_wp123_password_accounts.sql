-- WP-123 (25 October 2026), from the unmerged WP-79 branch (its migration 0105, renumbered):
-- accounts with an e-mail address and a password instead of the one-time sign-in link, on the
-- owner's decisions of 22 and 25 October 2026. Registration with e-mail confirmation, password
-- reset by e-mail, optional TOTP with recovery codes, the plan picked on the pricing page.
-- Built to docs/SECURITY_REQUIREMENTS.md (A1-A10). Additive and idempotent.
--
-- Nothing usable is stored: the password as an Argon2id hash, the e-mail tokens and the
-- second-step tickets as SHA-256 hashes, recovery codes as HMACs under a key the API
-- holds, the TOTP key sealed with AES-GCM under a key derived from the API's own key.

ALTER TABLE app_user ADD COLUMN IF NOT EXISTS password_hash text;
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS password_changed_at timestamptz;
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS totp_secret_enc bytea;
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS totp_enabled_at timestamptz;
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS totp_last_step bigint;

-- The plan. `plan` is the one in force: `free` for everyone until billing (WP-124) writes it from
-- verified payment events; no other path changes it (docs/SECURITY_REQUIREMENTS.md D3).
-- `plan_choice` / `billing_choice` are what the person picked on the pricing page before
-- registering (/signup?plan=&billing=), remembered so the site can say it again; they grant nothing.
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS plan text NOT NULL DEFAULT 'free'
    CHECK (plan IN ('free', 'pro', 'team', 'consultant', 'founding'));
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS plan_choice text
    CHECK (plan_choice IN ('free', 'pro', 'team', 'consultant', 'founding'));
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS billing_choice text
    CHECK (billing_choice IN ('monthly', 'yearly'));

-- An account can sign in only once its address is confirmed. Every account that exists
-- before this migration was created by following a link sent to its address, so it is
-- confirmed; it has no password yet and sets one through "forgot your password".
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'app_user'
                      AND column_name = 'email_verified_at') THEN
        ALTER TABLE app_user ADD COLUMN email_verified_at timestamptz;
        UPDATE app_user SET email_verified_at = created_at;
    END IF;
END
$$;

-- Single-use tokens: `verify` (24 hours, mailed), `reset` (1 hour, mailed) and `mfa`
-- (5 minutes, the ticket between the password and the second step; never mailed).
CREATE TABLE IF NOT EXISTS app_auth_token (
    token_hash bytea PRIMARY KEY,
    user_id    uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    purpose    text NOT NULL CHECK (purpose IN ('verify', 'reset', 'mfa')),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    used_at    timestamptz
);
CREATE INDEX IF NOT EXISTS app_auth_token_user ON app_auth_token (user_id, purpose);
CREATE INDEX IF NOT EXISTS app_auth_token_expiry ON app_auth_token (expires_at);

CREATE TABLE IF NOT EXISTS app_recovery_code (
    user_id   uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    code_hash bytea NOT NULL,
    used_at   timestamptz,
    PRIMARY KEY (user_id, code_hash)
);

-- The links are gone: one still in the table can no longer be used. The table stays (it is
-- empty and nothing writes it); it is a deletion candidate (docs/DELETION_CANDIDATES.md).
DELETE FROM app_login_token;

-- Privileges as for the other account tables (0027, 0036, 0042): the accounts role writes
-- them, the public API role reads nothing, the worker reads them for pg_dump only.
REVOKE ALL ON app_auth_token, app_recovery_code FROM dgate_api, dgate_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON app_auth_token, app_recovery_code TO dgate_app;
GRANT SELECT ON app_auth_token, app_recovery_code TO dgate_worker;
