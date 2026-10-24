-- WP-109 (round 4 of 24 October 2026, p05 and p09). Additive and idempotent.
--
-- 1. `research_may_apply_doc`: whether a university or a research organisation may apply, from the call's own eligibility facts
--    (dgate/who_apply.py `research_of`, run by the worker with `who_apply`); NULL where those facts say nothing. The list filter
--    "Universities and research organisations" (`who=research`, funding.RESEARCH_MAY_APPLY) reads it before the programme's rule.
ALTER TABLE call ADD COLUMN IF NOT EXISTS research_may_apply_doc boolean;

-- 2. `out_of_scope`: a call the scope rule no longer takes (sources/eu_portal.py `civil_subject`: healthy ageing, soil sealing, the
--    RAISE doctoral networks, wildlife trafficking, the EuroHPC quantum pilots were counted as dual-use by their programme division).
--    The connector no longer collects such a topic; the rows already held stay (a call row is never deleted) and are left out of the
--    lists and counts. Set by `python -m dgate.ops.wp109_scope --yes`.
ALTER TABLE call ADD COLUMN IF NOT EXISTS out_of_scope boolean NOT NULL DEFAULT false;

-- 3. The AID programme's name said the agency twice beside its funder line, without the accent (p05).
UPDATE programme SET name = 'AID calls for projects and RAPID'
 WHERE code = 'FR-AID' AND name = 'Agence de l''innovation de defense (AID) calls for projects and RAPID';
