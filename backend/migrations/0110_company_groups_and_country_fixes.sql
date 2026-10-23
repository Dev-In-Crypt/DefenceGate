-- Company groups of the supplier map and corrected supplier countries (WP-96, persona round of 23 October 2026,
-- findings A2.1 and A2.4). Additive and idempotent: new tables only, nothing dropped or rewritten here.
--
--   company_group_member        a contract winner listed under a curated company group (Rheinmetall, Leonardo,
--                               Saab, PGZ: dgate/ops/company_groups.py, each entry with its source). Display layer
--                               only, like buyer_family_member: no organisation is merged, and emptying the table
--                               undoes everything. `method` is 'curated_group', `evidence` the source and the name
--                               pattern that matched. Written by `python -m dgate.ops.company_groups --yes`.
--   organisation_country_fix    every country `python -m dgate.ops.supplier_countries --yes` corrected on a contract
--                               winner (and on its award rows): the old and the new country, the basis (identifier,
--                               name, legal_form_notice, legal_form, uk_is_gb) and when; `undone_at` when
--                               `--undo FROM TO` put it back. Nothing is deleted.

CREATE TABLE IF NOT EXISTS company_group_member (
    org_id      BIGINT PRIMARY KEY REFERENCES organisation(id),
    group_key   TEXT NOT NULL,
    method      TEXT NOT NULL,
    confidence  NUMERIC(3,2) NOT NULL,
    evidence    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS company_group_member_key ON company_group_member (group_key);

CREATE TABLE IF NOT EXISTS organisation_country_fix (
    id           BIGSERIAL PRIMARY KEY,
    org_id       BIGINT NOT NULL REFERENCES organisation(id),
    old_country  CHAR(2) NOT NULL,
    new_country  CHAR(2) NOT NULL,
    basis        TEXT NOT NULL,
    award_rows   INT NOT NULL DEFAULT 0,
    fixed_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    undone_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS organisation_country_fix_org ON organisation_country_fix (org_id);

-- A company removed on request leaves its group at once.
CREATE OR REPLACE FUNCTION dgate_company_group_drop_suppressed() RETURNS trigger AS $$
BEGIN
    DELETE FROM company_group_member WHERE org_id = NEW.id;
    RETURN NULL;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS organisation_company_group_drop ON organisation;
CREATE TRIGGER organisation_company_group_drop AFTER UPDATE OF suppressed ON organisation
    FOR EACH ROW WHEN (NEW.suppressed) EXECUTE FUNCTION dgate_company_group_drop_suppressed();

GRANT SELECT ON company_group_member TO dgate_api, dgate_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON company_group_member TO dgate_worker;
GRANT SELECT ON organisation_country_fix TO dgate_api;
GRANT SELECT, INSERT, UPDATE ON organisation_country_fix TO dgate_worker;
GRANT USAGE ON SEQUENCE organisation_country_fix_id_seq TO dgate_worker;
