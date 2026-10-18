-- The regulatory tracker (WP-36, 18 October 2026): what changed in the rules that matter to a supplier,
-- each entry with the primary source, a verbatim sentence of it and the day we last checked it.
-- Additive and idempotent. Loaded from `seeds/regulation_tracker.json` by `dgate.regulation`
-- (the worker applies it when it starts); an entry the seed stops listing is switched off, never deleted.
--
-- `status` is where the act stands: proposed | announced | agreed | adopted | in_force | unconfirmed.
-- `unconfirmed` is an entry whose point no primary text we could read settles; the entry says which.
-- `links` is a list of {kind: requirement|programme|page, code, label} to the pages the change touches.
CREATE TABLE IF NOT EXISTS regulation_entry (
    id            SERIAL PRIMARY KEY,
    code          TEXT NOT NULL UNIQUE,
    instrument    TEXT NOT NULL,
    title         TEXT NOT NULL,
    what_changed  TEXT NOT NULL,
    event_date    DATE NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('proposed', 'announced', 'agreed', 'adopted', 'in_force', 'unconfirmed')),
    affected      TEXT NOT NULL,
    source_url    TEXT NOT NULL,
    source_ref    TEXT NOT NULL,
    source_quote  TEXT NOT NULL CHECK (length(source_quote) > 0),
    checked_on    DATE NOT NULL,
    links         JSONB NOT NULL DEFAULT '[]'::jsonb,
    position      INT NOT NULL DEFAULT 0,
    active        BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS regulation_entry_event ON regulation_entry (event_date DESC) WHERE active;

-- The API role reads it, the worker role loads it, and the backup (which runs as the worker) can read
-- every table (test_the_worker_role_can_read_every_table_so_pg_dump_can).
GRANT SELECT ON regulation_entry TO dgate_api;
GRANT SELECT, INSERT, UPDATE ON regulation_entry TO dgate_worker;
GRANT USAGE, SELECT ON SEQUENCE regulation_entry_id_seq TO dgate_worker;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dgate_worker;
