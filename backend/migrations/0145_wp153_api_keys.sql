-- WP-153 (27 October 2026): keys of the data API, issued to a signed-in account (dgate/apikeys.py). Built to
-- docs/SECURITY_REQUIREMENTS.md K1-K3 and O1-O2. Closed until DGATE_API_KEYS_OPEN=1. Additive and idempotent.

-- One key. The key itself exists only in the answer that created it: here is its SHA-256 (a key is 256 random bits,
-- so a plain hash cannot be reversed by trying candidates) and `prefix`, the public part used to find the row.
CREATE TABLE IF NOT EXISTS api_key (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    name            text NOT NULL CHECK (length(name) BETWEEN 1 AND 60),
    prefix          text NOT NULL UNIQUE CHECK (prefix ~ '^[0-9a-f]{12}$'),
    key_hash        bytea NOT NULL UNIQUE,
    scopes          text[] NOT NULL CHECK (scopes <@ ARRAY['tenders', 'archive']::text[]),
    rate_per_minute integer NOT NULL DEFAULT 60 CHECK (rate_per_minute BETWEEN 1 AND 6000),
    daily_quota     integer NOT NULL DEFAULT 10000 CHECK (daily_quota BETWEEN 1 AND 10000000),
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL,
    last_used_at    timestamptz,
    revoked_at      timestamptz
);
CREATE INDEX IF NOT EXISTS api_key_owner ON api_key (owner_id, created_at);

-- How many requests a key made each day: what a licence is checked against. No address, no path.
CREATE TABLE IF NOT EXISTS api_key_usage (
    key_id   uuid NOT NULL REFERENCES api_key (id) ON DELETE CASCADE,
    day      date NOT NULL,
    requests integer NOT NULL DEFAULT 0,
    PRIMARY KEY (key_id, day)
);

-- The audit log of the keys: created and revoked, by whom (the account) and when. Append-only for the service role
-- (no UPDATE, no DELETE granted); the rows go with the account (ON DELETE CASCADE), as everything it owns does.
CREATE TABLE IF NOT EXISTS api_key_event (
    id       bigserial PRIMARY KEY,
    key_id   uuid NOT NULL REFERENCES api_key (id) ON DELETE CASCADE,
    owner_id uuid NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    event    text NOT NULL CHECK (event IN ('created', 'revoked')),
    at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS api_key_event_owner ON api_key_event (owner_id, at);

-- As for the other account tables: the accounts role writes them, the public API role reads nothing, the worker
-- reads them (pg_dump).
REVOKE ALL ON api_key, api_key_usage, api_key_event FROM dgate_api, dgate_worker;
REVOKE ALL ON api_key_event FROM dgate_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON api_key, api_key_usage TO dgate_app;
GRANT SELECT, INSERT ON api_key_event TO dgate_app;
GRANT USAGE ON SEQUENCE api_key_event_id_seq TO dgate_app;
GRANT SELECT ON api_key, api_key_usage, api_key_event TO dgate_worker;
