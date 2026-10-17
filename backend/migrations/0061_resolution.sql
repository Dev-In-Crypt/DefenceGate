-- Entity resolution, the part that waits for a person (WP-26, plan M2-10 and M2-13).
--
--   resolution_review  a pair of organisations the cascade thinks may be related and did not
--                      decide: trigram candidates (stage 3), an ambiguous exact name, a name
--                      that carries two different PICs. Nothing in it is merged. A person
--                      (or a later stage) closes it; `status` says how. Read it with
--                      `python -m dgate.ops.networks_report`.
--   resolution_gold    hand-labelled pairs of names, positives and hard negatives
--                      (parent and subsidiary, same name in two countries, a numbered
--                      sibling), the yardstick of `dgate resolution-eval`. Loaded from
--                      seeds/resolution_gold.json; the table holds what was last loaded.
--
-- Both are derived or curated working data: nothing here is served by the API as a fact.

CREATE TABLE IF NOT EXISTS resolution_review (
    id                BIGSERIAL PRIMARY KEY,
    org_a             BIGINT NOT NULL REFERENCES organisation(id),
    org_b             BIGINT NOT NULL REFERENCES organisation(id),
    proposed_relation TEXT NOT NULL,       -- same | parent_child | ambiguous_name | same_name_other_pic
    method            TEXT NOT NULL,       -- trigram | exact_name_ambiguous | pic_conflict
    confidence        NUMERIC(3,2),
    evidence          JSONB NOT NULL DEFAULT '{}'::jsonb,
    status            TEXT NOT NULL DEFAULT 'open',   -- open | merged | related | rejected
    decided_by        TEXT,
    decided_at        TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (org_a < org_b),
    UNIQUE (org_a, org_b, method)
);
CREATE INDEX IF NOT EXISTS resolution_review_open ON resolution_review (status) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS resolution_gold (
    id         SERIAL PRIMARY KEY,
    name_a     TEXT NOT NULL,
    country_a  CHAR(2) NOT NULL,
    name_b     TEXT NOT NULL,
    country_b  CHAR(2) NOT NULL,
    ids_a      JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {"pic": "999..."}; what the source stated
    ids_b      JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_match   BOOLEAN NOT NULL,
    kind       TEXT NOT NULL,                        -- spelling | legal_form | script | parent_child | sibling | other_country | other_entity
    note       TEXT,
    UNIQUE (name_a, country_a, name_b, country_b)
);

GRANT SELECT ON resolution_review, resolution_gold TO dgate_api;
GRANT SELECT, INSERT, UPDATE ON resolution_review, resolution_gold TO dgate_worker;
REVOKE DELETE ON resolution_review FROM dgate_worker;
