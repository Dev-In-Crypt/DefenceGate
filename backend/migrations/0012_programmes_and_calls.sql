-- Grants: funding programmes and their calls for proposals.
--
-- This is the product's first layer, not its second. A tender tells a supplier
-- what a ministry is buying this quarter; a call for proposals is where a
-- twenty-person manufacturer gets a development contract it could not win
-- alone, and the deadline for the European Defence Fund's 2026 calls is
-- 29 September 2026. Procurement notices are the information layer around it.
--
-- `programme` and `call` are taken from Part VII of the Data Architecture
-- document as written, plus the additions section 4.4 of the plan asks for and
-- three the feed makes necessary:
--
--   * `call_identifier` -- the portal separates a call from the topics inside
--     it (`EDF-2026-RA` holds `EDF-2026-RA-SENS-MSDT`). A topic is what an
--     applicant applies to, so a topic is the row, and the call it belongs to
--     is a column rather than a lost fact.
--   * `regime` -- why this call is in the database at all: published under a
--     defence programme, or a civil programme whose subject is dual-use. Kept
--     as a recorded reason for the same purpose as the classification signals
--     on `opportunity`: so that a change of scope is visible and reversible.
--   * `content_hash` / `first_seen_at` / `last_seen_at` -- a deadline that
--     moves is the single most valuable change this table can report, and it
--     is detected by the hash of the payload, exactly as for opportunities.
--
-- `native_id` is the portal's numeric `ccm2Id`, not the topic code: the code is
-- a human label that gets corrected, the number does not move.

CREATE TABLE programme (
    id                  SERIAL PRIMARY KEY,
    code                TEXT UNIQUE NOT NULL,  -- 'EDF' | 'EDIP' | 'HORIZON' | ...
    name                TEXT NOT NULL,
    total_budget        NUMERIC(16,2),
    currency            CHAR(3),
    period_start        DATE,
    period_end          DATE,
    legal_basis         TEXT                   -- regulation reference
);

CREATE TABLE call (
    id                  BIGSERIAL PRIMARY KEY,
    programme_id        INT NOT NULL REFERENCES programme(id),
    native_id           TEXT NOT NULL,
    topic_code          TEXT,
    call_identifier     TEXT,
    title               TEXT NOT NULL,
    budget              NUMERIC(16,2),
    opens_at            DATE,
    deadline_at         TIMESTAMPTZ,
    min_consortium_size INT,
    min_member_states   INT,
    eligibility_text    TEXT,
    eligibility_parsed  JSONB,
    conditions_raw      JSONB,
    type_of_action      TEXT,                  -- 'EDF-RA' research, 'EDF-DA' development, ...
    status              TEXT,                  -- 'forthcoming' | 'open' | 'closed' | 'evaluated'
    regime              TEXT NOT NULL,         -- 'defence' | 'dual_use'
    source_id           INT REFERENCES source(id),
    source_url          TEXT,
    content_hash        TEXT,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (programme_id, native_id)
);

CREATE INDEX call_deadline ON call (deadline_at);
CREATE INDEX call_status_regime ON call (status, regime);
CREATE INDEX call_topic_code ON call (topic_code);

-- The programmes the agreed scope covers. Budgets are left null rather than
-- guessed: the figure a programme is announced with, the figure in the
-- regulation and the figure after a transfer are three different numbers, and
-- none of them is needed to tell a supplier what to apply to.
INSERT INTO programme (code, name, period_start, period_end, legal_basis) VALUES
  ('EDF',     'European Defence Fund',                        '2021-01-01', '2027-12-31',
   'Regulation (EU) 2021/697'),
  ('EDIDP',   'European Defence Industrial Development Programme', '2019-01-01', '2020-12-31',
   'Regulation (EU) 2018/1092'),
  ('EDIP',    'European Defence Industry Programme',           '2025-01-01', '2027-12-31',
   'Regulation (EU) 2025/2643'),
  ('HORIZON', 'Horizon Europe',                               '2021-01-01', '2027-12-31',
   'Regulation (EU) 2021/695'),
  ('DIGITAL', 'Digital Europe Programme',                      '2021-01-01', '2027-12-31',
   'Regulation (EU) 2021/694')
ON CONFLICT (code) DO NOTHING;

-- The EU Funding and Tenders Portal publishes every call and topic as one
-- reference-data document, anonymously and without a key. Answers to the twelve
-- discovery questions live in docs/sources/eu_portal.md.
INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok)
VALUES
  ('eu_portal', 'EU Funding and Tenders Portal (SEDIA)', NULL, 'grant',
   'https://ec.europa.eu/info/funding-tenders/opportunities',
   'Commission Decision 2011/833/EU (reuse of Commission documents)',
   'Source: European Commission, Funding and Tenders Portal',
   TRUE, '2014-01-01', NULL, 'daily', TRUE)
ON CONFLICT (code) DO NOTHING;
