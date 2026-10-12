-- Accounts, saved searches, shortlist, follows and a cookieless visit counter.
-- Built to docs/SECURITY_REQUIREMENTS.md (A1-A6, O1-O3) and docs/design/ACCOUNT_CONTRACT.md.
--
-- Everything that identifies a person or reveals what a company is looking for lives in
-- app_* tables. They are reachable by their own role, `dgate_app`, and by nobody else:
-- the public API role (`dgate_api`) and the ingest worker get nothing on the secret ones,
-- because the default privileges of migration 0024 would otherwise hand them over.
--
-- Identifiers of owned objects are random UUIDs (O2). Secrets (sign-in tokens, session
-- ids) are stored only as SHA-256 hashes: the database never holds a usable credential.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dgate_app') THEN
        CREATE ROLE dgate_app NOLOGIN;
    END IF;
END
$$;

ALTER ROLE dgate_app SET statement_timeout = '5s';
ALTER ROLE dgate_app SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE dgate_app CONNECTION LIMIT 10;

GRANT USAGE ON SCHEMA public TO dgate_app;
-- It reads the public data (opportunities, calls, organisations) to build dashboards.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dgate_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO dgate_app;

-- ----------------------------------------------------------------- people

CREATE TABLE IF NOT EXISTS app_user (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email_canonical text NOT NULL,
    email_display   text NOT NULL,
    role            text CHECK (role IN ('supplier', 'prime', 'consultant', 'grant_writer', 'other')),
    tracks          text[] NOT NULL DEFAULT '{}',
    countries       text[] NOT NULL DEFAULT '{}',
    scope           text NOT NULL DEFAULT 'core' CHECK (scope IN ('core', 'all')),
    cadence         text NOT NULL DEFAULT 'daily' CHECK (cadence IN ('instant', 'daily', 'weekly', 'off')),
    onboarded       boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_visit_at   timestamptz
);
-- A1: one account per canonical address.
CREATE UNIQUE INDEX IF NOT EXISTS app_user_email_canonical ON app_user (email_canonical);

-- A2: a sign-in link is single use, short lived, stored as a hash and bound to the
-- browser that asked for it (binder_hash).
CREATE TABLE IF NOT EXISTS app_login_token (
    token_hash      bytea PRIMARY KEY,
    binder_hash     bytea NOT NULL,
    email_canonical text NOT NULL,
    email_display   text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL,
    used_at         timestamptz
);
CREATE INDEX IF NOT EXISTS app_login_token_expiry ON app_login_token (expires_at);

-- A5: sessions. `public_id` is what the account page lists and revokes by; the secret is
-- only ever held as `id_hash`.
CREATE TABLE IF NOT EXISTS app_session (
    id_hash      bytea PRIMARY KEY,
    public_id    uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    user_id      uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    created_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS app_session_user ON app_session (user_id);

-- A3: counts for the sign-in link limits. Only a hash of the address or IP is kept, and
-- the rows are pruned after a day.
CREATE TABLE IF NOT EXISTS app_auth_event (
    id       bigserial PRIMARY KEY,
    kind     text NOT NULL,
    key_hash bytea NOT NULL,
    at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS app_auth_event_lookup ON app_auth_event (kind, key_hash, at);

-- A4: a table, not code.
CREATE TABLE IF NOT EXISTS app_disposable_domain (domain text PRIMARY KEY);
INSERT INTO app_disposable_domain (domain) VALUES
    ('mailinator.com'), ('guerrillamail.com'), ('guerrillamail.net'), ('guerrillamail.org'),
    ('guerrillamail.biz'), ('guerrillamail.de'), ('sharklasers.com'), ('grr.la'),
    ('10minutemail.com'), ('10minutemail.net'), ('tempmail.com'), ('temp-mail.org'),
    ('temp-mail.io'), ('tempmail.net'), ('tempr.email'), ('yopmail.com'), ('yopmail.net'),
    ('yopmail.fr'), ('trashmail.com'), ('trashmail.net'), ('trashmail.de'),
    ('throwawaymail.com'), ('getnada.com'), ('maildrop.cc'), ('dispostable.com'),
    ('fakeinbox.com'), ('mintemail.com'), ('mohmal.com'), ('emailondeck.com'),
    ('mailnesia.com'), ('spambox.us'), ('discard.email'), ('mailcatch.com'),
    ('mytemp.email'), ('tempinbox.com'), ('burnermail.io'), ('mailtemp.info'),
    ('moakt.com'), ('tmpmail.org'), ('tmpmail.net'), ('inboxkitten.com'), ('1secmail.com'),
    ('1secmail.net'), ('1secmail.org'), ('mailforspam.com'), ('spamgourmet.com'),
    ('anonbox.net'), ('wegwerfmail.de'), ('wegwerfmail.net'), ('einrot.com')
ON CONFLICT DO NOTHING;

-- ------------------------------------------------------------ their data

CREATE TABLE IF NOT EXISTS app_saved_search (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    name            text NOT NULL,
    kind            text NOT NULL CHECK (kind IN ('tender', 'call')),
    filters         jsonb NOT NULL,
    cadence         text NOT NULL CHECK (cadence IN ('instant', 'daily', 'weekly', 'off')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_alerted_at timestamptz
);
CREATE INDEX IF NOT EXISTS app_saved_search_owner ON app_saved_search (owner_id, created_at DESC);

CREATE TABLE IF NOT EXISTS app_shortlist (
    owner_id   uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    kind       text NOT NULL CHECK (kind IN ('tender', 'call')),
    ref        text NOT NULL,
    status     text NOT NULL DEFAULT 'watching'
               CHECK (status IN ('watching', 'evaluating', 'bidding', 'submitted', 'dropped')),
    note       text NOT NULL DEFAULT '' CHECK (length(note) <= 500),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_id, kind, ref)
);

CREATE TABLE IF NOT EXISTS app_follow (
    owner_id   uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    kind       text NOT NULL CHECK (kind IN ('buyer', 'programme')),
    ref        text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_id, kind, ref)
);

-- --------------------------------------------------------- visit counter
-- Aggregates only: one row per day, page, referrer host and device class. No address, no
-- identifier, no user agent. Counted by the site's server, never by a script in the page.
CREATE TABLE IF NOT EXISTS app_hit_daily (
    day      date NOT NULL,
    route    text NOT NULL,
    referrer text NOT NULL DEFAULT '',
    device   text NOT NULL DEFAULT 'other' CHECK (device IN ('desktop', 'mobile', 'other')),
    hits     integer NOT NULL DEFAULT 0,
    PRIMARY KEY (day, route, referrer, device)
);

-- ------------------------------------------------------------- privileges
-- The default privileges of 0024 made every new table readable by the public API role
-- and writable by the worker. For these tables that is wrong: take it back, then grant
-- exactly what each role needs.
REVOKE ALL ON app_user, app_login_token, app_session, app_auth_event, app_disposable_domain,
              app_saved_search, app_shortlist, app_follow, app_hit_daily
    FROM dgate_api, dgate_worker;

GRANT SELECT, INSERT, UPDATE, DELETE ON app_user, app_login_token, app_session, app_auth_event,
    app_disposable_domain, app_saved_search, app_shortlist, app_follow, app_hit_daily TO dgate_app;
GRANT USAGE, SELECT ON SEQUENCE app_auth_event_id_seq TO dgate_app;

-- The worker sends digests: it reads who and what to send, and records that it did.
GRANT SELECT ON app_user TO dgate_worker;
GRANT SELECT, UPDATE (last_alerted_at) ON app_saved_search TO dgate_worker;
