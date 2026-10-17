-- Layer 3, the requirements model (WP-29, 17 October 2026): what separates a company from
-- taking part in a programme. Tables from Part VII of the Data Architecture document, with
-- the additions of plan section 4.5: every row carries its source, its verification status
-- ('V' verified by direct fetch, 'S' search results only, 'U' unverified: the technical
-- appendix's own marks) and the date it was last reviewed. The content is compiled by
-- people, loaded from seeds/requirements.json (python -m dgate.readiness.seed) and never
-- scraped. Nothing here is a customer's data: a company profile is not stored.
--
-- `kind`: 'document' is something a company obtains (a code, a certificate, a licence);
-- 'rule' is an eligibility rule that is assessed, not obtained.
-- `active`: a row the seed no longer lists is switched off, never deleted.
CREATE TABLE IF NOT EXISTS requirement (
    id                  SERIAL PRIMARY KEY,
    code                TEXT UNIQUE NOT NULL,
    name                TEXT NOT NULL,
    category            TEXT NOT NULL CHECK (category IN
                          ('identification', 'registration', 'quality', 'export_control',
                           'security', 'integrity', 'admission', 'origin')),
    kind                TEXT NOT NULL CHECK (kind IN ('document', 'rule')),
    summary             TEXT NOT NULL,
    description         TEXT,
    typical_cost_min    NUMERIC(10, 2),
    typical_cost_max    NUMERIC(10, 2),
    cost_currency       CHAR(3),
    cost_basis          TEXT CHECK (cost_basis IN ('free', 'vendor_range', 'not_stated')),
    cost_text           TEXT,
    cost_alt            JSONB,
    typical_days_min    INT,
    typical_days_max    INT,
    duration_text       TEXT,
    duration_note       TEXT,
    variants            JSONB NOT NULL DEFAULT '[]',
    extras              JSONB NOT NULL DEFAULT '{}',
    legal_basis         TEXT,
    mandatory_for       TEXT,
    source_url          TEXT NOT NULL,
    source_ref          TEXT,
    source_text         TEXT,
    text_origin         TEXT NOT NULL CHECK (text_origin IN ('primary', 'notes')),
    verification_status TEXT NOT NULL CHECK (verification_status IN ('V', 'S', 'U')),
    last_reviewed       DATE NOT NULL,
    position            INT NOT NULL DEFAULT 0,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (typical_cost_min IS NULL OR typical_cost_max IS NULL OR typical_cost_min <= typical_cost_max),
    CHECK (typical_days_min IS NULL OR typical_days_max IS NULL OR typical_days_min <= typical_days_max)
);

-- Dependency graph between requirements. 'before': the prerequisite is finished first.
-- 'before_or_with': it may be done before or together with the requirement (REOCE and the
-- export licence), so it orders the steps but adds no waiting time.
CREATE TABLE IF NOT EXISTS requirement_prerequisite (
    requirement_id      INT NOT NULL REFERENCES requirement(id),
    prerequisite_id     INT NOT NULL REFERENCES requirement(id),
    relation            TEXT NOT NULL DEFAULT 'before' CHECK (relation IN ('before', 'before_or_with')),
    PRIMARY KEY (requirement_id, prerequisite_id),
    CHECK (requirement_id <> prerequisite_id)
);

-- Which body issues a requirement in which country. country '*' = the same body for every
-- country. A country the appendix did not cover has no row: the answer is then "not
-- collected", never a guess.
CREATE TABLE IF NOT EXISTS requirement_issuer (
    id                  SERIAL PRIMARY KEY,
    requirement_id      INT NOT NULL REFERENCES requirement(id),
    country             TEXT NOT NULL CHECK (country = '*' OR country ~ '^[A-Z]{2}$'),
    issuer_name         TEXT NOT NULL,
    issuer_url          TEXT,
    notes               TEXT,
    verification_status TEXT NOT NULL CHECK (verification_status IN ('V', 'S', 'U')),
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (requirement_id, country, issuer_name)
);

CREATE INDEX IF NOT EXISTS requirement_issuer_country ON requirement_issuer (country);
