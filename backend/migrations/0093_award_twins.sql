-- One award, counted once, when TED and PLACSP both publish it (WP-61, 21 October 2026). Additive and
-- idempotent: a function and a view, nothing stored, nothing dropped.
--
-- A Spanish procedure above the EU thresholds is published in PLACSP and again in TED. Its winners are then
-- two `award` rows: one on the TED result notice, one on the PLACSP folder. Measured on production on
-- 21 October 2026: 373 of the TED result notices whose winners we hold share their eForms procedure
-- identifier (BT-04) with 307 PLACSP folders, 1,083 TED award rows in all. With the PLACSP winners on the
-- map, each of those wins would count twice for the supplier, its CPV division, its year and its buyer.
--
-- `award_twin` lists, for each current award row that is the second copy of a logical award, the row
-- preferred over it. Two rows are one award when
--   the procedure is the same   `procedure_id`: both notices carry the same procedure identifier (PLACSP's
--                               <cbc:UUID schemeName="TED">, TED's procedure-identifier); `ted_ref`: the
--                               PLACSP row's twin link (opportunity.ted_ref, migrations 0022 and 0035) names
--                               the TED notice itself, or a TED notice of the same procedure
--   and so is the winner        `organisation`: the resolution cascade put both on one organisation (after
--                               merges); `identifier`: both state the same tax or registration number
-- and at least one of them is PLACSP's (two TED notices of a procedure are two TED notices, as before).
-- The preferred row is the one that states a usable number, then the TED one, then the newer row: so a
-- PLACSP row with the winner's NIF stands for the award when the TED row has none, and otherwise the TED
-- row the map already showed stays. Both notices remain stored and linked (provenance: the profile lists
-- the other publication under the one it shows).
--
-- Why a view, not a `duplicate_of` column: the twin link (`ops/link_twins`, daily, after the ingests) and the
-- resolution (merges from the review queue) change after an award is loaded, and a stored mark would go stale
-- until something rewrote it. The view is always the current answer and needs no backfill on production.
-- Not matched on lot or value: `award` keeps neither (WP-37; the PLACSP value per lot stays in the landed
-- payload), and the notices' own values disagree on true pairs (PLACSP states the budget, TED the award:
-- median ratio 0.68, 75 of 372 pairs more than tenfold apart), so a value tolerance would split them.
--
-- The supplier map applies it only while DGATE_PLACSP_AWARDS_PUBLIC is true (`suppliers.scope()`); with the
-- PLACSP winners off the map nothing reads it.

-- A tax or registration number in a comparable form: letters and digits only, upper case, and the "ES" of a
-- Spanish VAT number taken off (ESA28599033 is the CIF A28599033). None for anything shorter than 6.
-- ponytail: only the Spanish VAT prefix is folded; PLACSP's foreign winners state a number without one.
CREATE OR REPLACE FUNCTION dgate_ident_key(t text) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $f$
    SELECT CASE WHEN length(k) < 6 THEN NULL
                WHEN k ~ '^ES[A-Z0-9][0-9]{7}[A-Z0-9]$' THEN substr(k, 3)
                ELSE k END
      FROM (SELECT regexp_replace(upper(coalesce(t, '')), '[^A-Z0-9]', '', 'g') AS k) s
$f$;

CREATE OR REPLACE VIEW award_twin AS
WITH src AS (
    SELECT id, code = 'ted' AS is_ted FROM source WHERE code IN ('ted', 'es_placsp', 'es_placsp_agg')
), cur AS (
    SELECT a.id, a.opportunity_id, dgate_ident_key(a.identifier_as_stated) AS ikey,
           COALESCE(org.merged_into, org.id) AS org_id, src.is_ted,
           o.native_id, o.procedure_identifier, o.ted_ref
      FROM award a
      JOIN opportunity o ON o.id = a.opportunity_id
      JOIN src ON src.id = o.source_id
      JOIN organisation org ON org.id = a.organisation_id
     WHERE a.superseded_at IS NULL AND a.excluded_reason IS NULL
), proc AS (
    -- same procedure identifier on two notices, not both TED's (both directions come out of the join)
    SELECT x.id AS a_id, y.id AS b_id, 'procedure_id' AS how
      FROM cur x JOIN cur y ON y.procedure_identifier = x.procedure_identifier AND y.opportunity_id <> x.opportunity_id
     WHERE x.procedure_identifier IS NOT NULL AND NOT (x.is_ted AND y.is_ted)
    UNION ALL
    -- the PLACSP row's twin link names the TED notice, or a TED notice of the same procedure
    SELECT p.id, t.id, 'ted_ref'
      FROM cur p
      JOIN opportunity r ON r.native_id = p.ted_ref AND r.source_id = (SELECT id FROM src WHERE is_ted)
      JOIN cur t ON t.is_ted AND (t.opportunity_id = r.id OR t.procedure_identifier = r.procedure_identifier)
     WHERE NOT p.is_ted AND p.ted_ref IS NOT NULL
), pair AS (
    SELECT a_id, b_id, how FROM proc
    UNION ALL
    SELECT b_id, a_id, how FROM proc WHERE how = 'ted_ref'
)
SELECT DISTINCT ON (d.id, k.id)
       d.id AS award_id, k.id AS preferred_id, pair.how AS procedure_method,
       CASE WHEN d.org_id = k.org_id THEN 'organisation' ELSE 'identifier' END AS winner_method
  FROM pair
  JOIN cur d ON d.id = pair.a_id
  JOIN cur k ON k.id = pair.b_id
 WHERE (d.org_id = k.org_id OR d.ikey = k.ikey)
   AND (k.ikey IS NOT NULL, k.is_ted, k.id) > (d.ikey IS NOT NULL, d.is_ted, d.id)
 ORDER BY d.id, k.id, pair.how;           -- 'procedure_id' before 'ted_ref'

GRANT SELECT ON award_twin TO dgate_api;
GRANT SELECT ON award_twin TO dgate_worker;
