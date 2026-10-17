-- The eligibility decision model (WP-29): the programmes and routes a company can ask about,
-- and the rules each one applies. A rule is a small JSON expression (see
-- dgate/readiness/engine.py for the language) that is true when the rule is met, with the
-- words to show for each outcome and the verbatim source. No model decides anything here.
--
-- The architecture document keys `programme_requirement` on (programme_id, requirement_id),
-- which cannot hold SAFE Article 16(10) as the two rules it is, nor the several rules of one
-- article. A rule has its own code, may point to the requirement that would fix it, and the
-- programmes are those of the readiness model, which are not all funding programmes with
-- calls (SAFE is a loan instrument, NATO supply is a route): so they are a table of their
-- own, and `call_programme_code` says which `programme.code` of the calls they map to.
CREATE TABLE IF NOT EXISTS readiness_programme (
    code                TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    summary             TEXT NOT NULL,
    kind                TEXT NOT NULL CHECK (kind IN ('programme', 'route', 'general')),
    legal_basis         TEXT,
    source_url          TEXT NOT NULL,
    call_programme_code TEXT,
    last_reviewed       DATE NOT NULL,
    position            INT NOT NULL DEFAULT 0,
    active              BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS programme_requirement (
    id                  SERIAL PRIMARY KEY,
    programme_code      TEXT NOT NULL REFERENCES readiness_programme(code),
    rule_code           TEXT NOT NULL,
    requirement_id      INT REFERENCES requirement(id),
    title               TEXT NOT NULL,
    obligation          TEXT NOT NULL CHECK (obligation IN ('mandatory', 'conditional', 'recommended')),
    rule_kind           TEXT NOT NULL CHECK (rule_kind IN
                          ('threshold', 'categorical', 'establishment', 'control', 'declaration',
                           'registration', 'contract', 'export', 'security', 'information')),
    applies_when        JSONB,
    condition_expr      JSONB,
    conditional_when    JSONB,
    texts               JSONB NOT NULL,
    note                TEXT,
    denominator         TEXT,
    source_url          TEXT NOT NULL,
    source_ref          TEXT NOT NULL,
    source_text         TEXT NOT NULL,
    text_origin         TEXT NOT NULL CHECK (text_origin IN ('primary', 'notes')),
    verification_status TEXT NOT NULL CHECK (verification_status IN ('V', 'S', 'U')),
    last_reviewed       DATE NOT NULL,
    position            INT NOT NULL DEFAULT 0,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (programme_code, rule_code)
);

CREATE INDEX IF NOT EXISTS programme_requirement_requirement ON programme_requirement (requirement_id);
