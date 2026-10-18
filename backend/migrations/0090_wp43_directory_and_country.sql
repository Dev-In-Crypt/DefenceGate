-- WP-43 (18 October 2026): findings N4 and the directory of the third verification (verify3-fixes.md, verify3-live.md).
-- Additive and idempotent. Nothing is deleted.
--
-- 1. The basis of an organisation's country (N4). 0086 stored a basis only where the record disputed its own address
--    ('vote', 'several'); NULL meant "the address, nothing contradicts it", which a reader cannot tell from "never
--    looked at" (the verifier found the column empty on every organisation). A new value names the undisputed case:
--      address  the source states one address country and nothing in the record contradicts it
--      vote     the name of the site and the VAT number of the record agree against its address (CSIC)
--      several  sites in several countries, nothing decides; country is the first, country_sites lists them
--      NULL     not looked at (an organisation that did not come from, or has not been checked against, a record
--               that states its country)
--    `python -m dgate.ops.org_countries --yes` sets the value on the organisations that hold a PIC.
ALTER TABLE organisation DROP CONSTRAINT IF EXISTS organisation_country_basis_check;
ALTER TABLE organisation ADD CONSTRAINT organisation_country_basis_check
    CHECK (country_basis IS NULL OR country_basis IN ('address', 'vote', 'several')) NOT VALID;
ALTER TABLE organisation VALIDATE CONSTRAINT organisation_country_basis_check;
COMMENT ON COLUMN organisation.country_basis IS
    'address = one address country, nothing contradicts it; vote = site name and VAT number agree against the address; several = sites in several countries, country is the first, see country_sites; NULL = not looked at.';

-- 2. The defence-relevant count of the directory. The directory lists organisations of the defence programmes by
--    default but showed and sorted by the all-programme totals (CNRS: 4,336 projects, 10 of them in the European
--    Defence Fund). `defence_projects` counts the projects of the defence programmes (EDF, EDIDP, PADR) only, with the
--    same live-organisation and family rules as `projects`; `networks.REFRESH_NETWORK_SQL` keeps it current. The
--    UPDATE gives the rows already there their value, so that the first page after a deploy is right before the
--    next rebuild.
ALTER TABLE organisation_network ADD COLUMN IF NOT EXISTS defence_projects INT NOT NULL DEFAULT 0;

WITH part AS (
  SELECT COALESCE(h.id, COALESCE(l.live_id, pa.organisation_id)) AS org, pa.project_id
    FROM participation pa
    JOIN project p ON p.id = pa.project_id
    JOIN programme pr ON pr.id = p.programme_id AND pr.code IN ('EDF', 'EDIDP', 'PADR')
    LEFT JOIN organisation_merged_live l ON l.id = pa.organisation_id
    LEFT JOIN organisation_family_member fm ON fm.org_id = COALESCE(l.live_id, pa.organisation_id)
    LEFT JOIN organisation h ON h.id = fm.head_org_id AND h.merged_into IS NULL AND NOT h.suppressed
   WHERE pa.active AND NOT COALESCE(l.suppressed, FALSE)),
agg AS (SELECT org, count(DISTINCT project_id) AS n FROM part GROUP BY org)
UPDATE organisation_network n SET defence_projects = a.n FROM agg a
 WHERE a.org = n.organisation_id AND n.defence_projects IS DISTINCT FROM a.n;

