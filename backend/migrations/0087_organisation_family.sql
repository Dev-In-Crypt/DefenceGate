-- WP-41 (18 October 2026): name families of organisations for the directory (N5).
-- Additive and idempotent. No organisation row, alias or participation is changed, and emptying
-- `organisation_family_member` undoes all of it.
--
-- One institution is held under several rows (Fraunhofer: 2,727 projects on one row and 8, 1 and 1 on three
-- more; AP-HP: six rows). Where a deterministic key joins them they are merged (ops/org_dedupe.py, the
-- existing reversible merge). Where only a trigram similarity of the names connects them, or one name sits
-- under several PICs, they are NOT merged (the owner's decision: bodies with different registration numbers
-- are never merged); they are shown as one card in the directory instead: "includes N name variants".
--
--   organisation_family_member  org_id is a member, head_org_id the row that carries the family's name and
--                               id in the directory; the head has no row of its own. `method` is the rule
--                               (dgate/org_family.py: name_variant, same_name), `confidence` its stored
--                               confidence. Written by `python -m dgate.ops.org_families`.
--   organisation_network.family_variants  on a head: how many member rows with a participation it stands
--                               for. The directory row of a head counts the projects of all its members.

CREATE TABLE IF NOT EXISTS organisation_family_member (
    org_id       BIGINT PRIMARY KEY REFERENCES organisation(id),
    head_org_id  BIGINT NOT NULL REFERENCES organisation(id),
    method       TEXT NOT NULL,
    confidence   NUMERIC(3,2) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (org_id <> head_org_id)
);
CREATE INDEX IF NOT EXISTS organisation_family_member_head ON organisation_family_member (head_org_id);

ALTER TABLE organisation_network ADD COLUMN IF NOT EXISTS family_variants INT NOT NULL DEFAULT 0;

-- An organisation removed on request (migration 0047) leaves every family at once, member or head: its
-- name must not be shown through a family.
CREATE OR REPLACE FUNCTION dgate_org_family_drop_suppressed() RETURNS trigger AS $$
BEGIN
    DELETE FROM organisation_family_member WHERE org_id = NEW.id OR head_org_id = NEW.id;
    RETURN NULL;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS organisation_org_family_drop ON organisation;
CREATE TRIGGER organisation_org_family_drop AFTER UPDATE OF suppressed ON organisation
    FOR EACH ROW WHEN (NEW.suppressed) EXECUTE FUNCTION dgate_org_family_drop_suppressed();

GRANT SELECT ON organisation_family_member TO dgate_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON organisation_family_member TO dgate_worker;
