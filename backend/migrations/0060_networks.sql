-- Layer 2, networks: who took part in which funded project (WP-26, 17 October 2026).
-- Additive and idempotent. Nothing is dropped, nothing is deleted.
--
--   project        a funded project: a CORDIS project (Horizon Europe, Horizon 2020, FP7) or
--                  an EDF project read from its factsheet. One key per source (`native_id`):
--                  the CORDIS record number for CORDIS, "<year>:<acronym>" or the grant number
--                  for EDF. `ga_number` is NOT unique: CORDIS holds four records under grant
--                  101197076 (measured 17 October 2026), so the grant number is a join hint, not a key.
--   participation  the edge organisation -> project: role, EU contribution, and how the link
--                  was decided (method and confidence, the rule of every alias and link).
--                  Rows are never deleted. A participant a later run no longer finds is marked
--                  `active = false`, so a composition change stays visible.
--   consortium_snapshot  who was in a project when we looked (one row per change of
--                  composition, see dgate/networks.py).
--
-- Organisations: the PIC (participant identification code) is `organisation.eu_pic`, which has
-- existed since 0001 with a unique index; what is added is how an organisation reached its PIC,
-- and a readable name (`canonical_name` is the normalised key, lower case and without the legal form).

ALTER TABLE organisation ADD COLUMN IF NOT EXISTS display_name   TEXT;
ALTER TABLE organisation ADD COLUMN IF NOT EXISTS pic_method     TEXT;
ALTER TABLE organisation ADD COLUMN IF NOT EXISTS pic_confidence NUMERIC(3,2);
-- Stage 1 of the cascade asks "this country, this VAT number"; CORDIS states one for 42,900 organisations.
CREATE INDEX IF NOT EXISTS organisation_vat ON organisation (country, vat_number)
    WHERE vat_number IS NOT NULL;

-- Horizon 2020 and FP7 as programmes (Horizon Europe is in 0012). Legal bases as published.
INSERT INTO programme (code, name, period_start, period_end, legal_basis) VALUES
  ('H2020', 'Horizon 2020',                   '2014-01-01', '2020-12-31',
   'Regulation (EU) No 1291/2013'),
  ('FP7',   'Seventh Framework Programme',    '2007-01-01', '2013-12-31',
   'Decision No 1982/2006/EC')
ON CONFLICT (code) DO NOTHING;

-- CORDIS: the Commission's research project database, read through its public SPARQL service.
-- The bulk files under /data/ are disallowed for robots by cordis.europa.eu/robots.txt and are
-- not fetched; see docs/sources/cordis.md. Licence as for all Commission documents.
--
-- Both sources start INACTIVE and the first completed run of each switches it on
-- (dgate/networks.py). `/v1/health` lists every active source and calls one that has never run
-- "never_run, unhealthy", which would degrade the service from the day this migration is applied
-- until the owner has run the two monthly loads by hand. The kind is `grant`, as for the other
-- funding sources, because the public sources list calls every other kind "tenders".
INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok, active)
VALUES
  ('cordis', 'CORDIS: EU research projects (Horizon Europe, Horizon 2020, FP7)', NULL, 'grant',
   'https://cordis.europa.eu/datalab/sparql',
   'Commission Decision 2011/833/EU (reuse of Commission documents)',
   'Source: CORDIS, European Commission',
   TRUE, '2007-01-01', NULL, 'monthly', TRUE, FALSE),
  ('edf_factsheets', 'European Defence Fund: project factsheets of the call results', NULL, 'grant',
   'https://defence-industry-space.ec.europa.eu',
   'Commission Decision 2011/833/EU (reuse of Commission documents)',
   'Source: European Commission, DG DEFIS, EDF results factsheets',
   TRUE, '2021-01-01', NULL, 'monthly', TRUE, FALSE)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS project (
    id               BIGSERIAL PRIMARY KEY,
    source_id        INT NOT NULL REFERENCES source(id),
    programme_id     INT REFERENCES programme(id),
    native_id        TEXT NOT NULL,
    cordis_id        TEXT,                       -- the CORDIS record number (rcn); NULL for EDF
    ga_number        TEXT,
    acronym          TEXT,
    title            TEXT NOT NULL,
    call_code        TEXT,
    topic_code       TEXT,
    action_type      TEXT,                       -- EDF: RA | DA | CSA
    category         TEXT,                       -- EDF capability category (GROUND, CYBER, ...)
    call_year        SMALLINT,
    status           TEXT,
    total_cost       NUMERIC(14,2),              -- EUR
    eu_contribution  NUMERIC(14,2),              -- EUR
    start_date       DATE,
    end_date         DATE,
    duration_months  SMALLINT,
    factsheet_url    TEXT,                       -- EDF only
    first_seen       DATE NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE (source_id, native_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS project_cordis_uq ON project (cordis_id) WHERE cordis_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS project_ga ON project (ga_number) WHERE ga_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS project_programme_start ON project (programme_id, start_date);

CREATE TABLE IF NOT EXISTS participation (
    id                    BIGSERIAL PRIMARY KEY,
    project_id            BIGINT NOT NULL REFERENCES project(id),
    organisation_id       BIGINT NOT NULL REFERENCES organisation(id),
    role                  TEXT NOT NULL,         -- coordinator | participant | third_party | partner | ...
    contribution          NUMERIC(14,2),         -- EUR; CORDIS only (the factsheets give none per entity)
    resolution_method     TEXT NOT NULL,         -- pic | alias | exact_name | exact_name_ambiguous
    resolution_confidence NUMERIC(3,2) NOT NULL,
    observed_at           DATE NOT NULL DEFAULT CURRENT_DATE,
    active                BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (project_id, organisation_id)
);
CREATE INDEX IF NOT EXISTS participation_org ON participation (organisation_id);

CREATE TABLE IF NOT EXISTS consortium_snapshot (
    id                 BIGSERIAL PRIMARY KEY,
    project_id         BIGINT NOT NULL REFERENCES project(id),
    observed_at        DATE NOT NULL,
    member_org_ids     BIGINT[] NOT NULL,
    coordinator_org_id BIGINT REFERENCES organisation(id),
    member_count       INT NOT NULL,
    country_count      INT NOT NULL,
    UNIQUE (project_id, observed_at)
);

-- What the language model said about one EDF factsheet (dgate/networks.py `run_edf`): the facts
-- after the quote check, what the check dropped, and what the call cost. Held by file hash and
-- prompt version, so a second run asks nothing about a file that did not change.
CREATE TABLE IF NOT EXISTS project_factsheet (
    url             TEXT PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES project(id),
    sha256          TEXT NOT NULL,
    pages           INT NOT NULL,
    facts           JSONB NOT NULL,
    dropped         JSONB NOT NULL DEFAULT '{}'::jsonb,
    model           TEXT NOT NULL,
    prompt_version  INT NOT NULL,
    input_tokens    INT NOT NULL DEFAULT 0,
    output_tokens   INT NOT NULL DEFAULT 0,
    cost_usd        NUMERIC(10,5) NOT NULL DEFAULT 0,
    extracted_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT ON project, participation, consortium_snapshot, project_factsheet TO dgate_api;
GRANT SELECT, INSERT, UPDATE ON project, participation, consortium_snapshot, project_factsheet
    TO dgate_worker;
REVOKE DELETE ON project, participation, consortium_snapshot, project_factsheet FROM dgate_worker;
