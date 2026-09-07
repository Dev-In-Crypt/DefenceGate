-- EU Defence Access Portal - Phase 1 schema
-- Postgres 15+. Requires pg_trgm.
--
-- Design rule: opportunity_version is append-only and is never updated.
-- The archive is the asset. Everything else can be rebuilt from it.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------- sources

CREATE TABLE IF NOT EXISTS source (
    id              SERIAL PRIMARY KEY,
    code            TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    country         CHAR(2),
    kind            TEXT NOT NULL,
    base_url        TEXT,
    licence         TEXT,
    attribution     TEXT,
    -- discovery checklist answers, kept with the source so nobody re-derives them
    has_history     BOOLEAN,
    history_from    DATE,
    retention_years INT,              -- NULL = no known limit. TED = 10.
    update_freq     TEXT,
    commercial_ok   BOOLEAN,
    active          BOOLEAN DEFAULT TRUE
);

INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok)
VALUES
  ('ted', 'Tenders Electronic Daily', NULL, 'tender',
   'https://api.ted.europa.eu',
   'Commission Decision 2011/833/EU; notices freely reusable incl. commercial',
   'Source: TED (Tenders Electronic Daily), © European Union',
   TRUE, '2012-01-01', 10, 'daily', TRUE),
  ('es_placsp', 'Plataforma de Contratacion del Sector Publico', 'ES', 'tender',
   'https://contrataciondelsectorpublico.gob.es',
   'Open public sector information (LCSP transparency obligations)',
   'Source: Plataforma de Contratacion del Sector Publico, Ministerio de Hacienda',
   TRUE, '2012-01-01', NULL, 'daily', TRUE),
  -- Dataset 2. Regional buyers reach PLACSP through aggregation and appear
  -- nowhere in dataset 1, so they need their own source row and coverage floor.
  ('es_placsp_agg', 'PLACSP plataformas agregadas (regional)', 'ES', 'tender',
   'https://contrataciondelsectorpublico.gob.es',
   'Open public sector information (LCSP transparency obligations)',
   'Source: Plataforma de Contratacion del Sector Publico, Ministerio de Hacienda',
   TRUE, '2016-01-01', NULL, 'daily', TRUE)
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------- taxonomy

CREATE TABLE IF NOT EXISTS capability (
    id          SERIAL PRIMARY KEY,
    code        TEXT UNIQUE NOT NULL,
    parent_id   INT REFERENCES capability(id),
    label_en    TEXT NOT NULL,
    description TEXT
);

-- Seeded from the EDF 2025 results page headings: this is the vocabulary
-- the buyer already uses, so we do not invent our own.
INSERT INTO capability (code, label_en) VALUES
  ('medical_cbrn',    'Defence medical support, CBRN, biotech and human factors'),
  ('info_superiority','Information superiority'),
  ('sensors',         'Advanced passive and active sensors'),
  ('cyber',           'Cyber'),
  ('space',           'Space'),
  ('digital',         'Digital transformation'),
  ('energy_env',      'Energy resilience and environmental transition'),
  ('materials',       'Materials and components'),
  ('air_combat',      'Air combat'),
  ('ground_combat',   'Ground combat'),
  ('protection_mob',  'Force protection and mobility'),
  ('naval_combat',    'Naval combat'),
  ('underwater',      'Underwater warfare'),
  ('sim_training',    'Simulation and training'),
  ('disruptive',      'Disruptive technologies')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------- organisations

CREATE TABLE IF NOT EXISTS organisation (
    id              BIGSERIAL PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    country         CHAR(2) NOT NULL,
    legal_form      TEXT,
    national_reg_no TEXT,
    vat_number      TEXT,
    eu_pic          TEXT,
    ncage_code      TEXT,
    size_class      TEXT,
    org_role        TEXT,
    is_defence_buyer BOOLEAN DEFAULT FALSE,
    first_seen      DATE NOT NULL DEFAULT CURRENT_DATE,
    last_seen       DATE NOT NULL DEFAULT CURRENT_DATE,
    confidence      NUMERIC(3,2) DEFAULT 1.00,
    review_status   TEXT DEFAULT 'auto',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS organisation_reg_uq
    ON organisation (country, national_reg_no) WHERE national_reg_no IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS organisation_pic_uq
    ON organisation (eu_pic) WHERE eu_pic IS NOT NULL;
CREATE INDEX IF NOT EXISTS organisation_name_trgm
    ON organisation USING gin (canonical_name gin_trgm_ops);

-- The compounding asset. Every name variant ever resolved, kept forever.
CREATE TABLE IF NOT EXISTS organisation_alias (
    id              BIGSERIAL PRIMARY KEY,
    organisation_id BIGINT NOT NULL REFERENCES organisation(id),
    raw_name        TEXT NOT NULL,
    normalised_name TEXT NOT NULL,
    source_id       INT REFERENCES source(id),
    country_hint    CHAR(2),
    match_method    TEXT NOT NULL,
    confidence      NUMERIC(3,2) NOT NULL,
    first_seen      DATE NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE (normalised_name, country_hint, source_id)
);

CREATE INDEX IF NOT EXISTS alias_norm_trgm
    ON organisation_alias USING gin (normalised_name gin_trgm_ops);

-- --------------------------------------------------------- opportunities

CREATE TABLE IF NOT EXISTS opportunity (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           INT NOT NULL REFERENCES source(id),
    native_id           TEXT NOT NULL,
    buyer_org_id        BIGINT REFERENCES organisation(id),
    buyer_name_raw      TEXT NOT NULL,
    country             CHAR(2),
    title_original      TEXT NOT NULL,
    title_en            TEXT,
    summary_en          TEXT,
    original_language   CHAR(2),
    procedure_type      TEXT,
    legal_basis         TEXT,
    value_amount        NUMERIC(16,2),
    value_currency      CHAR(3),
    published_at        DATE,
    deadline_at         TIMESTAMPTZ,
    cpv_codes           TEXT[],
    is_defence          BOOLEAN NOT NULL DEFAULT FALSE,
    -- the three signals kept separately so the logic stays tunable
    sig_legal_basis     BOOLEAN DEFAULT FALSE,
    sig_cpv             BOOLEAN DEFAULT FALSE,
    sig_buyer           BOOLEAN DEFAULT FALSE,
    sig_clearance       BOOLEAN DEFAULT FALSE,
    subcontracting_signal BOOLEAN DEFAULT FALSE,
    security_clearance_required BOOLEAN DEFAULT FALSE,
    source_url          TEXT,
    current_version     INT NOT NULL DEFAULT 1,
    -- normalised lifecycle: open | closed | awarded | cancelled | unknown
    status              TEXT DEFAULT 'open',
    -- the source's own code, kept so a mapping mistake stays diagnosable
    status_native       TEXT,
    UNIQUE (source_id, native_id)
);

CREATE INDEX IF NOT EXISTS opp_open_deadline
    ON opportunity (country, deadline_at) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS opp_published
    ON opportunity (published_at DESC);
CREATE INDEX IF NOT EXISTS opp_cpv
    ON opportunity USING gin (cpv_codes);
CREATE INDEX IF NOT EXISTS opp_defence
    ON opportunity (is_defence, published_at DESC);

-- THE ARCHIVE. Append-only. No UPDATE, no DELETE, ever.
CREATE TABLE IF NOT EXISTS opportunity_version (
    id              BIGSERIAL PRIMARY KEY,
    opportunity_id  BIGINT NOT NULL REFERENCES opportunity(id),
    version         INT NOT NULL,
    observed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_from      TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to        TIMESTAMPTZ,
    payload         JSONB NOT NULL,
    changed_fields  TEXT[],
    raw_hash        TEXT NOT NULL,
    UNIQUE (opportunity_id, version)
);

CREATE INDEX IF NOT EXISTS oppver_timeline
    ON opportunity_version (opportunity_id, valid_from DESC);

CREATE TABLE IF NOT EXISTS opportunity_capability (
    opportunity_id BIGINT REFERENCES opportunity(id) ON DELETE CASCADE,
    capability_id  INT REFERENCES capability(id),
    confidence     NUMERIC(3,2),
    PRIMARY KEY (opportunity_id, capability_id)
);

-- ------------------------------------------------------------ operations

CREATE TABLE IF NOT EXISTS raw_ingest (
    id           BIGSERIAL PRIMARY KEY,
    source_id    INT NOT NULL REFERENCES source(id),
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    native_id    TEXT,
    content_hash TEXT NOT NULL,
    storage_key  TEXT NOT NULL,
    content_type TEXT,
    processed    BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS raw_recent ON raw_ingest (source_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS raw_hash ON raw_ingest (content_hash);

-- Silent ingestion failure is the primary technical risk. This table exists
-- so that a source going quiet is loud.
CREATE TABLE IF NOT EXISTS ingest_run (
    id              BIGSERIAL PRIMARY KEY,
    source_id       INT NOT NULL REFERENCES source(id),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running',
    records_fetched INT DEFAULT 0,
    records_new     INT DEFAULT 0,
    records_changed INT DEFAULT 0,
    expected_min    INT,
    error_message   TEXT
);

CREATE TABLE IF NOT EXISTS enrichment (
    id          BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id   BIGINT NOT NULL,
    task        TEXT NOT NULL,
    input_hash  TEXT NOT NULL,
    model       TEXT NOT NULL,
    output      JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (entity_type, entity_id, task, input_hash)
);

-- ---------------------------------------------------------- watchlists

CREATE TABLE IF NOT EXISTS watchlist (
    id          BIGSERIAL PRIMARY KEY,
    account_id  BIGINT NOT NULL,
    name        TEXT NOT NULL,
    filters     JSONB NOT NULL,
    channel     TEXT NOT NULL DEFAULT 'email',
    target      TEXT NOT NULL,
    active      BOOLEAN DEFAULT TRUE,
    last_run_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS watchlist_delivery (
    id             BIGSERIAL PRIMARY KEY,
    watchlist_id   BIGINT NOT NULL REFERENCES watchlist(id),
    opportunity_id BIGINT NOT NULL REFERENCES opportunity(id),
    delivered_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (watchlist_id, opportunity_id)
);

-- ------------------------------------------------ append-only enforcement
--
-- The archive is the asset. A single careless UPDATE or DELETE destroys
-- history that cannot be rebuilt from any source, so the rule is enforced by
-- the database rather than by everyone remembering it. Closing a version with
-- valid_to is the one permitted update.

CREATE OR REPLACE FUNCTION opportunity_version_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'opportunity_version is append-only: DELETE is never permitted (id=%)', OLD.id;
    END IF;

    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.opportunity_id IS DISTINCT FROM OLD.opportunity_id
       OR NEW.version        IS DISTINCT FROM OLD.version
       OR NEW.observed_at    IS DISTINCT FROM OLD.observed_at
       OR NEW.valid_from     IS DISTINCT FROM OLD.valid_from
       OR NEW.payload::text  IS DISTINCT FROM OLD.payload::text
       OR NEW.changed_fields IS DISTINCT FROM OLD.changed_fields
       OR NEW.raw_hash       IS DISTINCT FROM OLD.raw_hash THEN
        RAISE EXCEPTION
            'opportunity_version is append-only: only valid_to may be updated (id=%)', OLD.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS opportunity_version_append_only ON opportunity_version;
CREATE TRIGGER opportunity_version_append_only
    BEFORE UPDATE OR DELETE ON opportunity_version
    FOR EACH ROW EXECUTE FUNCTION opportunity_version_guard();

-- ------------------------------------------------------- search and flags

ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS is_dual_use BOOLEAN DEFAULT FALSE;

ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS search_tsv tsvector
    GENERATED ALWAYS AS (
        to_tsvector('simple',
            coalesce(title_original, '') || ' ' ||
            coalesce(title_en, '')       || ' ' ||
            coalesce(summary_en, ''))
    ) STORED;

CREATE INDEX IF NOT EXISTS opp_search ON opportunity USING gin (search_tsv);
