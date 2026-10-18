-- The supplier map (WP-37, 18 October 2026): who won the defence-relevant result notices of TED.
-- Additive and idempotent. Nothing is dropped, nothing is deleted.
--
--   award_notice  a result notice whose winners a run has read, and what came of it. It is the
--                 idempotence key (a second run asks TED about no notice listed here) and the
--                 count of what was left out: winners that are natural persons, winners with no
--                 country. `raw_key` is where the (person-blanked) record sits in the raw store.
--   award         one winning organisation of one notice. The organisation is the one the
--                 resolution cascade of WP-26 found (`resolution_method`, `resolution_confidence`
--                 say how); `name_as_stated` and `identifier_as_stated` are what the buyer
--                 published, the only place the notice's own spelling is kept. No value: a notice's
--                 value is on `opportunity`, and a profile shows it only where `winners_in_notice`
--                 is 1.
--
-- A natural person is never written: the loader (dgate/awards.py) skips and counts them.

CREATE TABLE IF NOT EXISTS award_notice (
    opportunity_id     BIGINT PRIMARY KEY REFERENCES opportunity(id),
    read_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_key            TEXT,
    winners_seen       INT NOT NULL DEFAULT 0,
    winners_kept       INT NOT NULL DEFAULT 0,
    skipped_person     INT NOT NULL DEFAULT 0,
    skipped_no_country INT NOT NULL DEFAULT 0,
    status             TEXT NOT NULL CHECK (status IN ('loaded', 'no_supplier', 'no_winner_data'))
);

CREATE TABLE IF NOT EXISTS award (
    id                    BIGSERIAL PRIMARY KEY,
    opportunity_id        BIGINT NOT NULL REFERENCES opportunity(id),
    organisation_id       BIGINT NOT NULL REFERENCES organisation(id),
    supplier_country      CHAR(2) NOT NULL,
    name_as_stated        TEXT NOT NULL,
    identifier_as_stated  TEXT,
    winners_in_notice     SMALLINT NOT NULL CHECK (winners_in_notice >= 1),
    cpv_main              TEXT,                 -- the first military code of the notice, else its first code
    resolution_method     TEXT NOT NULL,
    resolution_confidence NUMERIC(3,2) NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (opportunity_id, organisation_id)
);
CREATE INDEX IF NOT EXISTS award_organisation ON award (organisation_id);
CREATE INDEX IF NOT EXISTS award_country_cpv ON award (supplier_country, (left(cpv_main, 2)));
