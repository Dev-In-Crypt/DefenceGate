-- Buyer families (WP-22, 16 October 2026): one body that appears under several organisation
-- rows is shown as one buyer. A DISPLAY layer: no organisation row, no alias and no
-- `opportunity.buyer_org_id` is changed, and emptying this table undoes all of it.
--
-- `org_id` is a member, `head_org_id` the organisation that carries the family's name and
-- id on the buyer list. The head has no row of its own. `method` is the rule that put the
-- member there (dgate/buyer_family.py); `confidence` is 0.95 for an identical name and 0.90
-- for a named rule. Written by `python -m dgate.ops.buyer_families` (daily in the worker).
-- Additive and idempotent.
CREATE TABLE IF NOT EXISTS buyer_family_member (
    org_id       BIGINT PRIMARY KEY REFERENCES organisation(id),
    head_org_id  BIGINT NOT NULL REFERENCES organisation(id),
    method       TEXT NOT NULL,
    confidence   NUMERIC(3,2) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (org_id <> head_org_id)
);
CREATE INDEX IF NOT EXISTS buyer_family_member_head ON buyer_family_member (head_org_id);

-- The family a buyer belongs to, as the head's id (the buyer's own id when it has none).
CREATE OR REPLACE FUNCTION dgate_buyer_head(org BIGINT) RETURNS BIGINT AS $$
    SELECT COALESCE((SELECT head_org_id FROM buyer_family_member WHERE org_id = org), org)
$$ LANGUAGE sql STABLE;

-- Every organisation of the family a buyer belongs to (the head and its members), for any
-- member id. Use it as `o.buyer_org_id = ANY(ARRAY(SELECT unnest(dgate_family_ids(x))))`: a bare
-- function call on the right of ANY is not used as an index condition, the array sub-select is.
CREATE OR REPLACE FUNCTION dgate_family_ids(org BIGINT) RETURNS BIGINT[] AS $$
    SELECT ARRAY(SELECT dgate_buyer_head(org)
                 UNION
                 SELECT org_id FROM buyer_family_member WHERE head_org_id = dgate_buyer_head(org))
$$ LANGUAGE sql STABLE;

-- An organisation suppressed on request (migration 0047) leaves every family at once,
-- whether it is a member or the head: its name must not be shown through a family.
CREATE OR REPLACE FUNCTION dgate_family_drop_suppressed() RETURNS trigger AS $$
BEGIN
    DELETE FROM buyer_family_member WHERE org_id = NEW.id OR head_org_id = NEW.id;
    RETURN NULL;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS organisation_family_drop ON organisation;
CREATE TRIGGER organisation_family_drop AFTER UPDATE OF suppressed ON organisation
    FOR EACH ROW WHEN (NEW.suppressed) EXECUTE FUNCTION dgate_family_drop_suppressed();

GRANT SELECT ON buyer_family_member TO dgate_api, dgate_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON buyer_family_member TO dgate_worker;
